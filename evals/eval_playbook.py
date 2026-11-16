"""C5 eval: issue detection against the gold-derived rule status.

Gold status = the playbook stance applied to the *gold* NLI label, so every (contract, rule) pair has
a gold status without extra labelling. Predicted status = the same deterministic C5 applied to the C4
predictions stored in an NLI result file. C5 itself is deterministic (unit-tested), so this eval
measures how C4 errors propagate into the business decision.
Metrics, per playbook (perspective):
- issue P/R/F1 where issue = VIOLATION or MISSING (business targets: recall ≥ 0.85, precision ≥ 0.70)
- high-severity issue recall (the issues that must never be missed)
- status accuracy (5 statuses)
- risk score: Spearman ρ and mean absolute error between predicted and gold per-contract scores
"""

from __future__ import annotations

import glob
import json
import statistics as st
from pathlib import Path

from evals.common import parse_args, prf, print_table, save_result
from nda_review.config import RESULTS_DIR
from nda_review.data import list_playbooks, load_playbook, load_split
from nda_review.playbook import ISSUE_STATUSES, assess
from nda_review.schemas import NLIDecision, NLIResult

DEFAULT_TAGS = [
    "majority",
    "zeroshot",
    "finetuned",
    "llm-gpt-oss-120b-nli-medium-full",
    "llm-gpt-oss-120b-nli_v3-medium-full",
    "llm-gpt-oss-120b-nli_v4-medium-full",
    "llm-gpt-oss-120b-nli_v3-high-full",
    "llm-gpt-oss-120b-nli_v3-medium-retrieved",
    "llm-gpt-oss-20b-nli_v3-medium-full",
    "llm-qwen3.8-27b-nli_v3-none-full",
]


def load_nli(split: str, tag: str) -> dict[str, NLIResult] | None:
    files = sorted(glob.glob(str(RESULTS_DIR / "nli" / f"*_{split}_{tag}.json")))
    if not files:
        return None
    recs = json.loads(Path(files[-1]).read_text())["records"]
    out: dict[str, NLIResult] = {}
    for r in recs:
        res = out.setdefault(r["doc_id"], NLIResult(doc_id=r["doc_id"], method=tag, decisions=[]))
        res.decisions.append(
            NLIDecision(hypothesis_id=r["hypothesis"], label=r["pred"], evidence=r["pred_evidence"])
        )
    return out


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    ma, mb = st.mean(ra), st.mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return cov / (va * vb) if va and vb else 0.0


def evaluate(docs, pred: dict[str, NLIResult], pb_name: str) -> tuple[dict, list[dict]]:
    pb = load_playbook(pb_name)
    records, gold_risk, pred_risk = [], [], []
    for doc in docs:
        gold_nli = NLIResult(
            doc_id=doc.doc_id,
            method="gold",
            decisions=[
                NLIDecision(hypothesis_id=h, label=lab, evidence=doc.evidence[h])
                for h, lab in doc.labels.items()
            ],
        )
        g, p = assess(gold_nli, pb), assess(pred[doc.doc_id], pb)
        gold_risk.append(g.risk_score)
        pred_risk.append(p.risk_score)
        pf = {f.rule_id: f for f in p.findings}
        for gf in g.findings:
            records.append(
                {
                    "doc_id": doc.doc_id,
                    "playbook": pb_name,
                    "rule": gf.rule_id,
                    "severity": gf.severity,
                    "gold": gf.status,
                    "pred": pf[gf.rule_id].status,
                }
            )
    is_issue = lambda s: s in ISSUE_STATUSES  # noqa: E731
    tp = sum(is_issue(r["gold"]) and is_issue(r["pred"]) for r in records)
    p_, r_, f_ = prf(
        tp, sum(is_issue(r["pred"]) for r in records), sum(is_issue(r["gold"]) for r in records)
    )
    high = [r for r in records if r["severity"] == "high" and is_issue(r["gold"])]
    viol_tp = sum(r["gold"] == r["pred"] == "VIOLATION" for r in records)
    vp, vr, vf = prf(
        viol_tp,
        sum(r["pred"] == "VIOLATION" for r in records),
        sum(r["gold"] == "VIOLATION" for r in records),
    )
    metrics = {
        "issue_p": p_,
        "issue_r": r_,
        "issue_f1": f_,
        "n_gold_issues": sum(is_issue(r["gold"]) for r in records),
        "high_sev_issue_recall": sum(is_issue(r["pred"]) for r in high) / len(high) if high else 0,
        "violation_p": vp,
        "violation_r": vr,
        "violation_f1": vf,
        "status_accuracy": st.mean(r["gold"] == r["pred"] for r in records),
        "risk_spearman": spearman(pred_risk, gold_risk),
        "risk_mae": st.mean(abs(a - b) for a, b in zip(pred_risk, gold_risk, strict=True)),
        "n_rule_checks": len(records),
    }
    return metrics, records


def main() -> None:
    args = parse_args(__doc__, [("--tags", {"nargs": "*", "default": DEFAULT_TAGS})])
    docs = load_split(args.split, args.limit)
    metrics, records, rows = {}, [], []
    for tag in args.tags:
        pred = load_nli(args.split, tag)
        if pred is None:
            print(f"(no NLI result for {tag}, skipped)")
            continue
        for pb in list_playbooks():
            m, recs = evaluate(docs, pred, pb)
            metrics[f"{tag}/{pb}"] = m
            records += [r | {"nli": tag} for r in recs]
            rows.append({"nli": tag, "playbook": pb, **m})
    print_table(
        rows,
        [
            "nli",
            "playbook",
            "issue_p",
            "issue_r",
            "issue_f1",
            "high_sev_issue_recall",
            "violation_f1",
            "status_accuracy",
            "risk_spearman",
            "risk_mae",
            "n_gold_issues",
        ],
    )
    path = save_result(
        "playbook",
        args.split,
        config={"nli_tags": args.tags},
        metrics=metrics,
        records=records,
        n=len(docs),
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

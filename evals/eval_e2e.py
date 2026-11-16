"""End-to-end eval: the whole pipeline on the original files, exactly as a user runs it.

The component evals give each component gold input from upstream, so an error is charged to the component
that made it. This eval removes every gold input: each original PDF/HTML/TXT file goes through
`pipeline.review_file` (C1 → C2 → C3 → C4 → C5 → C6 → C7) and only the outputs are compared with gold.
The gap to the oracle numbers (same contracts, gold spans) is the cost of upstream errors, mostly C1/C2.

Metrics (n = contracts):
- C4 labels: macro-F1 and Contradiction-F1 vs the gold document labels (labels don't depend on segmentation).
- C4 evidence, overlap match: e2e spans differ from gold spans, so a predicted evidence span matches a gold
  evidence span when they share ≥ 50 % of the shorter span's words. Pairs with gold label E or C, as in
  eval_nli. The oracle C4 run is scored with the same rule, so both numbers are comparable.
- C5 issue P/R vs the gold-derived status (the business metric), both playbooks, oracle next to it.
- C6 (--playbook): drafted rate, term mismatch, fix rate (judge NLI on the revised text, as in eval_redline)
  and **gold issues resolved**: gold issues that were raised AND fixed / all gold issues, i.e. the share of
  real problems for which the user gets a working fix.
- C7: coverage of raised issues, coverage of gold issues, absence-claim accuracy vs gold, invented clause
  references, recommendation consistency.
- Operations: LLM calls, cost and latency per contract (from the traces), failed contracts.
"""

from __future__ import annotations

import logging
import statistics as st
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from evals.common import SYSTEM_NLI_TAG, norm_words, parse_args, print_table, save_result
from evals.eval_memo import invented_refs
from evals.eval_playbook import evaluate as evaluate_c5
from evals.eval_playbook import load_nli
from evals.eval_redline import term_mismatches
from evals.judge import judge_nli
from evals.metrics import classification_metrics
from nda_review import pipeline
from nda_review.config import JUDGE_MODEL, SYSTEM_MODEL
from nda_review.data import list_playbooks, load_hypotheses, load_playbook, load_split
from nda_review.memo import PROMPT as MEMO_PROMPT
from nda_review.nli import DEFAULT_PROMPT as NLI_PROMPT
from nda_review.playbook import ISSUE_STATUSES, assess
from nda_review.redline import PROMPT as REDLINE_PROMPT
from nda_review.schemas import NLIDecision, NLIResult
from nda_review.segment import segment

log = logging.getLogger(__name__)
MATCH = 0.5  # word-overlap threshold for the evidence match


def overlap(a: list[str], b: list[str]) -> float:
    """Shared words (multiset) / words of the shorter span."""
    if not a or not b:
        return 0.0
    return sum((Counter(a) & Counter(b)).values()) / min(len(a), len(b))


def evidence_counts(gold: list[str], pred: list[str]) -> dict:
    """Overlap-matched evidence counts for one (contract, hypothesis) pair."""
    g, p = [norm_words(t) for t in gold], [norm_words(t) for t in pred]
    return {
        "n_gold": len(g),
        "n_pred": len(p),
        "gold_found": sum(any(overlap(x, y) >= MATCH for y in p) for x in g),
        "pred_correct": sum(any(overlap(y, x) >= MATCH for x in g) for y in p),
    }


def evidence_summary(counts: list[dict]) -> dict:
    s = lambda k: sum(c[k] for c in counts)  # noqa: E731
    p = s("pred_correct") / s("n_pred") if s("n_pred") else 0.0
    r = s("gold_found") / s("n_gold") if s("n_gold") else 0.0
    return {"p": p, "r": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "n_pairs": len(counts)}


def gold_nli(doc) -> NLIResult:
    return NLIResult(
        doc_id=doc.doc_id,
        method="gold",
        decisions=[
            NLIDecision(hypothesis_id=h, label=lab, evidence=doc.evidence[h])
            for h, lab in doc.labels.items()
        ],
    )


def main() -> None:
    args = parse_args(
        __doc__,
        [
            ("--playbook", {"default": "disclosing_party"}),
            ("--workers", {"type": int, "default": 3}),
            ("--no-judge", {"action": "store_true", "help": "skip the C6 fix-rate judge"}),
        ],
    )
    docs = load_split(args.split, args.limit)
    hyps = load_hypotheses()
    pb = load_playbook(args.playbook)

    def one(doc) -> dict:
        t0 = time.time()
        res = pipeline.review_file(doc.raw_path, args.playbook)
        wall = time.time() - t0
        span_text = {s.id: s.text for s in res.contract.spans}
        gold_span_text = {s.id: s.text for s in doc.contract.spans}
        pred = res.nli.by_hypothesis()
        ev = [
            evidence_counts(
                [gold_span_text[i] for i in doc.evidence[h]],
                [span_text[i] for i in pred[h].evidence],
            )
            for h, lab in doc.labels.items()
            if lab != "NotMentioned"
        ]
        gold_report = assess(gold_nli(doc), pb)
        gold_issues = {f.rule_id for f in gold_report.findings if f.status in ISSUE_STATUSES}
        findings = {f.rule_id: f for f in res.report.findings}
        raised = {r for r, f in findings.items() if f.status in ISSUE_STATUSES}
        drafted = {r.rule_id: r for r in res.redlines.redlines}
        after = None
        if not args.no_judge and drafted:
            judged = assess(judge_nli(segment(res.revised_text, doc.doc_id), hyps), pb)
            after = {f.rule_id: f.status for f in judged.findings}
        fixed = {r for r in raised if after is not None and after[r] not in ISSUE_STATUSES}
        memo_items = {i.rule_id: i for i in res.memo.issues if i.rule_id in findings}
        absence = [
            i
            for i in memo_items.values()
            if not i.citations and findings[i.rule_id].status == "MISSING"
        ]
        calls = res.traces
        return {
            "doc_id": doc.doc_id,
            "format": res.ingest.source_format if res.ingest else None,
            "n_spans": len(res.contract.spans),
            "n_gold_spans": len(doc.contract.spans),
            "labels": {h: [doc.labels[h], pred[h].label] for h in doc.labels},
            "evidence": ev,
            "gold_issues": sorted(gold_issues),
            "raised": sorted(raised),
            "drafted": sorted(drafted),
            "term_mismatch": {
                r: m
                for r, x in drafted.items()
                if (m := term_mismatches(x.new_text, res.contract.text))
            },
            "judged": after is not None,
            "fixed": sorted(fixed),
            "resolved": sorted(gold_issues & raised & fixed),
            "memo_covered": sorted(raised & set(memo_items)),
            "absence_claims": len(absence),
            "absence_correct": sum(
                doc.labels[findings[i.rule_id].hypothesis_id] == "NotMentioned" for i in absence
            ),
            "invented_refs": sum(
                bool(invented_refs(f"{i.headline} {i.explanation} {i.ask}", res.contract.text))
                for i in res.memo.issues
            ),
            "n_memo_items": len(res.memo.issues),
            "recommendation_ok": res.memo.recommendation == res.report.recommendation,
            "nli": res.nli.model_dump(),
            "n_llm_calls": len(calls),
            "cache_hits": sum(t["cache_hit"] for t in calls),
            "cost_usd": round(sum(t["cost_usd"] for t in calls), 6),
            "llm_latency_s": round(sum(t["latency_s"] for t in calls if not t["cache_hit"]), 2),
            "timings_s": res.timings_s,
            "wall_s": round(wall, 2),
        }

    def safe(doc):
        try:
            return one(doc)
        except Exception as e:  # an e2e failure is a result, not a crash; counted and listed
            log.warning("%s failed: %s", doc.doc_id, str(e)[:200])
            return {"doc_id": doc.doc_id, "error": f"{type(e).__name__}: {str(e)[:300]}"}

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(tqdm(ex.map(safe, docs), total=len(docs)))
    records = [r for r in results if "error" not in r]
    failures = [r for r in results if "error" in r]
    ok = {r["doc_id"] for r in records}
    ok_docs = [d for d in docs if d.doc_id in ok]

    # --- C4: e2e vs oracle on the same contracts
    gold_l = [lab[0] for r in records for lab in r["labels"].values()]
    pred_l = [lab[1] for r in records for lab in r["labels"].values()]
    c4 = classification_metrics(gold_l, pred_l)
    e2e_pred = {r["doc_id"]: NLIResult.model_validate(r["nli"]) for r in records}
    oracle_pred = load_nli(args.split, SYSTEM_NLI_TAG) or {}
    have_oracle = all(d.doc_id in oracle_pred for d in ok_docs)
    metrics: dict = {
        "n_contracts": len(docs),
        "n_failed_docs": len(failures),
        "failures": failures,
        "c4_e2e": {
            "macro_f1": c4["macro_f1"],
            "contradiction_f1": c4["Contradiction"]["f1"],
            "accuracy": c4["accuracy"],
            "n_pairs": c4["n"],
            "evidence_overlap": evidence_summary([c for r in records for c in r["evidence"]]),
        },
    }
    if have_oracle:
        og, op, oev = [], [], []
        for d in ok_docs:
            byh = oracle_pred[d.doc_id].by_hypothesis()
            span_text = {s.id: s.text for s in d.contract.spans}
            for h, lab in d.labels.items():
                og.append(lab)
                op.append(byh[h].label)
                if lab != "NotMentioned":
                    oev.append(
                        evidence_counts(
                            [span_text[i] for i in d.evidence[h]],
                            [span_text[i] for i in byh[h].evidence],
                        )
                    )
        oc4 = classification_metrics(og, op)
        metrics["c4_oracle"] = {
            "macro_f1": oc4["macro_f1"],
            "contradiction_f1": oc4["Contradiction"]["f1"],
            "accuracy": oc4["accuracy"],
            "n_pairs": oc4["n"],
            "evidence_overlap": evidence_summary(oev),
        }

    # --- C5: business metric, both playbooks
    for name in list_playbooks():
        m, _ = evaluate_c5(ok_docs, e2e_pred, name)
        metrics[f"c5_e2e/{name}"] = m
        if have_oracle:
            metrics[f"c5_oracle/{name}"], _ = evaluate_c5(ok_docs, oracle_pred, name)

    # --- C6 / C7 for --playbook
    s = lambda k: sum(len(r[k]) if isinstance(r[k], list | dict) else r[k] for r in records)  # noqa: E731
    judged = [r for r in records if r["judged"]]
    metrics["c6_e2e"] = {
        "drafted_rate": s("drafted") / s("raised") if s("raised") else 1.0,
        "term_mismatch_rate": s("term_mismatch") / s("drafted") if s("drafted") else 0.0,
        "fix_rate_raised": sum(len(r["fixed"]) for r in judged)
        / sum(len(r["raised"]) for r in judged)
        if judged
        else None,
        "gold_issues_resolved": sum(len(r["resolved"]) for r in judged)
        / sum(len(r["gold_issues"]) for r in judged)
        if judged
        else None,
        "n_raised": s("raised"),
        "n_gold_issues": s("gold_issues"),
        "n_judged_contracts": len(judged),
    }
    gold_raised = sum(len(set(r["gold_issues"]) & set(r["raised"])) for r in records)
    metrics["c7_e2e"] = {
        "coverage_raised": s("memo_covered") / s("raised") if s("raised") else 1.0,
        "coverage_gold": sum(len(set(r["gold_issues"]) & set(r["memo_covered"])) for r in records)
        / s("gold_issues"),
        "gold_issues_raised": gold_raised / s("gold_issues"),
        "absence_claim_accuracy": s("absence_correct") / s("absence_claims")
        if s("absence_claims")
        else None,
        "n_absence_claims": s("absence_claims"),
        "invented_ref_rate": s("invented_refs") / s("n_memo_items") if s("n_memo_items") else 0.0,
        "recommendation_consistency": st.mean(r["recommendation_ok"] for r in records),
    }
    fresh = [r for r in records if r["cache_hits"] < r["n_llm_calls"]]
    metrics["ops"] = {
        "llm_calls_per_contract": st.mean(r["n_llm_calls"] for r in records),
        "cost_usd_per_contract": st.mean(r["cost_usd"] for r in records),
        "llm_latency_s_median": st.median(r["llm_latency_s"] for r in fresh) if fresh else None,
        "n_uncached_contracts": len(fresh),
        "c1_c2_s_median": st.median(
            r["timings_s"]["C1 ingest"] + r["timings_s"]["C2 segment"] for r in records
        ),
        "formats": dict(Counter(r["format"] for r in records)),
        "span_ratio_e2e_vs_gold": sum(r["n_spans"] for r in records)
        / sum(r["n_gold_spans"] for r in records),
    }

    rows = []
    for setting in ("e2e", "oracle"):
        c4m = metrics.get(f"c4_{setting}")
        if not c4m:
            continue
        row = {
            "setting": setting,
            "C4 macroF1": c4m["macro_f1"],
            "C4 contraF1": c4m["contradiction_f1"],
            "C4 evid F1 (overlap)": c4m["evidence_overlap"]["f1"],
        }
        for name in list_playbooks():
            c5 = metrics[f"c5_{setting}/{name}"]
            row[f"C5 R/P {name}"] = f"{c5['issue_r']:.3f} / {c5['issue_p']:.3f}"
        rows.append(row)
    print_table(rows)
    print_table([metrics["c6_e2e"] | metrics["c7_e2e"]])
    print_table(
        [{k: v for k, v in metrics["ops"].items() if k != "formats"} | {"failed": len(failures)}]
    )
    path = save_result(
        "e2e",
        args.split,
        n=len(docs),
        metrics=metrics,
        records=records,
        tag=args.playbook,
        config={
            "playbook": args.playbook,
            "system_model": SYSTEM_MODEL,
            "judge_model": JUDGE_MODEL if not args.no_judge else None,
            "prompts": {"nli": NLI_PROMPT, "redline": REDLINE_PROMPT, "memo": MEMO_PROMPT},
            "oracle_nli_tag": SYSTEM_NLI_TAG,
            "evidence_match_threshold": MATCH,
        },
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

"""Judge validation: is the Qwen judge reliable enough for the C6 and C7 metrics?

A. NLI judge (C6 fix rate and collateral)
   A1 agreement with ContractNLI gold on the original dev contracts (accuracy, macro-F1, Cohen's κ),
      plus κ with the system model's predictions;
   A2 known-good vs known-bad insertions: for each dev contract, insert the playbook's preferred clause
      for every gold MISSING issue (should become OK) vs an irrelevant clause (should stay an issue).
B. Redline-quality judge: known-good (preferred clause) vs known-bad (opposite position, wrong topic)
   on 12 disclosing-party rules → mean score per case type, pass/fail accuracy, κ.
C. Faithfulness judge: for gold Entailment pairs, a true claim with gold citations (supported) vs the same
   claim with citations of another topic (unsupported) vs a false "silent" claim (unsupported).
D. Second annotator: Claude Code's labels on real C6/C7 outputs (evals/data/claude_code_annotations.json)
   vs the judge, Cohen's κ (Claude Code is a model, reported as such — no human labels available).
"""

from __future__ import annotations

import json
import random
import statistics as st
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from tqdm import tqdm

from evals.common import SYSTEM_NLI_TAG, parse_args, print_table, save_result
from evals.eval_playbook import load_nli
from evals.judge import judge_faithfulness, judge_nli, judge_redlines
from evals.metrics import classification_metrics
from nda_review.config import JUDGE_MODEL, SEED
from nda_review.data import load_hypotheses, load_playbook, load_split
from nda_review.llm import LLMError
from nda_review.playbook import ISSUE_STATUSES, assess, position_text
from nda_review.schemas import NLIDecision, NLIResult
from nda_review.segment import segment

CASES = Path(__file__).parent / "data" / "judge_cases.yaml"
ANNOTATIONS = Path(__file__).parent / "data" / "claude_code_annotations.json"


def cohen_kappa(a: list, b: list) -> float:
    n = len(a)
    if not n:
        return 0.0
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def part_a(docs, hyps, pb, workers):
    cases = yaml.safe_load(CASES.read_text())
    rules = {r.id: r for r in pb.rules}

    def one(doc):
        judged = judge_nli(doc.contract, hyps)
        gold_nli = NLIResult(
            doc_id=doc.doc_id,
            method="gold",
            decisions=[NLIDecision(hypothesis_id=h, label=lab) for h, lab in doc.labels.items()],
        )
        missing = [
            f
            for f in assess(gold_nli, pb).findings
            if f.status == "MISSING" and rules[f.rule_id].preferred_clause
        ]
        out = {
            "doc_id": doc.doc_id,
            "judge": {d.hypothesis_id: d.label for d in judged.decisions},
            "good": [],
            "bad": [],
        }
        if missing:
            good = (
                doc.contract.text
                + "\n"
                + "\n".join(rules[f.rule_id].preferred_clause for f in missing)
            )
            bad = doc.contract.text + "\n" + cases["irrelevant_clause"]
            for kind, text in (("good", good), ("bad", bad)):
                rep = assess(judge_nli(segment(text, doc.doc_id), hyps), pb)
                st_ = {f.rule_id: f.status for f in rep.findings}
                out[kind] = [{"rule": f.rule_id, "status_after": st_[f.rule_id]} for f in missing]
        return out

    def safe(doc):
        try:
            return one(doc)
        except LLMError as e:  # counted, not fatal: the judge's failure rate is part of the result
            return {"doc_id": doc.doc_id, "error": str(e)[:200]}

    with ThreadPoolExecutor(workers) as ex:
        all_recs = list(tqdm(ex.map(safe, docs), total=len(docs), desc="A"))
    recs = [r for r in all_recs if "error" not in r]
    docs = [d for d in docs if any(r["doc_id"] == d.doc_id for r in recs)]
    gold = [d.labels[h.id] for d in docs for h in hyps]
    by_doc = {r["doc_id"]: r for r in recs}
    judge = [by_doc[d.doc_id]["judge"][h.id] for d in docs for h in hyps]
    m = classification_metrics(gold, judge)
    sys_pred = load_nli("dev", SYSTEM_NLI_TAG)
    metrics = {
        "A1_accuracy": m["accuracy"],
        "A1_macro_f1": m["macro_f1"],
        "A1_kappa_vs_gold": cohen_kappa(gold, judge),
        "A1_n_pairs": len(gold),
        "A_failed_docs": len(all_recs) - len(recs),
    }
    if sys_pred:
        sysl = [sys_pred[d.doc_id].by_hypothesis()[h.id].label for d in docs for h in hyps]
        metrics["A1_kappa_vs_system"] = cohen_kappa(sysl, judge)
        metrics["A1_system_kappa_vs_gold"] = cohen_kappa(gold, sysl)
    good = [x for r in recs for x in r["good"]]
    bad = [x for r in recs for x in r["bad"]]
    metrics |= {
        "A2_known_good_fixed": st.mean(x["status_after"] not in ISSUE_STATUSES for x in good),
        "A2_known_bad_still_issue": st.mean(x["status_after"] in ISSUE_STATUSES for x in bad),
        "A2_n": len(good),
    }
    return metrics, recs


def part_b(pb, hyps, workers):
    cases = yaml.safe_load(CASES.read_text())
    hyp_text = {h.id: h.text for h in hyps}
    rules = {r.id: r for r in pb.rules}
    ids = sorted(cases["opposite"])
    rng = random.Random(SEED)
    items = []
    for rid in ids:
        r = rules[rid]
        other = rules[rng.choice([x for x in ids if x != rid])]
        base = {
            "rule_id": rid,
            "position": position_text(r, hyp_text[r.hypothesis]),
            "action": "insert",
            "original": "(end of the contract)",
        }
        items += [
            base | {"new_text": r.preferred_clause, "expected": "good", "case": "preferred"},
            base | {"new_text": cases["opposite"][rid], "expected": "bad", "case": "opposite"},
            base | {"new_text": other.preferred_clause, "expected": "bad", "case": "wrong_topic"},
        ]

    def one(it):
        s = judge_redlines([it])
        return it | {"score": s[0].score if s else None, "problems": s[0].problems if s else None}

    with ThreadPoolExecutor(workers) as ex:
        recs = list(tqdm(ex.map(one, items), total=len(items), desc="B"))
    ok = [r for r in recs if r["score"] is not None]
    exp = [r["expected"] for r in ok]
    got = ["good" if r["score"] >= 4 else "bad" for r in ok]
    metrics = {
        f"B_mean_score_{c}": st.mean(r["score"] for r in ok if r["case"] == c)
        for c in ("preferred", "opposite", "wrong_topic")
    }
    metrics |= {
        "B_pass_fail_accuracy": st.mean(e == g for e, g in zip(exp, got, strict=True)),
        "B_kappa": cohen_kappa(exp, got),
        "B_n": len(ok),
        "B_failed_calls": len(recs) - len(ok),
    }
    return metrics, recs


def part_c(docs, hyps, workers):
    rng = random.Random(SEED)
    hyp_text = {h.id: h.text for h in hyps}
    pairs = [(d, h) for d in docs for h, lab in d.labels.items() if lab == "Entailment"]
    pairs = rng.sample(pairs, min(40, len(pairs)))
    items = []
    for d, h in pairs:

        def text(ids: list[int], d=d) -> list[str]:
            return [" ".join(d.contract.spans[i].text.split()) for i in ids]

        other_ids = sorted(
            {i for hh, ids in d.evidence.items() if hh != h for i in ids} - set(d.evidence[h])
        )
        claim = f"The contract provides that {hyp_text[h][0].lower() + hyp_text[h][1:]}"
        items.append(
            {
                "rule_id": h,
                "claim": claim,
                "cited": text(d.evidence[h]),
                "expected": True,
                "case": "true_claim",
            }
        )
        if other_ids:
            items.append(
                {
                    "rule_id": h,
                    "claim": claim,
                    "cited": text(rng.sample(other_ids, min(2, len(other_ids)))),
                    "expected": False,
                    "case": "wrong_citation",
                }
            )
        items.append(
            {
                "rule_id": h,
                "claim": f"The contract is silent on this point: {hyp_text[h]}",
                "cited": text(d.evidence[h]),
                "expected": False,
                "case": "false_silence",
            }
        )

    def one(it):
        v = judge_faithfulness([it])
        return it | {
            "supported": v[0].supported if v else None,
            "reason": v[0].reason if v else None,
        }

    with ThreadPoolExecutor(workers) as ex:
        recs = list(tqdm(ex.map(one, items), total=len(items), desc="C"))
    ok = [r for r in recs if r["supported"] is not None]
    metrics = {
        f"C_acc_{c}": st.mean(r["supported"] == r["expected"] for r in ok if r["case"] == c)
        for c in ("true_claim", "wrong_citation", "false_silence")
    }
    metrics |= {
        "C_accuracy": st.mean(r["supported"] == r["expected"] for r in ok),
        "C_kappa": cohen_kappa([r["expected"] for r in ok], [r["supported"] for r in ok]),
        "C_n": len(ok),
        "C_failed_calls": len(recs) - len(ok),
    }
    return metrics, recs


def part_d():
    if not ANNOTATIONS.exists():
        return {"D_status": "no annotations yet"}, []
    ann = json.loads(ANNOTATIONS.read_text())
    out, recs = {}, []
    for kind in ("redline", "memo"):
        rs = [a for a in ann if a["kind"] == kind and a.get("judge") is not None]
        if rs:
            out[f"D_{kind}_agreement"] = st.mean(a["claude_code"] == a["judge"] for a in rs)
            out[f"D_{kind}_kappa"] = cohen_kappa(
                [a["claude_code"] for a in rs], [a["judge"] for a in rs]
            )
            out[f"D_{kind}_n"] = len(rs)
            recs += rs
    return out, recs


def main() -> None:
    args = parse_args(
        __doc__, [("--parts", {"default": "ABCD"}), ("--workers", {"type": int, "default": 6})]
    )
    docs = load_split(args.split, args.limit)
    hyps = load_hypotheses()
    pb = load_playbook("disclosing_party")
    metrics, records = {}, {}
    for part, fn in (
        ("A", lambda: part_a(docs, hyps, pb, args.workers)),
        ("B", lambda: part_b(pb, hyps, args.workers)),
        ("C", lambda: part_c(docs, hyps, args.workers)),
        ("D", part_d),
    ):
        if part in args.parts:
            m, r = fn()
            metrics |= m
            records[part] = r
    print_table([{"metric": k, "value": v} for k, v in metrics.items()])
    path = save_result(
        "judge_validation",
        args.split,
        n=len(docs),
        metrics=metrics,
        records=records,
        config={"judge_model": JUDGE_MODEL, "parts": args.parts},
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

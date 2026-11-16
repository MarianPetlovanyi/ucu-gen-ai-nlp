"""C4 eval: document-level NLI labels and evidence spans vs ContractNLI gold.

Unit: one (contract, hypothesis) pair; dev = 61 contracts × 17 hypotheses = 1037 pairs.
Label metrics: macro-F1 over {Entailment, Contradiction, NotMentioned} (classes are imbalanced, so
accuracy alone would reward predicting the majority), Contradiction-F1 (the rare class that becomes a
VIOLATION downstream), accuracy, confusion matrix, per-hypothesis accuracy.
Evidence metrics (pairs whose gold label is E or C): span-level micro P/R/F1 and macro F1 of the
predicted span ids against gold evidence ids. Contracts use gold spans (oracle C2) to isolate C4.

Methods:
  majority    train-majority label per hypothesis (+ top-2 exemplar spans as evidence)
  zeroshot    un-tuned DeBERTa-v3 MNLI span scores (Colab), doc label by thresholds
  finetuned   DeBERTa-v3 fine-tuned on train spans (Colab), doc label by thresholds
  llm         gpt-oss via nda_review.nli.classify (--model, --prompt, --effort, --context)
Thresholds of the DeBERTa baselines are tuned on dev and frozen for test.
"""

from __future__ import annotations

import collections
import json
import logging
import statistics as st
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from evals.common import nli_tag, parse_args, print_table, save_result
from evals.metrics import LABELS, classification_metrics, confusion, evidence_prf
from nda_review import nli
from nda_review.config import PROCESSED_DIR, SYSTEM_MODEL
from nda_review.data import load_hypotheses, load_split
from nda_review.llm import LLMError
from nda_review.retrieve import retrieve
from nda_review.schemas import NLIDecision, NLIResult

log = logging.getLogger(__name__)

PROBS = PROCESSED_DIR / "finetuned" / "span_probs.json"
THRESHOLDS = PROCESSED_DIR / "finetuned" / "thresholds.json"


def score(results: dict, docs, hyps) -> tuple[dict, list[dict]]:
    gold, pred, ev_pairs, records = [], [], [], []
    for doc in docs:
        by_h = results[doc.doc_id].by_hypothesis()
        for h in hyps:
            d = by_h[h.id]
            g = doc.labels[h.id]
            gold.append(g)
            pred.append(d.label)
            if g != "NotMentioned":
                ev_pairs.append((set(doc.evidence[h.id]), set(d.evidence)))
            records.append(
                {
                    "doc_id": doc.doc_id,
                    "hypothesis": h.id,
                    "gold": g,
                    "pred": d.label,
                    "gold_evidence": doc.evidence[h.id],
                    "pred_evidence": d.evidence,
                    "rationale": d.rationale,
                }
            )
    m = classification_metrics(gold, pred)
    metrics = {
        "macro_f1": m["macro_f1"],
        "accuracy": m["accuracy"],
        "contradiction_f1": m["Contradiction"]["f1"],
        "per_class": {k: m[k] for k in LABELS},
        "confusion": confusion(gold, pred),
        "evidence": evidence_prf(ev_pairs),
        "n_pairs": len(gold),
    }
    per_h = collections.defaultdict(list)
    for r in records:
        per_h[r["hypothesis"]].append(r["gold"] == r["pred"])
    metrics["per_hypothesis_accuracy"] = {h: round(st.mean(v), 3) for h, v in per_h.items()}
    return metrics, records


def run_llm(docs, hyps, args) -> dict:
    def one(doc):
        span_ids = None
        if args.context == "retrieved":
            hits = retrieve(doc.contract, hyps, k=args.k)
            span_ids = {x.span_id for r in hits.values() for x in r.hits}
        try:
            return doc.doc_id, nli.classify(
                doc.contract,
                hyps,
                model=args.model,
                prompt=args.prompt,
                reasoning_effort=args.effort,
                span_ids=span_ids,
            )
        except LLMError as e:
            # A failed call is scored as "all NotMentioned, no evidence" (what the system would have
            # nothing to show for) and counted, so the failure rate is part of the result.
            log.warning("%s failed: %s", doc.doc_id, str(e)[:200])
            decisions = [NLIDecision(hypothesis_id=h.id, label="NotMentioned") for h in hyps]
            return doc.doc_id, NLIResult(doc_id=doc.doc_id, method="failed", decisions=decisions)

    with ThreadPoolExecutor(args.workers) as ex:
        return dict(tqdm(ex.map(one, docs), total=len(docs), desc="llm"))


def run_span_probs(docs, hyps, kind: str, split: str) -> tuple[dict, dict]:
    probs = json.loads(PROBS.read_text())[kind][split]
    pdocs = {d.doc_id: probs[d.doc_id.split("/")[1]] for d in docs}

    def predict(te, tc):
        return {
            d.doc_id: nli.span_probs_baseline(d.contract, hyps, pdocs[d.doc_id], te, tc, kind)
            for d in docs
        }

    thresholds = json.loads(THRESHOLDS.read_text()) if THRESHOLDS.exists() else {}
    if split == "dev" or kind not in thresholds:
        grid = [0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98]
        best = max(
            ((te, tc) for te in grid for tc in grid),
            key=lambda t: score(predict(*t), docs, hyps)[0]["macro_f1"],
        )
        thresholds[kind] = {"t_entail": best[0], "t_contra": best[1], "tuned_on": split}
        THRESHOLDS.write_text(json.dumps(thresholds, indent=1))
    t = thresholds[kind]
    return predict(t["t_entail"], t["t_contra"]), t


def main() -> None:
    args = parse_args(
        __doc__,
        [
            (
                "--method",
                {"default": "llm", "choices": ["majority", "zeroshot", "finetuned", "llm"]},
            ),
            ("--model", {"default": SYSTEM_MODEL}),
            ("--prompt", {"default": nli.DEFAULT_PROMPT}),
            ("--effort", {"default": "medium"}),
            ("--context", {"default": "full", "choices": ["full", "retrieved"]}),
            ("--k", {"type": int, "default": 10}),
            ("--workers", {"type": int, "default": 8}),
        ],
    )
    docs = load_split(args.split, args.limit)
    hyps = load_hypotheses()
    config = {"method": args.method, "limit": args.limit}
    if args.method == "majority":
        results = {d.doc_id: nli.majority_baseline(d.contract, hyps) for d in docs}
        tag = "majority"
    elif args.method in ("zeroshot", "finetuned"):
        results, thr = run_span_probs(docs, hyps, args.method, args.split)
        config |= {"thresholds": thr, "probs_file": str(PROBS.name)}
        config |= {"meta": json.loads(PROBS.read_text())["meta"]}
        tag = args.method
    else:
        results = run_llm(docs, hyps, args)
        config |= {
            "model": args.model,
            "prompt": args.prompt,
            "effort": args.effort,
            "prompt_hash": nli.prompt_version_hash(args.prompt),
            "context": args.context,
            "k": args.k if args.context == "retrieved" else None,
        }
        tag = nli_tag(args.model, args.prompt, args.effort, args.context)
    metrics, records = score(results, docs, hyps)
    metrics["n_failed_docs"] = sum(r.method == "failed" for r in results.values())
    ev = metrics["evidence"]
    print_table(
        [
            {
                "method": tag,
                "n_pairs": metrics["n_pairs"],
                "macro_f1": metrics["macro_f1"],
                "contradiction_f1": metrics["contradiction_f1"],
                "accuracy": metrics["accuracy"],
                "ev_p": ev["micro_p"],
                "ev_r": ev["micro_r"],
                "ev_f1": ev["micro_f1"],
            }
        ]
    )
    print("confusion (rows gold, cols pred):", json.dumps(metrics["confusion"]))
    path = save_result(
        "nli", args.split, config=config, metrics=metrics, records=records, n=len(docs), tag=tag
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

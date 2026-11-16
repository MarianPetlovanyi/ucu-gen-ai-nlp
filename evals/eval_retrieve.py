"""C3 eval: are the gold evidence spans ranked near the top?

Candidates are the gold spans of the document (oracle segmentation, isolates C3 from C2). Queries are
the (document, hypothesis) pairs whose gold label is Entailment or Contradiction (only those have
evidence). Metrics:
- Recall@k: share of a pair's gold evidence spans in the top k (k = 1, 3, 5, 10), averaged over pairs.
  Recall@10 is what matters when C3 feeds a small model with a limited context.
- Hit@k: at least one gold evidence span in the top k (enough to justify a label).
- MRR: 1 / rank of the first gold evidence span.
Baseline: BM25 with the hypothesis as the query.
"""

from __future__ import annotations

import collections
import statistics as st

import numpy as np

from evals.common import parse_args, print_table, save_result
from nda_review.config import EMBED_MODEL
from nda_review.data import load_hypotheses, load_split
from nda_review.retrieve import score_spans

KS = (1, 3, 5, 10)
METHODS = ("bm25", "dense", "exemplar", "hybrid")


def main() -> None:
    args = parse_args(__doc__)
    docs = load_split(args.split, args.limit)
    hyps = load_hypotheses()
    records = []
    for doc in docs:
        scores = {m: score_spans(doc.contract, hyps, m) for m in METHODS}
        for h in hyps:
            if doc.labels[h.id] == "NotMentioned" or not doc.evidence[h.id]:
                continue
            gold = set(doc.evidence[h.id])
            for m in METHODS:
                order = list(np.argsort(-scores[m][h.id]))
                ranks = sorted(order.index(i) + 1 for i in gold)
                rec = {
                    "doc_id": doc.doc_id,
                    "hypothesis": h.id,
                    "label": doc.labels[h.id],
                    "method": m,
                    "n_gold": len(gold),
                    "n_spans": len(order),
                    "first_rank": ranks[0],
                    "ranks": ranks[:10],
                }
                for k in KS:
                    rec[f"recall@{k}"] = sum(r <= k for r in ranks) / len(gold)
                    rec[f"hit@{k}"] = float(ranks[0] <= k)
                rec["rr"] = 1.0 / ranks[0]
                records.append(rec)

    def agg(rs: list[dict]) -> dict:
        out = {f"recall@{k}": st.mean(r[f"recall@{k}"] for r in rs) for k in KS}
        out |= {f"hit@{k}": st.mean(r[f"hit@{k}"] for r in rs) for k in (1, 5)}
        out["mrr"] = st.mean(r["rr"] for r in rs)
        out["n_pairs"] = len(rs)
        return out

    metrics = {m: agg([r for r in records if r["method"] == m]) for m in METHODS}
    per_h = collections.defaultdict(dict)
    for m in METHODS:
        for h in hyps:
            rs = [r for r in records if r["method"] == m and r["hypothesis"] == h.id]
            if rs:
                per_h[h.id][m] = round(st.mean(r["recall@10"] for r in rs), 3)
    metrics["per_hypothesis_recall@10"] = per_h
    print_table([{"method": m, **metrics[m]} for m in METHODS])
    print("\nRecall@10 per hypothesis:")
    print_table(
        [
            {
                "hyp": h,
                "n": sum(1 for r in records if r["hypothesis"] == h and r["method"] == "bm25"),
                **v,
            }
            for h, v in per_h.items()
        ]
    )
    path = save_result(
        "retrieve",
        args.split,
        n=len(docs),
        metrics=metrics,
        records=records,
        config={
            "methods": METHODS,
            "embed_model": EMBED_MODEL,
            "ks": KS,
            "exemplars": "train gold evidence, top-3 mean cosine",
        },
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

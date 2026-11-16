"""Paired comparison of two C4 runs on the same split: per-hypothesis deltas and a paired bootstrap
over documents (95% CI of the metric difference). Use before accepting a prompt/model change.

Usage: uv run python -m evals.compare_runs <tag_a> <tag_b> [--split dev] [--boot 1000]
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import random
from pathlib import Path

from evals.metrics import classification_metrics, evidence_prf
from nda_review.config import RESULTS_DIR, SEED


def load_records(split: str, tag: str) -> list[dict]:
    files = sorted(glob.glob(str(RESULTS_DIR / "nli" / f"*_{split}_{tag}.json")))
    if not files:
        raise SystemExit(f"no result for {tag}")
    return json.loads(Path(files[-1]).read_text())["records"]


def metrics(recs: list[dict]) -> dict[str, float]:
    m = classification_metrics([r["gold"] for r in recs], [r["pred"] for r in recs])
    ev = evidence_prf(
        [
            (set(r["gold_evidence"]), set(r["pred_evidence"]))
            for r in recs
            if r["gold"] != "NotMentioned"
        ]
    )
    return {
        "macro_f1": m["macro_f1"],
        "contradiction_f1": m["Contradiction"]["f1"],
        "evidence_f1": ev["micro_f1"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--boot", type=int, default=1000)
    args = ap.parse_args()
    ra, rb = load_records(args.split, args.a), load_records(args.split, args.b)
    key = lambda r: (r["doc_id"], r["hypothesis"])  # noqa: E731
    ia, ib = {key(r): r for r in ra}, {key(r): r for r in rb}
    assert ia.keys() == ib.keys(), "runs cover different pairs"
    print(f"{'metric':18s} {'A':>7s} {'B':>7s} {'B-A':>7s}  95% CI (paired bootstrap over docs)")
    docs = sorted({k[0] for k in ia})
    by_doc_a, by_doc_b = collections.defaultdict(list), collections.defaultdict(list)
    for k in ia:
        by_doc_a[k[0]].append(ia[k])
        by_doc_b[k[0]].append(ib[k])
    ma, mb = metrics(ra), metrics(rb)
    rng = random.Random(SEED)
    diffs = collections.defaultdict(list)
    for _ in range(args.boot):
        sample = [rng.choice(docs) for _ in docs]
        sa = [r for d in sample for r in by_doc_a[d]]
        sb = [r for d in sample for r in by_doc_b[d]]
        xa, xb = metrics(sa), metrics(sb)
        for m in xa:
            diffs[m].append(xb[m] - xa[m])
    for m in ma:
        d = sorted(diffs[m])
        lo, hi = d[int(0.025 * len(d))], d[int(0.975 * len(d))]
        print(f"{m:18s} {ma[m]:7.3f} {mb[m]:7.3f} {mb[m] - ma[m]:+7.3f}  [{lo:+.3f}, {hi:+.3f}]")
    print("\nper hypothesis: accuracy A → B, evidence F1 A → B")
    for h in sorted({k[1] for k in ia}, key=lambda x: int(x.split("-")[1])):
        xa = [ia[k] for k in ia if k[1] == h]
        xb = [ib[k] for k in ib if k[1] == h]
        acc = lambda xs: sum(r["gold"] == r["pred"] for r in xs) / len(xs)  # noqa: E731
        ev = lambda xs: evidence_prf(  # noqa: E731
            [
                (set(r["gold_evidence"]), set(r["pred_evidence"]))
                for r in xs
                if r["gold"] != "NotMentioned"
            ]
        )["micro_f1"]
        flag = " *" if abs(acc(xb) - acc(xa)) >= 0.05 or abs(ev(xb) - ev(xa)) >= 0.05 else ""
        print(f"  {h:7s} acc {acc(xa):.2f} → {acc(xb):.2f}   ev {ev(xa):.2f} → {ev(xb):.2f}{flag}")


if __name__ == "__main__":
    main()

"""C2 eval: does segmentation reproduce the ContractNLI spans (the evidence units)?

Two settings:
- oracle input: segment the *gold* text, so C2 is measured in isolation. Spans are compared by
  whitespace-trimmed character offsets.
  * span P/R/F1: a predicted span counts only if both boundaries match a gold span exactly.
  * boundary P/R/F1: span start positions; more lenient, credits each correct cut.
  * evidence-span recall: share of gold *evidence* spans reproduced exactly. These are the spans
    that C4 has to cite, so this is the number that matters downstream.
- end-to-end input: segment the C1 output of the original file. Offsets differ from gold, so a
  gold span counts as recovered when a predicted span has the same normalised word sequence.
Baseline: method=lines (one span per line).
"""

from __future__ import annotations

import statistics as st

from evals.common import norm_words, parse_args, prf, print_table, save_result
from nda_review.data import load_split
from nda_review.ingest import ingest
from nda_review.segment import segment


def _trim(text: str, s: int, e: int) -> tuple[int, int]:
    seg = text[s:e]
    lead = len(seg) - len(seg.lstrip())
    return s + lead, s + len(seg.rstrip())


def evaluate_doc(doc, method: str, end_to_end: bool) -> dict:
    text = doc.contract.text
    gold = [_trim(text, sp.start, sp.end) for sp in doc.contract.spans]
    gold = [g for g in gold if g[1] > g[0]]
    ev_ids = sorted({i for ids in doc.evidence.values() for i in ids})
    rec = {"doc_id": doc.doc_id, "method": method, "setting": "e2e" if end_to_end else "oracle"}
    if not end_to_end:
        pred = [(sp.start, sp.end) for sp in segment(text, doc.doc_id, method).spans]
        tp = len(set(pred) & set(gold))
        bp, br, bf = prf(len({s for s, _ in pred} & {s for s, _ in gold}), len(pred), len(gold))
        ev_gold = {
            _trim(text, doc.contract.spans[i].start, doc.contract.spans[i].end) for i in ev_ids
        }
        rec |= {
            "n_pred": len(pred),
            "n_gold": len(gold),
            "tp": tp,
            "boundary_p": bp,
            "boundary_r": br,
            "boundary_f1": bf,
            "ev_n": len(ev_gold),
            "ev_found": len(ev_gold & set(pred)),
            "ev_missed": [text[s:e][:150] for s, e in sorted(ev_gold - set(pred))][:5],
        }
    else:
        ing = ingest(doc.raw_path).text
        pred = {" ".join(norm_words(sp.text)) for sp in segment(ing, doc.doc_id, method).spans}
        gold_t = [" ".join(norm_words(text[s:e])) for s, e in gold]
        ev_t = {" ".join(norm_words(doc.contract.spans[i].text)) for i in ev_ids}
        rec |= {
            "n_pred": len(pred),
            "n_gold": len(gold_t),
            "tp": sum(g in pred for g in gold_t),
            "ev_n": len(ev_t),
            "ev_found": len(ev_t & pred),
        }
    return rec


def summarise(records: list[dict]) -> dict:
    tp, n_pred, n_gold = (sum(r[k] for r in records) for k in ("tp", "n_pred", "n_gold"))
    p, r, f = prf(tp, n_pred, n_gold)
    out = {
        "span_p": p,
        "span_r": r,
        "span_f1": f,
        "n_gold_spans": n_gold,
        "evidence_recall": sum(r["ev_found"] for r in records) / sum(r["ev_n"] for r in records),
        "n_evidence_spans": sum(r["ev_n"] for r in records),
    }
    if "boundary_f1" in records[0]:
        out["boundary_f1"] = st.mean(r["boundary_f1"] for r in records)
    return out


def main() -> None:
    args = parse_args(__doc__)
    docs = load_split(args.split, args.limit)
    metrics, records, rows = {}, [], []
    for e2e in (False, True):
        for method in ("lines", "rules"):
            recs = [evaluate_doc(d, method, e2e) for d in docs]
            key = f"{'e2e' if e2e else 'oracle'}/{method}"
            metrics[key] = summarise(recs)
            records += recs
            rows.append({"setting": key, **metrics[key]})
    print_table(
        rows,
        [
            "setting",
            "span_p",
            "span_r",
            "span_f1",
            "boundary_f1",
            "evidence_recall",
            "n_gold_spans",
            "n_evidence_spans",
        ],
    )
    path = save_result(
        "segment",
        args.split,
        config={"limit": args.limit},
        metrics=metrics,
        records=records,
        n=len(docs),
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

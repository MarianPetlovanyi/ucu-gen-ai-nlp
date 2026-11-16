"""C1 eval: does ingestion of the original PDF/HTML/TXT file reproduce the ContractNLI gold text?

Metrics (macro-averaged over documents, and per source format):
- word P/R/F1: multiset overlap of lowercase word tokens. Recall = content kept, precision = no junk
  (page numbers, headers, SEC cover pages). Insensitive to line breaks.
- line F1: multiset overlap of whitespace-normalised lines. Measures paragraph reconstruction, which
  matters because segmentation (C2) treats every line break as a span boundary.
- evidence recoverability: share of gold evidence spans (≥3 words) whose word sequence occurs
  contiguously in the output. A missed span cannot be cited downstream.
Baseline: method=naive (raw extraction, original hard line breaks).
"""

from __future__ import annotations

import collections
import statistics as st
import time

from evals.common import norm_words, parse_args, prf, print_table, save_result
from nda_review.data import load_split
from nda_review.ingest import ingest


def _multiset_prf(pred: list[str], gold: list[str]) -> tuple[float, float, float]:
    tp = sum((collections.Counter(pred) & collections.Counter(gold)).values())
    return prf(tp, len(pred), len(gold))


def _lines(text: str) -> list[str]:
    return [" ".join(norm_words(x)) for x in text.split("\n") if norm_words(x)]


def evaluate_doc(doc, method: str) -> dict:
    t0 = time.time()
    res = ingest(doc.raw_path, method=method)
    secs = time.time() - t0
    gold = doc.contract.text
    wp, wr, wf = _multiset_prf(norm_words(res.text), norm_words(gold))
    lp, lr, lf = _multiset_prf(_lines(res.text), _lines(gold))
    flat = " " + " ".join(norm_words(res.text)) + " "
    ev_ids = sorted({i for ids in doc.evidence.values() for i in ids})
    ev_texts = [" ".join(norm_words(doc.contract.spans[i].text)) for i in ev_ids]
    ev_texts = [t for t in ev_texts if len(t.split()) >= 3]
    found = [f" {t} " in flat for t in ev_texts]
    return {
        "doc_id": doc.doc_id,
        "format": res.source_format,
        "method": method,
        "word_p": wp,
        "word_r": wr,
        "word_f1": wf,
        "line_p": lp,
        "line_r": lr,
        "line_f1": lf,
        "evidence_n": len(ev_texts),
        "evidence_found": sum(found),
        "evidence_missing": [t[:120] for t, ok in zip(ev_texts, found, strict=True) if not ok][:5],
        "seconds": round(secs, 3),
        "warnings": res.warnings,
        "n_chars": len(res.text),
    }


def summarise(records: list[dict]) -> dict:
    def agg(rs: list[dict]) -> dict:
        ev_n = sum(r["evidence_n"] for r in rs)
        return {
            "n_docs": len(rs),
            "word_p": st.mean(r["word_p"] for r in rs),
            "word_r": st.mean(r["word_r"] for r in rs),
            "word_f1": st.mean(r["word_f1"] for r in rs),
            "line_f1": st.mean(r["line_f1"] for r in rs),
            "evidence_recoverability": sum(r["evidence_found"] for r in rs) / ev_n if ev_n else 0,
            "evidence_n": ev_n,
            "sec_per_doc": st.mean(r["seconds"] for r in rs),
        }

    out = {"all": agg(records)}
    for fmt in sorted({r["format"] for r in records}):
        out[fmt] = agg([r for r in records if r["format"] == fmt])
    return out


def main() -> None:
    args = parse_args(__doc__)
    docs = load_split(args.split, args.limit)
    metrics, all_records = {}, []
    rows = []
    for method in ("naive", "reflow"):
        records = [evaluate_doc(d, method) for d in docs]
        all_records += records
        metrics[method] = summarise(records)
        for scope, m in metrics[method].items():
            rows.append({"method": method, "scope": scope, **m})
    print_table(
        rows,
        [
            "method",
            "scope",
            "n_docs",
            "word_p",
            "word_r",
            "word_f1",
            "line_f1",
            "evidence_recoverability",
            "evidence_n",
            "sec_per_doc",
        ],
    )
    path = save_result(
        "ingest",
        args.split,
        config={"methods": ["naive", "reflow"], "limit": args.limit},
        metrics=metrics,
        records=all_records,
        n=len(docs),
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()

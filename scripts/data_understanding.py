"""CRISP-DM phase 2: descriptive statistics and quality checks for ContractNLI.

Usage: uv run python scripts/data_understanding.py
Writes data/processed/data_stats.json and prints markdown tables for docs/crisp-dm/02-data-understanding.md.
"""

from __future__ import annotations

import collections
import json
import re
import statistics as st
from pathlib import Path

RAW = Path("data/raw/contract-nli/contract-nli")
OUT = Path("data/processed/data_stats.json")
CHARS_PER_TOKEN = 4.0  # rough English estimate; good enough for budgeting


def pct(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def main() -> None:
    labels = json.loads((RAW / "train.json").read_text())["labels"]
    stats: dict = {"splits": {}, "per_hypothesis": {}}
    all_texts: dict[str, str] = {}
    for split in ("train", "dev", "test"):
        docs = json.loads((RAW / f"{split}.json").read_text())["documents"]
        chars = [len(d["text"]) for d in docs]
        n_spans = [len(d["spans"]) for d in docs]
        span_chars = [e - s for d in docs for s, e in d["spans"]]
        label_counts: collections.Counter = collections.Counter()
        ev_counts = []
        per_h: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        doc_types = collections.Counter(d.get("document_type") for d in docs)
        n_ann_sets = collections.Counter(len(d["annotation_sets"]) for d in docs)
        non_ascii_heavy = 0
        for d in docs:
            all_texts[f"{split}/{d['id']}"] = d["text"]
            letters = re.findall(r"[A-Za-zÀ-ÿ]", d["text"])
            accented = re.findall(r"[À-ÿ]", d["text"])
            if letters and len(accented) / len(letters) > 0.02:
                non_ascii_heavy += 1
            for h, a in d["annotation_sets"][0]["annotations"].items():
                label_counts[a["choice"]] += 1
                per_h[h][a["choice"]] += 1
                if a["choice"] != "NotMentioned":
                    ev_counts.append(len(a["spans"]))
        stats["splits"][split] = {
            "n_docs": len(docs),
            "chars_median": st.median(chars),
            "chars_p90": pct(chars, 0.9),
            "chars_max": max(chars),
            "approx_tokens_median": round(st.median(chars) / CHARS_PER_TOKEN),
            "approx_tokens_max": round(max(chars) / CHARS_PER_TOKEN),
            "spans_median": st.median(n_spans),
            "spans_max": max(n_spans),
            "span_chars_median": st.median(span_chars),
            "span_chars_p95": pct(span_chars, 0.95),
            "labels": dict(label_counts),
            "evidence_spans_per_pair_median": st.median(ev_counts),
            "evidence_spans_per_pair_max": max(ev_counts),
            "document_types": {str(k): v for k, v in doc_types.items()},
            "annotation_sets_per_doc": {str(k): v for k, v in n_ann_sets.items()},
            "docs_with_many_accented_letters": non_ascii_heavy,
        }
        if split != "test":  # decisions are made on train/dev only
            for h, c in per_h.items():
                agg = stats["per_hypothesis"].setdefault(
                    h, {"short": labels[h]["short_description"], "E": 0, "C": 0, "N": 0}
                )
                agg["E"] += c["Entailment"]
                agg["C"] += c["Contradiction"]
                agg["N"] += c["NotMentioned"]

    # exact duplicate texts across splits (leakage check)
    by_text: dict[str, list[str]] = collections.defaultdict(list)
    for key, text in all_texts.items():
        by_text[re.sub(r"\s+", " ", text).strip().lower()].append(key)
    dups = [keys for keys in by_text.values() if len(keys) > 1]
    cross_split = [k for k in dups if len({x.split("/")[0] for x in k}) > 1]
    stats["duplicates"] = {
        "groups": len(dups),
        "cross_split_groups": len(cross_split),
        "examples": cross_split[:5],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(stats, indent=2))

    print(
        "| split | docs | median chars (≈tokens) | max chars (≈tokens) | spans/doc median | E | C | N |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for split, s in stats["splits"].items():
        lab = s["labels"]
        print(
            f"| {split} | {s['n_docs']} | {s['chars_median']:.0f} (≈{s['approx_tokens_median']}) | "
            f"{s['chars_max']} (≈{s['approx_tokens_max']}) | {s['spans_median']} | "
            f"{lab.get('Entailment', 0)} | {lab.get('Contradiction', 0)} | {lab.get('NotMentioned', 0)} |"
        )
    print()
    for split, s in stats["splits"].items():
        print(
            f"{split}: doc types={s['document_types']} ann_sets={s['annotation_sets_per_doc']} "
            f"accented-heavy docs={s['docs_with_many_accented_letters']} "
            f"span chars median={s['span_chars_median']} p95={s['span_chars_p95']} "
            f"evidence/pair median={s['evidence_spans_per_pair_median']} max={s['evidence_spans_per_pair_max']}"
        )
    print("duplicates:", stats["duplicates"])


if __name__ == "__main__":
    main()

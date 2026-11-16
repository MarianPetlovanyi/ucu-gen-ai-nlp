# Phase 2: Data understanding
Status: closed 2026-11-14
Reproduce: `uv run python scripts/data_understanding.py` → `data/processed/data_stats.json`

## Existing datasets considered (before any synthetic data)
| Dataset | What it has | Fit for us | Decision |
|---|---|---|---|
| **ContractNLI** (Koreeda & Manning, 2021) | 607 NDAs, 17 hypotheses, a label for every (doc, hypothesis) pair, gold evidence spans, original PDF/HTML files | Exactly our task: document-level NLI + evidence, and gold for C1–C5 | **Chosen** |
| CUAD | 510 commercial contracts, 41 clause types (extractive) | Clause extraction, not entailment; mostly non-NDAs | Not used (possible future rule extension) |
| LexGLUE `unfair_tos` | Terms-of-service sentences, 8 unfairness types | Consumer ToS, not B2B NDAs | Not used |
| LEDGAR | Provision-level topic classification | Topic only, no stance | Not used |
| Synthetic NDAs | — | Not needed, real annotated data exists | Not generated |

The gold labels for the derived tasks are built **deterministically from ContractNLI gold**, not synthesised.
For example, rule status = playbook stance applied to the gold NLI label (see phase 3).

**License:** CC BY 4.0 (`data/raw/contract-nli/contract-nli/LICENSE`, plus the Hitachi America terms of use).

## Structure
Each document has `text`, `spans` (character offsets of sentences and list items, the evidence unit), `document_type`,
`url`, and one `annotation_set` mapping each of the 17 hypotheses to `{choice, spans}`. The 17 hypotheses are the
same for every document. The original files (`raw/`, 607 PDF/HTML/TXT) are included, so ingestion (C1) can be
evaluated against the gold text.

## Size and length
| split | docs | median chars (≈tokens) | max chars (≈tokens) | spans/doc median | Entailment | Contradiction | NotMentioned |
|---|---|---|---|---|---|---|---|
| train | 423 | 9 936 (≈2 484) | 54 571 (≈13 643) | 71 | 3 530 | 841 | 2 820 |
| dev | 61 | 11 299 (≈2 825) | 32 359 (≈8 090) | 72 | 519 | 95 | 423 |
| test | 123 | 9 614 (≈2 404) | 41 779 (≈10 445) | 72 | 968 | 220 | 903 |

- Every contract fits whole in gpt-oss's 131K context. Retrieval is therefore not needed to fit the context. It is
  needed for **evidence localisation**, for the small local baselines (512-token limit), and for highlighting in the UI.
- Spans: median 101 chars, p95 ≈ 430 chars. Evidence spans per labelled pair: median 2, max 32.
- Budget: about 3–4k input tokens per contract for a full-document review, roughly $0.001–0.002 per contract with gpt-oss-120b.

## Label distribution per hypothesis (train + dev; test not inspected)
| hyp | concept | E | C | N |
|---|---|---|---|---|
| nda-1 | Explicit identification | 110 | 122 | 252 |
| nda-2 | Only technical information | 29 | 353 | 102 |
| nda-3 | Verbal information included | 315 | 4 | 165 |
| nda-4 | Limited use | 414 | 10 | 60 |
| nda-5 | Sharing with employees | 399 | 15 | 70 |
| nda-7 | Sharing with third parties | 298 | 125 | 61 |
| nda-8 | Notice on compelled disclosure | 321 | 0 | 163 |
| nda-10 | Confidentiality of agreement | 188 | 2 | 294 |
| nda-11 | No reverse engineering | 67 | 1 | 416 |
| nda-12 | Independent development | 303 | 0 | 181 |
| nda-13 | Acquire from third party | 358 | 0 | 126 |
| nda-15 | No licensing | 366 | 0 | 118 |
| nda-16 | Return of information | 203 | 3 | 278 |
| nda-17 | Permissible copy | 100 | 84 | 300 |
| nda-18 | No solicitation | 104 | 0 | 380 |
| nda-19 | Survival of obligations | 343 | 11 | 130 |
| nda-20 | Post-agreement possession | 131 | 206 | 147 |

## Findings that drive later decisions
1. **Class imbalance.** Contradiction is about 11% overall and is concentrated in nda-1, 2, 7, 17 and 20. Six
   hypotheses have *no* contradictions at all. So we report **macro-F1 and Contradiction-F1**, not only accuracy,
   and we include a majority-per-hypothesis baseline, which is strong for skewed hypotheses.
2. **Many protections are simply missing.** nda-11 ("no reverse engineering") is NotMentioned in 86% of NDAs. For a
   disclosing party, "MISSING" is the most frequent issue type. That's why C6 must *insert* clauses, not only
   rewrite them.
3. **Single annotation set per document.** There's no inter-annotator agreement, so gold noise can't be quantified.
   Error analysis must separate model errors from probable label errors.
4. **One cross-split duplicate** (train/538 = test/537). It is excluded from few-shot examples and fine-tuning data
   (phase 3).
5. **Document sources:** 62% PDFs found by web search, plus SEC filings (text and HTML). PDF extraction artefacts
   (headers, broken lines) are a risk for C1 and C2.
6. **Negation by exception** ("…except that Recipient may retain one archival copy") is the known hard case for this
   dataset, per the dataset authors.

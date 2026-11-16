# Phase 5: Evaluation
Status: closed 2026-11-14; reopened and closed again 2026-11-16 for the end-to-end eval (iteration 17, section
"E2E"). 18 log rows; final test numbers in section "Final test".

All numbers below are on the **dev** split (61 NDAs, 17 hypotheses each = 1 037 contract–hypothesis pairs) unless
marked otherwise. *n* is given next to every metric. Each number comes from a result file in
`evals/results/<component>/`, which also stores the config, model ids, prompt hash and per-example records.

## How each component is evaluated, and why
Each component is evaluated **in isolation** (gold input from upstream, the "oracle" setting), so an error is
charged to the component that made it. C1→C2 and C4→C5→C6/C7 are also evaluated **end to end**, and so is the
whole chain C1→C7 from the original file, with no gold input at all (section "E2E").

| # | Primary metric | Why this metric (what the business loses when it is low) | Reference point |
|---|---|---|---|
| C1 | **Evidence recoverability** (share of gold evidence spans whose words all appear in order in the extracted text), plus word F1 and line F1 against the gold text | A clause lost or garbled in extraction can never be cited. Word F1 alone hides lost paragraph structure, so line F1 measures paragraph boundaries, which C2 needs | `naive` extraction |
| C2 | **Evidence-span recall** (gold evidence spans reproduced exactly), plus span F1 and boundary F1 | Evidence is cited at span level, so a merged or split clause makes evidence P/R wrong even when the reasoning is right | `lines` (one span per line) |
| C3 | **Recall@k** (k = 1, 3, 5, 10) and MRR over pairs with evidence | C3 decides which clauses the UI shows and where C6 inserts new text. Recall@10 matters when it filters the context of the LLM | BM25, dense query, hybrid |
| C4 | **Macro-F1** over E/C/N, **Contradiction-F1**, evidence micro P/R/F1 | Classes are imbalanced (E 50%, N 41%, C 9%). A Contradiction is the most expensive miss (the contract says the opposite of our position). Evidence F1 measures whether the cited clause is the right one | majority-per-hypothesis (train), zero-shot DeBERTa, fine-tuned DeBERTa |
| C5 | **Issue recall** (VIOLATION or MISSING) and precision vs status derived from gold labels; high-severity recall; risk Spearman ρ | A missed issue is the expensive error (phase 1 target recall ≥ 0.85). Precision is the lawyer's wasted time. ρ checks that risk ranks contracts as gold would | the same playbook on majority-baseline labels |
| C6 | **Fix rate** (judge NLI re-check: issue gone), **collateral rate** (other rules' status changed), **term mismatch** (generic playbook term the contract doesn't define), edit ratio, judge quality 1–5 (secondary) | A redline is only useful if it fixes the issue *without* breaking another rule, in the contract's own language, with a small edit a counterparty will accept | `template` (paste the playbook's preferred clause) |
| C7 | **Coverage** (every issue has a memo item), **citation validity and relevance** (cited spans exist and are evidence of that rule), **faithfulness** of cited claims (judge), **absence-claim accuracy** ("the contract is silent" vs gold), invented clause references | A memo that omits an issue or cites the wrong clause misleads the lawyer | deterministic checks + validated judge |
| E2E | **Gold issues resolved** (gold issue raised AND fixed by the redline, judge) / all gold issues; C4/C5 vs gold with no gold input; cost and latency per contract | This is what the user gets: a problem in the NDA either ends up with a working fix or it doesn't, whichever component failed | the same metrics with gold upstream (oracle) |
| Judge | agreement with known-good / known-bad cases, κ vs gold, κ vs Claude Code labels | A judge metric is only meaningful if the judge can tell good from bad | — |

---

## C1 Ingestion
`eval_ingest.py`. 61 raw dev files (38 PDF, 12 TXT, 11 HTML) vs the gold reflowed text.

| method | word F1 | line F1 | evidence recoverability (n = 860 spans) | sec/doc |
|---|---|---|---|---|
| naive | 0.990 | 0.130 | 0.966 | 0.008 |
| **reflow** (chosen) | **0.996** | **0.682** | **0.984** | 0.008 |

By format (reflow): PDF line F1 0.640 / recoverability 0.981 (n = 38 docs). HTML 0.750 / 0.995 (n = 11).
TXT 0.753 / 0.978 (n = 12). The naive and reflow methods extract the same words; reflow differs by restoring the
paragraph structure.

**Failure analysis.** 957 of the 2 759 gold lines are not reproduced exactly (all formats). Categories were
assigned automatically by comparing each gold line with the extracted lines:

| Cause | Lines | Typical case |
|---|---|---|
| Missing break, short line (< 6 words): headings, signature-block fields ("Title:", "Director"), labels | 357 | the reflow joins them with the next line |
| Missing break, long line: sub-clauses that gold keeps on separate lines but we join as one paragraph, because the previous line doesn't end a sentence | 396 | dev/35 "4.5.1 immediately notify …" |
| Extra break inside a gold line (a paragraph continuing after a page break or a column gap) | 115 | PDF page breaks after a sentence-ending line |
| Text differs: two-column signature blocks interleaved, extraction artefacts | 89 | dev/29 "Authorized Signature Authorized Signature" |

Most of the missing breaks are in signature blocks and headings, which carry no evidence. That's why line F1
is low while evidence recoverability is high.

14 of 860 evidence spans are unrecoverable (n = 10 docs). Diagnosed from the records by finding where the
gold span stops matching the extracted text:

| Cause | Count | Example |
|---|---|---|
| Typos or missing spaces in the gold text itself | 2 | dev/64 "suchf information", dev/69 "ConfidentialInformation" |
| A real hyphen at a line end removed by de-hyphenation | 1 | dev/73 "non-confidential" → "nonconfidential" |
| A signature block or footer interleaved mid-sentence by the PDF layout | 1 | dev/3 |
| The PDF content differs from the gold text (template with alternative clauses) | 2 | dev/37 |
| The divergence is after the stored 120-character prefix (not diagnosed further) | 8 | dev/7, dev/398, dev/405, dev/595 … |

The line F1 ceiling is partly a gold convention (headings, signature blocks), so evidence recoverability is
the mission-critical number, and it is 98.4%.

## C2 Segmentation
`eval_segment.py`. 5 039 gold spans, of which 878 are evidence (n = 61 docs).

| setting | method | span F1 | boundary F1 | evidence-span recall |
|---|---|---|---|---|
| oracle (gold text) | lines | 0.454 | 0.722 | 0.251 |
| oracle (gold text) | rules, iteration 2 | 0.831 | 0.937 | 0.905 |
| oracle (gold text) | **rules, iteration 11** (final) | **0.854** | **0.946** | **0.943** |
| end to end (C1 → C2) | lines | 0.341 | — | 0.185 |
| end to end (C1 → C2) | rules, iteration 2 | 0.742 | — | 0.811 |
| end to end (C1 → C2) | **rules, iteration 11** (final) | **0.764** | — | **0.843** |

**Failure analysis.** All 83 evidence spans missed by iteration 2 on oracle text (n = 878) were categorised
automatically (where the predicted cut falls inside a gold span) and sampled by hand (seed 13):

| Cause | Count | Example | Action |
|---|---|---|---|
| Split before a numeral that restates a number word | 33 | "within thirty **(30)** days", "three **(3)** years" | **fixed in iteration 11**. Train: no boundary in 576/583 cases |
| Under-split: gold cuts where we don't (e.g. "1. a." headings, "Information which:" + list on the same line) | 38 | dev/406, dev/64 | kept. No consistent rule on train |
| Over-split after a bare section number ("2.2 ") | 8 | dev/20, dev/7 | kept. These are the 38% of train cases that go the other way |
| Over-split at a sentence end inside citations/abbreviations ("C.F.R. § 99.") | 4 | dev/9, dev/73 | kept (rare) |

After iteration 11, 50 evidence spans (5.7%) are still missed on oracle text. End to end, another ~10 points
are lost to C1 paragraph errors. A downstream LLM still sees the same text, so this mostly hurts the
evidence-span metric, not the label. That's why C3/C4 are evaluated on gold spans and the end-to-end effect is
reported separately.

## C3 Evidence retrieval
`eval_retrieve.py`. Pairs with gold evidence: n = 614. Candidates are the gold spans of the document.

| method | R@1 | R@3 | R@5 | R@10 | hit@1 | MRR |
|---|---|---|---|---|---|---|
| BM25 (hypothesis as query) | 0.219 | 0.395 | 0.498 | 0.664 | 0.355 | 0.509 |
| dense (bge-small, hypothesis as query) | 0.212 | 0.412 | 0.518 | 0.671 | 0.319 | 0.495 |
| hybrid RRF (BM25 + exemplar) | 0.333 | 0.552 | 0.673 | 0.808 | 0.524 | 0.667 |
| **exemplar kNN** (chosen) | 0.320 | **0.626** | **0.732** | **0.834** | **0.529** | **0.683** |

**Failure analysis.** The weakest hypotheses at R@10 are:
- nda-2 "only technical information" (0.661): the evidence is the whole definition list, often more than 10
  spans.
- nda-18 no-solicitation (0.692): rare, with phrasing that varies.
- nda-17 copies (0.706) and nda-20 retention (0.729): the two topics share vocabulary ("copies"), so their
  exemplars compete.

The hypothesis wording is short and abstract ("Receiving Party may share some Confidential Information with
some third-parties"), and legal drafting rarely reuses it. That is why both query-based retrievers lose to the
exemplar retriever, which matches against how *real contracts* phrase each topic (train evidence).

## C4 NLI + evidence
`eval_nli.py`. n = 1 037 pairs (E 519, C 95, N 423), 61 docs. Evidence micro P/R/F1 is computed over the 614
pairs with gold evidence.

| method | macro-F1 | C-F1 | acc | evidence P | evidence R | evidence F1 |
|---|---|---|---|---|---|---|
| majority per hypothesis (train priors) + top-2 exemplar spans | 0.633 | 0.516 | 0.681 | 0.445 | 0.359 | 0.397 |
| zero-shot DeBERTa-v3 MNLI (span level, thresholds tuned on dev) | 0.182 | 0.191 | 0.184 | 0.032 | 0.033 | 0.032 |
| fine-tuned DeBERTa-v3 (29 826 train span pairs, 2 epochs, Colab T4; thresholds tuned on dev) | 0.786 | 0.677 | 0.830 | 0.759 | 0.628 | 0.687 |
| gpt-oss-120b, prompt v1 (generic) | 0.750 | 0.592 | 0.807 | 0.805 | 0.487 | 0.607 |
| gpt-oss-120b, prompt v2 | 0.742 | 0.581 | 0.799 | 0.760 | 0.529 | 0.623 |
| gpt-oss-120b, prompt v3 | 0.775 | 0.631 | 0.825 | 0.794 | 0.546 | 0.647 |
| **gpt-oss-120b, prompt v4** (chosen) | **0.782** | **0.642** | **0.831** | 0.792 | 0.518 | 0.626 |
| *ablation*: gpt-oss-20b, v3 | 0.770 | 0.655 | 0.813 | 0.646 | 0.532 | 0.583 |
| *ablation*: 120b v3, retrieved context (top-10 per hypothesis via C3) | 0.760 | 0.623 | 0.807 | 0.837 | 0.465 | 0.598 |
| *ablation*: 120b v3, reasoning effort high | 0.764 | 0.629 | 0.811 | 0.829 | 0.542 | 0.656 |
| *ablation*: **qwen3.8-27b** (the judge model), v3, no reasoning | **0.830** | **0.696** | **0.881** | **0.900** | **0.615** | **0.731** |

Confusion for v4 (rows = gold, columns = predicted):

| | E | C | N |
|---|---|---|---|
| **E** (519) | 460 | 13 | 46 |
| **C** (95) | 13 | 78 | 4 |
| **N** (423) | 42 | 57 | 324 |

**Is a difference real?** `evals/compare_runs.py` gives a paired bootstrap over documents (500 resamples,
95% CI of B − A):

| comparison | Δ macro-F1 | Δ C-F1 | Δ evidence F1 |
|---|---|---|---|
| v3 → v4 | +0.007 [−0.011, +0.026] | +0.011 [−0.025, +0.045] | −0.020 [−0.043, +0.000] |
| v3 medium → v3 high effort | −0.011 [−0.036, +0.015] | −0.002 [−0.043, +0.044] | +0.009 [−0.019, +0.035] |
| gpt-oss-120b v4 → qwen3.8-27b v3 | **+0.048 [+0.018, +0.077]** | +0.054 [−0.013, +0.122] | **+0.104 [+0.079, +0.130]** |

None of the label differences between the LLM variants is significant at n = 61 documents. The gain over the
majority baseline is: macro-F1 +0.15, evidence F1 +0.23.
v4 fixed what it targeted (nda-17 accuracy 0.66 → 0.74). It also moved other hypotheses both ways (nda-16
0.82 → 0.74, nda-1 0.66 → 0.72), because any prompt change perturbs every output. **v4 was adopted on the
business metric** (C5 issue recall ≥ 0.85 on both playbooks; v3 misses it on the receiving playbook). Its
evidence F1 is lower (0.626) but still above the 0.60 target, and the CI of that drop touches 0.

**Ablation readings:**
- *20b vs 120b*: the labels are almost as good (macro-F1 −0.005, within noise at n = 1 037), but evidence
  precision drops by 15 points. The bigger model cites the right clause more often, which is the user-visible
  part.
- *Retrieved context*: precision goes up, but recall is lower (−8 points evidence recall) and macro-F1 is
  −0.015. Restricting the context hides clauses that matter (definitions, cross-references). All contracts fit
  in context, so full context is kept.
- *qwen3.8-27b* (iteration 14): judge validation part A showed that the judge model agrees with gold better than
  the system does. As a C4 model it is significantly better on labels (+0.048 macro-F1) and evidence (+0.104
  evidence F1, it cites the definitions and exceptions that gold marks). It is better on 14 of 17 hypotheses
  (nda-20 0.54 → 0.69), worse on nda-19. **It was not adopted**, for two reasons. First, the decision is taken
  on the business metric: Qwen is more conservative, so issue recall on the disclosing playbook drops to
  0.831, below the 0.85 target (see C5). Second, Qwen is the independent judge for C6/C7. Making it the system
  model would mean a new judge and a new judge validation, two days before the deadline.
- *Reasoning effort high*: no gain (macro-F1 −0.011, within noise), and slower. In the first run one contract
  used up the 16k-token budget and returned no JSON, which crashed the eval. The eval now records and counts
  failed docs (iteration 8). In the re-run that contract succeeded (0 failed docs out of 61).

### Failure analysis (v3, 181 errors, 18 read in full with seed 13)
| Category | Count | Examples / evidence | Ours or label |
|---|---|---|---|
| **Annotation-convention mismatch: nda-20** retention. "Return all copies" with no exception: we say C, gold says N | 22 (N→C) | dev/44, dev/20, dev/9, dev/16. Train has this pattern as C in 127/148 contracts, dev as C in only 6/22 | **label drift between splits**. Not fixed (would mean tuning to dev) |
| **nda-17 copies conflated with nda-20 retention**: a clause allowing *retention* of an archival copy, or a return clause naming "all copies", is read as permission to *make* copies | 14 (N→E) + 5 (C→E) | dev/63, dev/598, dev/590, dev/595, dev/586, dev/33 | **ours**. On train, contracts that allow retention are N for nda-17 in 77/117 → fixed in v4 |
| nda-2 "only technical information": a broad definition (business, financial) read as C | 11 (N→C) | dev/39, dev/17, dev/64 | train: C 305 vs N 70 for the same pattern → **dev label noise**. Kept |
| nda-10 "agreement terms are confidential": definition includes "terms of this Agreement", we say N | 13 (E→N) | dev/35, dev/205 | train is split, E 118 vs N 102 → ambiguous convention. Kept |
| nda-7 sharing with third parties: "need-to-know employees only" read as C | 11 (E→C) + 4 (N→C) | dev/486 | ours (scope of "employees" vs "third parties"), partly label noise |
| nda-1 explicit identification | 11 (N→C) + 7 other | dev/32 (definition lists "marked" as one of several alternatives) | mixed |
| Evidence: correct label but a different span cited (evidence recall 0.55) | — | the model cites the operative clause, gold also marks definitions and exceptions | partly convention: gold evidence is exhaustive, ours is minimal |

## C5 Playbook compliance + risk
`eval_playbook.py`. Gold rule status = the same playbook applied to the **gold** labels. n = 1 037 rule checks
per playbook (61 contracts × 17 rules). Gold issues: 295 (disclosing), 217 (receiving).
C5 is deterministic: on gold labels it reproduces the gold status by construction (unit tests in
`tests/test_playbook.py`). So this eval measures **how C4 errors propagate into business decisions**, and
selects the C4 variant.

| C4 upstream | playbook | issue P | issue R | issue F1 | high-sev R | violation F1 | risk ρ | risk MAE |
|---|---|---|---|---|---|---|---|---|
| majority | disclosing | 0.713 | 0.590 | 0.646 | 0.431 | 0.000 | 0.00 | 11.2 |
| majority | receiving | 0.776 | 0.654 | 0.710 | 0.000 | 0.203 | 0.00 | 13.1 |
| 120b v1 | disclosing | 0.857 | 0.831 | 0.843 | 0.813 | 0.596 | 0.64 | 5.9 |
| 120b v3 | disclosing | 0.873 | 0.861 | 0.867 | 0.829 | 0.700 | 0.67 | 5.5 |
| 120b v3 | receiving | 0.879 | **0.839** | 0.858 | 0.857 | 0.529 | 0.85 | 6.2 |
| **120b v4** (chosen) | disclosing | 0.861 | **0.864** | 0.863 | 0.829 | 0.707 | 0.63 | 5.8 |
| **120b v4** (chosen) | receiving | **0.901** | **0.880** | **0.890** | 0.857 | 0.558 | 0.85 | 5.9 |
| 120b v3 high effort | disclosing | 0.811 | 0.871 | 0.840 | 0.813 | 0.691 | 0.48 | 7.4 |
| 120b v3 retrieved ctx | disclosing | 0.835 | 0.875 | 0.854 | 0.870 | 0.700 | 0.75 | 5.1 |
| 20b v3 | disclosing | 0.846 | 0.800 | 0.822 | 0.707 | 0.667 | 0.56 | 6.4 |
| qwen3.8-27b v3 (ablation) | disclosing | **0.942** | 0.831 | **0.883** | 0.805 | 0.718 | 0.67 | 5.4 |
| qwen3.8-27b v3 (ablation) | receiving | **0.936** | 0.880 | **0.907** | **0.929** | 0.614 | 0.88 | 4.7 |
| zero-shot DeBERTa (baseline) | disclosing | 0.462 | 0.817 | 0.590 | 0.821 | 0.025 | −0.17 | 34.7 |
| zero-shot DeBERTa (baseline) | receiving | 0.471 | 0.931 | 0.625 | 1.000 | 0.208 | −0.14 | 44.8 |
| fine-tuned DeBERTa (baseline) | disclosing | 0.895 | 0.749 | 0.815 | 0.780 | 0.535 | 0.46 | 8.1 |
| fine-tuned DeBERTa (baseline) | receiving | 0.894 | 0.820 | 0.856 | 0.571 | 0.592 | 0.76 | 7.1 |
| *union* v4 ∪ qwen (offline estimate: issue if either flags) | disclosing | 0.855 | **0.902** | 0.878 | — | — | — | — |
| *union* v4 ∪ qwen (offline estimate) | receiving | 0.889 | **0.922** | 0.905 | — | — | — | — |

Against the phase-1 targets, issue recall ≥ 0.85 is **met** (0.864 / 0.880) and issue precision ≥ 0.70 is
**met** (0.861 / 0.901). High-severity recall is 0.83–0.86. The majority baseline has risk ρ = 0 because it
gives every contract the same labels.

**Failure analysis (v4, disclosing playbook): 40 missed issues and 41 false alarms out of 1 037 checks.** All
of them are C4 label errors, since C5 adds none:

| Rule (hypothesis) | Missed | False alarms | Root cause in C4 (see C4 failure analysis) |
|---|---|---|---|
| R11 agreement confidential (nda-10) | — | 12 | "terms of this Agreement" inside the CI definition, which the model doesn't count. Train convention is ambiguous (E 118 / N 102) |
| R09 return on termination (nda-16) | 6 | 8 | "on request" vs "on termination". v4 moved this hypothesis (0.82 → 0.74) |
| R07 oral information covered (nda-3) | 7 | — | a definition with no limit on form ("all information …") is read as covering oral disclosure; gold wants an explicit mention (7/7 checked). dev/82 "written or oral information" labelled N looks like label noise |
| R05 no marking requirement (nda-1) | 5 | 2 | the marking convention. Still the weakest hypothesis (0.72) |
| R10 no retention (nda-20) | — | 5 | train/dev label drift |
| R03, R04, R01 (high severity) | 5 + 4 + 7 | 3 + 3 + 2 | spread over different phrasings, no single pattern |

**Model choice on the business metric (iteration 14).** Qwen as the C4 model has higher F1, but recall on the
disclosing playbook drops below target (0.831): 50 missed issues vs 40. 36 of Qwen's 50 misses are gold
NotMentioned pairs that Qwen labels Entailment, so it reads a protection into a contract that doesn't have it.
Most are R09 return on termination (12, the "on request" convention) and R04 survival (8). The two models make
different errors. Flagging an issue when *either* model flags it (computed offline
from the two dev runs, no new calls) reaches recall 0.902 / 0.922 at precision 0.855 / 0.889. Both targets are
met with a margin. This needs a second C4 call (+≈$0.001 per contract) and a new independent judge, so it is the
first item under next steps, not part of the evaluated system.

The two most valuable next steps would be a nda-10 convention decided by the business (does "terms are
Confidential Information" count?) and per-hypothesis self-consistency (several samples, majority vote) on the
four weakest hypotheses. Neither was done, so the test split stays clean.

## C6 Redline drafter
`eval_redline.py`, disclosing playbook, **gold upstream** (issues derived from gold labels), so C6 is not
charged for C4 errors. n = 295 issues (49 VIOLATION, 246 MISSING) in 61 contracts.

Each redline set is applied to the contract (`apply_redlines`), and the **judge re-runs NLI on the revised
contract** (Qwen, validated in part A).
- *Fix rate*: the issue's rule is no longer VIOLATION/MISSING. It is also reported on the 248 issues where the
  judge agrees, on the *original* contract, that there is an issue ("judge-confirmed"), so judge-vs-gold
  disagreement can't count as a fix.
- *Collateral rate*: the share of the *other* rules whose status changed. It measures whether a redline broke
  something else.
- *Edit ratio*: character-level change, a proxy for how much a counterparty has to read.
- *Term mismatch*: the redline uses one of the playbook's generic terms ("Receiving Party", "Disclosing Party",
  "Confidential Information", "Purpose", "Representatives") that the contract never uses. In such a contract
  the term is undefined, and the clause may have no effect. This is what the LLM is supposed to add over the
  template (CLAUDE.md lesson 4).
- *Judge quality* 1–5: secondary. On subtle errors it doesn't agree with a second annotator (judge validation D).

| method | fix rate (n = 295) | fix rate, judge-confirmed (n = 248) | collateral | edit ratio | term mismatch | judge quality | failed docs |
|---|---|---|---|---|---|---|---|
| template (preferred clause verbatim, no LLM) | 0.993 | 0.992 | 0.034 | 0.072 | 0.441 | 4.88 | 0 |
| LLM, prompt `redline` (v1) | 0.966 | 0.960 | 0.028 | 0.069 | 0.163 | 4.78 | 0 |
| LLM, prompt `redline_v2` | 0.990 | 0.988 | 0.030 | 0.071 | 0.041 | 4.80 | 0 |
| template + `safe_anchor` | 0.993 | 0.992 | 0.034 | 0.071 | 0.441 | 4.89 | 0 |
| **LLM `redline_v2` + `safe_anchor`** (chosen) | **0.986** | **0.984** | **0.028** | 0.070 | **0.041** | 4.83 | 0 |

Insertions whose anchor is a list lead-in, a list item or mid-sentence: LLM 84/254 → **4/254**, template
119/252 → 8/252 (the remaining ones hit the 12-span limit).

Results: `evals/results/redline/20261114T134646_dev_disclosing_party-gold.json` (v1),
`…T140055_…` (v2), `…T140624_…` (v2 + safe anchors).

Against the targets, fix rate ≥ 0.80 ✅ and collateral ≤ 5 % ✅.

**Reading.**
- On fix rate the template is as good as the LLM. Pasting the playbook clause fixes the issue by construction.
- The template's weakness is that 44 % of its redlines use a term the contract doesn't define. An example is
  "Receiving Party" in a contract about the "Recipient" and the "Company". A lawyer would have to rewrite those
  by hand.
- The LLM v2 does this in 4 % of redlines, with the same fix rate and collateral.
- The collateral rate (≈ 3 %) sits at the judge's noise level. Revising a contract makes the judge re-read
  every clause, and part A2 shows that ≈ 1 % of statuses flip even for an irrelevant edit. Most collateral
  changes are on the hypotheses where the judge is least stable (nda-20, nda-7, nda-3, nda-17).

**Failure analysis.** All unfixed redlines were read.
- *v1, 10 unfixed, all R10* (no retention after return). In 9 of the 10 the LLM wrote the playbook's
  **fallback** ("except copies in automatic electronic back-ups …") into the redline. The 10th (dev/27) kept
  the contract's own "as required by applicable law" exception. Drafting the concession up front defeats the position. → `redline_v2`: draft the
  preferred position only, remove the exception that causes the conflict, and use only terms the contract
  uses (iteration 13). R10 fixed: 3/13 → 10/13.
- *v2, 3 unfixed, all R10:*
  - dev/27 keeps "except as may be required by applicable law";
  - dev/547 inserts a new clause instead of replacing the backup clause, and re-creates a backup exception;
  - dev/563 replaces spans 42–45 but leaves span 46 ("…any Confidential Information retained pursuant to the
    second sentence…"), so the contract still implies retention.

  These are the hard cases: a retention exception spread over several spans, or a "required by law" carve-out
  that lawyers usually accept.
- *Insertion placement* (found by the second annotator, judge validation D). 3 of 26 sampled redlines that the
  judge accepted were inserted in the wrong place: after a definitions lead-in "In this Agreement:", inside a
  list of exclusions, or after a span that ends mid-sentence. A deterministic check over *all* insertions showed
  the anchor ends without sentence-final punctuation, or is followed by a list item, for 33 % of LLM
  insertions (81/248) and 47 % of template insertions (116/246). → `safe_anchor()` moves the insertion point
  forward to the end of the sentence or list, at most 12 spans (iteration 15, unit-tested).

  Result: fix rate 0.990 → 0.986. That is one issue, dev/64 R10, a *replace* redline the change didn't touch.
  Other insertions in the same contract moved, and the judge re-read the contract differently, so this is
  judge noise. Collateral 0.030 → 0.028. Of the 3 misplaced redlines in the annotated sample:
  - dev/37 now follows the end of the interpretation list;
  - dev/69 now follows the end of the non-solicitation list;
  - dev/15 moved to the end of the exclusions list. This is better, but the clause still sits in that section.

**Remaining C6 risk.** The judge-quality score can't see drafting defects such as a deleted definition, a term
the contract doesn't define, or a kept carve-out (judge validation D). The deterministic checks (term mismatch,
anchor safety) cover two of these. A lawyer still has to review every redline, and the UI shows them as a diff
and never applies them silently.

## C7 Negotiation memo
`eval_memo.py`, disclosing playbook. The upstream is the chosen system (C4 v4 → C5), so the memo is evaluated as
the lawyer would receive it. 61 memos, 296 issue items, mean 228 words.
Result: `evals/results/memo/20261114T134903_dev_disclosing_party.json`.

Memo items come in two kinds, and each kind gets the check that fits it (iteration 9):
- **Cited claims** ("clause X says Y, which conflicts with our position"), mostly VIOLATIONs. The judge checks
  whether the cited span text supports the claim.
- **Absence claims** ("the contract is silent on reverse engineering"), MISSING issues with no citation. No
  span can support a claim of silence, so these are checked against **gold**: the claim is correct iff the gold
  label for that hypothesis is NotMentioned.

| Metric | memo v1 (chosen) | memo v2 (rejected) | n (v1) | Kind |
|---|---|---|---|---|
| Coverage (each C5 issue has a memo item) | **1.000** | 1.000 | 296 issues | deterministic |
| Spurious items (memo item for a rule without an issue) | 0 | 0 | 296 | deterministic |
| Citation validity (cited span ids exist) | 1.000 | 1.000 | 77 citations | deterministic |
| Citation relevance (cited span is gold evidence for that rule) | **0.935** | 0.800 | 77 / 100 | vs gold |
| Faithfulness of cited claims | **0.872** | 0.852 | 47 / 54 claims | judge (validated, see below) |
| Absence-claim accuracy | 0.867 | 0.876 | 249 / 242 claims | vs gold |
| Invented references ("clause 18" where 18 is a span id, or a number not printed in the contract) | 0.061 | 0.051 | 296 items | deterministic |
| Recommendation consistent with risk band | 1.000 | 1.000 | 61 memos | deterministic |

**memo v2** told the model not to use span ids as clause numbers and not to add details beyond the cited
text. Invented references fell from 18 to 15 items, but the model then cited more and looser spans:
citation relevance fell 0.935 → 0.800, and faithfulness 0.872 → 0.852. **Rejected**; v1 stays (iteration 12).

**Failure analysis (all failures read).**
- *Absence claims, 33 wrong out of 249.* The memo said "silent" where gold has Entailment or Contradiction.
  Every one is inherited: C4 labelled the pair NotMentioned and C7 reported it faithfully. By rule: R11 12,
  R09 8, R03 3, R04 3, R01 2, R12 2, R02/R07/R08 1 each. These match the C5 false alarms (R11 nda-10 convention,
  R09 "on request" vs "on termination"). C7 itself adds no error here.
- *Cited claims, 6 judged unsupported out of 47.* Claude Code read all 47 claims with their cited span text
  (labels in `evals/data/claude_code_annotations.json`, written before looking at the judge verdicts) and found
  5 unsupported. The two readings agree on 42/47 (κ = 0.49, see "Judge validation" part D). The real defects are:
  - wrong span: dev/54 R09 cites "Any commercial relations must be agreed separately" for a return-on-request
    claim, and dev/44 R03 cites a consent clause;
  - an added detail: dev/28 R05 "reduced to writing and marked within ten days" is not in the cited spans;
  - an overstatement: dev/10 R05 calls a definition with an alternative ("marked … *or* clearly intended to be
    disclosed in confidence") a marking requirement;
  - a self-contradiction: dev/13 R05 has the headline "No requirement to mark" over spans that do require marking.
  The other three judge rejections (dev/15, dev/16, dev/39) are claims the cited text does support. They all
  call a span id a "clause"/"section" number, which the judge appears to punish as an unsupported detail.
  That defect is real but is already counted by the invented-reference metric.
- *Invented references, 18 of 296 items.* The model sees span ids in brackets and sometimes writes
  "clause 18". This is the most visible defect for a lawyer. memo v2 did not fix it (above). The robust fix would
  be in code: give the model the contract's own clause numbers (from C2's enumerators) instead of span ids, or
  strip numeric references after generation. Not done; listed as next step.

## E2E: the whole pipeline from the original files
`evals/eval_e2e.py` (iteration 17). Result: `evals/results/e2e/20261116T111138_dev_disclosing_party.json`.

The component evals give each component gold input, so they say *which* component made an error, but not what
the user gets. Here each original PDF/HTML/TXT file goes through `pipeline.review_file`, the same code the app
calls (C1→C2→C3→C4→C5→C6→C7). No gold text, spans, labels or issues are used anywhere upstream; only the outputs
are compared with gold. "Oracle" is the same system with gold spans, on the same contracts.

Dev: 61 contracts (38 PDF, 12 TXT, 11 HTML), 0 failed.

| Stage | Metric | End to end (n) | Oracle | Target |
|---|---|---|---|---|
| C1+C2 | predicted spans per gold span | 0.874 (coarser) | 1 | — |
| C4 | macro-F1 / Contradiction-F1 | **0.792** / 0.650 (1 037 pairs) | 0.782 / 0.642 | — |
| C4 | evidence F1, overlap match (≥ 50 % of the shorter span's words) | 0.744 | 0.731 | — |
| C5 | issue R / P, disclosing | **0.864** / 0.882 (295 gold issues) | 0.864 / 0.861 | R ≥ 0.85 ✅ P ≥ 0.70 ✅ |
| C5 | issue R / P, receiving | **0.889** / 0.889 | 0.880 / 0.901 | ✅ ✅ |
| C6 | redline drafted / fix rate (judge) / term mismatch, on the raised issues | 1.000 / **0.993** (289) / 0.066 | gold upstream: 1.000 / 0.986 / 0.041 | fix ≥ 0.80 ✅ |
| C7 | coverage of raised issues / absence-claim accuracy / invented refs | 1.000 / 0.893 (243) / 0.076 | 1.000 / 0.867 / 0.061 | coverage ✅ |
| **All** | **gold issues resolved**: raised and fixed / all gold issues (disclosing) | **0.858** (253 of 295) | — | — |
| Ops | LLM calls / cost / LLM time per contract (median, 59 uncached) | 3 / $0.005 / 12.5 s | — | < $0.02, < 2 min ✅ |

**Reading.**
- **C1/C2 errors do not reach the business metric on dev.** C2's exact-match evidence-span recall end to end is
  0.843, but a merged span still contains the clause, and C4 reads the whole contract. 63 of 1 037 labels (6 %)
  differ between end to end and oracle, in both directions: end to end right 35, oracle right 24, both wrong 4.
  In all 20 of those pairs that have gold evidence, the evidence survived C1/C2 (≥ 80 % of its words in one
  span). The flips come from the LLM's sensitivity to the input form (other line breaks and span ids), not from
  lost text. The macro-F1 difference is noise: paired bootstrap over documents, 95 % CI [−0.009, +0.030].
- The overlap-match evidence F1 is slightly lenient for longer spans (a long span that contains the gold
  clause matches it). It is only there to compare end to end with oracle under the same rule; it is not
  comparable with the exact-match evidence F1 of C4 (0.626).
- **Detection, not drafting, is the bottleneck.** 42 of 295 gold issues are not resolved: 40 were never raised
  (C4 misses, the same limit as in C5), 2 were raised but the judge still sees the issue after the redline.
  This confirms the component-level conclusion from raw files: next step 1 (a second C4 model for recall) is
  the one that moves the user-level number.
- **The pipeline test found a wiring gap the evals could not.** `tests/test_pipeline_e2e.py` runs C1→C7 with a
  fake LLM that also returns invalid span ids and extra redlines. It showed that C6 dropped a "replace" redline
  that had no valid target when the rule had no evidence (a MISSING rule), so that issue silently got no fix.
  It is now turned into an insertion. This never happened in a real run (drafted rate 1.0 in every C6 run on
  dev and test), so no reported number changes.

## Judge validation
`evals/validate_judge.py`. Judge: `qwen/qwen3.8-27b` (Qwen family; the system is gpt-oss), temperature 0.
It is used three ways: NLI on revised contracts (C6 fix rate and collateral), redline quality 1–5 (C6), and
faithfulness of memo claims (C7). Results: `evals/results/judge_validation/20261114T135721_dev.json` (A),
`…T132411_dev.json` (B, C) and `…T135822_dev.json` (D).

| Part | What is tested | Cases (n) | Result | Verdict |
|---|---|---|---|---|
| A1 | NLI judge (prompt `nli_v3`) vs **gold** labels on dev | 1 020 pairs (60 docs; 1 doc lost to rate limits) | accuracy 0.881, macro-F1 0.830, **κ = 0.79 vs gold** (the system: κ = 0.71) | the fix-rate judge is more accurate than the system it checks ✅ |
| A2 | Known-good: append the playbook's preferred clause for each MISSING rule. Known-bad: append an irrelevant governing-law clause | 248 issues | known-good fixed **1.00**. Known-bad still an issue 0.86 (213/248). Of the 35 that are not, 33 were already non-issues in the judge's reading of the *original* contract (judge vs gold disagreement); only **2 (≈ 1 %) flip** because of the irrelevant change | fix detection ✅. A no-op edit almost never looks like a fix. This is why C6 also reports the fix rate on the judge-confirmed issues only |
| B | Redline-quality judge: preferred clause (good) vs opposite position or wrong topic (bad, written by Claude Code, `evals/data/judge_cases.yaml`) | 36 | mean score 4.92 / 1.00 / 1.00, pass/fail accuracy 1.00, κ = 1.0 | gross errors ✅ |
| C | Faithfulness judge: true claim with gold evidence (good), the same claim with other spans cited, or a false "silent" claim (bad) | 120 | accuracy 0.84, κ = 0.63. True claims accepted 0.70, wrong citations rejected 0.98, false silence rejected 0.85 | usable, **strict**: it rejects 30 % of true claims, so faithfulness is a lower bound |
| D-memo | Faithfulness judge vs **Claude Code** labels on all 47 real cited memo claims | 47 | agreement 0.89, κ = 0.49. Claude Code 42 supported, judge 41 | consistent in level, different on individual claims (see C7) |
| D-redline | Redline-quality judge (score ≥ 4 = acceptable) vs Claude Code on real C6 v2 redlines. Stratified: all 4 with judge score < 4, plus 26 random (seed 13) | 30 | agreement 0.70, **κ = 0.02** | **not validated on subtle errors** ❌ |

**What D-redline shows.** On the 26 random redlines the judge accepted, Claude Code found 6 not acceptable:
- 3 insertion-placement errors: after "In this Agreement:", inside a list of exclusions, and after a span that
  ends mid-sentence;
- a replacement that deletes a recital defining the parties;
- a clause using "Confidential Information" in a contract that has no such term;
- a kept "as required by law" retention exception.

The judge, for its part, flagged 3 that Claude Code accepted. One of those is a fair point (dev/435 deletes the
"Residual Information" definition). The judge reliably separates the right position from the wrong one (B)
but does not check *where* text goes or whether the defined terms exist.

Consequences for reporting:
- C6 quality (≈ 4.8 / 5) is reported as a secondary number with this caveat. Claude Code's estimate on the
  random stratum is that **20 of 26 (≈ 0.77)** of the redlines are acceptable as drafted. With n = 26 this is
  rough.
- The C6 headline metric is the fix rate. It rests on the NLI judge, which is validated against gold (A1/A2).
- Claude Code is a model annotator, not a lawyer. Its labels are a second opinion, not ground truth.

## Iteration log
| # | Component | Change | Metric delta (dev) | Decision |
|---|---|---|---|---|
| 1 | C1 | line repair: lone enumerators in HTML table cells, lowercase continuation lines | line F1 0.639 → 0.682 (HTML 0.53 → 0.75), recoverability = | keep |
| 2 | C2 | inline enumeration cut only after `;:,`/"and/or" → cut before every inline `(a)`, plus bare section numbers (rules measured on train misses) | evidence-span recall 0.782 → 0.905, span F1 0.798 → 0.831 | keep |
| 3 | C3 | BM25 / dense → exemplar kNN over train evidence | R@10 0.664 → 0.834, MRR 0.509 → 0.683 | keep exemplar |
| 4 | C4 | majority baseline → gpt-oss-120b prompt v1 | macro-F1 0.633 → 0.750, evidence F1 0.397 → 0.607 | keep LLM |
| 5 | C4 | v2: definitions + evidence rules + conventions for nda-1, nda-16 (taken from dev error analysis) | macro-F1 0.750 → 0.742, C-F1 0.592 → 0.581 | **revert parts**: the nda-16 rule came from a single dev example and is wrong on train (150 vs 69) |
| 6 | C4 | v3: v2 conventions re-checked against train counts (nda-1, nda-16, nda-20) | macro-F1 → 0.775, C-F1 → 0.631, evidence F1 → 0.647 | keep. Lesson: conventions are checked on train, never adopted from dev |
| 7 | C4 | ablations: 20b, retrieved context | see table above | keep 120b + full context |
| 8 | evals | C4 effort-high run crashed on one empty JSON response. C6 and judge-A runs crashed on Qwen rate limits (4 evals in parallel) | — | evals now record and count failed docs (`n_failed_docs`). Backoff honours `retry-after`, 14 attempts |
| 9 | C7 eval | **metric fix**: 246 of 291 memo items are absence claims ("the contract is silent on X") with no citations. Faithfulness to cited text can't check those, and the judge marked them unsupported at random (119 vs 127) | faithfulness 0.575 (invalid) → cited-claim faithfulness 0.911 (n = 45, judge) + absence-claim accuracy 0.878 (n = 246, vs gold) | keep the new definition. Old number kept here for transparency |
| 10 | C4 | v4: one convention (nda-17 copying ≠ retention), checked on train (77/117 and 101/170 NotMentioned) | macro-F1 +0.007 [−0.011, +0.026], evidence F1 −0.020 [−0.043, 0.000]. C5 issue recall: disclosing 0.861 → 0.864, receiving 0.839 → 0.880 | **adopt v4** (meets the business recall target on both playbooks). Re-ran C5 and C7 |
| 11 | C2 | don't split before a numeral that restates a number word ("thirty (30) days"). Train: no boundary in 576/583 | evidence-span recall 0.905 → 0.943 (oracle), 0.811 → 0.843 (end to end) | keep. Re-ran C6 (its judge sees C2 output) |
| 12 | C7 | memo_v2: don't use span ids as clause numbers, don't add details beyond the cited text. New deterministic metric: invented references | invented refs 0.061 → 0.051, citation relevance 0.935 → 0.800, faithfulness 0.872 → 0.852 | **reject**, keep memo v1. The fix belongs in code (real clause numbers), listed as next step |
| 13 | C6 | error analysis: all 10 unfixed v1 redlines are R10, 9 of them drafting the playbook's *fallback*. The template looked as good as the LLM, so the LLM's supposed advantage was measured with a new metric (term mismatch) → `redline_v2` | fix 0.966 → 0.990, term mismatch 0.163 → 0.041 (template 0.441), collateral 0.028 → 0.030 | **adopt v2** |
| 14 | C4 | judge validation A showed that the judge model (qwen3.8-27b) agrees with gold better than the system. Measured as a C4 ablation | macro-F1 +0.048 [+0.018, +0.077], evidence F1 +0.104 [+0.079, +0.130]. C5 disclosing recall 0.864 → 0.831 (below target), precision 0.861 → 0.942 | **not adopted**: fails the recall target, and it is the independent judge. The union of both models (recall 0.902 / 0.922, offline) is next step 1 |
| 15 | C6 | judge validation D: the redline-quality judge doesn't agree with Claude Code on real redlines (κ = 0.02). It misses insertion placement. A deterministic check showed 33 % (LLM) / 47 % (template) of insertion anchors are list lead-ins, list items or mid-sentence → `safe_anchor()` | unsafe insertion anchors LLM 84/254 → 4/254, template 119/252 → 8/252. Fix rate 0.990 → 0.986 (one replace redline, judge noise), collateral 0.030 → 0.028. 2 of the 3 annotated misplacements now correct | **adopt** (deterministic, unit-tested) |
| 16 | all | dev decisions frozen (C4 `nli_v4`, C6 `redline_v2` + `safe_anchor`, C7 `memo` v1). `scripts/final_test.sh` run once on test | see "Final test" | no changes after this point |
| 17 | E2E | new eval of the whole pipeline from the original files (`eval_e2e.py`) and pipeline tests with a fake LLM (`tests/test_pipeline_e2e.py`). The test found that C6 dropped a replace redline without a valid target for a MISSING rule; it is now inserted | C4 macro-F1 0.792 end to end vs 0.782 oracle (CI [−0.009, +0.030]); C5 disclosing R 0.864 = oracle; gold issues resolved 0.858. The C6 fix changes no number (drafted rate 1.0 everywhere) | keep. No system change from this eval; run once on test ("Final test") |
| 18 | C4/C5 | DeBERTa-v3 span-NLI baselines from the Colab run (`notebooks/finetune_colab.ipynb`, run through the Colab CLI on a T4): zero-shot MNLI model and the same model fine-tuned on train span pairs. Span scores → document label by two thresholds tuned on dev, frozen for test | fine-tuned: macro-F1 0.786 dev / 0.784 test (LLM 0.782 / 0.793), evidence F1 0.687 / 0.702 (LLM 0.626 / 0.643); but C5 disclosing issue R 0.749 dev / 0.755 test (LLM 0.864 / 0.881), below the 0.85 target. Zero-shot: macro-F1 0.18 / 0.20 | keep the LLM: chosen on the business metric (C5 recall), not on F1. The fine-tuned model is the stronger evidence locator (+0.06 evidence F1), a candidate for C3. Zero-shot collapses because an MNLI model scores many unrelated clauses P(contradiction) ≥ 0.98, and the max over ~100 spans per contract then says Contradiction almost everywhere (dev: 774 of 942 non-C pairs). Its dev numbers are tuned on dev, so they are optimistic; the test numbers are the fair comparison |

## Final test (run once, 2026-11-14, `scripts/final_test.sh`)
Test split: 123 NDAs, 2 091 pairs. Nothing was tuned on test. Result files are `evals/results/*/20261114T14*_test*.json`.

| # | Metric | Baseline (test) | System, test (n) | System, dev | Target |
|---|---|---|---|---|---|
| C1 | evidence recoverability / line F1 | naive 0.969 / 0.164 | **0.977** / 0.660 (1 719 spans, 123 files) | 0.984 / 0.682 | — |
| C2 | evidence-span recall, oracle / end to end | lines 0.291 / 0.184 | **0.931** / 0.782 (1 761 spans) | 0.943 / 0.843 | — |
| C3 | R@10 / MRR | BM25 0.664 / 0.508 | **0.853** / 0.733 (1 188 pairs) | 0.834 / 0.683 | — |
| C4 | macro-F1 / C-F1 / evidence F1 | majority 0.617 / 0.506 / 0.418; fine-tuned DeBERTa 0.784 / 0.679 / 0.702; zero-shot DeBERTa 0.199 / 0.212 / 0.042 | **0.793 / 0.643 / 0.643** (2 091 pairs, 0 failed docs) | 0.782 / 0.642 / 0.626 | evidence F1 ≥ 0.60 ✅ |
| C5 | issue P / R, disclosing | majority 0.748 / 0.586; fine-tuned DeBERTa 0.922 / **0.755** | **0.885 / 0.881** (628 gold issues) | 0.861 / 0.864 | R ≥ 0.85 ✅, P ≥ 0.70 ✅ |
| C5 | issue P / R, receiving | majority 0.780 / 0.614; fine-tuned DeBERTa 0.900 / 0.842 | **0.909 / 0.915** (469 gold issues) | 0.901 / 0.880 | ✅ ✅ |
| C6 | fix rate / collateral / term mismatch (gold upstream) | template 0.994 / 0.037 / 0.488 | **0.995 / 0.032 / 0.068** (621 issues, 122 contracts; 1 contract failed on judge rate limits) | 0.986 / 0.028 / 0.041 | ✅ ✅ |
| C7 | coverage / citation relevance / faithfulness / absence accuracy / invented refs | — | **1.000** (625) / 0.842 (177) / 0.871 (101) / 0.903 (524) / 0.078 | 1.000 / 0.935 / 0.872 / 0.867 / 0.061 | coverage ✅ |
| E2E | from the original files, no gold input (`eval_e2e.py`, run 2026-11-16): C4 macro-F1 / C5 disclosing R / P / C6 fix rate on raised issues / **gold issues resolved** | — | 0.787 / 0.879 / 0.868 / 0.994 / **0.874** (628 gold issues, 123 contracts: 76 PDF, 24 TXT, 23 HTML; 0 failed) | 0.792 / 0.864 / 0.882 / 0.993 / 0.858 | R ≥ 0.85 ✅ |

**Reading.**
- Test confirms dev. Every business target is met, and no component drops by more than about 6 points.
- The largest drops are C2 end to end (−0.06) and C7 citation relevance (−0.09). For C2 the cause is upstream:
  10 PDFs whose C1 line F1 is < 0.3 account for 136 of the 383 missed evidence spans.
- The C7 drop was not analysed further, to keep the test split untouched.
- C6 has 1 failed contract (n_failed_docs = 1), which is reported rather than re-run.
- End to end (whole pipeline from the original file) the business numbers hold on test: C5 disclosing recall
  0.879 vs 0.881 oracle; C4 macro-F1 0.787 vs 0.793 oracle, a noise-level difference (paired bootstrap over
  contracts, 95 % CI [−0.019, +0.006]). 160 of 2 091 labels differ from the oracle run (oracle right 86, end to
  end right 64). 549 of 628 gold issues are raised and fixed; of the other 79, 76 are never raised and 3 are
  raised but not fixed. Detection (C4) remains the bottleneck, not drafting.
- Baselines: the fine-tuned DeBERTa matches the LLM on macro-F1 (0.784 vs 0.793) and beats it on evidence F1
  (0.702 vs 0.643), but misses the business target: disclosing issue recall 0.755 vs 0.881 (iteration 18).

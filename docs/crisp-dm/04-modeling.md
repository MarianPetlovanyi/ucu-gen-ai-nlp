# Phase 4: Modeling
Status: closed 2026-11-14 (the C4 prompt went through 3 iterations, see the iteration log in phase 5)

Data flow and LLM vs tool calls: `docs/diagrams/data_flow.md`. Every component is a pure function with
pydantic input and output (`src/nda_review/schemas.py`), and `pipeline.py` wires them together.

| # | Component | Purpose | Input → Output | Technique (chosen) | Baselines / alternatives evaluated | Call type |
|---|---|---|---|---|---|---|
| C1 | Ingestion `ingest.py` | Read any NDA file | file path → `IngestResult` (text, one paragraph per line, warnings) | PDF: PyMuPDF layout **blocks**, repeated header/footer removal, page-number filter, de-hyphenation, list-item split, page-break merge. HTML: stdlib parser, block tags → newlines, table cells joined. TXT: blank-line paragraphs, wrap undo. Then a format-independent line repair | `naive`: raw extraction with the original hard line breaks | tool |
| C2 | Segmentation `segment.py` | Make clauses addressable (the evidence unit) | text → `Contract` (numbered spans with offsets) | Rules: every newline; sentence ends with a legal-abbreviation list; before inline `(a)/(ii)/(3)`; after bare section numbers (`2.1`) | `lines`: one span per line | tool |
| C3 | Evidence retrieval `retrieve.py` | Rank the clauses relevant to a rule (UI hints, insertion anchors for C6, context for small models) | `Contract` × hypotheses → `RetrievalResult` per hypothesis | **Exemplar kNN**: bge-small embedding of each span, scored by its mean top-3 cosine similarity to *train* gold evidence spans of that hypothesis | BM25 (hypothesis as query), dense query–span similarity, hybrid RRF (BM25 + exemplar) | local model |
| C4 | NLI + evidence `nli.py` | Decide what the contract says on each of the 17 topics and cite it | `Contract` × 17 hypotheses → `NLIResult` (label + evidence span ids + rationale) | **gpt-oss-120b**, one call per contract with all hypotheses, reasoning effort *medium*, JSON → pydantic, invalid span ids dropped. Prompt `nli_v4` (v3 plus one nda-17 convention, iteration 10): definitions, annotation conventions checked on train, evidence-citation rules | train-majority label per hypothesis; zero-shot DeBERTa-v3 MNLI (span level, thresholds); DeBERTa fine-tuned on train span pairs (Colab); ablations: gpt-oss-20b, retrieved-only context (top-10 per hypothesis), reasoning effort *high*, prompts v1/v2/v3. Variants compared with a paired bootstrap over documents (`evals/compare_runs.py`), chosen on the C5 business metric | LLM |
| C5 | Playbook compliance `playbook.py` | Apply company policy | `NLIResult` × `Playbook` → `ComplianceReport` (status per rule, risk 0–100, recommendation) | Deterministic. The stance maps label → status (`must_entail`: C→VIOLATION, N→MISSING; `must_not_entail`: E→VIOLATION; `review_if_entailed`: E→REVIEW). Risk = Σ severity weight × status weight / maximum. Recommendation thresholds come from the playbook YAML | n/a (rule-based by design: policy must be auditable) | tool |
| C6 | Redline drafter `redline.py` | Fix the contract | report issues + `Contract` + playbook → `RedlineSet` (replace span ids or insert after span id + new text) → revised text. Insertion points are moved to the end of the sentence or list by the deterministic `safe_anchor()` (iteration 15) | **gpt-oss-120b**, one call per contract. Gets the client position, rationale, preferred clause and fallback, the conflicting span ids (VIOLATION) or C3 anchor candidates (MISSING). Prompt `redline_v2` (iteration 13): draft the preferred position (never the fallback), use the contract's own defined terms, minimal change, no side effects | `template`: paste the playbook's preferred clause verbatim (no LLM) | LLM |
| C7 | Negotiation memo `memo.py` | Explain to the business user and counsel | report + `Contract` + playbook → `Memo` (summary, one item per issue with ask, fallback, span citations) | **gpt-oss-120b**, one call per contract. The recommendation is decided by C5 policy, not the LLM. Citations are span ids and are validated | none (no meaningful non-LLM memo); checked deterministically for coverage and citations, plus a judge for faithfulness. Prompt `memo` (v1). `memo_v2` was tried and rejected (iteration 12) | LLM |

## Design decisions and why
- **One LLM call per contract for C4, not one per rule.** Contracts fit in context (median ≈2.5k tokens), so a
  single call sees the cross-references between clauses ("except as provided in Section 5") and costs about
  $0.002 per contract. 17 separate calls would cost 17× more for the same context.
- **Evidence as span ids, not quotes.** Hallucinated evidence is impossible by construction. Invalid ids are
  dropped and counted, and evidence quality is measured against gold.
- **Business logic as configuration.** Stance, severity, weights and thresholds live in `playbooks/*.yaml`. The
  same contract gets opposite verdicts under the two perspectives, and no code changes.
- **The LLM explains, the policy decides.** The sign/negotiate/reject recommendation is computed in C5 from the
  playbook thresholds. C7 only writes the reasons, which keeps the decision auditable and deterministic.
- **Independent judge.** C6 and C7 are graded by `qwen/qwen3.8-27b`, a different model family from the system
  model, which avoids self-preference bias. The judge is validated before its numbers are reported.
- **Retrieval is not needed to fit the context**, because every contract fits whole. C3 is still a component
  because it powers the UI hints and the C6 insertion anchors, and its value as a context filter is measured in
  the C4 "retrieved context" ablation.
- **Local compute.** A GTX 1050 with 2 GB can't host a useful LLM (measured: qwen3:1.7b at 31 tok/s,
  misrouted a simple query). Local compute is used only for bge-small. DeBERTa fine-tuning runs on Colab (T4).

## Parameters
| Setting | Value |
|---|---|
| System model | `openai/gpt-oss-120b`, temperature 0, seed 13, reasoning effort medium, max 16k completion tokens |
| Judge model | `qwen/qwen3.8-27b`, temperature 0, JSON mode, reasoning off |
| Embeddings | `BAAI/bge-small-en-v1.5`, max 256 tokens, CPU |
| Fine-tuned baseline | `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, 2 epochs, lr 2e-5, batch 32, max length 256, 3 negatives per pair, fp16 on a T4 |
| Prompts (versioned, hashed in every result file) | `src/nda_review/prompts/{nli,nli_v2,nli_v3,nli_v4,redline,redline_v2,memo,memo_v2,judge_redline,judge_faithfulness}.md`. In use: `nli_v4`, `redline_v2`, `memo`. The NLI judge (C6 fix check) uses `nli_v3`, frozen so the C6 numbers stay comparable |

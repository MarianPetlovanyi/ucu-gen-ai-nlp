---
name: add-component
description: Add or substantially change a pipeline component (C1–C7) of the NDA reviewer with its eval, tests and docs. Use whenever creating a new module in src/nda_review/ or changing a component's inputs/outputs.
---

# Add a component (definition of done)

A component is **not done** until every box below is ticked. Work through them in order.

1. **Contract first.** Add the pydantic input and output models to `src/nda_review/schemas.py`. Write one sentence on
   the component's purpose, its input, its output, and whether it calls an LLM (and which model) or a tool.
2. **Implementation.** Add `src/nda_review/<module>.py` with one public function. LLM calls go only through
   `nda_review.llm`. Prompts go in `src/nda_review/prompts/<component>.md`.
3. **Baseline.** Every model-based component needs a trivial or classic baseline (majority class, BM25,
   rule-based, zero-shot small model) so the score has a reference point.
4. **Eval.** Add `evals/eval_<component>.py` with an `--split {dev,test}` flag and an optional `--limit N`.
   - Choose the metric from the component's job. Write down why it fits and what a high or low score means.
   - Save the result JSON to `evals/results/<component>/<timestamp>_<split>.json` with config, model ids, prompt
     hash, n, the metrics, and **per-example records** (needed for error analysis).
   - Print a short summary table.
5. **Tests.** Deterministic logic gets `tests/test_<module>.py`. Don't unit-test LLM text.
6. **Run it.** Run on dev, then run the `error-analysis` skill on the result.
7. **Docs.** Update the component's row in `docs/crisp-dm/04-modeling.md` and `05-evaluation.md`, and update the
   diagram in `docs/diagrams/` if the data flow changed.
8. **Gate.** `uv run ruff check . && uv run pytest -q` passes.

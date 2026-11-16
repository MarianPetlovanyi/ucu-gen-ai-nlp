# NDA Playbook Reviewer: instructions for the coding agent

## What we are building
A company reviews incoming NDAs against its own **playbook**: a set of rules such as "the counter-party must not
reverse-engineer our materials". For each rule the system decides whether the contract entails it, contradicts it,
or doesn't mention it, cites the evidence spans, scores the risk, drafts redlines that fix the violations, and writes
a negotiation memo. Data: ContractNLI (607 NDAs, 17 fixed hypotheses with gold labels and evidence spans).
This is a university assignment graded on: system understanding, a working prototype, **an evaluation of every
component**, and how well the coding agent is steered (this file and `.claude/skills/`).
Deadline: Monday 2026-11-16. Prefer a finished and evaluated component over a half-finished extra one.

## Process: CRISP-DM is mandatory
Work in CRISP-DM phases. Each phase has one document in `docs/crisp-dm/`:
`01-business-understanding.md`, `02-data-understanding.md`, `03-data-preparation.md`, `04-modeling.md`,
`05-evaluation.md`, `06-deployment.md`.
- Do not start a phase until the document for the previous phase exists and is current. Use the
  `crisp-dm-checkpoint` skill to close a phase.
- CRISP-DM is a loop. After every eval run, do error analysis (`error-analysis` skill), then decide whether to go
  back to data prep or modeling. Log each iteration (change → metric delta → decision) in the iteration log in
  `05-evaluation.md`.
- Business rules live in `playbooks/*.yaml`, never hard-coded in Python.

## Architecture: one component = module + eval + doc
| # | Component | Module | Eval |
|---|-----------|--------|------|
| C1 | Ingestion (PDF/HTML/TXT → text) | `ingest.py` | text similarity vs gold text on raw files |
| C2 | Segmentation (text → spans) | `segment.py` | span-boundary P/R/F1 vs gold spans |
| C3 | Evidence retrieval (rule → ranked spans) | `retrieve.py` | Recall@k, MRR vs gold evidence |
| C4 | NLI + evidence (contract × rules → label + span ids) | `nli.py` | macro-F1, Contradiction-F1, evidence P/R/F1; baselines |
| C5 | Playbook compliance + risk (labels → rule status) | `playbook.py` | violation P/R/F1 vs gold-derived status |
| C6 | Redline drafter (violation → replacement text) | `redline.py` | fix rate (re-checked by judge NLI), collateral change, edit ratio, judge score |
| C7 | Negotiation memo | `memo.py` | coverage of violations, citation validity, judge faithfulness |
| E2E | Whole pipeline from the original file | `pipeline.py` | `eval_e2e.py`: C4/C5 vs gold with no gold input, gold issues resolved, cost; `tests/test_pipeline_e2e.py` |

Rules:
- Each component exposes a pure function with **pydantic** input and output models (`src/nda_review/schemas.py`).
- A component counts as done only when `evals/eval_<component>.py` exists, has run on the **dev** split, and its
  numbers are in `05-evaluation.md` together with an explanation of the failures. Use the `add-component` skill.
- `pipeline.py` wires the components together. `app/streamlit_app.py` only calls `pipeline.py`.
- Component evals isolate one component (gold upstream). `eval_e2e.py` measures the chain as a user runs it.
  Re-run it after any component change; `tests/test_pipeline_e2e.py` must pass (wiring, with a fake LLM).

## Data rules (eval hygiene)
- Splits: `train` is for few-shot examples, priors and fine-tuning. `dev` is for every iteration.
  `test` is only for the final reported numbers, run explicitly with `--split test`. Never tune prompts on test
  examples or copy them into prompts.
- `data/raw/` is read-only, downloaded data. Never edit it. Derived files go to `data/processed/`.
- Report n (sample size) next to every metric. With small n, say so and don't over-interpret.

## LLM rules
- All model calls go through `nda_review.llm` (it handles the disk cache, JSONL trace logging, retries and
  rate-limit backoff). Never call the Groq SDK directly from components.
- Model ids live in `config.py`. System model: `openai/gpt-oss-120b`. **Judge: `qwen/qwen3.8-27b`.** The judge must
  come from a different model family than the system it grades. Don't use gpt-oss to judge gpt-oss.
- gpt-oss models are reasoning models: hidden reasoning tokens count against `max_tokens`. Never set
  `max_tokens` below 2000. Set `reasoning_effort` explicitly.
- Structured output: request JSON, validate it with pydantic, and on a validation error retry once with the error
  message. Never parse model text with regexes.
- Prompts live in `src/nda_review/prompts/*.md`, not inline in Python, so they can be diffed between iterations.
- Every LLM judge metric needs a judge-validation result (agreement with known-good and known-bad cases) before
  its numbers are reported.

## Code quality
- Python 3.12, managed with `uv`. Type hints on all public functions. Small, single-purpose functions.
- `uv run ruff check . && uv run ruff format .` must pass. Deterministic logic (segmentation, compliance, metrics)
  gets `pytest` tests in `tests/`.
- No notebooks for core logic. The exception is `notebooks/finetune_colab.ipynb`, which is self-contained.
- Use `logging`, not `print`, in library code. Eval scripts may print summary tables.
- Make results reproducible: fixed seeds, and every eval result JSON stores the config, model ids, prompt hash,
  split, n and timestamp.

## Security
- Never read, print or log `.env` or API keys. The key is loaded via python-dotenv only.
- Never commit `data/raw/`, `models/`, `.env` or the LLM cache.

## Commands
```bash
uv sync                                                    # install
uv run ruff check . && uv run pytest -q                    # quality gate
uv run python -m evals.eval_<component> --split dev        # eval a component
uv run python -m evals.eval_<component> --split test       # final numbers only
uv run python -m evals.eval_e2e --split dev                # whole pipeline from the original files
uv run streamlit run app/streamlit_app.py                  # demo UI
```

## How to work in this repo
- Plan before coding. State which CRISP-DM phase and which component a change belongs to.
- Keep diffs small. After any change to a component, re-run its eval and every downstream eval that depends on it.
- Never change a metric definition or eval set to make numbers look better. If an eval is wrong, fix it, explain
  why in the iteration log, and re-run the earlier baselines.
- Report failures honestly in the docs. A low score with a clear explanation is worth more than an unexplained
  high one.

## Lessons learned in this project (keep following them)
- Annotation conventions written into a prompt must be verified on **train** label counts, never taken from
  dev examples (prompt v2 overfit to one dev example; v3 and v4 rules all cite train counts).
- Differences between LLM variants are often noise at n = 61 documents. Use `evals.compare_runs` (paired
  bootstrap) and decide on the business metric (C5), not on a +0.007 macro-F1.
- When a judge metric looks bad, check that the metric fits the output first (memo absence claims cannot be
  "supported by citations"; iteration 9).
- The LLM is not automatically better than the simple baseline (C6 template vs LLM). Measure the dimension
  where the LLM is supposed to add value (e.g. the contract's own defined terms) instead of assuming it.
- Synthetic known-good/known-bad cases are not enough to validate a judge. The redline judge scored κ = 1.0 on
  synthetic cases but κ = 0.02 against a second annotator on real outputs (it can't see placement or deleted
  definitions). Validate every judge on **real system outputs** too, and turn its blind spots into
  deterministic checks (iteration 15).
- A better model on F1 is not automatically the better system: Qwen beat gpt-oss on macro-F1 but missed the
  recall target (iteration 14). Always re-run C5 before adopting a C4 change.

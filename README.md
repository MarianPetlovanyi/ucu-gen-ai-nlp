# NDA Playbook Reviewer

A first-pass NDA review against a company **playbook**. For each of 17 negotiating positions the system decides
whether the contract **entails** it, **contradicts** it or **doesn't mention** it, and cites the exact clauses.
It then turns the labels into a rule status and a risk score, drafts **redlines** that fix the violations, and
writes a **negotiation memo**. Data: [ContractNLI](https://stanfordnlp.github.io/contract-nli/) (607 NDAs,
17 hypotheses, gold labels and evidence spans, CC BY 4.0).

UCU GenAI, Assignment 1. The project follows CRISP-DM: see `docs/crisp-dm/01…06`. The data flow is in
`docs/diagrams/data_flow.md`.

## Components
| # | Component | Module | Type | Eval |
|---|---|---|---|---|
| C1 | Ingestion (PDF/HTML/TXT → text) | `ingest.py` | tool | word F1, line F1, evidence recoverability vs gold text |
| C2 | Segmentation (text → spans) | `segment.py` | tool | span/boundary F1, evidence-span recall |
| C3 | Evidence retrieval (rule → spans) | `retrieve.py` | local embeddings | Recall@k, MRR vs gold evidence |
| C4 | NLI + evidence | `nli.py` | LLM `gpt-oss-120b` | macro-F1, Contradiction-F1, evidence P/R/F1 vs 3 baselines |
| C5 | Playbook compliance + risk | `playbook.py` | deterministic | issue P/R/F1, risk Spearman ρ vs gold-derived status |
| C6 | Redline drafter | `redline.py` | LLM `gpt-oss-120b` | fix rate (judge NLI), collateral changes, edit ratio, judge quality |
| C7 | Negotiation memo | `memo.py` | LLM `gpt-oss-120b` | coverage, citation validity/relevance, judge faithfulness |

The judge is `qwen/qwen3.8-27b`, from a different model family than the system. It is validated in
`evals/validate_judge.py` before any judge-based number is reported.

## Setup
Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                    # installs deps (torch cu124 wheel; CPU works too)
uv run python scripts/download_data.py     # ContractNLI → data/raw/contract-nli/
echo "GROQ_API_KEY=..." > .env             # Groq key; loaded with python-dotenv only
```

The LLM disk cache (`.cache/llm/`) makes re-runs free and deterministic. Without a key, cached evals still
replay.

## Run
```bash
uv run streamlit run app/streamlit_app.py                 # demo UI
uv run ruff check . && uv run pytest -q                    # quality gate
```

Evaluations (dev = iteration split, test = final numbers only):
```bash
uv run python -m evals.eval_ingest   --split dev
uv run python -m evals.eval_segment  --split dev
uv run python -m evals.eval_retrieve --split dev
uv run python -m evals.eval_nli      --split dev --method majority
uv run python -m evals.eval_nli      --split dev --method llm            # prompt nli_v4 (default)
uv run python -m evals.eval_nli      --split dev --method zeroshot    # needs data/processed/finetuned/span_probs.json
uv run python -m evals.eval_nli      --split dev --method finetuned   # (produced by notebooks/finetune_colab.ipynb)
uv run python -m evals.eval_playbook --split dev
uv run python -m evals.eval_redline  --split dev
uv run python -m evals.eval_memo     --split dev
uv run python -m evals.validate_judge --split dev
uv run python -m evals.eval_e2e      --split dev    # whole pipeline C1→C7 from the original files, no gold input
uv run python -m evals.compare_runs <tag_a> <tag_b>          # paired bootstrap between two C4 runs
./scripts/final_test.sh                                     # final test-split numbers (run once)
```
Each run writes `evals/results/<component>/<timestamp>_<split>[_tag].json`. The file holds the config, model ids,
prompt hash, n, the metrics and per-example records.

Fine-tuned baseline: open `notebooks/finetune_colab.ipynb` in Colab (T4 GPU) and choose Run all. Put the
downloaded `span_probs.json` into `data/processed/finetuned/`.

## Web app (Next.js)
A second UI with a contract preview (evidence highlights, redlines as track changes with accept/reject, download
of the revised text) and an evaluation dashboard. `app/api.py` is a thin FastAPI layer over `pipeline.py`; the
Next.js app in `web/` proxies `/api/*` to it.
```bash
uv run uvicorn app.api:app --port 8000                                      # terminal 1: API
cd web && npm install && npm run build && npm run start                     # terminal 2: UI on http://localhost:3000
```
- `npm run dev` instead of `build && start` gives hot reload.
- If port 8000 or 3000 is taken, use other ports. The API address is fixed at build time:
  `uv run uvicorn app.api:app --port 8010`, then
  `NDA_API_URL=http://127.0.0.1:8010 npm run build && npm run start -- -p 3010`.
- Demo deep link: `http://localhost:3000/?example=dev/3&playbook=disclosing_party&tab=preview` runs that review
  as soon as the page loads.

## Deployment (DigitalOcean)
Live demo: **https://ucu.nlp.justsolution.co** (Caddy → Next.js → FastAPI on one droplet, Docker Compose).
```bash
export TF_VAR_do_token=...                                           # DO API token, never committed
terraform -chdir=deploy/terraform init && terraform -chdir=deploy/terraform apply   # droplet, reserved IP, firewall
deploy/set_login.sh ucu                                              # demo login (basic auth); password → deploy/.credentials
deploy/deploy.sh                                                     # rsync code + data + LLM cache + .env, build, start
```
The demo sits behind a login (HTTP basic auth in Caddy, covering the UI and `/api/*`), so strangers can't spend
the Groq key. Change it with `deploy/set_login.sh <user>` (or `NDA_PASSWORD=... deploy/set_login.sh <user>`) and
re-run `deploy/deploy.sh`.
DNS is managed at the registrar: add an `A` record for the host to `terraform output ip`. Details in
`docs/crisp-dm/06-deployment.md`.

## Repository layout
```
src/nda_review/   components C1–C7, schemas (pydantic), llm gateway (cache, traces, retries), pipeline
  prompts/        versioned prompts (nli…nli_v4, redline, redline_v2, memo, memo_v2, judge_*)
playbooks/        business rules as YAML (disclosing_party, receiving_party)
evals/            one eval per component + judge validation; results/ holds every run
app/              Streamlit UI and the FastAPI layer for web/ (both call only pipeline.py)
web/              Next.js UI (preview, redlines, evaluation dashboard)
deploy/           Terraform (DigitalOcean) + Docker Compose + deploy.sh for the public demo
docs/crisp-dm/    phase documents 01–06 (05 has all numbers + iteration log)
docs/diagrams/    data-flow diagram; UML (uml.drawio: use case, component, sequence, class, activity) + PNGs
.claude/skills/   agent skills: add-component, run-eval, error-analysis, crisp-dm-checkpoint
CLAUDE.md         instructions for the coding agent
notebooks/        finetune_colab.ipynb (self-contained, DeBERTa baseline)
```

## Disclaimer
The output is a draft for a lawyer, not legal advice. Lumen Robotics is a fictional company. The judge-validation
"known-bad" clauses and the second-annotator labels were written by Claude Code (a model), not by a lawyer.

#!/usr/bin/env bash
# Final test-split numbers. Run ONCE, after every dev decision is frozen (CLAUDE.md eval hygiene).
# Order matters: eval_playbook / eval_memo read the C4 test results.
set -euo pipefail
cd "$(dirname "$0")/.."

SYS_TAG=llm-gpt-oss-120b-nli_v4-medium-full

uv run python -m evals.eval_ingest   --split test
uv run python -m evals.eval_segment  --split test
uv run python -m evals.eval_retrieve --split test
uv run python -m evals.eval_nli      --split test --method majority
uv run python -m evals.eval_nli      --split test --method llm --workers 4
uv run python -m evals.eval_playbook --split test --tags majority "$SYS_TAG"
uv run python -m evals.eval_memo     --split test --workers 3
uv run python -m evals.eval_redline  --split test --workers 3
uv run python -m evals.eval_e2e      --split test --workers 3   # added 2026-11-16 (iteration 17)

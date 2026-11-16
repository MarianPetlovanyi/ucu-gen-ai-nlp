"""Central configuration: paths, model ids, seeds. Components import from here, never hard-code."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "contract-nli" / "contract-nli"
RAW_FILES_DIR = RAW_DIR / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CACHE_DIR = ROOT / ".cache" / "llm"
TRACE_DIR = ROOT / ".cache" / "traces"
RESULTS_DIR = ROOT / "evals" / "results"
PLAYBOOK_DIR = ROOT / "playbooks"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
MODELS_DIR = ROOT / "models"

SEED = 13

# --- LLMs (Groq) ---------------------------------------------------------------------------
SYSTEM_MODEL = "openai/gpt-oss-120b"  # runs C4 (NLI), C6 (redlines), C7 (memo)
SYSTEM_MODEL_SMALL = "openai/gpt-oss-20b"  # ablation only
JUDGE_MODEL = "qwen/qwen3.8-27b"  # independent judge: different model family than the system
SYSTEM_REASONING_EFFORT = "medium"
MIN_MAX_TOKENS = 2000  # gpt-oss spends hidden reasoning tokens from this budget

# USD per million tokens (input, output). Used only for cost reporting.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.29, 0.59),
    "qwen/qwen3.6-27b": (0.29, 0.59),
}

# --- Local models ---------------------------------------------------------------------------
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
ZS_NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"

# --- Data -----------------------------------------------------------------------------------
# Exact duplicate of test/537 (see docs/crisp-dm/02-data-understanding.md). Excluded from every
# train-derived artefact (few-shot examples, retrieval exemplars, fine-tuning data).
EXCLUDED_TRAIN_IDS = {"538"}

LABELS = ("Entailment", "Contradiction", "NotMentioned")

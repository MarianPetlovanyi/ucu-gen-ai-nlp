"""Shared helpers for the component evals: argument parsing, result saving, small text utils."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from nda_review.config import RESULTS_DIR, SYSTEM_MODEL, SYSTEM_REASONING_EFFORT
from nda_review.nli import DEFAULT_PROMPT


def nli_tag(model: str, prompt: str, effort: str, context: str = "full") -> str:
    """File tag of a C4 LLM run (see eval_nli)."""
    return f"llm-{model.split('/')[-1]}-{prompt}-{effort}-{context}"


# The C4 configuration the deployed system uses; downstream evals (C5–C7) read its predictions.
SYSTEM_NLI_TAG = nli_tag(SYSTEM_MODEL, DEFAULT_PROMPT, SYSTEM_REASONING_EFFORT)


def parse_args(description: str, extra: Sequence[tuple[str, dict]] = ()) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--split", choices=["dev", "test", "train"], default="dev")
    p.add_argument("--limit", type=int, default=None, help="smoke tests only; never report")
    for flag, kw in extra:
        p.add_argument(flag, **kw)
    return p.parse_args()


def _git_rev() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "no-commit"


def save_result(
    component: str,
    split: str,
    *,
    config: dict,
    metrics: dict,
    records: list[dict],
    n: int,
    tag: str = "",
) -> Path:
    """Write evals/results/<component>/<timestamp>_<split>[_tag].json and return the path."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = RESULTS_DIR / component / f"{ts}_{split}{'_' + tag if tag else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "component": component,
        "split": split,
        "n": n,
        "timestamp": ts,
        "git": _git_rev(),
        "config": config,
        "metrics": metrics,
        "records": records,
    }
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def latest_result(component: str, split: str = "dev", tag: str | None = None) -> dict | None:
    files = sorted((RESULTS_DIR / component).glob(f"*_{split}*.json"))
    if tag is not None:
        files = [f for f in files if f.stem.endswith(tag)]
    return json.loads(files[-1].read_text()) if files else None


def print_table(rows: list[dict], cols: list[str] | None = None) -> None:
    if not rows:
        return
    cols = cols or list(rows[0])
    fmt = [lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(fmt[0](r.get(c, "")) for c in cols) + " |")


def norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def prf(tp: float, n_pred: float, n_gold: float) -> tuple[float, float, float]:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f

"""The only gateway to LLMs. Disk cache, JSONL traces, retries with backoff, pydantic validation.

Usage:
    out = chat_json(SYSTEM_MODEL, system=..., user=..., schema=MyModel, component="nli")

Cache key = sha256(model, messages, params), so any prompt change invalidates the cache.
Each call (cached or not) appends one trace line to .cache/traces/<date>.jsonl.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from nda_review.config import (
    CACHE_DIR,
    MIN_MAX_TOKENS,
    PRICES_PER_MTOK,
    PROMPT_DIR,
    ROOT,
    SEED,
    TRACE_DIR,
)

log = logging.getLogger(__name__)

_client = None
# Collects the traces of the current pipeline run, so the UI can show them.
_run_traces: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "run_traces", default=None
)


class LLMError(RuntimeError):
    pass


def _get_client():
    global _client
    if _client is None:
        from groq import Groq

        load_dotenv(ROOT / ".env")  # never log or print the key
        _client = Groq(max_retries=0, timeout=180)
    return _client


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def prompt_hash(*texts: str) -> str:
    return hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]


def start_trace_collection() -> list[dict]:
    traces: list[dict] = []
    _run_traces.set(traces)
    return traces


def _cost(model: str, usage: dict) -> float:
    pin, pout = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (usage.get("prompt_tokens", 0) * pin + usage.get("completion_tokens", 0) * pout) / 1e6


def _trace(record: dict) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    collected = _run_traces.get()
    if collected is not None:
        collected.append(record)


def _params(model: str, max_tokens: int, reasoning_effort: str | None, temperature: float) -> dict:
    params: dict[str, Any] = {
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "seed": SEED,
        "response_format": {"type": "json_object"},
    }
    if model.startswith("openai/gpt-oss"):
        if max_tokens < MIN_MAX_TOKENS:
            raise ValueError(f"gpt-oss needs max_tokens >= {MIN_MAX_TOKENS} (hidden reasoning)")
        params["reasoning_effort"] = reasoning_effort or "medium"
    elif model.startswith("qwen/"):
        params["reasoning_effort"] = reasoning_effort or "none"
    return params


MAX_ATTEMPTS = 14  # with the 60 s cap this tolerates ~10 min of rate limiting (parallel eval runs)


def _retry_after(err: Exception) -> float | None:
    """Seconds the server asks us to wait (Groq sends `retry-after` on 429), plus a little jitter."""
    resp = getattr(err, "response", None)
    value = resp.headers.get("retry-after") if resp is not None else None
    try:
        return min(float(value), 120.0) + random.uniform(0, 1) if value else None
    except ValueError:
        return None


def _call_api(model: str, messages: list[dict], params: dict) -> tuple[str, dict]:
    """One API call with exponential backoff on rate limits and transient errors.

    Groq returns 400 `json_validate_failed` when the model emits invalid JSON (e.g. a judge that
    "thinks aloud" inside a string field). We then retry with an explicit brevity instruction."""
    import groq

    delay = 2.0
    msgs = list(messages)
    json_retries = 0
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = _get_client().chat.completions.create(model=model, messages=msgs, **params)
            usage = resp.usage.model_dump() if resp.usage else {}
            return resp.choices[0].message.content or "", usage
        except (groq.RateLimitError, groq.APIConnectionError, groq.InternalServerError) as e:
            wait = _retry_after(e) or delay
            log.warning(
                "LLM transient error (%s), retry %d in %.0fs", type(e).__name__, attempt, wait
            )
            time.sleep(wait)
            delay = min(delay * 2, 60)
        except groq.BadRequestError as e:
            if "json_validate_failed" in str(e) and json_retries < 2:
                json_retries += 1
                log.warning("%s produced invalid JSON, retrying with a brevity instruction", model)
                msgs = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "Your previous answer was not valid JSON. Answer again with valid JSON only. "
                            "Keep every text field under 30 words and do not reason inside the JSON."
                        ),
                    },
                ]
                continue
            raise LLMError(str(e)[:500]) from e
    raise LLMError("LLM call failed after retries")


def chat_raw(
    model: str,
    messages: list[dict],
    *,
    component: str,
    max_tokens: int = 4000,
    reasoning_effort: str | None = None,
    temperature: float = 0.0,
    use_cache: bool = True,
) -> tuple[str, dict]:
    """Cached JSON-mode chat call. Returns (content, trace record)."""
    params = _params(model, max_tokens, reasoning_effort, temperature)
    key = hashlib.sha256(
        json.dumps(
            {"model": model, "messages": messages, "params": params}, sort_keys=True
        ).encode()
    ).hexdigest()
    cache_path: Path = CACHE_DIR / key[:2] / f"{key}.json"
    t0 = time.time()
    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        content, usage, cache_hit = cached["content"], cached["usage"], True
    else:
        content, usage = _call_api(model, messages, params)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"content": content, "usage": usage}), encoding="utf-8")
        cache_hit = False
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "component": component,
        "model": model,
        "cache_hit": cache_hit,
        "latency_s": round(time.time() - t0, 3),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "cost_usd": round(_cost(model, usage), 6),
        "key": key[:12],
    }
    _trace(record)
    return content, record


def chat_json[T: BaseModel](
    model: str,
    *,
    system: str,
    user: str,
    schema: type[T],
    component: str,
    max_tokens: int = 4000,
    reasoning_effort: str | None = None,
    temperature: float = 0.0,
) -> T:
    """Ask for JSON matching `schema`. On a validation error, retry once with the error message."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    content, _ = chat_raw(
        model,
        messages,
        component=component,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
    )
    try:
        return schema.model_validate_json(content)
    except ValidationError as err:
        log.warning("%s: invalid output, retrying once: %s", component, str(err)[:300])
        messages += [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": f"Your JSON did not match the schema:\n{err}\nReturn corrected JSON only.",
            },
        ]
        content, _ = chat_raw(
            model,
            messages,
            component=component,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
        )
        try:
            return schema.model_validate_json(content)
        except ValidationError as err2:
            raise LLMError(f"{component}: invalid output after retry: {err2}") from err2

"""LLM judges used by the evals. Model: JUDGE_MODEL (Qwen), a different family than the system model.
Every judge here is validated in evals/validate_judge.py before its numbers are reported."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from nda_review import llm, nli
from nda_review.config import JUDGE_MODEL
from nda_review.schemas import Contract, Hypothesis, NLIResult

log = logging.getLogger(__name__)
JUDGE_NLI_PROMPT = "nli_v3"  # same annotation conventions as the system, different model family


def judge_nli(contract: Contract, hyps: list[Hypothesis]) -> NLIResult:
    """Independent NLI check (used for the redline fix rate and collateral changes)."""
    return nli.classify(
        contract, hyps, model=JUDGE_MODEL, prompt=JUDGE_NLI_PROMPT, reasoning_effort="none"
    )


class RedlineScore(BaseModel):
    rule_id: str
    score: int
    problems: str = ""


class _Scores(BaseModel):
    scores: list[RedlineScore]


def judge_redlines(items: list[dict]) -> list[RedlineScore]:
    """items: {rule_id, position, original, action, new_text}."""
    if not items:
        return []
    user = "\n\n".join(
        f"rule_id: {it['rule_id']}\nrequired position: {it['position']}\naction: {it['action']}\n"
        f"original text: {it['original']}\nproposed text: {it['new_text']}"
        for it in items
    )
    try:
        out = llm.chat_json(
            JUDGE_MODEL,
            system=llm.load_prompt("judge_redline"),
            user=user,
            schema=_Scores,
            component="judge_redline",
            max_tokens=4000,
        )
    except llm.LLMError as e:  # counted as missing scores, reported as judge failures
        log.error("judge_redline failed: %s", str(e)[:200])
        return []
    return out.scores


class Verdict(BaseModel):
    rule_id: str
    supported: bool
    reason: str = ""


class _Verdicts(BaseModel):
    verdicts: list[Verdict]


def judge_faithfulness(items: list[dict]) -> list[Verdict]:
    """items: {rule_id, claim, cited: [span texts]}."""
    if not items:
        return []
    user = "\n\n".join(
        f"rule_id: {it['rule_id']}\nmemo claim: {it['claim']}\ncited spans:\n"
        + ("\n".join(f"- {t}" for t in it["cited"]) or "- (none)")
        for it in items
    )
    try:
        out = llm.chat_json(
            JUDGE_MODEL,
            system=llm.load_prompt("judge_faithfulness"),
            user=user,
            schema=_Verdicts,
            component="judge_faithfulness",
            max_tokens=4000,
        )
    except llm.LLMError as e:
        log.error("judge_faithfulness failed: %s", str(e)[:200])
        return []
    return out.verdicts

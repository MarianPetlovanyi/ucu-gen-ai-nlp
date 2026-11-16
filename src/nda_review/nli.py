"""C4 NLI + evidence: (contract spans × hypotheses) → label + evidence span ids per hypothesis.

LLM component: one call to the system model (gpt-oss-120b) per contract with all hypotheses, the
contract as numbered spans, JSON output validated by pydantic. Post-processing drops cited ids that
do not exist (hallucinated evidence) and clears evidence for NotMentioned.
Baselines (no LLM): majority label per hypothesis (train prior) and span-level DeBERTa NLI scores
(zero-shot or fine-tuned on Colab) aggregated to a document label with thresholds.
"""

from __future__ import annotations

import collections
import logging
from functools import lru_cache

from pydantic import BaseModel

from nda_review import llm
from nda_review.config import SYSTEM_MODEL, SYSTEM_REASONING_EFFORT
from nda_review.schemas import Contract, Hypothesis, NLIDecision, NLIResult

log = logging.getLogger(__name__)
DEFAULT_PROMPT = "nli_v4"  # v4 adopted in iteration 10 (see 05-evaluation.md)


class _LLMOut(BaseModel):
    decisions: list[NLIDecision]


def format_contract(contract: Contract, span_ids: set[int] | None = None) -> str:
    lines = [
        f"[{s.id}] {' '.join(s.text.split())}"
        for s in contract.spans
        if span_ids is None or s.id in span_ids
    ]
    return "\n".join(lines)


def format_hypotheses(hyps: list[Hypothesis]) -> str:
    return "\n".join(f"{h.id}: {h.text}" for h in hyps)


def prompt_version_hash(prompt: str = DEFAULT_PROMPT) -> str:
    return llm.prompt_hash(llm.load_prompt(prompt))


def _clean(
    raw: list[NLIDecision], contract: Contract, hyps: list[Hypothesis]
) -> tuple[list[NLIDecision], dict]:
    valid_ids = {s.id for s in contract.spans}
    by_h = {d.hypothesis_id: d for d in raw}
    stats = {"invalid_ids": 0, "missing_hypotheses": 0}
    out = []
    for h in hyps:
        d = by_h.get(h.id)
        if d is None:
            stats["missing_hypotheses"] += 1
            out.append(
                NLIDecision(hypothesis_id=h.id, label="NotMentioned", rationale="(no output)")
            )
            continue
        ev = [i for i in dict.fromkeys(d.evidence) if i in valid_ids]
        stats["invalid_ids"] += len(set(d.evidence)) - len(ev)
        if d.label == "NotMentioned":
            ev = []
        out.append(d.model_copy(update={"evidence": ev}))
    return out, stats


def classify(
    contract: Contract,
    hyps: list[Hypothesis],
    *,
    model: str = SYSTEM_MODEL,
    prompt: str = DEFAULT_PROMPT,
    reasoning_effort: str = SYSTEM_REASONING_EFFORT,
    span_ids: set[int] | None = None,
) -> NLIResult:
    """C4 entry point (LLM). `span_ids` restricts the context (retrieval ablation)."""
    user = (
        f"CONTRACT\n{format_contract(contract, span_ids)}\n\nHYPOTHESES\n{format_hypotheses(hyps)}"
    )
    out = llm.chat_json(
        model,
        system=llm.load_prompt(prompt),
        user=user,
        schema=_LLMOut,
        component="nli",
        max_tokens=16000,
        reasoning_effort=reasoning_effort,
    )
    decisions, stats = _clean(out.decisions, contract, hyps)
    if any(stats.values()):
        log.info("%s: %s", contract.doc_id, stats)
    return NLIResult(doc_id=contract.doc_id, method=f"llm:{model}:{prompt}", decisions=decisions)


# --- baselines --------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def train_priors() -> dict[str, str]:
    """Majority label per hypothesis on the train split."""
    from nda_review.data import load_split

    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for doc in load_split("train"):
        for h, lab in doc.labels.items():
            counts[h][lab] += 1
    return {h: c.most_common(1)[0][0] for h, c in counts.items()}


def majority_baseline(contract: Contract, hyps: list[Hypothesis]) -> NLIResult:
    """Train-majority label; evidence = top-2 exemplar-retrieved spans when the label is not N."""
    from nda_review.retrieve import retrieve

    priors = train_priors()
    hits = retrieve(contract, hyps, k=2)
    decisions = [
        NLIDecision(
            hypothesis_id=h.id,
            label=priors[h.id],
            evidence=[x.span_id for x in hits[h.id].hits] if priors[h.id] != "NotMentioned" else [],
        )
        for h in hyps
    ]
    return NLIResult(doc_id=contract.doc_id, method="majority", decisions=decisions)


def span_probs_baseline(
    contract: Contract,
    hyps: list[Hypothesis],
    probs: dict[str, list[list[float]]],
    t_entail: float,
    t_contra: float,
    method: str,
    max_evidence: int = 3,
) -> NLIResult:
    """Aggregate span-level [P(entail), P(contradict)] to a document label.

    Contradiction if any span has P(c) ≥ t_contra (and it beats the best entailment), else
    Entailment if any span has P(e) ≥ t_entail, else NotMentioned. Evidence = the top spans
    above the threshold of the chosen label.
    """
    decisions = []
    for h in hyps:
        p = probs[h.id]
        best_e = max(range(len(p)), key=lambda i: p[i][0])
        best_c = max(range(len(p)), key=lambda i: p[i][1])
        if p[best_c][1] >= t_contra and p[best_c][1] >= p[best_e][0]:
            label, col, t = "Contradiction", 1, t_contra
        elif p[best_e][0] >= t_entail:
            label, col, t = "Entailment", 0, t_entail
        else:
            decisions.append(NLIDecision(hypothesis_id=h.id, label="NotMentioned"))
            continue
        ranked = sorted((i for i in range(len(p)) if p[i][col] >= t), key=lambda i: -p[i][col])
        decisions.append(
            NLIDecision(hypothesis_id=h.id, label=label, evidence=ranked[:max_evidence])
        )
    return NLIResult(doc_id=contract.doc_id, method=method, decisions=decisions)

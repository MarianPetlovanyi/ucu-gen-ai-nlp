"""C6 Redline drafter: compliance issues → replacement or inserted clause text.

LLM component (gpt-oss-120b, one call per contract covering all VIOLATION/MISSING issues). The playbook
supplies the target position (preferred clause, fallback); C3 supplies anchor candidates for
insertions. `template_redlines` is the no-LLM baseline: paste the playbook's preferred clause verbatim.
`apply_redlines` produces the revised contract text, which the eval re-checks with the judge.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from nda_review import llm
from nda_review.config import SYSTEM_MODEL, SYSTEM_REASONING_EFFORT
from nda_review.nli import format_contract
from nda_review.playbook import position_text
from nda_review.retrieve import retrieve
from nda_review.schemas import (
    ComplianceReport,
    Contract,
    Hypothesis,
    Playbook,
    Redline,
    RedlineSet,
    RuleFinding,
)

log = logging.getLogger(__name__)
PROMPT = "redline_v2"  # iteration 13: preferred position only, contract terms


class _LLMOut(BaseModel):
    redlines: list[Redline]


def _issues(report: ComplianceReport) -> list[RuleFinding]:
    return [f for f in report.findings if f.status in ("VIOLATION", "MISSING")]


def _anchors(contract: Contract, hyps: list[Hypothesis], issues: list[RuleFinding]) -> dict:
    by_id = {h.id: h for h in hyps}
    need = [by_id[f.hypothesis_id] for f in issues if f.status == "MISSING"]
    if not need:
        return {}
    hits = retrieve(contract, need, k=3)
    return {h: [x.span_id for x in r.hits] for h, r in hits.items()}


def _describe(issues: list[RuleFinding], playbook: Playbook, hyps, anchors) -> str:
    rules = {r.id: r for r in playbook.rules}
    hyp_text = {h.id: h.text for h in hyps}
    blocks = []
    for f in issues:
        r = rules[f.rule_id]
        lines = [
            f"- rule_id: {f.rule_id} ({f.status}, severity {f.severity})",
            f"  client position: {position_text(r, hyp_text[f.hypothesis_id])}",
            f"  preferred clause: {r.preferred_clause or '-'}",
            f"  acceptable fallback: {r.fallback or '-'}",
        ]
        if f.status == "VIOLATION":
            lines.append(f"  evidence spans (conflicting wording): {f.evidence}")
        else:
            lines.append(f"  suggested anchor spans: {anchors.get(f.hypothesis_id, [])}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


# A span is a safe place to insert a new clause only if it ends a sentence and the next span does not
# continue a list. Measured on dev (iteration 15): 33 % of the LLM's and 47 % of the template's insertion
# anchors were list lead-ins ("…that:"), list items ("…; or") or headings.
_SENTENCE_END = re.compile(r"[.!?][\"”’)\]]*\s*$")
_LIST_ITEM = re.compile(r"^\s*\(?(?:[a-z]{1,2}|[ivxlc]{1,5}|\d{1,2})\)\s")
MAX_ANCHOR_SHIFT = 12


def safe_anchor(contract: Contract, span_id: int) -> int:
    """Move an insertion anchor forward to the end of the sentence or list it belongs to."""
    spans = contract.spans
    for j in range(span_id, min(span_id + MAX_ANCHOR_SHIFT, len(spans))):
        nxt = spans[j + 1].text if j + 1 < len(spans) else ""
        if _SENTENCE_END.search(spans[j].text) and not _LIST_ITEM.match(nxt):
            return j
    return span_id


def _validate(
    redlines: list[Redline], issues: list[RuleFinding], contract: Contract
) -> list[Redline]:
    """Keep one redline per issue, with existing span ids; fall back to sensible targets."""
    valid = {s.id for s in contract.spans}
    by_rule = {r.rule_id: r for r in redlines}
    out = []
    for f in issues:
        r = by_rule.get(f.rule_id)
        if r is None or not r.new_text.strip():
            log.warning("%s: no redline for %s", contract.doc_id, f.rule_id)
            continue
        targets = [i for i in r.target_span_ids if i in valid]
        if r.action == "replace" and not targets:
            targets = [i for i in f.evidence if i in valid]
            if not targets:  # nothing to replace (e.g. a MISSING rule): insert instead of dropping
                log.warning(
                    "%s: %s replace without valid target, inserted", contract.doc_id, f.rule_id
                )
                r = r.model_copy(update={"action": "insert"})
        if r.action == "insert":
            targets = [safe_anchor(contract, (targets or [contract.spans[-1].id])[0])]
        if targets:
            out.append(r.model_copy(update={"target_span_ids": targets}))
    return out


def draft_redlines(
    contract: Contract,
    report: ComplianceReport,
    playbook: Playbook,
    hyps: list[Hypothesis],
    *,
    model: str = SYSTEM_MODEL,
) -> RedlineSet:
    """C6 entry point (LLM)."""
    issues = _issues(report)
    if not issues:
        return RedlineSet(doc_id=contract.doc_id, redlines=[])
    anchors = _anchors(contract, hyps, issues)
    user = (
        f"CONTRACT\n{format_contract(contract)}\n\n"
        f"ISSUES (client playbook: {playbook.name})\n{_describe(issues, playbook, hyps, anchors)}"
    )
    out = llm.chat_json(
        model,
        system=llm.load_prompt(PROMPT),
        user=user,
        schema=_LLMOut,
        component="redline",
        max_tokens=16000,
        reasoning_effort=SYSTEM_REASONING_EFFORT,
    )
    return RedlineSet(doc_id=contract.doc_id, redlines=_validate(out.redlines, issues, contract))


def template_redlines(
    contract: Contract, report: ComplianceReport, playbook: Playbook, hyps: list[Hypothesis]
) -> RedlineSet:
    """Baseline without an LLM: the playbook's preferred clause, verbatim."""
    issues = _issues(report)
    anchors = _anchors(contract, hyps, issues)
    rules = {r.id: r for r in playbook.rules}
    redlines = []
    for f in issues:
        text = rules[f.rule_id].preferred_clause
        if not text:
            continue
        if f.status == "VIOLATION" and f.evidence:
            redlines.append(
                Redline(
                    rule_id=f.rule_id, action="replace", target_span_ids=f.evidence, new_text=text
                )
            )
        else:
            anchor = (anchors.get(f.hypothesis_id) or [contract.spans[-1].id])[0]
            redlines.append(
                Redline(
                    rule_id=f.rule_id,
                    action="insert",
                    target_span_ids=[safe_anchor(contract, anchor)],
                    new_text=text,
                )
            )
    return RedlineSet(doc_id=contract.doc_id, redlines=redlines)


def apply_redlines(contract: Contract, redlines: RedlineSet) -> str:
    """Revised contract text. Replacements: the first target span gets the new text, the other target
    spans are removed. Insertions: a new line after the anchor span. Conflicts (a span targeted by two
    replacements) keep the first redline."""
    replace_at: dict[int, str] = {}
    remove: set[int] = set()
    insert_after: dict[int, list[str]] = {}
    for r in redlines.redlines:
        if r.action == "replace":
            first, *rest = sorted(r.target_span_ids)
            if first in replace_at or first in remove:
                continue
            replace_at[first] = r.new_text.strip()
            remove.update(i for i in rest if i not in replace_at)
        else:
            insert_after.setdefault(r.target_span_ids[0], []).append(r.new_text.strip())
    text, out, pos = contract.text, [], 0
    for s in contract.spans:
        out.append(text[pos : s.start])
        if s.id in replace_at:
            out.append(replace_at[s.id])
        elif s.id not in remove:
            out.append(text[s.start : s.end])
        for ins in insert_after.get(s.id, []):
            out.append("\n" + ins)
        pos = s.end
    out.append(text[pos:])
    return "".join(out)

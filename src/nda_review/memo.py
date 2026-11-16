"""C7 Negotiation memo: compliance report + contract → grounded memo with span citations.

LLM component (gpt-oss-120b, one call per contract). The recommendation is decided by the playbook
policy in C5; the LLM explains it. Citations are span ids and are validated (non-existent ids dropped).
"""

from __future__ import annotations

from nda_review import llm
from nda_review.config import SYSTEM_MODEL, SYSTEM_REASONING_EFFORT
from nda_review.nli import format_contract
from nda_review.playbook import ISSUE_STATUSES, position_text
from nda_review.schemas import ComplianceReport, Contract, Hypothesis, Memo, Playbook

PROMPT = "memo"  # memo_v2 was tried and rejected in iteration 12 (see 05-evaluation.md)


def _findings_block(report: ComplianceReport, playbook: Playbook, hyps: list[Hypothesis]) -> str:
    rules = {r.id: r for r in playbook.rules}
    hyp_text = {h.id: h.text for h in hyps}
    lines = []
    for f in report.findings:
        r = rules[f.rule_id]
        line = (
            f"- {f.rule_id} [{f.status}, severity {f.severity}] {position_text(r, hyp_text[f.hypothesis_id])}"
            f" | contract label: {f.label} | evidence spans: {f.evidence}"
        )
        if f.status in ISSUE_STATUSES:
            line += f" | preferred: {r.preferred_clause or '-'} | fallback: {r.fallback or '-'}"
        lines.append(line)
    return "\n".join(lines)


def write_memo(
    contract: Contract,
    report: ComplianceReport,
    playbook: Playbook,
    hyps: list[Hypothesis],
    *,
    model: str = SYSTEM_MODEL,
) -> Memo:
    """C7 entry point (LLM)."""
    user = (
        f"CONTRACT\n{format_contract(contract)}\n\n"
        f"PLAYBOOK: {playbook.name}\nRISK SCORE: {report.risk_score}/100\n"
        f"DECIDED RECOMMENDATION: {report.recommendation}\n\n"
        f"FINDINGS\n{_findings_block(report, playbook, hyps)}"
    )
    memo = llm.chat_json(
        model,
        system=llm.load_prompt(PROMPT),
        user=user,
        schema=Memo,
        component="memo",
        max_tokens=12000,
        reasoning_effort=SYSTEM_REASONING_EFFORT,
    )
    valid = {s.id for s in contract.spans}
    issues = [
        i.model_copy(update={"citations": [c for c in i.citations if c in valid]})
        for i in memo.issues
    ]
    return memo.model_copy(update={"issues": issues})

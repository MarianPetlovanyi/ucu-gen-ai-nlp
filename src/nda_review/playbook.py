"""C5 Playbook compliance + risk: NLI labels × playbook rules → status per rule and a risk score.

Deterministic component (no LLM). The business logic is configuration: each rule in
playbooks/*.yaml has a stance that maps the NLI label of its hypothesis to a status, a severity, and
the playbook's scoring weights turn the statuses into a 0–100 risk score.
"""

from __future__ import annotations

from nda_review.schemas import (
    ComplianceReport,
    Label,
    NLIResult,
    Playbook,
    Rule,
    RuleFinding,
    Stance,
    Status,
)

STATUS_BY_STANCE: dict[Stance, dict[Label, Status]] = {
    "must_entail": {"Entailment": "OK", "Contradiction": "VIOLATION", "NotMentioned": "MISSING"},
    "must_not_entail": {"Entailment": "VIOLATION", "Contradiction": "OK", "NotMentioned": "OK"},
    "review_if_entailed": {"Entailment": "REVIEW", "Contradiction": "OK", "NotMentioned": "OK"},
    "info": {"Entailment": "INFO", "Contradiction": "INFO", "NotMentioned": "INFO"},
}
ISSUE_STATUSES = ("VIOLATION", "MISSING")


def position_text(rule: Rule, hypothesis_text: str) -> str:
    """The client's position in plain words (shared by the drafter C6 and the judge)."""
    if rule.stance == "must_entail":
        req = f"The contract MUST provide that: {hypothesis_text}"
    elif rule.stance == "must_not_entail":
        req = f"The contract must NOT provide that: {hypothesis_text} (it should say the opposite or nothing)"
    else:
        req = f"Topic: {hypothesis_text}"
    return f"{rule.title}. {req} Reason: {rule.rationale}"


def rule_status(stance: Stance, label: Label) -> Status:
    return STATUS_BY_STANCE[stance][label]


def risk_score(findings: list[RuleFinding], playbook: Playbook) -> float:
    """Weighted share of the maximum possible risk, in [0, 100]."""
    sev, stw = playbook.scoring.severity_weights, playbook.scoring.status_weights
    scored = [f for f in findings if f.stance != "info"]
    worst = sum(sev[f.severity] * max(stw.values()) for f in scored)
    actual = sum(sev[f.severity] * stw[f.status] for f in scored)
    return round(100 * actual / worst, 1) if worst else 0.0


def assess(nli: NLIResult, playbook: Playbook) -> ComplianceReport:
    """C5 entry point."""
    by_h = nli.by_hypothesis()
    findings = []
    for rule in playbook.rules:
        d = by_h[rule.hypothesis]
        findings.append(
            RuleFinding(
                rule_id=rule.id,
                hypothesis_id=rule.hypothesis,
                title=rule.title,
                stance=rule.stance,
                severity=rule.severity,
                label=d.label,
                status=rule_status(rule.stance, d.label),
                evidence=d.evidence,
                rationale=d.rationale,
            )
        )
    order = {"VIOLATION": 0, "MISSING": 1, "REVIEW": 2, "OK": 3, "INFO": 4}
    sev = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order[f.status], sev[f.severity], f.rule_id))
    risk = risk_score(findings, playbook)
    return ComplianceReport(
        doc_id=nli.doc_id,
        playbook=playbook.name,
        findings=findings,
        risk_score=risk,
        recommendation=recommend(findings, risk, playbook),
    )


def recommend(findings: list[RuleFinding], risk: float, playbook: Playbook) -> str:
    """Business decision from the playbook thresholds (not from the LLM)."""
    serious = any(f.status in ISSUE_STATUSES and f.severity in ("high", "medium") for f in findings)
    if risk >= playbook.scoring.reject_min_risk:
        return "reject"
    if not serious and risk <= playbook.scoring.sign_max_risk:
        return "sign"
    return "negotiate"

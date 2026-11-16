"""Pydantic contracts between the components (C1–C7). Every component takes and returns these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Label = Literal["Entailment", "Contradiction", "NotMentioned"]
Stance = Literal["must_entail", "must_not_entail", "review_if_entailed", "info"]
Severity = Literal["high", "medium", "low"]
Status = Literal["OK", "VIOLATION", "MISSING", "REVIEW", "INFO"]


# --- C1 ingestion ---------------------------------------------------------------------------
class IngestResult(BaseModel):
    """C1 output: plain text with one paragraph / list item per line."""

    text: str
    source_format: Literal["pdf", "html", "txt"]
    n_pages: int | None = None
    warnings: list[str] = Field(default_factory=list)


# --- C2 segmentation ------------------------------------------------------------------------
class Span(BaseModel):
    """A sentence or list item: the unit of evidence. `start`/`end` are character offsets."""

    id: int
    start: int
    end: int
    text: str


class Contract(BaseModel):
    """A segmented contract: the input of C3/C4."""

    doc_id: str
    text: str
    spans: list[Span]


# --- hypotheses and playbook ----------------------------------------------------------------
class Hypothesis(BaseModel):
    id: str  # e.g. "nda-11"
    short: str  # e.g. "No reverse engineering"
    text: str  # full hypothesis sentence


class Rule(BaseModel):
    id: str
    hypothesis: str
    title: str
    stance: Stance
    severity: Severity
    rationale: str
    preferred_clause: str | None = None
    fallback: str | None = None


class Scoring(BaseModel):
    severity_weights: dict[Severity, float] = {"high": 3, "medium": 2, "low": 1}
    status_weights: dict[Status, float] = {
        "VIOLATION": 1.0,
        "MISSING": 0.75,
        "REVIEW": 0.25,
        "OK": 0.0,
        "INFO": 0.0,
    }
    sign_max_risk: float = 10
    reject_min_risk: float = 60


class Playbook(BaseModel):
    name: str
    perspective: str
    scoring: Scoring = Field(default_factory=Scoring)
    rules: list[Rule]


# --- C3 retrieval ---------------------------------------------------------------------------
class RetrievalHit(BaseModel):
    span_id: int
    score: float


class RetrievalResult(BaseModel):
    hypothesis_id: str
    hits: list[RetrievalHit]  # best first


# --- C4 NLI ---------------------------------------------------------------------------------
class NLIDecision(BaseModel):
    hypothesis_id: str
    label: Label
    evidence: list[int] = Field(default_factory=list)  # span ids
    rationale: str = ""


class NLIResult(BaseModel):
    doc_id: str
    method: str
    decisions: list[NLIDecision]

    def by_hypothesis(self) -> dict[str, NLIDecision]:
        return {d.hypothesis_id: d for d in self.decisions}


# --- C5 compliance --------------------------------------------------------------------------
class RuleFinding(BaseModel):
    rule_id: str
    hypothesis_id: str
    title: str
    stance: Stance
    severity: Severity
    label: Label
    status: Status
    evidence: list[int] = Field(default_factory=list)
    rationale: str = ""


class ComplianceReport(BaseModel):
    doc_id: str
    playbook: str
    findings: list[RuleFinding]
    risk_score: float  # 0 (no issues) .. 100 (every weighted rule is an issue)
    recommendation: Literal["sign", "negotiate", "reject"] = "negotiate"

    @property
    def issues(self) -> list[RuleFinding]:
        return [f for f in self.findings if f.status in ("VIOLATION", "MISSING")]


# --- C6 redlines ----------------------------------------------------------------------------
class Redline(BaseModel):
    rule_id: str
    action: Literal["replace", "insert"]
    # replace: the span ids whose text is replaced; insert: one span id after which to insert
    target_span_ids: list[int]
    new_text: str
    explanation: str = ""


class RedlineSet(BaseModel):
    doc_id: str
    redlines: list[Redline]


# --- C7 memo --------------------------------------------------------------------------------
class MemoIssue(BaseModel):
    rule_id: str
    headline: str
    explanation: str
    ask: str
    fallback: str = ""
    citations: list[int] = Field(default_factory=list)  # span ids


class Memo(BaseModel):
    summary: str
    recommendation: Literal["sign", "negotiate", "reject"]
    issues: list[MemoIssue]

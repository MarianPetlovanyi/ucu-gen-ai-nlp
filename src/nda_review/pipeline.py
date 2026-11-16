"""Wires C1–C7 into one review. The Streamlit app calls only this module.

file/text ─C1 ingest─▶ text ─C2 segment─▶ Contract ─C3 retrieve─▶ evidence candidates (UI, anchors)
                                             └──────C4 NLI (LLM)──▶ labels+evidence ─C5 playbook─▶ report
report ─C6 redline (LLM)─▶ redlines ─apply─▶ revised text;  report ─C7 memo (LLM)─▶ memo
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from nda_review import llm
from nda_review.data import load_hypotheses, load_playbook
from nda_review.ingest import ingest, ingest_text
from nda_review.memo import write_memo
from nda_review.nli import classify
from nda_review.playbook import assess
from nda_review.redline import apply_redlines, draft_redlines
from nda_review.retrieve import retrieve
from nda_review.schemas import (
    ComplianceReport,
    Contract,
    IngestResult,
    Memo,
    NLIResult,
    RedlineSet,
    RetrievalResult,
)
from nda_review.segment import segment

log = logging.getLogger(__name__)


class ReviewResult(BaseModel):
    playbook: str
    ingest: IngestResult | None = None
    contract: Contract
    retrieval: dict[str, RetrievalResult]
    nli: NLIResult
    report: ComplianceReport
    redlines: RedlineSet | None = None
    revised_text: str | None = None
    memo: Memo | None = None
    timings_s: dict[str, float] = Field(default_factory=dict)
    traces: list[dict] = Field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(t.get("cost_usd", 0.0) for t in self.traces)


def review_contract(
    contract: Contract,
    playbook_name: str,
    *,
    ingest_result: IngestResult | None = None,
    with_redlines: bool = True,
    with_memo: bool = True,
) -> ReviewResult:
    """C3–C7 on an already segmented contract (also used for dataset contracts with gold spans)."""
    traces = llm.start_trace_collection()
    timings: dict[str, float] = {}
    hyps = load_hypotheses()
    pb = load_playbook(playbook_name)

    def timed(name, fn, *a, **kw):
        t0 = time.time()
        out = fn(*a, **kw)
        timings[name] = round(time.time() - t0, 2)
        return out

    retrieval = timed("C3 retrieve", retrieve, contract, hyps, k=5)
    nli = timed("C4 nli", classify, contract, hyps)
    report = timed("C5 playbook", assess, nli, pb)
    redlines = revised = memo = None
    if with_redlines:
        redlines = timed("C6 redline", draft_redlines, contract, report, pb, hyps)
        revised = apply_redlines(contract, redlines)
    if with_memo:
        memo = timed("C7 memo", write_memo, contract, report, pb, hyps)
    return ReviewResult(
        playbook=playbook_name,
        ingest=ingest_result,
        contract=contract,
        retrieval=retrieval,
        nli=nli,
        report=report,
        redlines=redlines,
        revised_text=revised,
        memo=memo,
        timings_s=timings,
        traces=list(traces),
    )


def review_file(path: str | Path, playbook_name: str, **kw) -> ReviewResult:
    """Full pipeline C1–C7 for an uploaded PDF/HTML/TXT file."""
    t0 = time.time()
    ing = ingest(path)
    t1 = time.time()
    contract = segment(ing.text, doc_id=Path(path).name)
    t2 = time.time()
    res = review_contract(contract, playbook_name, ingest_result=ing, **kw)
    res.timings_s = {
        "C1 ingest": round(t1 - t0, 2),
        "C2 segment": round(t2 - t1, 2),
    } | res.timings_s
    return res


def review_text(text: str, playbook_name: str, doc_id: str = "pasted", **kw) -> ReviewResult:
    ing = ingest_text(text)
    contract = segment(ing.text, doc_id=doc_id)
    return review_contract(contract, playbook_name, ingest_result=ing, **kw)

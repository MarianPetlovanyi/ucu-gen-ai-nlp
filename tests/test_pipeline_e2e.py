"""End-to-end tests of the pipeline wiring (C1 → C7), without network calls.

1. `test_pipeline_wiring_*`: a fake LLM that also returns invalid span ids and redlines for rules that are not
   issues. Checks that every stage gets its input, that the validation code drops what it must, and that
   redlines are applied. Runs everywhere (no data, no API key, no embedding model).
2. `test_cached_replay_on_real_file`: the real pipeline on an original ContractNLI file, replayed from the LLM
   disk cache. Skipped when the raw data or a cache entry is missing; a real API call is never made.
LLM output quality is not unit-tested here (CLAUDE.md); it is measured by evals/eval_e2e.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nda_review import llm, pipeline, redline
from nda_review.config import RAW_DIR
from nda_review.data import load_playbook
from nda_review.playbook import ISSUE_STATUSES
from nda_review.schemas import (
    Hypothesis,
    Memo,
    MemoIssue,
    NLIDecision,
    Redline,
    RetrievalHit,
    RetrievalResult,
)

PLAYBOOK = "disclosing_party"
BAD_ID = 9999  # a span id that never exists: every stage must drop it

CONTRACT = """MUTUAL NON-DISCLOSURE AGREEMENT
1. The Recipient shall keep the Confidential Information secret.
2. The Recipient may share Confidential Information with its employees.
3. The Recipient may reverse engineer any samples.
4. This Agreement is governed by the laws of Delaware.
"""


def _hyps() -> list[Hypothesis]:
    pb = load_playbook(PLAYBOOK)
    return [Hypothesis(id=r.hypothesis, short=r.title, text=r.title) for r in pb.rules]


def _fake_retrieve(contract, hyps, k=5, **_):
    hits = [RetrievalHit(span_id=s.id, score=1.0) for s in contract.spans[:k]]
    return {h.id: RetrievalResult(hypothesis_id=h.id, hits=hits) for h in hyps}


def _fake_chat_json(model, *, system, user, schema, component, **_):
    pb = load_playbook(PLAYBOOK)
    if component == "nli":
        labels = ("Contradiction", "Entailment", "NotMentioned")
        return schema(
            decisions=[
                NLIDecision(hypothesis_id=r.hypothesis, label=labels[i % 3], evidence=[1, BAD_ID])
                for i, r in enumerate(pb.rules)
            ]
        )
    if component == "redline":  # one redline for EVERY rule; C6 must keep only the issues
        return schema(
            redlines=[
                Redline(
                    rule_id=r.id,
                    action="replace" if i % 2 else "insert",
                    target_span_ids=[BAD_ID] if i % 2 else [2],
                    new_text=f"NEW CLAUSE FOR {r.id}.",
                )
                for i, r in enumerate(pb.rules)
            ]
        )
    if component == "memo":
        return Memo(
            summary="s",
            recommendation="negotiate",
            issues=[
                MemoIssue(
                    rule_id=r.id, headline="h", explanation="e", ask="a", citations=[1, BAD_ID]
                )
                for r in pb.rules
            ],
        )
    raise AssertionError(f"unexpected LLM component {component}")


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _fake_chat_json)
    monkeypatch.setattr(llm, "_call_api", lambda *a, **k: pytest.fail("network call in a test"))
    monkeypatch.setattr(pipeline, "retrieve", _fake_retrieve)
    monkeypatch.setattr(redline, "retrieve", _fake_retrieve)
    monkeypatch.setattr(pipeline, "load_hypotheses", _hyps)


def check_invariants(res: pipeline.ReviewResult) -> None:
    """Structural guarantees every review must satisfy, whatever the LLM says."""
    valid = {s.id for s in res.contract.spans}
    pb = load_playbook(res.playbook)
    # C2: spans cover the text in order
    assert res.contract.spans, "no spans"
    for s in res.contract.spans:
        assert res.contract.text[s.start : s.end] == s.text
    # C4: one decision per hypothesis, evidence ids exist, NotMentioned has no evidence
    assert {d.hypothesis_id for d in res.nli.decisions} >= {r.hypothesis for r in pb.rules}
    for d in res.nli.decisions:
        assert set(d.evidence) <= valid
        assert d.label != "NotMentioned" or not d.evidence
    # C5: one finding per playbook rule, recommendation is the policy's
    assert sorted(f.rule_id for f in res.report.findings) == sorted(r.id for r in pb.rules)
    issues = {f.rule_id for f in res.report.findings if f.status in ISSUE_STATUSES}
    # C6: at most one redline per issue, only for issues, valid targets, applied to the text
    assert res.redlines is not None and res.revised_text is not None
    ids = [r.rule_id for r in res.redlines.redlines]
    assert len(ids) == len(set(ids)) and set(ids) <= issues
    for r in res.redlines.redlines:
        assert r.target_span_ids and set(r.target_span_ids) <= valid
        assert r.new_text.strip() in res.revised_text
    # C7: citations exist
    assert res.memo is not None
    for item in res.memo.issues:
        assert set(item.citations) <= valid


def test_pipeline_wiring_text(fake_llm):
    res = pipeline.review_text(CONTRACT, PLAYBOOK, doc_id="t")
    check_invariants(res)
    issues = [f for f in res.report.findings if f.status in ISSUE_STATUSES]
    assert issues, "the fake labels must produce issues, otherwise C6/C7 are not exercised"
    assert len(res.redlines.redlines) == len(issues)  # the extra redlines were dropped
    assert res.revised_text != res.contract.text
    assert all(BAD_ID not in d.evidence for d in res.nli.decisions)
    assert set(res.timings_s) == {"C3 retrieve", "C4 nli", "C5 playbook", "C6 redline", "C7 memo"}


@pytest.mark.parametrize("suffix", [".txt", ".html"])
def test_pipeline_wiring_file(fake_llm, tmp_path: Path, suffix: str):
    path = tmp_path / f"nda{suffix}"
    body = CONTRACT
    if suffix == ".html":
        body = (
            "<html><body>"
            + "".join(f"<p>{line}</p>" for line in CONTRACT.splitlines())
            + "</body></html>"
        )
    path.write_text(body, encoding="utf-8")
    res = pipeline.review_file(path, PLAYBOOK)
    check_invariants(res)
    assert "reverse engineer" in res.contract.text
    assert list(res.timings_s)[:2] == ["C1 ingest", "C2 segment"]


def test_pipeline_without_redlines_and_memo(fake_llm):
    res = pipeline.review_text(CONTRACT, PLAYBOOK, with_redlines=False, with_memo=False)
    assert res.redlines is None and res.memo is None and res.revised_text is None


@pytest.mark.skipif(not (RAW_DIR / "dev.json").exists(), reason="ContractNLI not downloaded")
def test_cached_replay_on_real_file(monkeypatch):
    from nda_review.data import load_split

    doc = load_split("dev", 1)[0]
    monkeypatch.setattr(
        llm,
        "_call_api",
        lambda *a, **k: pytest.skip("not in the LLM cache; run evals.eval_e2e first"),
    )
    res = pipeline.review_file(doc.raw_path, PLAYBOOK)
    check_invariants(res)
    assert all(t["cache_hit"] for t in res.traces)
    assert len(res.nli.decisions) == 17

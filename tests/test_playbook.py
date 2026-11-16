import pytest

from nda_review.data import list_playbooks, load_hypotheses, load_playbook
from nda_review.playbook import assess, rule_status
from nda_review.schemas import NLIDecision, NLIResult


@pytest.mark.parametrize(
    "stance,label,status",
    [
        ("must_entail", "Entailment", "OK"),
        ("must_entail", "Contradiction", "VIOLATION"),
        ("must_entail", "NotMentioned", "MISSING"),
        ("must_not_entail", "Entailment", "VIOLATION"),
        ("must_not_entail", "NotMentioned", "OK"),
        ("review_if_entailed", "Entailment", "REVIEW"),
        ("review_if_entailed", "Contradiction", "OK"),
        ("info", "Contradiction", "INFO"),
    ],
)
def test_rule_status(stance, label, status):
    assert rule_status(stance, label) == status


def _nli(label: str) -> NLIResult:
    return NLIResult(
        doc_id="x",
        method="test",
        decisions=[NLIDecision(hypothesis_id=h.id, label=label) for h in load_hypotheses()],
    )


@pytest.mark.parametrize("name", list_playbooks())
def test_playbooks_cover_every_hypothesis_once(name):
    pb = load_playbook(name)
    hyps = {h.id for h in load_hypotheses()}
    assert sorted(r.hypothesis for r in pb.rules) == sorted(hyps)
    assert len({r.id for r in pb.rules}) == len(pb.rules)


def test_risk_score_bounds_and_order():
    pb = load_playbook("disclosing_party")
    all_missing = assess(_nli("NotMentioned"), pb)
    all_entailed = assess(_nli("Entailment"), pb)
    assert 0 <= all_entailed.risk_score <= 100 and 0 <= all_missing.risk_score <= 100
    # for a disclosing party most protections are must_entail: silence is riskier than entailment
    assert all_missing.risk_score > all_entailed.risk_score
    assert all_missing.findings[0].status in ("VIOLATION", "MISSING")  # issues sorted first


def test_recommendation_thresholds():
    pb = load_playbook("disclosing_party")
    assert assess(_nli("NotMentioned"), pb).recommendation in ("negotiate", "reject")
    ok = _nli("Entailment")
    # disclosing playbook: entailing everything still violates must_not_entail rules -> not "sign"
    assert assess(ok, pb).recommendation != "sign"

from evals.common import prf
from evals.metrics import classification_metrics, confusion, evidence_prf


def test_prf_handles_zero_division():
    assert prf(0, 0, 0) == (0.0, 0.0, 0.0)
    assert prf(1, 2, 4) == (0.5, 0.25, 1 / 3)


def test_classification_metrics_perfect_and_macro():
    gold = ["Entailment", "Contradiction", "NotMentioned", "Entailment"]
    m = classification_metrics(gold, gold)
    assert m["accuracy"] == 1.0 and m["macro_f1"] == 1.0
    pred = ["Entailment", "NotMentioned", "NotMentioned", "Entailment"]
    m = classification_metrics(gold, pred)
    assert m["Contradiction"]["f1"] == 0.0
    assert m["accuracy"] == 0.75
    assert confusion(gold, pred)["Contradiction"]["NotMentioned"] == 1


def test_evidence_prf_micro_and_macro():
    pairs = [({1, 2}, {2, 3}), ({5}, set())]
    m = evidence_prf(pairs)
    assert m["micro_p"] == 0.5 and m["micro_r"] == 1 / 3
    assert m["macro_f1"] == 0.25  # (0.5 + 0) / 2


def test_e2e_evidence_overlap_match():
    from evals.eval_e2e import evidence_counts, overlap

    assert overlap(["a", "b"], ["a", "b", "c", "d"]) == 1.0  # shorter span fully contained
    assert overlap(["a"], []) == 0.0
    c = evidence_counts(
        ["The Recipient shall not reverse engineer.", "Unrelated clause about notices."],
        ["Recipient shall not reverse engineer the samples", "Governing law is Delaware."],
    )
    assert c == {"n_gold": 2, "n_pred": 2, "gold_found": 1, "pred_correct": 1}

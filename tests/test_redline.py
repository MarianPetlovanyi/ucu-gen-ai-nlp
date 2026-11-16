from nda_review.redline import apply_redlines, safe_anchor
from nda_review.schemas import Redline, RedlineSet
from nda_review.segment import segment

C = segment("Clause zero.\nClause one.\nClause two.")


def rs(*redlines: Redline) -> RedlineSet:
    return RedlineSet(doc_id="t", redlines=list(redlines))


def red(action: str, ids: list[int], text: str) -> Redline:
    return Redline(rule_id="R", action=action, target_span_ids=ids, new_text=text, explanation="")


def test_replace_first_target_and_drop_the_rest():
    out = apply_redlines(C, rs(red("replace", [1, 2], "New clause.")))
    assert out == "Clause zero.\nNew clause.\n"


def test_insert_after_anchor():
    out = apply_redlines(C, rs(red("insert", [0], "Inserted.")))
    assert out == "Clause zero.\nInserted.\nClause one.\nClause two."


def test_conflicting_replacements_keep_the_first():
    out = apply_redlines(C, rs(red("replace", [1], "A."), red("replace", [1], "B.")))
    assert "A." in out and "B." not in out


def test_no_redlines_is_identity():
    assert apply_redlines(C, rs()) == C.text


def test_safe_anchor_moves_past_a_list():
    c = segment(
        "The Recipient agrees that:\n(a) it will not copy;\n(b) it will not disclose.\nNext clause."
    )
    assert safe_anchor(c, 0) == 2


def test_safe_anchor_moves_to_sentence_end():
    c = segment("The Company will not solicit,\nany employee of the other party.\nNext clause.")
    assert safe_anchor(c, 0) == 1


def test_safe_anchor_keeps_a_sentence_end():
    assert safe_anchor(C, 1) == 1


def test_safe_anchor_skips_a_heading():
    c = segment("1. Confidential Information\nThe Recipient shall keep it secret.\nNext.")
    assert safe_anchor(c, 0) == 1

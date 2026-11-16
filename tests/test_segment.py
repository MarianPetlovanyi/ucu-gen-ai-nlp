from nda_review.segment import segment


def texts(text: str) -> list[str]:
    return [s.text.strip() for s in segment(text).spans]


def test_every_line_is_a_boundary():
    assert texts("First clause\nSecond clause") == ["First clause", "Second clause"]


def test_sentence_split_but_not_after_abbreviation():
    out = texts("Acme Inc. shall keep it secret. The term is 2 years.")
    assert out == ["Acme Inc. shall keep it secret.", "The term is 2 years."]


def test_inline_enumeration_starts_new_span():
    out = texts("The Recipient shall (a) keep it secret and (b) not copy it.")
    assert out == ["The Recipient shall", "(a) keep it secret and", "(b) not copy it."]


def test_offsets_point_into_text():
    text = "Line one.\nLine two (i) item."
    c = segment(text)
    assert all(text[s.start : s.end] == s.text for s in c.spans)
    assert [s.id for s in c.spans] == list(range(len(c.spans)))


def test_lines_method_one_span_per_line():
    assert len(segment("A. B.\nC (a) d", method="lines").spans) == 2


def test_numeral_after_number_word_is_not_an_enumerator():
    out = texts("The term is three (3) years and (a) it renews.")
    assert out == ["The term is three (3) years and", "(a) it renews."]

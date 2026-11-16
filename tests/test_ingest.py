from nda_review.ingest import ingest, ingest_text, merge_broken_lines


def test_merge_lone_enumerator_with_next_line():
    assert merge_broken_lines("1.\nDefinitions apply.") == "1. Definitions apply."


def test_merge_lowercase_continuation():
    assert (
        merge_broken_lines("The Recipient shall\nnot disclose.")
        == "The Recipient shall not disclose."
    )


def test_keep_line_after_finished_sentence():
    assert merge_broken_lines("It ends here.\nnext para") == "It ends here.\nnext para"


def test_pasted_text_hard_wraps_are_joined():
    res = ingest_text(
        "The Receiving Party shall keep\nall information secret.\n\nThis Agreement is governed\nby law."
    )
    assert res.text.split("\n") == [
        "The Receiving Party shall keep all information secret.",
        "This Agreement is governed by law.",
    ]


def test_html_block_tags_become_lines(tmp_path):
    p = tmp_path / "nda.html"
    p.write_text(
        "<html><body><h1>NDA</h1><p>First   clause.</p><p>Second clause.</p></body></html>"
    )
    assert ingest(p).text.split("\n") == ["NDA", "First clause.", "Second clause."]

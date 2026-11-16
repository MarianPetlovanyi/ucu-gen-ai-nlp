"""C2 Segmentation: contract text → spans (sentences and list items), the unit of evidence.

Tool component (no LLM): rule-based. Every line break is a boundary (as in ContractNLI). Inside a
line we split at sentence ends (with a legal-abbreviation list) and before inline enumerations
such as "; (b)" or "and (ii)". `method="lines"` is the baseline: one span per line.
"""

from __future__ import annotations

import re
from typing import Literal

from nda_review.schemas import Contract, Span

Method = Literal["rules", "lines"]

_ABBREV = {
    "inc",
    "ltd",
    "co",
    "corp",
    "llc",
    "plc",
    "no",
    "nos",
    "e.g",
    "i.e",
    "mr",
    "mrs",
    "ms",
    "dr",
    "st",
    "u.s",
    "u.k",
    "sec",
    "art",
    "para",
    "vs",
    "v",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "a.m",
    "p.m",
    "approx",
    "dept",
    "fig",
    "s.a",
    "n.v",
    "b.v",
    "gmbh",
    "pty",
    "cf",
    "viz",
    "ref",
    "tel",
    "esq",
    "jr",
    "sr",
    "et al",
    "incl",
    "max",
    "min",
}

# candidate sentence end: terminal punctuation (+ closing quotes/brackets) + space + a sentence start
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])[\"”’)\]]*\s+(?=[\"“‘(\[]?[A-Z0-9])")
# inline enumeration: ContractNLI cuts before every "(a)", "(ii)", "(3)" inside a line
_ENUM_BOUNDARY = re.compile(r"\s+(?=\((?:[a-zA-Z]|[ivxIVX]{1,4}|\d{1,2})\)\s)")
# a bare multi-level section number ("2.1 The Recipient ...") is its own span in ContractNLI
# (62% of such lines in train; see docs/crisp-dm/03-data-preparation.md)
_BARE_SECTION_NO = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2})+\s+(?=[A-Z])")
_LEADING_ENUM = re.compile(
    r"^\s*(?:\(?[A-Za-z0-9]{1,4}(?:\.\d{1,2})*[.)]|(?:Section|Article|Clause)\s+\S+)\s*$"
)


# "three (3) years", "thirty (30) days": a numeral restating a number word is not an enumerator
# (train: no span boundary in 576 of 583 cases; iteration 11 in 05-evaluation.md)
_NUM_WORD = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen"
    r"|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
    r"|hundred|thousand|million)"
)
_NUMBER_WORD_BEFORE = re.compile(rf"\b{_NUM_WORD}(?:[\s-]+{_NUM_WORD})*\s+$", re.IGNORECASE)


def _is_abbreviation(left: str) -> bool:
    """`left` is the text before a candidate boundary (ends with '.')."""
    m = re.search(r"(\S+)\.[\"”’)\]]*$", left)
    if not m:
        return False
    word = m.group(1).lower().lstrip("(“\"'")
    if word in _ABBREV or re.fullmatch(r"[a-z]", word):  # "et al." / initials "Barry I."
        return True
    # a bare enumerator such as "13." or "IV." or "a." at line start is a heading number
    return bool(_LEADING_ENUM.match(left))


def _split_line(line: str, offset: int) -> list[tuple[int, int]]:
    cuts = set()
    for m in _SENT_BOUNDARY.finditer(line):
        if not _is_abbreviation(line[: m.start()]):
            cuts.add(m.end())
    for m in _ENUM_BOUNDARY.finditer(line):
        if line[m.end() + 1 : m.end() + 2].isdigit() and _NUMBER_WORD_BEFORE.search(
            line[: m.end()]
        ):
            continue
        cuts.add(m.end())
    m = _BARE_SECTION_NO.match(line)
    if m:
        cuts.add(m.end())
    bounds = [0, *sorted(c for c in cuts if 0 < c < len(line)), len(line)]
    out = []
    for s, e in zip(bounds, bounds[1:], strict=False):
        seg = line[s:e]
        if seg.strip():
            lead = len(seg) - len(seg.lstrip())
            out.append((offset + s + lead, offset + s + len(seg.rstrip())))
    return out


def segment(text: str, doc_id: str = "uploaded", method: Method = "rules") -> Contract:
    """C2 entry point: returns the contract with numbered spans (ids are 0-based, in order)."""
    offsets: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        if line.strip():
            if method == "lines":
                lead = len(line) - len(line.lstrip())
                offsets.append((pos + lead, pos + len(line.rstrip())))
            else:
                offsets += _split_line(line, pos)
        pos += len(line) + 1
    spans = [Span(id=i, start=s, end=e, text=text[s:e]) for i, (s, e) in enumerate(offsets)]
    return Contract(doc_id=doc_id, text=text, spans=spans)

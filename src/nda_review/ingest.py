"""C1 Ingestion: PDF / HTML / TXT file → plain text with one paragraph or list item per line.

Tool component (no LLM): PyMuPDF for PDF layout blocks, the stdlib HTML parser, and reflow heuristics
that undo hard line wrapping, hyphenation, page numbers and repeated headers/footers.
`method="naive"` is the baseline: raw text extraction with the original line breaks.
"""

from __future__ import annotations

import collections
import html
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from nda_review.schemas import IngestResult

log = logging.getLogger(__name__)
Method = Literal["reflow", "naive"]

_PAGE_NO = re.compile(
    r"^\s*(?:page\s*)?[-–—]?\s*\d{1,3}\s*[-–—]?\s*(?:(?:/|of)\s*\d{1,3})?\s*$|^\s*<page>\s*$",
    re.IGNORECASE,
)
_ENUM_START = re.compile(
    r"^\s*(?:\(?[a-zA-Z]{1,2}\)|\(?[ivxlIVXL]{1,5}\)|\(?\d{1,2}(?:\.\d{1,2})*[.)]|•|-\s|[A-Z]\.\s)"
)
_SENT_END = re.compile(r"[.:;!?][\"”’)]?\s*$")
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "tr",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "ul",
    "ol",
    "blockquote",
    "center",
    "dd",
    "dt",
    "hr",
    "section",
    "article",
    "body",
    "title",
    "td",
}
_SKIP_TAGS = {"script", "style", "head", "title"}


def _clean_line(line: str) -> str:
    return re.sub(r"[ \t ​]+", " ", line).strip()


def _join_wrapped(lines: list[str]) -> str:
    """Join hard-wrapped lines of one paragraph, undoing end-of-line hyphenation."""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if not out:
            out = ln
        elif re.search(r"[a-z]-$", out) and ln[:1].islower():
            out = out[:-1] + ln
        else:
            out = f"{out} {ln}"
    return out


def _split_list_items(lines: list[str]) -> list[list[str]]:
    """Inside a block, start a new paragraph where a line starts with an enumerator
    and the previous line ended a sentence (or the clause list continues)."""
    groups: list[list[str]] = []
    for ln in lines:
        if groups and not (_ENUM_START.match(ln) and _SENT_END.search(groups[-1][-1])):
            groups[-1].append(ln)
        else:
            groups.append([ln])
    return groups


# --- PDF ------------------------------------------------------------------------------------
def _pdf_blocks(path: Path) -> tuple[list[list[list[str]]], int]:
    import pymupdf

    pages = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            blocks = []
            for b in page.get_text("blocks", sort=True):
                if b[6] != 0:  # image block
                    continue
                lines = [_clean_line(x) for x in b[4].split("\n")]
                lines = [x for x in lines if x]
                if lines:
                    blocks.append(lines)
            pages.append(blocks)
        return pages, len(pages)


def _repeated_margins(pages: list[list[list[str]]]) -> set[str]:
    """Header/footer lines: first/last two blocks that repeat (digits ignored) on ≥50% of pages."""
    if len(pages) < 3:
        return set()
    counts: collections.Counter = collections.Counter()
    for blocks in pages:
        keys = {re.sub(r"\d+", "#", " ".join(b)) for b in blocks[:2] + blocks[-2:]}
        counts.update(keys)
    return {k for k, c in counts.items() if c >= max(3, len(pages) // 2) and len(k) < 200}


def _ingest_pdf(path: Path, method: Method) -> IngestResult:
    import pymupdf

    if method == "naive":
        with pymupdf.open(path) as pdf:
            text = "".join(p.get_text() for p in pdf)
            n = len(pdf)
        lines = [_clean_line(x) for x in text.split("\n")]
        return IngestResult(text="\n".join(x for x in lines if x), source_format="pdf", n_pages=n)

    pages, n_pages = _pdf_blocks(path)
    margins = _repeated_margins(pages)
    paragraphs: list[str] = []
    for blocks in pages:
        for b in blocks:
            if re.sub(r"\d+", "#", " ".join(b)) in margins:
                continue
            b = [x for x in b if not _PAGE_NO.match(x)]
            for group in _split_list_items(b):
                para = _join_wrapped(group)
                if para:
                    paragraphs.append(para)
    paragraphs = _merge_page_breaks(paragraphs)
    warnings = []
    if sum(len(p) for p in paragraphs) < 200 * max(1, n_pages):
        warnings.append("very little text extracted: the PDF may be scanned (OCR not supported)")
    return IngestResult(
        text="\n".join(paragraphs), source_format="pdf", n_pages=n_pages, warnings=warnings
    )


def _merge_page_breaks(paragraphs: list[str]) -> list[str]:
    """A paragraph that ends without punctuation followed by one starting in lower case is one
    sentence split by a page or column break."""
    out: list[str] = []
    for p in paragraphs:
        if out and not _SENT_END.search(out[-1]) and p[:1].islower():
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return out


# --- TXT ------------------------------------------------------------------------------------
def _reflow_plain(text: str) -> str:
    """Plain text with hard wraps: paragraphs are separated by blank lines or indentation."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    paragraphs: list[str] = []
    for chunk in re.split(r"\n\s*\n", text):
        lines = [ln for ln in chunk.split("\n") if ln.strip() and not _PAGE_NO.match(ln)]
        if not lines:
            continue
        # an indented line or an enumerator after a finished sentence starts a new paragraph
        groups: list[list[str]] = []
        for ln in lines:
            new_para = bool(groups) and (
                (_ENUM_START.match(ln) and _SENT_END.search(groups[-1][-1]))
                or (re.match(r"^\s{4,}\S", ln) and _SENT_END.search(groups[-1][-1]))
            )
            if not groups or new_para:
                groups.append([ln])
            else:
                groups[-1].append(ln)
        paragraphs += [p for p in (_join_wrapped(g) for g in groups) if p]
    return "\n".join(_clean_line(p) for p in paragraphs)


def _ingest_txt(path: Path, method: Method) -> IngestResult:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if method == "naive":
        lines = [_clean_line(x) for x in raw.splitlines()]
        return IngestResult(text="\n".join(x for x in lines if x), source_format="txt")
    return IngestResult(text=_reflow_plain(raw), source_format="txt")


# --- HTML -----------------------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.pre = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in _SKIP_TAGS:
            self.skip += 1
        elif tag == "pre":
            self.pre += 1
            self.parts.append("\n\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n" if tag != "td" else " ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.parts.append("\n\n")
        elif tag == "td":
            self.parts.append(" ")  # table cells of one row form one line (e.g. "1." | "Text")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.pre:
            self.parts.append(f"\x00PRE{data}\x00")  # keep line structure of <pre> blocks
        else:
            self.parts.append(re.sub(r"\s+", " ", data))


def _ingest_html(path: Path, method: Method) -> IngestResult:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if method == "naive":
        text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        lines = [_clean_line(x) for x in text.splitlines()]
        return IngestResult(text="\n".join(x for x in lines if x), source_format="html")
    parser = _TextExtractor()
    parser.feed(raw)
    joined = "".join(parser.parts)
    out_lines: list[str] = []
    for piece in re.split(r"\x00", joined):
        if piece.startswith("PRE"):
            out_lines += _reflow_plain(piece[3:]).split("\n")
        else:
            out_lines += [_clean_line(x) for x in piece.split("\n")]
    out_lines = [x for x in out_lines if x and not _PAGE_NO.match(x)]
    return IngestResult(text="\n".join(out_lines), source_format="html")


_LONE_ENUM = re.compile(r"^\(?(?:\d{1,2}(?:\.\d{1,2})*|[a-zA-Z]|[ivxlIVXL]{1,5})[.)]?$")


def merge_broken_lines(text: str) -> str:
    """Format-independent repair: attach a lone enumerator ("1.", "(a)") to the following line, and
    join a line that does not end a sentence with a following line that starts in lower case."""
    out: list[str] = []
    for ln in text.split("\n"):
        if out and (
            _LONE_ENUM.match(out[-1]) or (not _SENT_END.search(out[-1]) and ln[:1].islower())
        ):
            out[-1] = f"{out[-1]} {ln}"
        else:
            out.append(ln)
    return "\n".join(out)


def ingest(path: str | Path, method: Method = "reflow") -> IngestResult:
    """C1 entry point. Detects the format from the file extension."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        res = _ingest_pdf(path, method)
    elif ext in (".htm", ".html"):
        res = _ingest_html(path, method)
    elif ext in (".txt", ".text", ".md", ""):
        res = _ingest_txt(path, method)
    else:
        raise ValueError(f"unsupported file type: {ext}")
    if method == "reflow":
        res.text = merge_broken_lines(res.text)
    return res


def ingest_text(text: str) -> IngestResult:
    """For pasted text: treat as plain text with possible hard wraps."""
    return IngestResult(text=merge_broken_lines(_reflow_plain(text)), source_format="txt")

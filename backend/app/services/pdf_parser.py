"""PDF -> list of (page_number, text).

Page numbers are kept so every chunk (and therefore every citation) can point
at a 1-based page.
"""

import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfParseError(Exception):
    """The file couldn't be parsed or contains no extractable text."""


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based
    text: str


_SPACES = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_PAGE_LABEL = re.compile(r"^(page\s+)?\d+(\s*(/|of)\s*\d+)?$", re.IGNORECASE)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces, trim each line, and cap blank-line runs.

    Single newlines are kept: in PDFs they often separate table cells or list
    items, which makes them useful split points for the chunker.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def _strip_running_headers(pages: list[str]) -> list[str]:
    """Remove running headers/footers (lines repeated on most pages) and bare page labels.

    Repeated boilerplate like "Company | Title" on every page adds nothing to
    any chunk and makes unrelated chunks look similar to the embedding model.
    Only applied to multi-page documents; with one page nothing "repeats".
    """
    if len(pages) < 2:
        return [
            "\n".join(ln for ln in p.split("\n") if not _PAGE_LABEL.match(ln.strip())).strip() for p in pages
        ]
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({ln for ln in page.split("\n") if ln.strip()})
    threshold = max(2, int(len(pages) * 0.6 + 0.5))
    repeated = {ln for ln, n in counts.items() if n >= threshold}
    cleaned = []
    for page in pages:
        keep = [ln for ln in page.split("\n") if ln not in repeated and not _PAGE_LABEL.match(ln.strip())]
        cleaned.append("\n".join(keep).strip())
    return cleaned


def parse_pdf(data: bytes) -> tuple[list[PageText], int]:
    """Extract normalized text page by page.

    Returns (non-empty pages, total page count). Raises PdfParseError for
    corrupt/encrypted files or PDFs with no text layer (e.g. scanned images,
    which would need OCR).
    """
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise PdfParseError("PDF is password-protected")
        raw = [normalize_whitespace(page.extract_text() or "") for page in reader.pages]
    except PdfReadError as exc:
        raise PdfParseError(f"Could not read PDF: {exc}") from exc

    page_count = len(raw)
    cleaned = _strip_running_headers(raw)
    pages = [PageText(i, text) for i, text in enumerate(cleaned, start=1) if text]
    if not pages:
        raise PdfParseError("No extractable text found (the PDF may be scanned images)")
    return pages, page_count

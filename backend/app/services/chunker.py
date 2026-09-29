"""Recursive character text splitting with overlap.

Strategy: try to split on the "largest" natural boundary first (paragraph),
and only fall back to smaller ones (line -> sentence -> word -> character)
for pieces that are still too long. Small pieces are then greedily merged back
up to `chunk_size`, and the tail of each chunk is repeated at the start of the
next (`overlap`) so a fact that straddles a boundary is still retrievable.

Chunks never span two pages: each page is chunked independently. That keeps
every citation to a single page number (see docs/DECISIONS.md).
"""

import math
import re
from dataclasses import dataclass

from app.services.pdf_parser import PageText

# (split pattern, string used to re-join pieces), from coarsest to finest.
_SEPARATORS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\n\s*\n"), "\n\n"),  # paragraphs
    (re.compile(r"\n"), "\n"),  # lines (table cells, list items)
    (re.compile(r"(?<=[.!?])\s+"), " "),  # sentences (keeps the punctuation)
    (re.compile(r"\s+"), " "),  # words
]


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    page_number: int
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token for English).

    Good enough for context budgeting and logging; exact counts would need the
    specific LLM's tokenizer, which differs per provider.
    """
    return max(1, math.ceil(len(text) / 4))


def _merge(pieces: list[str], joiner: str, size: int, overlap: int) -> list[str]:
    """Greedily pack pieces into chunks <= size, carrying up to `overlap` chars forward."""
    chunks: list[str] = []
    current: list[str] = []
    length = 0  # length of joiner.join(current)
    for piece in pieces:
        added = len(piece) + (len(joiner) if current else 0)
        if current and length + added > size:
            chunks.append(joiner.join(current))
            # Drop pieces from the front until what remains fits in the overlap
            # budget *and* leaves room for the new piece.
            while current and (length > overlap or length + len(piece) + len(joiner) > size):
                length -= len(current[0]) + (len(joiner) if len(current) > 1 else 0)
                current.pop(0)
            added = len(piece) + (len(joiner) if current else 0)
        current.append(piece)
        length += added
    if current:
        chunks.append(joiner.join(current))
    return chunks


def _split(text: str, size: int, overlap: int, level: int = 0) -> list[str]:
    if len(text) <= size:
        return [text]
    if level >= len(_SEPARATORS):
        # No boundary left (e.g. a 2,000-char URL): hard cut with overlap.
        step = max(1, size - overlap)
        return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]

    pattern, joiner = _SEPARATORS[level]
    pieces = [p.strip() for p in pattern.split(text) if p.strip()]
    if len(pieces) <= 1:
        return _split(text, size, overlap, level + 1)

    out: list[str] = []
    pending: list[str] = []
    for piece in pieces:
        if len(piece) <= size:
            pending.append(piece)
        else:
            if pending:
                out.extend(_merge(pending, joiner, size, overlap))
                pending = []
            out.extend(_split(piece, size, overlap, level + 1))
    if pending:
        out.extend(_merge(pending, joiner, size, overlap))
    return out


def split_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split one block of text into overlapping chunks of at most `chunk_size` characters."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")
    text = text.strip()
    if not text:
        return []
    return [c for c in _split(text, chunk_size, overlap) if c.strip()]


def chunk_pages(pages: list[PageText], chunk_size: int = 800, overlap: int = 150) -> list[TextChunk]:
    """Chunk each page independently and number chunks across the whole document."""
    chunks: list[TextChunk] = []
    for page in pages:
        for content in split_text(page.text, chunk_size, overlap):
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    page_number=page.page_number,
                    content=content,
                    token_count=estimate_tokens(content),
                )
            )
    return chunks

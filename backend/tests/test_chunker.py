"""Unit tests for text normalization, header stripping and chunking."""

import pytest

from app.services.chunker import chunk_pages, estimate_tokens, split_text
from app.services.pdf_parser import PageText, PdfParseError, normalize_whitespace, parse_pdf
from tests.helpers import make_pdf

SENTENCES = " ".join(f"Sentence number {i} talks about topic {i}." for i in range(200))


def test_empty_input_gives_no_chunks() -> None:
    assert split_text("") == []
    assert split_text("   \n\n  ") == []
    assert chunk_pages([]) == []


def test_short_text_is_one_chunk() -> None:
    assert split_text("Hello world.", chunk_size=800, overlap=150) == ["Hello world."]


def test_chunks_respect_max_size() -> None:
    chunks = split_text(SENTENCES, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_consecutive_chunks_overlap() -> None:
    chunks = split_text(SENTENCES, chunk_size=300, overlap=80)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        # The next chunk starts with text copied from the end of the previous one.
        assert nxt[:20] in prev, (prev, nxt)


def test_zero_overlap_has_no_repeated_text() -> None:
    chunks = split_text(SENTENCES, chunk_size=300, overlap=0)
    assert " ".join(chunks) == SENTENCES


def test_no_text_is_lost() -> None:
    chunks = split_text(SENTENCES, chunk_size=250, overlap=60)
    for i in range(200):
        assert any(f"Sentence number {i} talks" in c for c in chunks), i


def test_splits_on_paragraphs_first() -> None:
    para_a = "Alpha paragraph. " * 10
    para_b = "Beta paragraph. " * 10
    chunks = split_text(f"{para_a.strip()}\n\n{para_b.strip()}", chunk_size=200, overlap=0)
    assert len(chunks) == 2
    assert chunks[0].startswith("Alpha") and "Beta" not in chunks[0]
    assert chunks[1].startswith("Beta")


def test_sentence_boundaries_preserved() -> None:
    chunks = split_text(SENTENCES, chunk_size=300, overlap=0)
    assert all(c.endswith(".") for c in chunks)


def test_giant_word_is_hard_split() -> None:
    blob = "x" * 2000
    chunks = split_text(blob, chunk_size=500, overlap=100)
    assert all(len(c) <= 500 for c in chunks)
    assert chunks[0] == "x" * 500


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        split_text("abc", chunk_size=100, overlap=100)
    with pytest.raises(ValueError):
        split_text("abc", chunk_size=0, overlap=0)


def test_chunks_never_cross_pages() -> None:
    pages = [PageText(1, "Page one text. " * 100), PageText(2, "Page two text. " * 100)]
    chunks = chunk_pages(pages, chunk_size=300, overlap=50)
    for c in chunks:
        if c.page_number == 1:
            assert "two" not in c.content
        else:
            assert "one" not in c.content
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.page_number for c in chunks} == {1, 2}
    assert all(c.token_count == estimate_tokens(c.content) for c in chunks)


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("a  \t b\r\n\n\n\nc  ") == "a b\n\nc"


def test_parse_pdf_keeps_pages_and_strips_running_headers() -> None:
    header = "Acme Corp | Handbook"
    pdf = make_pdf(
        [
            f"{header}\nPage 1\nThe first page is about leave.",
            f"{header}\nPage 2\n",  # only header -> becomes empty and is skipped
            f"{header}\nPage 3\nThe third page is about salaries.",
        ]
    )
    pages, page_count = parse_pdf(pdf)
    assert page_count == 3
    assert [p.page_number for p in pages] == [1, 3]
    assert pages[0].text == "The first page is about leave."
    assert all(header not in p.text and "Page" not in p.text for p in pages)


def test_parse_pdf_rejects_textless_pdf() -> None:
    with pytest.raises(PdfParseError):
        parse_pdf(make_pdf([""]))


def test_parse_pdf_rejects_garbage() -> None:
    with pytest.raises(PdfParseError):
        parse_pdf(b"%PDF-1.4 this is not really a pdf")

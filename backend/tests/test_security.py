"""Security tests: upload validation and security helpers.

(Prompt-injection tests are added with the chat pipeline.)
"""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.utils.upload_validation import sanitize_filename
from tests.helpers import make_pdf

PDF = make_pdf(["Hello world, this is a test document."])


async def _post(client: AsyncClient, headers: dict, name: str, data: bytes, mime: str) -> tuple[int, dict]:
    r = await client.post("/api/documents", headers=headers, files=[("files", (name, data, mime))])
    return r.status_code, r.json()


# --- Upload validation ---------------------------------------------------------


async def test_rejects_non_pdf_extension(client: AsyncClient, auth_headers: dict) -> None:
    status, body = await _post(client, auth_headers, "notes.txt", PDF, "application/pdf")
    assert status == 415
    assert body["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


async def test_rejects_wrong_mime_type(client: AsyncClient, auth_headers: dict) -> None:
    status, _ = await _post(client, auth_headers, "doc.pdf", PDF, "text/html")
    assert status == 415


async def test_rejects_renamed_non_pdf(client: AsyncClient, auth_headers: dict) -> None:
    # Right extension and MIME, wrong content: the magic-byte check must catch it.
    fake = b"MZ\x90\x00 this is actually an executable"
    status, body = await _post(client, auth_headers, "invoice.pdf", fake, "application/pdf")
    assert status == 415
    assert "not a valid PDF" in body["error"]["message"]


async def test_rejects_html_disguised_as_pdf(client: AsyncClient, auth_headers: dict) -> None:
    status, _ = await _post(
        client, auth_headers, "x.pdf", b"<html><script>alert(1)</script>", "application/pdf"
    )
    assert status == 415


async def test_rejects_empty_file(client: AsyncClient, auth_headers: dict) -> None:
    status, body = await _post(client, auth_headers, "empty.pdf", b"", "application/pdf")
    assert status == 400
    assert body["error"]["code"] == "EMPTY_FILE"


async def test_rejects_oversized_file(client: AsyncClient, auth_headers: dict, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = PDF + b"0" * (1024 * 1024)
    status, body = await _post(client, auth_headers, "big.pdf", big, "application/pdf")
    assert status == 413
    assert body["error"]["code"] == "FILE_TOO_LARGE"


async def test_bad_file_in_batch_rejects_whole_batch(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.post(
        "/api/documents",
        headers=auth_headers,
        files=[
            ("files", ("good.pdf", PDF, "application/pdf")),
            ("files", ("bad.pdf", b"nope", "application/pdf")),
        ],
    )
    assert r.status_code == 415
    assert (await client.get("/api/documents", headers=auth_headers)).json() == []


async def test_path_traversal_filename_is_neutralized(client: AsyncClient, auth_headers: dict) -> None:
    status, body = await _post(client, auth_headers, "../../etc/passwd.pdf", PDF, "application/pdf")
    assert status == 202
    assert body[0]["filename"] == "passwd.pdf"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../secret.pdf", "secret.pdf"),
        ("C:\\Users\\me\\file.pdf", "file.pdf"),
        ("bad\x00name.pdf", "badname.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_long_names() -> None:
    name = sanitize_filename("a" * 400 + ".pdf")
    assert len(name) <= 255 and name.endswith(".pdf")


# --- Security helpers ----------------------------------------------------------


def test_password_hash_roundtrip() -> None:
    h = hash_password("Correct Horse 1")
    assert h != "Correct Horse 1" and h.startswith("$2")
    assert verify_password("Correct Horse 1", h)
    assert not verify_password("correct horse 1", h)
    assert hash_password("same") != hash_password("same")  # salted


def test_verify_password_handles_malformed_hash() -> None:
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_token_roundtrip() -> None:
    import uuid

    uid = uuid.uuid4()
    assert decode_access_token(create_access_token(uid)) == uid
    assert decode_access_token("garbage") is None

"""Upload validation: never trust the client's filename or Content-Type alone.

Three independent checks, because each is easy to spoof on its own:
1. extension (.pdf)  2. declared MIME type  3. magic bytes (`%PDF-` header).
Plus a size limit enforced while reading, so an oversized upload can't
exhaust memory before we notice.
"""

import re
import unicodedata
from pathlib import PurePath

from fastapi import UploadFile

from app.core.errors import AppError

PDF_MAGIC = b"%PDF-"
ALLOWED_MIME_TYPES = {"application/pdf", "application/x-pdf"}
MAX_FILES_PER_REQUEST = 10
_UNSAFE_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]")


def sanitize_filename(raw: str | None) -> str:
    """Make a user-supplied filename safe to store and display (it is never used as a path)."""
    name = PurePath((raw or "").replace("\\", "/")).name  # drop any directory components
    name = unicodedata.normalize("NFC", name)
    name = _UNSAFE_CHARS.sub("", name).strip() or "document.pdf"
    if len(name) > 255:
        stem, _, ext = name.rpartition(".")
        name = f"{stem[: 250 - len(ext)]}.{ext}" if stem else name[:255]
    return name


def validate_pdf_bytes(filename: str, content_type: str | None, data: bytes, max_bytes: int) -> None:
    """Raise AppError unless the upload looks like a real PDF within the size limit."""
    if not filename.lower().endswith(".pdf"):
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", f"{filename}: only .pdf files are accepted")
    if (content_type or "").split(";")[0].strip().lower() not in ALLOWED_MIME_TYPES:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", f"{filename}: file type must be application/pdf")
    if len(data) > max_bytes:
        raise AppError(
            413, "FILE_TOO_LARGE", f"{filename}: exceeds the {max_bytes // (1024 * 1024)} MB size limit"
        )
    if len(data) == 0:
        raise AppError(400, "EMPTY_FILE", f"{filename}: file is empty")
    if not data.startswith(PDF_MAGIC):
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", f"{filename}: file content is not a valid PDF")


async def read_and_validate(upload: UploadFile, max_bytes: int) -> tuple[str, bytes]:
    """Read at most max_bytes+1 bytes (enough to detect 'too large') and validate."""
    filename = sanitize_filename(upload.filename)
    data = await upload.read(max_bytes + 1)
    validate_pdf_bytes(filename, upload.content_type, data, max_bytes)
    return filename, data

"""Local file storage for uploaded PDFs.

Files are stored under a server-generated UUID name, never the user-supplied
filename, which rules out path traversal (`../../etc/passwd`), collisions and
odd characters. The original name is kept only as display metadata in the DB.
Swapping this module for S3/GCS would not affect the rest of the app.
"""

import asyncio
import uuid
from pathlib import Path

from app.core.config import get_settings


def _root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve(storage_path: str) -> Path:
    """Resolve a stored relative path and refuse anything outside the upload root."""
    root = _root()
    path = (root / storage_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("storage path escapes upload directory")
    return path


async def save_upload(data: bytes) -> str:
    """Write bytes to a new UUID-named file and return its path relative to the upload root."""
    name = f"{uuid.uuid4().hex}.pdf"
    await asyncio.to_thread((_root() / name).write_bytes, data)
    return name


async def read_upload(storage_path: str) -> bytes:
    return await asyncio.to_thread(_resolve(storage_path).read_bytes)


async def delete_upload(storage_path: str) -> None:
    await asyncio.to_thread(_resolve(storage_path).unlink, True)

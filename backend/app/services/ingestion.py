"""Ingestion pipeline: parse -> chunk -> embed -> store.

Runs as a FastAPI BackgroundTask after the upload response has been sent, so
the user isn't kept waiting. It opens its *own* DB session: the request's
session is closed by the time a background task runs.
"""

import asyncio
import logging
import time
import uuid
from pathlib import PurePath

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Chunk, Document, DocumentStatus
from app.db.session import SessionLocal
from app.services.chunker import TextChunk, chunk_pages
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.pdf_parser import PdfParseError, parse_pdf
from app.utils.storage import read_upload

logger = logging.getLogger(__name__)


def document_title(filename: str) -> str:
    """'Orbitra_Vault_Product_Guide.pdf' -> 'Orbitra Vault Product Guide'."""
    return PurePath(filename).stem.replace("_", " ").replace("-", " ").strip()


def embedding_text(title: str, chunk: TextChunk) -> str:
    """Text that gets embedded for a chunk: the document title + the chunk.

    Prepending the title ("contextual chunk header") lets queries like
    "according to the vendor notes…" match chunks whose body never names the
    document. Only the embedding sees the title; `content` stays verbatim.
    """
    return f"{title}\n{chunk.content}"


async def _store_chunks(
    db: AsyncSession,
    document_id: uuid.UUID,
    chunks: list[TextChunk],
    vectors: list[list[float]],
) -> None:
    """Bulk insert in a single statement (executemany), not one INSERT per chunk."""
    rows = [
        {
            "id": uuid.uuid4(),
            "document_id": document_id,
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
            "content": c.content,
            "token_count": c.token_count,
            "embedding": v,
        }
        for c, v in zip(chunks, vectors, strict=True)
    ]
    await db.execute(insert(Chunk), rows)


async def ingest_document(document_id: uuid.UUID, embedder: EmbeddingProvider | None = None) -> None:
    """Process one uploaded document and set its status to `ready` or `failed`.

    Never raises: any failure is recorded on the document row so the UI can
    show it, instead of disappearing into a background-task traceback.
    """
    settings = get_settings()
    embedder = embedder or get_embedding_provider()
    started = time.perf_counter()

    async with SessionLocal() as db:
        doc = await db.get(Document, document_id)
        if doc is None:  # deleted before processing started
            return
        try:
            data = await read_upload(doc.storage_path)
            # pypdf is pure-Python and CPU-bound: keep it off the event loop.
            pages, page_count = await asyncio.to_thread(parse_pdf, data)
            chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)

            title = document_title(doc.filename)
            vectors: list[list[float]] = []
            batch = settings.embedding_batch_size
            for i in range(0, len(chunks), batch):
                texts = [embedding_text(title, c) for c in chunks[i : i + batch]]
                vectors.extend(await embedder.embed_documents(texts))

            # Chunks + status flip commit together: a document is never "ready"
            # with half its chunks, and a failure leaves no orphan chunks.
            await _store_chunks(db, doc.id, chunks, vectors)
            await db.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(
                    status=DocumentStatus.ready,
                    page_count=page_count,
                    chunk_count=len(chunks),
                    error_message=None,
                )
            )
            await db.commit()
            logger.info(
                "ingestion_done",
                extra={
                    "document_id": str(doc.id),
                    "pages": page_count,
                    "chunks": len(chunks),
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded
            await db.rollback()
            message = str(exc) if isinstance(exc, PdfParseError) else "Processing failed unexpectedly"
            logger.exception("ingestion_failed", extra={"document_id": str(document_id)})
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.failed, error_message=message)
            )
            await db.commit()


async def fail_stale_processing_documents() -> int:
    """On startup, mark documents stuck in `processing` as failed.

    BackgroundTasks live in process memory; if the server restarted mid-ingestion
    those jobs are gone. (A durable queue like Celery/RQ would retry them instead.)
    """
    async with SessionLocal() as db:
        result = await db.execute(
            update(Document)
            .where(Document.status == DocumentStatus.processing)
            .values(
                status=DocumentStatus.failed,
                error_message="Processing was interrupted by a server restart. Upload the file again.",
            )
        )
        await db.commit()
        return result.rowcount or 0

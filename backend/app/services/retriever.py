"""Vector retrieval over the current user's chunks with pgvector.

Security property: the user filter is applied *inside* the SQL query (join to
documents.user_id), never as a post-filter in Python, so another user's text
can't reach the prompt even by accident.
"""

import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    content: str
    score: float  # cosine similarity in [-1, 1]; higher is more similar


async def search_chunks(
    db: AsyncSession,
    query_vector: list[float],
    user_id: uuid.UUID,
    top_k: int,
    min_similarity: float,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks by cosine similarity, dropping those below `min_similarity`.

    `<=>` is pgvector's cosine *distance* (1 - similarity). Ordering by the raw
    distance expression lets Postgres use the HNSW index; the threshold is then
    applied to the small top-k result rather than in the WHERE clause (a WHERE on
    distance would prevent the index-ordered scan).
    """
    distance = Chunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(Chunk, Document.filename, distance.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.user_id == user_id, Document.status == DocumentStatus.ready)
        .order_by(distance)
        .limit(top_k)
    )
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))

    rows = (await db.execute(stmt)).all()
    results = [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            page_number=chunk.page_number,
            content=chunk.content,
            score=round(1.0 - float(dist), 4),
        )
        for chunk, filename, dist in rows
    ]
    return [r for r in results if r.score >= min_similarity]


async def retrieve(
    db: AsyncSession,
    embedder: EmbeddingProvider,
    query: str,
    user_id: uuid.UUID,
    top_k: int,
    min_similarity: float,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """Embed the query, search, and log retrieval latency and hit count."""
    started = time.perf_counter()
    vector = await embedder.embed_query(query)
    embed_ms = (time.perf_counter() - started) * 1000
    results = await search_chunks(db, vector, user_id, top_k, min_similarity, document_ids)
    logger.info(
        "retrieval",
        extra={
            "embed_ms": round(embed_ms, 1),
            "retrieval_ms": round((time.perf_counter() - started) * 1000, 1),
            "chunks_retrieved": len(results),
            "top_score": results[0].score if results else None,
        },
    )
    return results

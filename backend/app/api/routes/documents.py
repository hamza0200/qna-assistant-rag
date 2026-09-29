"""Document upload, listing, status polling and deletion; chunk lookup for citations.

Every query is scoped to the current user. Accessing someone else's document
returns 404 (not 403) so the API doesn't confirm that the ID exists.
"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.core.rate_limit import limiter, upload_limit
from app.db.models import Chunk, Document, DocumentStatus, User
from app.schemas.documents import ChunkOut, DocumentOut
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.ingestion import ingest_document
from app.utils.storage import delete_upload, save_upload
from app.utils.upload_validation import MAX_FILES_PER_REQUEST, read_and_validate

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


def get_embedder() -> EmbeddingProvider:
    """Dependency wrapper so tests can swap in a fake embedder."""
    return get_embedding_provider()


async def _get_owned_document(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    doc = (
        await db.execute(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document")
    return doc


@router.post("/documents", response_model=list[DocumentOut], status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(upload_limit)
async def upload_documents(
    request: Request,
    background: BackgroundTasks,
    files: list[UploadFile] = File(..., description="One or more PDF files"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedder: EmbeddingProvider = Depends(get_embedder),
) -> list[Document]:
    """Validate and store PDFs, then ingest them in the background.

    Returns 202 Accepted with `status=processing`; clients poll
    GET /documents/{id} until the status becomes `ready` or `failed`.
    All files are validated before any is saved, so a bad file in a batch
    doesn't leave a half-accepted upload behind.
    """
    if not files:
        raise AppError(400, "NO_FILES", "No files were uploaded")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise AppError(400, "TOO_MANY_FILES", f"Upload at most {MAX_FILES_PER_REQUEST} files at a time")

    max_bytes = get_settings().max_upload_bytes
    validated = [await read_and_validate(f, max_bytes) for f in files]

    docs: list[Document] = []
    for filename, data in validated:
        storage_path = await save_upload(data)
        doc = Document(
            user_id=user.id,
            filename=filename,
            storage_path=storage_path,
            status=DocumentStatus.processing,
        )
        db.add(doc)
        docs.append(doc)
    await db.commit()

    for doc in docs:
        await db.refresh(doc)
        background.add_task(ingest_document, doc.id, embedder)
    logger.info("documents_uploaded", extra={"count": len(docs), "user_id": str(user.id)})
    return docs


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Document]:
    result = await db.execute(
        select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
    )
    return list(result.scalars())


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Document:
    return await _get_owned_document(db, user, document_id)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete the row (chunks cascade via ON DELETE CASCADE) and then the file."""
    doc = await _get_owned_document(db, user, document_id)
    storage_path = doc.storage_path
    await db.delete(doc)
    await db.commit()
    # File removal after the commit: if it fails we leak a file (harmless, can be
    # swept), rather than having a DB row that points at a missing file.
    try:
        await delete_upload(storage_path)
    except OSError:
        logger.warning("file_delete_failed", extra={"document_id": str(document_id)})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
async def get_chunk(
    chunk_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ChunkOut:
    """Full chunk text for the citation viewer. Ownership is enforced through the parent document."""
    row = (
        await db.execute(
            select(Chunk, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id == chunk_id, Document.user_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Chunk")
    chunk, filename = row
    return ChunkOut(
        id=chunk.id,
        document_id=chunk.document_id,
        filename=filename,
        page_number=chunk.page_number,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
    )

"""Streaming chat endpoint (SSE) and conversation history routes."""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.api.routes.documents import get_embedder
from app.core.errors import NotFoundError
from app.core.rate_limit import chat_limit, limiter
from app.db.models import Conversation, User
from app.schemas.chat import ChatRequest, ConversationDetail, ConversationSummary
from app.services.embeddings import EmbeddingProvider
from app.services.llm import LLMProvider, get_llm_provider
from app.services.rag import ChatInput, answer_stream, conversation_title

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


def get_llm_factory() -> Callable[[], LLMProvider]:
    """Dependency returning a *factory*, so a missing API key becomes an SSE error
    event inside the stream rather than an exception before it starts. Overridden in tests."""
    return get_llm_provider


def sse(event: str, data: Any) -> str:
    """Format one Server-Sent Event frame. JSON-encoding keeps newlines in tokens safe."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _get_owned_conversation(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> Conversation:
    conv = (
        await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        )
    ).scalar_one_or_none()
    if conv is None:
        raise NotFoundError("Conversation")
    return conv


@router.post("/chat", response_class=StreamingResponse)
@limiter.limit(chat_limit)
async def chat(
    request: Request,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedder: EmbeddingProvider = Depends(get_embedder),
    llm_factory: Callable[[], LLMProvider] = Depends(get_llm_factory),
) -> StreamingResponse:
    """Answer a question about the user's documents as a text/event-stream.

    Validation, auth and conversation ownership are checked *before* the stream
    starts, so those failures are normal JSON errors with proper status codes.
    Once streaming, failures arrive as an `error` event (the 200 is already sent).
    """
    if body.conversation_id:
        conv = await _get_owned_conversation(db, user, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id, title=conversation_title(body.message))
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    inp = ChatInput(
        user_id=user.id, conversation_id=conv.id, message=body.message, document_ids=body.document_ids
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event, data in answer_stream(inp, embedder, llm_factory):
            yield sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Stop reverse proxies (nginx) from buffering the stream into one blob.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars())


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Conversation:
    # selectinload fetches all messages in one extra query (avoids N+1 lazy loads,
    # which async SQLAlchemy forbids anyway).
    conv = (
        await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        )
    ).scalar_one_or_none()
    if conv is None:
        raise NotFoundError("Conversation")
    return conv


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    conv = await _get_owned_conversation(db, user, conversation_id)
    await db.delete(conv)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

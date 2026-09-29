"""RAG orchestration: retrieve -> prompt -> stream -> citations -> persist.

`answer_stream` is an async generator of (event, data) pairs matching the SSE
contract documented in docs/API.md (meta, token*, citations, done | error). It knows
nothing about HTTP; the chat route turns the pairs into SSE frames.
"""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import anyio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Conversation, Message, MessageRole
from app.db.session import SessionLocal
from app.services.embeddings import EmbeddingProvider
from app.services.llm import LLMError, LLMProvider, LLMUsage
from app.services.prompts import (
    NO_CONTEXT_ANSWER,
    SYSTEM_PROMPT,
    build_messages,
    format_sources,
    retrieval_query,
)
from app.services.retriever import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

Event = tuple[str, Any]

_CITATION_REF = re.compile(r"\[(\d{1,2})\]")
SNIPPET_CHARS = 240


@dataclass
class ChatInput:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    message: str
    document_ids: list[uuid.UUID] | None


def conversation_title(message: str) -> str:
    """First line of the first question, trimmed to a sidebar-friendly length."""
    title = " ".join(message.split())
    return title if len(title) <= 60 else title[:57].rstrip() + "…"


def cited_indices(answer: str, max_index: int) -> list[int]:
    """Source numbers referenced as [n] in the answer, in first-mention order."""
    seen: list[int] = []
    for match in _CITATION_REF.finditer(answer):
        n = int(match.group(1))
        if 1 <= n <= max_index and n not in seen:
            seen.append(n)
    return seen


def build_citations(answer: str, sources: list[RetrievedChunk]) -> list[dict[str, Any]]:
    """Citations for the sources the answer actually referenced.

    Numbers keep their original [n] so inline markers match the chips. If the
    answer cites nothing (e.g. it's a "not found" reply), no chips are shown —
    showing sources that weren't used would imply support that isn't there.
    """
    citations = []
    for n in sorted(cited_indices(answer, len(sources))):
        s = sources[n - 1]
        snippet = " ".join(s.content.split())
        citations.append(
            {
                "index": n,
                "chunk_id": str(s.chunk_id),
                "document_id": str(s.document_id),
                "filename": s.filename,
                "page": s.page_number,
                "score": s.score,
                "snippet": snippet[:SNIPPET_CHARS] + ("…" if len(snippet) > SNIPPET_CHARS else ""),
            }
        )
    return citations


async def load_history(db: AsyncSession, conversation_id: uuid.UUID, limit: int) -> list[tuple[str, str]]:
    """Last `limit` messages (oldest first) as (role, content) pairs."""
    rows = (
        await db.execute(
            select(Message.role, Message.content)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).all()
    history = [(role.value, content) for role, content in reversed(rows)]
    # Providers require the conversation to start with a user turn.
    while history and history[0][0] != "user":
        history.pop(0)
    return history


async def retrieve_for_turn(
    db: AsyncSession,
    embedder: EmbeddingProvider,
    inp: ChatInput,
    previous_question: str | None,
) -> list[RetrievedChunk]:
    """Retrieve for the question alone, plus (for follow-ups) question+previous question; merge.

    Searching both ways means a follow-up like "and what SLA does it include?"
    still finds the Business-plan chunk, while an unrelated new question isn't
    dragged toward the previous topic.
    """
    s = get_settings()
    results = await retrieve(
        db, embedder, inp.message, inp.user_id, s.top_k, s.min_similarity, inp.document_ids
    )
    if previous_question:
        combined = retrieval_query(inp.message, previous_question)
        extra = await retrieve(
            db, embedder, combined, inp.user_id, s.top_k, s.min_similarity, inp.document_ids
        )
        by_id = {r.chunk_id: r for r in results}
        for r in extra:
            if r.chunk_id not in by_id or r.score > by_id[r.chunk_id].score:
                by_id[r.chunk_id] = r
        results = sorted(by_id.values(), key=lambda r: r.score, reverse=True)[: s.top_k]
    return results


async def _persist_assistant(
    message_id: uuid.UUID, conversation_id: uuid.UUID, content: str, citations: list[dict[str, Any]]
) -> None:
    async with SessionLocal() as db:
        db.add(
            Message(
                id=message_id,
                conversation_id=conversation_id,
                role=MessageRole.assistant,
                content=content,
                citations=citations,
            )
        )
        await db.execute(
            update(Conversation).where(Conversation.id == conversation_id).values(updated_at=func.now())
        )
        await db.commit()


async def answer_stream(
    inp: ChatInput,
    embedder: EmbeddingProvider,
    get_llm: Callable[[], LLMProvider],
) -> AsyncIterator[Event]:
    """Run one chat turn and yield SSE events.

    The user message is saved before anything else, so it survives LLM failures.
    The assistant message is saved when the answer completes — or, if the client
    disconnects / presses Stop, with whatever partial text was generated.
    """
    s = get_settings()
    started = time.perf_counter()
    assistant_id = uuid.uuid4()
    answer_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    completed = False
    usage = LLMUsage()
    sources: list[RetrievedChunk] = []

    async with SessionLocal() as db:
        history = await load_history(db, inp.conversation_id, s.history_messages)
        db.add(Message(conversation_id=inp.conversation_id, role=MessageRole.user, content=inp.message))
        await db.commit()

        yield "meta", {"conversation_id": str(inp.conversation_id), "message_id": str(assistant_id)}

        previous_question = next((c for r, c in reversed(history) if r == "user"), None)
        retrieved = await retrieve_for_turn(db, embedder, inp, previous_question)

    try:
        if not retrieved:
            # Nothing relevant: answer deterministically and skip the LLM call
            # entirely (no cost, no latency, no chance to hallucinate).
            answer_parts.append(NO_CONTEXT_ANSWER)
            yield "token", {"text": NO_CONTEXT_ANSWER}
        else:
            sources_text, sources = format_sources(retrieved, s.max_context_chars)
            messages = build_messages(inp.message, sources_text, history)
            llm = get_llm()
            async for text in llm.stream(SYSTEM_PROMPT, messages, usage):
                answer_parts.append(text)
                yield "token", {"text": text}
            citations = build_citations("".join(answer_parts), sources)

        yield "citations", citations
        completed = True
        yield "done", {}
    except LLMError as exc:
        logger.warning("llm_error", extra={"code": exc.code})
        yield "error", {"code": exc.code, "message": exc.message}
    finally:
        answer = "".join(answer_parts).strip()
        if not completed and answer:
            # Stopped or failed mid-answer: keep the partial text (the user saw it),
            # with the citations it had referenced so far.
            citations = build_citations(answer, sources)
        if answer:
            # Shielded: on client disconnect this generator is being cancelled, and
            # anyio would otherwise cancel the DB write too.
            with anyio.CancelScope(shield=True):
                await _persist_assistant(assistant_id, inp.conversation_id, answer, citations)
        logger.info(
            "chat_turn",
            extra={
                "conversation_id": str(inp.conversation_id),
                "completed": completed,
                "llm_called": bool(sources),
                "chunks_retrieved": len(retrieved),
                "chunks_in_prompt": len(sources),
                "citations": len(citations),
                "llm_model": usage.model or None,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "llm_first_token_ms": usage.first_token_ms,
                "llm_total_ms": usage.total_ms,
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )

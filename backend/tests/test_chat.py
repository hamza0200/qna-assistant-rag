"""Chat route tests with the LLM mocked.

The fake LLM records every prompt it receives, so tests can assert on what the
model *would* see (sources, history) and on whether it was called at all.
"""

import json
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.routes.chat import get_llm_factory
from app.core.config import get_settings
from app.db.models import Message
from app.db.session import SessionLocal
from app.main import app
from app.services.llm import LLMError, LLMProvider, LLMUsage
from app.services.prompts import NO_CONTEXT_ANSWER
from app.services.rag import ChatInput, answer_stream
from tests.conftest import fake_embedder
from tests.helpers import make_pdf

PRODUCT_PDF = make_pdf(
    [
        "Plans and pricing\nThe Business plan costs USD 29 per user per month billed annually.",
        "Uptime\nThe Business plan includes a 99.9% uptime SLA.",
    ]
)
HANDBOOK_PDF = make_pdf(["Annual leave\nEmployees receive 20 working days of annual leave per year."])


class FakeLLM(LLMProvider):
    def __init__(self, tokens: list[str] | None = None, fail_with: LLMError | None = None) -> None:
        self.tokens = tokens or ["The Business plan costs ", "USD 29 per user per month [1]."]
        self.fail_with = fail_with
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def stream(
        self, system: str, messages: list[dict[str, str]], usage: LLMUsage | None = None
    ) -> AsyncIterator[str]:
        self.calls.append((system, messages))
        for t in self.tokens:
            yield t
        if self.fail_with:
            raise self.fail_with
        if usage is not None:
            usage.model, usage.input_tokens, usage.output_tokens = "fake", 100, 20


@pytest.fixture
def fake_llm() -> AsyncIterator[FakeLLM]:
    llm = FakeLLM()
    app.dependency_overrides[get_llm_factory] = lambda: (lambda: llm)
    yield llm
    app.dependency_overrides.pop(get_llm_factory, None)


@pytest.fixture(autouse=True)
def _low_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    # The fake bag-of-words embedder produces lower similarities than the real model.
    monkeypatch.setattr(get_settings(), "min_similarity", 0.2)


def parse_sse(body: str) -> list[tuple[str, object]]:
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def upload(client: AsyncClient, headers: dict, name: str, data: bytes) -> str:
    r = await client.post(
        "/api/documents", headers=headers, files=[("files", (name, data, "application/pdf"))]
    )
    assert r.status_code == 202
    return r.json()[0]["id"]


async def ask(client: AsyncClient, headers: dict, message: str, **extra: object) -> list[tuple[str, object]]:
    r = await client.post("/api/chat", headers=headers, json={"message": message, **extra})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return parse_sse(r.text)


async def test_event_order_and_citations(client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM) -> None:
    await upload(client, auth_headers, "Vault_Product_Guide.pdf", PRODUCT_PDF)
    events = await ask(client, auth_headers, "How much does the Business plan cost per user?")

    names = [e for e, _ in events]
    assert names[0] == "meta"
    assert names[-2:] == ["citations", "done"]
    assert set(names[1:-2]) == {"token"}

    answer = "".join(d["text"] for e, d in events if e == "token")
    assert answer == "The Business plan costs USD 29 per user per month [1]."

    citations = dict(events)["citations"]
    assert len(citations) == 1  # only [1] was referenced
    c = citations[0]
    assert c["index"] == 1 and c["filename"] == "Vault_Product_Guide.pdf" and c["page"] == 1
    assert "USD 29" in c["snippet"]
    assert set(c) == {"index", "chunk_id", "document_id", "filename", "page", "score", "snippet"}

    # The model saw the source wrapped in delimiters, and the grounding rules.
    system, messages = fake_llm.calls[0]
    assert "untrusted document content" in system
    assert '<source id="1" file="Vault_Product_Guide.pdf" page="1">' in messages[-1]["content"]


async def test_messages_and_citations_are_persisted(
    client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM
) -> None:
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    events = await ask(client, auth_headers, "What does the Business plan cost?")
    meta = dict(events)["meta"]

    r = await client.get(f"/api/conversations/{meta['conversation_id']}", headers=auth_headers)
    conv = r.json()
    assert conv["title"] == "What does the Business plan cost?"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assistant = conv["messages"][1]
    assert assistant["id"] == meta["message_id"]
    assert assistant["citations"][0]["filename"] == "guide.pdf"

    listing = (await client.get("/api/conversations", headers=auth_headers)).json()
    assert [c["id"] for c in listing] == [meta["conversation_id"]]


async def test_no_relevant_context_skips_llm(
    client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM
) -> None:
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    events = await ask(client, auth_headers, "Quel est le cours de l'action?")  # nothing overlaps
    answer = "".join(d["text"] for e, d in events if e == "token")
    assert answer == NO_CONTEXT_ANSWER
    assert dict(events)["citations"] == []
    assert [e for e, _ in events][-1] == "done"
    assert fake_llm.calls == []  # the LLM was never called


async def test_no_documents_at_all(client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM) -> None:
    events = await ask(client, auth_headers, "What does the Business plan cost?")
    assert "".join(d["text"] for e, d in events if e == "token") == NO_CONTEXT_ANSWER
    assert fake_llm.calls == []


async def test_follow_up_includes_history(client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM) -> None:
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    first = await ask(client, auth_headers, "What does the Business plan cost?")
    conv_id = dict(first)["meta"]["conversation_id"]
    fake_llm.tokens = ["It includes a 99.9% uptime SLA [1]."]
    await ask(client, auth_headers, "And what uptime SLA does it include?", conversation_id=conv_id)

    _, messages = fake_llm.calls[1]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "What does the Business plan cost?"
    assert "99.9%" in messages[-1]["content"]  # the uptime chunk was retrieved for the follow-up


async def test_history_is_capped(
    client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "history_messages", 2)
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    conv_id = dict(await ask(client, auth_headers, "Business plan cost?"))["meta"]["conversation_id"]
    for _ in range(3):
        await ask(client, auth_headers, "Business plan cost again?", conversation_id=conv_id)
    _, messages = fake_llm.calls[-1]
    assert len(messages) == 3  # 2 history messages + the new question


async def test_document_filter(client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM) -> None:
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    handbook_id = await upload(client, auth_headers, "handbook.pdf", HANDBOOK_PDF)
    # Restricted to the handbook, a pricing question finds nothing relevant.
    events = await ask(client, auth_headers, "Business plan cost per user?", document_ids=[handbook_id])
    assert fake_llm.calls == [] or "handbook.pdf" in fake_llm.calls[0][1][-1]["content"]
    for _, messages in fake_llm.calls:
        assert "guide.pdf" not in messages[-1]["content"]
    assert [e for e, _ in events][-1] == "done"


async def test_llm_error_becomes_error_event(
    client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM
) -> None:
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    fake_llm.tokens = ["Partial "]
    fake_llm.fail_with = LLMError("LLM_TIMEOUT", "The AI provider took too long to respond.")
    events = await ask(client, auth_headers, "What does the Business plan cost?")
    assert [e for e, _ in events] == ["meta", "token", "error"]
    assert dict(events)["error"]["code"] == "LLM_TIMEOUT"

    conv_id = dict(events)["meta"]["conversation_id"]
    conv = (await client.get(f"/api/conversations/{conv_id}", headers=auth_headers)).json()
    # The question is kept, and the partial answer the user already saw is saved.
    assert [(m["role"], m["content"]) for m in conv["messages"]] == [
        ("user", "What does the Business plan cost?"),
        ("assistant", "Partial"),
    ]


async def test_missing_provider_config(client: AsyncClient, auth_headers: dict) -> None:
    def broken_factory() -> LLMProvider:
        raise LLMError("LLM_NOT_CONFIGURED", "The AI provider is not configured on the server.")

    app.dependency_overrides[get_llm_factory] = lambda: broken_factory
    try:
        await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
        events = await ask(client, auth_headers, "What does the Business plan cost?")
    finally:
        app.dependency_overrides.pop(get_llm_factory, None)
    assert dict(events)["error"]["code"] == "LLM_NOT_CONFIGURED"


async def test_stop_mid_stream_persists_partial_answer(client: AsyncClient, auth_headers: dict) -> None:
    """Simulates the Stop button / client disconnect: the generator is closed early."""
    await upload(client, auth_headers, "guide.pdf", PRODUCT_PDF)
    conv_id = dict(await ask(client, auth_headers, "hello"))["meta"][
        "conversation_id"
    ]  # creates a conversation
    me = (await client.get("/api/auth/me", headers=auth_headers)).json()

    llm = FakeLLM(tokens=["The Business ", "plan costs ", "USD 29 [1].", " More text."])
    factory: Callable[[], LLMProvider] = lambda: llm  # noqa: E731
    inp = ChatInput(uuid.UUID(me["id"]), uuid.UUID(conv_id), "What does the Business plan cost?", None)
    stream = answer_stream(inp, fake_embedder, factory)
    received = []
    async for event, _data in stream:
        received.append(event)
        if received.count("token") == 2:
            break
    await stream.aclose()

    async with SessionLocal() as db:
        last = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == uuid.UUID(conv_id))
                    .order_by(Message.created_at)
                )
            )
            .scalars()
            .all()[-1]
        )
    assert last.role.value == "assistant"
    assert last.content == "The Business plan costs"


# --- Validation and ownership ---------------------------------------------------


async def test_blank_message_rejected(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.post("/api/chat", headers=auth_headers, json={"message": "   "})
    assert r.status_code == 422


async def test_chat_requires_auth(client: AsyncClient) -> None:
    r = await client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 401


async def test_cannot_post_into_someone_elses_conversation(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict, fake_llm: FakeLLM
) -> None:
    conv_id = dict(await ask(client, auth_headers, "hello"))["meta"]["conversation_id"]
    r = await client.post(
        "/api/chat", headers=other_auth_headers, json={"message": "hi", "conversation_id": conv_id}
    )
    assert r.status_code == 404
    assert (await client.get(f"/api/conversations/{conv_id}", headers=other_auth_headers)).status_code == 404
    assert (
        await client.delete(f"/api/conversations/{conv_id}", headers=other_auth_headers)
    ).status_code == 404
    assert (await client.get("/api/conversations", headers=other_auth_headers)).json() == []


async def test_retrieval_never_crosses_users(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict, fake_llm: FakeLLM
) -> None:
    alice_doc = await upload(client, auth_headers, "alice-secret.pdf", PRODUCT_PDF)
    # Even naming Alice's document ID explicitly doesn't let Mallory search it.
    events = await ask(
        client, other_auth_headers, "What does the Business plan cost?", document_ids=[alice_doc]
    )
    assert "".join(d["text"] for e, d in events if e == "token") == NO_CONTEXT_ANSWER
    assert fake_llm.calls == []


async def test_delete_conversation(client: AsyncClient, auth_headers: dict, fake_llm: FakeLLM) -> None:
    conv_id = dict(await ask(client, auth_headers, "hello"))["meta"]["conversation_id"]
    assert (await client.delete(f"/api/conversations/{conv_id}", headers=auth_headers)).status_code == 204
    assert (await client.get(f"/api/conversations/{conv_id}", headers=auth_headers)).status_code == 404

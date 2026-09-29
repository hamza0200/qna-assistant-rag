"""Document API: upload -> background ingestion, listing, deletion, ownership (IDOR)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.models import Chunk
from app.db.session import SessionLocal
from tests.helpers import make_pdf

PDF = make_pdf(
    [
        "Vault pricing\nThe Business plan costs USD 29 per user per month.",
        "Support\nEnterprise customers get a dedicated support manager.",
    ]
)


async def upload(client: AsyncClient, headers: dict, name: str = "guide.pdf", data: bytes = PDF) -> dict:
    r = await client.post(
        "/api/documents", headers=headers, files=[("files", (name, data, "application/pdf"))]
    )
    assert r.status_code == 202, r.text
    return r.json()[0]


async def test_upload_ingests_to_ready(client: AsyncClient, auth_headers: dict) -> None:
    created = await upload(client, auth_headers)
    assert created["status"] == "processing"
    assert "storage_path" not in created

    # httpx's ASGI transport waits for background tasks, so ingestion is done here.
    r = await client.get(f"/api/documents/{created['id']}", headers=auth_headers)
    doc = r.json()
    assert doc["status"] == "ready", doc
    assert doc["page_count"] == 2
    assert doc["chunk_count"] >= 2
    assert doc["error_message"] is None


async def test_upload_multiple_files(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.post(
        "/api/documents",
        headers=auth_headers,
        files=[("files", ("a.pdf", PDF, "application/pdf")), ("files", ("b.pdf", PDF, "application/pdf"))],
    )
    assert r.status_code == 202
    assert [d["filename"] for d in r.json()] == ["a.pdf", "b.pdf"]
    listing = (await client.get("/api/documents", headers=auth_headers)).json()
    assert len(listing) == 2


async def test_textless_pdf_marked_failed(client: AsyncClient, auth_headers: dict) -> None:
    created = await upload(client, auth_headers, data=make_pdf([""]))
    doc = (await client.get(f"/api/documents/{created['id']}", headers=auth_headers)).json()
    assert doc["status"] == "failed"
    assert "No extractable text" in doc["error_message"]


async def test_chunk_endpoint_returns_text(client: AsyncClient, auth_headers: dict) -> None:
    created = await upload(client, auth_headers)
    async with SessionLocal() as db:
        chunk_id = (
            await db.execute(select(Chunk.id).where(Chunk.document_id == uuid.UUID(created["id"])).limit(1))
        ).scalar_one()
    r = await client.get(f"/api/chunks/{chunk_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "guide.pdf"
    assert body["page_number"] in (1, 2)
    assert body["content"]


async def test_delete_cascades_to_chunks(client: AsyncClient, auth_headers: dict) -> None:
    created = await upload(client, auth_headers)
    doc_id = uuid.UUID(created["id"])
    r = await client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert r.status_code == 204
    assert (await client.get(f"/api/documents/{doc_id}", headers=auth_headers)).status_code == 404
    async with SessionLocal() as db:
        remaining = (
            await db.execute(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id))
        ).scalar_one()
    assert remaining == 0


async def test_documents_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/documents")).status_code == 401
    r = await client.post("/api/documents", files=[("files", ("a.pdf", PDF, "application/pdf"))])
    assert r.status_code == 401


# --- IDOR: another user must not see or touch Alice's documents or chunks ---------


async def test_other_user_cannot_access_document(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    created = await upload(client, auth_headers)
    doc_id = created["id"]

    assert (await client.get("/api/documents", headers=other_auth_headers)).json() == []
    r = await client.get(f"/api/documents/{doc_id}", headers=other_auth_headers)
    assert r.status_code == 404  # 404, not 403: don't confirm the ID exists
    r = await client.delete(f"/api/documents/{doc_id}", headers=other_auth_headers)
    assert r.status_code == 404
    # Still there for the owner.
    assert (await client.get(f"/api/documents/{doc_id}", headers=auth_headers)).status_code == 200


async def test_other_user_cannot_read_chunk(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    created = await upload(client, auth_headers)
    async with SessionLocal() as db:
        chunk_id = (
            await db.execute(select(Chunk.id).where(Chunk.document_id == uuid.UUID(created["id"])).limit(1))
        ).scalar_one()
    r = await client.get(f"/api/chunks/{chunk_id}", headers=other_auth_headers)
    assert r.status_code == 404


async def test_unknown_and_malformed_ids(client: AsyncClient, auth_headers: dict) -> None:
    assert (await client.get(f"/api/documents/{uuid.uuid4()}", headers=auth_headers)).status_code == 404
    r = await client.get("/api/documents/not-a-uuid", headers=auth_headers)
    assert r.status_code == 422

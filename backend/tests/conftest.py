"""Test fixtures.

Tests run against a real Postgres + pgvector database (`<db>_test`), not
SQLite: vector search, JSONB and enum behaviour can't be faked faithfully.
Environment is configured *before* importing the app, because settings and
the engine are created at import time.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://docmind:docmind@localhost:5433/docmind_test"
)
os.environ["ENVIRONMENT"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-123"
os.environ["LOG_LEVEL"] = "WARNING"

import tempfile  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="docmind-test-uploads-")

from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


async def _ensure_database_exists() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    conn = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port, database="postgres"
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def _database() -> AsyncIterator[None]:
    """Create a fresh schema once per test session."""
    await _ensure_database_exists()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Isolate tests: wipe all rows after each test."""
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register_and_login(client: AsyncClient, email: str, password: str = "Password123!") -> str:
    r = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    token = await register_and_login(client, "alice@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_auth_headers(client: AsyncClient) -> dict[str, str]:
    """A second user, for IDOR tests."""
    token = await register_and_login(client, "mallory@example.com")
    return {"Authorization": f"Bearer {token}"}

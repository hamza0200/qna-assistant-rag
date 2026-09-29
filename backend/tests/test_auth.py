"""Auth flow: register, login, /me, and the ways they must fail."""

from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient

from app.core.config import get_settings


async def test_register_login_me(client: AsyncClient) -> None:
    r = await client.post("/api/auth/register", json={"email": "Bob@Example.com", "password": "Password123"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "bob@example.com"  # normalized
    assert "password" not in body and "password_hash" not in body

    r = await client.post("/api/auth/login", json={"email": "bob@example.com", "password": "Password123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "bob@example.com"


async def test_duplicate_email_rejected(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": "Password123"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    r = await client.post("/api/auth/register", json={**payload, "email": "DUP@example.com"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_short_password_rejected(client: AsyncClient) -> None:
    r = await client.post("/api/auth/register", json={"email": "x@example.com", "password": "short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "short" not in r.json()["error"]["message"]  # input value is not echoed back


async def test_invalid_email_rejected(client: AsyncClient) -> None:
    r = await client.post("/api/auth/register", json={"email": "not-an-email", "password": "Password123"})
    assert r.status_code == 422


async def test_wrong_password_and_unknown_user_look_identical(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={"email": "c@example.com", "password": "Password123"})
    wrong = await client.post("/api/auth/login", json={"email": "c@example.com", "password": "nope-nope"})
    unknown = await client.post("/api/auth/login", json={"email": "z@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_me_requires_token(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_rejects_garbage_token(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


async def test_me_rejects_expired_token(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    me = (await client.get("/api/auth/me", headers=auth_headers)).json()
    s = get_settings()
    past = datetime.now(UTC) - timedelta(hours=2)
    expired = jwt.encode(
        {"sub": me["id"], "iat": past, "exp": past + timedelta(minutes=1), "type": "access"},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


async def test_me_rejects_token_signed_with_other_key(client: AsyncClient, auth_headers: dict) -> None:
    me = (await client.get("/api/auth/me", headers=auth_headers)).json()
    forged = jwt.encode(
        {"sub": me["id"], "exp": datetime.now(UTC) + timedelta(minutes=5), "type": "access"},
        "attacker-controlled-secret-key!!",
        algorithm="HS256",
    )
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_me_rejects_alg_none_token(client: AsyncClient, auth_headers: dict) -> None:
    me = (await client.get("/api/auth/me", headers=auth_headers)).json()
    unsigned = jwt.encode(
        {"sub": me["id"], "exp": datetime.now(UTC) + timedelta(minutes=5), "type": "access"},
        None,
        algorithm="none",
    )
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {unsigned}"})
    assert r.status_code == 401

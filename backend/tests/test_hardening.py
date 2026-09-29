"""Cross-cutting hardening: rate limits, error shape, request IDs, security headers, LLM error mapping."""

from collections.abc import Iterator
from contextlib import asynccontextmanager

import anthropic
import httpx2
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.services.llm import AnthropicProvider, LLMError


@pytest.fixture
def rate_limits_on() -> Iterator[None]:
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


async def test_login_is_rate_limited(client: AsyncClient, rate_limits_on: None) -> None:
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    statuses = [(await client.post("/api/auth/login", json=body)).status_code for _ in range(6)]
    assert statuses[:5] == [401] * 5  # limit is 5/minute
    r = await client.post("/api/auth/login", json=body)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in r.headers


async def test_chat_limit_is_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict, rate_limits_on: None, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_chat", "2/minute")
    limiter.reset()
    for _ in range(2):
        assert (
            await client.post("/api/chat", headers=auth_headers, json={"message": "hi"})
        ).status_code == 200
    assert (await client.post("/api/chat", headers=auth_headers, json={"message": "hi"})).status_code == 429
    # A different user on the same IP has their own budget.
    r = await client.post("/api/chat", headers=other_auth_headers, json={"message": "hi"})
    assert r.status_code == 200


async def test_unknown_route_uses_error_shape(client: AsyncClient) -> None:
    r = await client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


async def test_wrong_method_uses_error_shape(client: AsyncClient) -> None:
    r = await client.put("/api/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


async def test_unhandled_exception_hides_details(client: AsyncClient, monkeypatch) -> None:
    from app.main import app

    @app.get("/api/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail: db password is hunter2")

    try:
        from httpx import ASGITransport

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as c:
            r = await c.get("/api/_boom")
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/api/_boom"]
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
    assert "hunter2" not in r.text


async def test_request_id_and_security_headers(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert len(r.headers["X-Request-ID"]) == 16
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]

    r = await client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["X-Request-ID"] == "trace-abc-123"  # well-formed IDs propagate

    evil = "fake-log-line' OR 1=1 --"
    r = await client.get("/api/health", headers={"X-Request-ID": evil})
    assert r.headers["X-Request-ID"] != evil  # malformed ones are replaced


async def test_cors_allows_only_configured_origin(client: AsyncClient) -> None:
    allowed = get_settings().cors_origin_list[0]
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}
    ok = await client.options("/api/chat", headers={"Origin": allowed, **pre})
    assert ok.headers.get("access-control-allow-origin") == allowed
    bad = await client.options("/api/chat", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in bad.headers


# --- LLM provider: request shape and error mapping (SDK mocked, no network) ------


def _provider(monkeypatch) -> AnthropicProvider:
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "test-key-not-real")
    return AnthropicProvider(s)


def test_anthropic_request_includes_caps_effort_and_fallback(monkeypatch) -> None:
    params = _provider(monkeypatch)._request_params("SYS", [{"role": "user", "content": "q"}])
    s = get_settings()
    assert params["model"] == s.llm_model and params["max_tokens"] == s.llm_max_tokens
    assert params["system"] == "SYS"
    assert params["output_config"] == {"effort": s.llm_effort}
    assert params["fallbacks"] == "default" and params["betas"] == [AnthropicProvider.FALLBACK_BETA]


def test_missing_api_key_is_a_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    with pytest.raises(LLMError) as exc:
        AnthropicProvider(get_settings())
    assert exc.value.code == "LLM_NOT_CONFIGURED"


_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (anthropic.APITimeoutError(request=_REQ), "LLM_TIMEOUT"),
        (anthropic.APIConnectionError(request=_REQ), "LLM_UNAVAILABLE"),
        (
            anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=_REQ), body=None),
            "LLM_RATE_LIMITED",
        ),
        (
            anthropic.InternalServerError("boom", response=httpx2.Response(500, request=_REQ), body=None),
            "LLM_UNAVAILABLE",
        ),
        (
            anthropic.BadRequestError(
                "Your credit balance is too low to access the Anthropic API.",
                response=httpx2.Response(400, request=_REQ),
                body=None,
            ),
            "LLM_BILLING",
        ),
        (
            anthropic.NotFoundError("model: nope", response=httpx2.Response(404, request=_REQ), body=None),
            "LLM_NOT_CONFIGURED",
        ),
    ],
)
async def test_anthropic_errors_are_normalized(monkeypatch, error: Exception, code: str) -> None:
    provider = _provider(monkeypatch)

    @asynccontextmanager
    async def failing_stream(**_: object):
        raise error
        yield  # pragma: no cover

    monkeypatch.setattr(provider.client.beta.messages, "stream", failing_stream)
    with pytest.raises(LLMError) as exc:
        async for _ in provider.stream("sys", [{"role": "user", "content": "q"}]):
            pass
    assert exc.value.code == code
    assert "boom" not in exc.value.message  # provider internals aren't shown to users

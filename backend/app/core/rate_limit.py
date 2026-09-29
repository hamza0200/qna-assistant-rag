"""Rate limiting with slowapi.

Authenticated requests are limited per user (so users behind one NAT/office IP
don't share a budget); anonymous requests (login) are limited per client IP.
Limits are in-memory, i.e. per process — fine for one instance; with several
replicas you'd point slowapi at Redis (`storage_uri="redis://..."`).
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.errors import error_body
from app.core.security import decode_access_token


def _rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        user_id = decode_access_token(auth[7:])
        if user_id is not None:
            return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_limit_key, enabled=get_settings().rate_limit_enabled)


# Callables (not strings) so tests can change limits via settings at runtime.
def login_limit() -> str:
    return get_settings().rate_limit_login


def chat_limit() -> str:
    return get_settings().rate_limit_chat


def upload_limit() -> str:
    return get_settings().rate_limit_upload


async def rate_limit_exceeded_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=error_body("RATE_LIMITED", f"Too many requests: limit is {exc.detail}"),
        headers={"Retry-After": "60"},
    )

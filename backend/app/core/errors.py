"""Consistent error shape for every API failure.

All errors leave the API as {"error": {"code": "...", "message": "..."}} so
the frontend needs exactly one error-parsing path, and stack traces never
reach clients (they are logged server-side instead).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Raise from services/routes to return a specific status + error code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class NotFoundError(AppError):
    def __init__(self, what: str = "Resource") -> None:
        # Same 404 for "doesn't exist" and "belongs to someone else", so an
        # attacker can't probe which IDs exist (no IDOR information leak).
        super().__init__(404, "NOT_FOUND", f"{what} not found")


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "RATE_LIMITED",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Summarize pydantic errors as "field: message" without echoing input values
        # (which could contain passwords).
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
            parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
        return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", "; ".join(parts)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"error_type": type(exc).__name__})
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "Internal server error"))

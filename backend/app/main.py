"""FastAPI application factory: middleware, routers, exception handlers."""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.routes import auth, chat, documents, health
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import request_id_var, setup_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.db.session import engine
from app.services.embeddings import get_embedding_provider
from app.services.ingestion import fail_stale_processing_documents

logger = logging.getLogger("app.request")

_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

# The API only returns JSON/SSE, so it can use a strict policy: nothing may be
# framed, sniffed into another content type, or load sub-resources.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook.

    The embedding model is loaded once here (in a thread, it takes ~1 s) rather
    than lazily on the first request, so no user pays the cold-start cost.
    """
    await asyncio.to_thread(get_embedding_provider)
    failed = await fail_stale_processing_documents()
    if failed:
        logger.warning("stale_documents_failed", extra={"count": failed})
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    # Interactive API docs are handy in development but advertise the attack
    # surface in production, so they're switched off there.
    docs = settings.environment != "production"
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    # CORS restricted to the configured frontend origin(s) only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # we use a bearer header, not cookies
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a request ID to every log line and response, add security headers, log latency."""
        # Accept a caller's ID (for tracing across services) only if it's well-formed:
        # it ends up in logs, so arbitrary input would allow log injection.
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            response.headers.update(SECURITY_HEADERS)
            if request.url.path == "/docs":  # Swagger UI loads scripts from a CDN
                del response.headers["Content-Security-Policy"]
            # For streaming responses this measures time-to-headers, not the full stream;
            # the chat route logs its own end-to-end timings.
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    app.state.limiter = limiter
    register_exception_handlers(app)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()

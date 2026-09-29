# Running interview notes (collected while building)

## Phase 1 — Scaffold
- **Multi-stage Docker builds** (`backend/Dockerfile`, `frontend/Dockerfile`): the builder stage has compilers and caches; the runtime stage copies only the virtualenv / Next standalone output. Smaller images, smaller attack surface, faster pulls. Both run as a non-root user.
- **Baking the embedding model into the image**: the FastEmbed model is downloaded during `docker build`, so containers start fast, work offline, and every replica uses the identical model version.
- **Health endpoint returns 503 when the DB is down** (`backend/app/api/routes/health.py`) so a load balancer or orchestrator can pull the instance out of rotation. Liveness ("process is up") vs readiness ("can serve traffic") is a common follow-up question.
- **Request IDs via `ContextVar`** (`backend/app/core/logging.py`): async handlers share one thread, so thread-locals would leak between requests; ContextVars are scoped per asyncio task. The ID is also returned as `X-Request-ID` so a user-reported error can be matched to server logs.
- **`NEXT_PUBLIC_*` env vars are inlined at build time** in Next.js: changing them needs a rebuild. Never put secrets in them.
- **Next.js 16 changes**: `middleware.ts` is renamed `proxy.ts`; request APIs (`cookies()`, `headers()`, `params`) are async only; Turbopack is the default bundler.

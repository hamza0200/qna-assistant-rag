# Running interview notes (collected while building)

## Phase 1 — Scaffold
- **Multi-stage Docker builds** (`backend/Dockerfile`, `frontend/Dockerfile`): the builder stage has compilers and caches; the runtime stage copies only the virtualenv / Next standalone output. Smaller images, smaller attack surface, faster pulls. Both run as a non-root user.
- **Baking the embedding model into the image**: the FastEmbed model is downloaded during `docker build`, so containers start fast, work offline, and every replica uses the identical model version.
- **Health endpoint returns 503 when the DB is down** (`backend/app/api/routes/health.py`) so a load balancer or orchestrator can pull the instance out of rotation. Liveness ("process is up") vs readiness ("can serve traffic") is a common follow-up question.
- **Request IDs via `ContextVar`** (`backend/app/core/logging.py`): async handlers share one thread, so thread-locals would leak between requests; ContextVars are scoped per asyncio task. The ID is also returned as `X-Request-ID` so a user-reported error can be matched to server logs.
- **`NEXT_PUBLIC_*` env vars are inlined at build time** in Next.js: changing them needs a rebuild. Never put secrets in them.
- **Next.js 16 changes**: `middleware.ts` is renamed `proxy.ts`; request APIs (`cookies()`, `headers()`, `params`) are async only; Turbopack is the default bundler.

## Phase 2 — Database + auth
- **UUID primary keys** (`backend/app/db/models.py`): not enumerable (`/documents/1`, `/documents/2`…), can be generated without a DB round trip, safe to merge across shards. Cost: 16 bytes vs 4/8, random inserts fragment B-tree indexes a little (UUIDv7 fixes that).
- **Unique constraint instead of "SELECT then INSERT"** (`backend/app/api/routes/auth.py`): check-then-act is a race condition; the unique index makes the DB the single arbiter and we translate `IntegrityError` into 409.
- **User enumeration defenses at login**: identical error for "no such user" and "wrong password", *and* bcrypt runs against a dummy hash when the user doesn't exist so timing is equal.
- **JWT pitfalls covered by tests** (`backend/tests/test_auth.py`): expired token, wrong signing key, `alg: none`. The decoder pins `algorithms=[...]` rather than trusting the token header.
- **bcrypt's 72-byte limit**: longer passwords are silently truncated by the algorithm, so we reject them explicitly at the schema layer.
- **Tests hit real Postgres (a `_test` database)**, not SQLite: pgvector, JSONB and enums can't be emulated. Tables are truncated between tests for isolation.
- **Client-side route guard ≠ security** (`frontend/src/components/RequireAuth.tsx`): it's UX. The backend enforces auth on every request. `useSyncExternalStore` with a server snapshot avoids hydration mismatches when reading localStorage.
- **npm lockfile gotcha**: an incremental `npm i` on a newer npm produced a lockfile `npm ci` rejected in Docker (optional wasm deps). Fix: regenerate the lockfile and match the npm major (Node 24 image). Good "debugging a CI-only failure" story.

## Phase 3 — Ingestion
- **202 Accepted + polling** is the REST pattern for async work: the resource is created immediately in a `processing` state; the client polls `GET /documents/{id}`. The frontend polls every 2 s *only while* something is processing.
- **Don't block the event loop**: pypdf and ONNX inference are CPU-bound and synchronous. Inside `async def`, calling them directly would freeze every other request (including live chat streams). `asyncio.to_thread` moves them to a worker thread. (The GIL is released inside ONNX Runtime's native code, so this gives real parallelism for embeddings.)
- **Background task needs its own DB session**: the request-scoped session is closed once the response is sent.
- **Atomicity**: chunks are bulk-inserted and the status flipped to `ready` in one transaction, so a document is never `ready` with half its chunks, and a failure leaves no orphan chunks.
- **Failures are data**: errors are written to `documents.error_message` and shown in the UI, instead of vanishing into a background traceback.
- **BGE query instruction**: `bge-*-v1.5` models recommend prefixing *queries* (not passages) with "Represent this sentence for searching relevant passages: " — asymmetric retrieval. FastEmbed doesn't add it for this model, so `embeddings.py` does.
- **Normalized embeddings** ⇒ cosine similarity = dot product, and cosine distance (`<=>`) = 1 − similarity.
- **Measured**: the 5 sample PDFs (12 pages) became 32 chunks in ~0.5 s total on CPU.
- **Magic bytes**: `%PDF-` at offset 0. Renaming `malware.exe` to `invoice.pdf` with a spoofed `Content-Type` passes the first two checks but not this one (test in `tests/test_security.py`).
- **React 19 lint rule `set-state-in-effect`**: fetch in an effect and set state in the promise callback, returning a cancel function so late responses after unmount are ignored.

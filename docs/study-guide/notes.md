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

## Phase 4 — Retrieval + chat
- **BGE similarity scores are compressed**: measured on the sample docs, a totally off-topic query ("capital of France") still scores ~0.41 and an in-domain but unanswerable one ("stock price") ~0.69, while good matches are ~0.70–0.84. A threshold only removes clearly off-topic queries; it can't detect "unanswerable but on-topic" — the LLM's grounding instructions have to do that. The spec default (0.35) filters nothing for this model.
- **Dense retrieval misses acronyms**: "What are the RPO and RTO?" didn't retrieve the security-policy chunk that defines them. Embeddings capture meaning, not exact tokens — the argument for hybrid (BM25/full-text + vector) search.
- **Threshold after ORDER BY, not in WHERE**: `ORDER BY embedding <=> :q LIMIT k` can use the HNSW index; adding `WHERE (embedding <=> :q) < x` generally can't. So filter the top-k in the application.
- **The LLM isn't called when retrieval is empty** (`rag.answer_stream`): zero cost, zero latency, zero hallucination risk for clearly unanswerable questions.
- **Streaming lifecycle**: auth/validation/ownership errors are checked *before* the stream starts (proper 4xx JSON); once the 200 and headers are sent, failures can only be reported as an `error` event.
- **Client disconnect / Stop**: aborting the fetch closes the connection; Starlette cancels the generator, which closes the provider stream (stopping token generation and billing). The partial answer is persisted inside `anyio.CancelScope(shield=True)` — anyio cancellation is *level-triggered*, so any `await` inside a cancelled scope would itself be cancelled without the shield.
- **React closure bug found in e2e testing**: a `setState(prev => …)` updater referenced a mutable local (`assistantId`) that was reassigned right after the call. Updaters run later, at render time, so they saw the *new* value. Fix: capture into a `const` before calling `setState`. Classic interview story about stale/mutable closures.
- **`memo` on MessageBubble** so earlier messages don't re-render on every streamed token; stable callbacks via `useCallback`.
- **Prompt-injection defences in the prompt layer** (`prompts.py`): untrusted-data rule in the system prompt, `<source>` delimiters, neutralising delimiter look-alikes inside chunks, no secrets or tools available to the model.

## Phase 5 — Hardening
- **What's tested vs what's measured for prompt injection**: tests pin down the deterministic defences (injected text only ever appears inside a `<source>` block, chunks can't close their own delimiter, filenames can't forge attributes, no secrets anywhere in the prompt). Whether the *model* obeys is probabilistic — that's measured by the eval (Q19), not asserted by unit tests.
- **Limits are also a security control**: 4,000-char questions, `max_tokens` on answers, a character budget on context, 20 MB uploads, 10 files per request — each bounds cost or resource use for a single request.
- **Rate-limit keys**: per user when authenticated, per IP otherwise. In-memory counters don't work across replicas — use Redis.
- **Log injection**: a client-supplied `X-Request-ID` is echoed into logs, so it's only accepted if it matches `[A-Za-z0-9-]{1,64}`.
- **500s never leak internals**: the catch-all handler logs the traceback server-side and returns a generic message (test asserts the secret in the exception text isn't in the response).
- **CSP `connect-src`** limits where browser JS can send data — useful damage control for tokens stored in localStorage.
- **`upgrade-insecure-requests` gotcha**: it would rewrite `http://localhost` API calls to https in local dev, so it's only for production behind TLS.
- **Test speed**: bcrypt cost is configurable; tests use 4 rounds (vs 12 in prod), taking the suite from ~20 s to ~2.5 s. Each +1 round doubles hashing time.
- **Accessibility caught by tests**: `aria-label` on a plain `div` isn't announced by screen readers — it needs a role (`role="group"`). Testing Library's role queries surface these issues.

## Phase 6 — Seed + eval
- **Retrieval hit-rate 21/21 (100%)** at document and page level with `TOP_K=5`, `MIN_SIMILARITY=0.45` (see `docs/EVAL_RESULTS.md`).
- **Threshold tuning story (ADR-020)**: in-domain answerable questions scored 0.508–0.84 top-1; off-topic probes 0.416–0.541 — overlapping distributions, so a threshold can only remove clearly off-topic questions. The rest is the prompt's job. Great answer to "how did you pick the threshold?": *measured, on a labelled set, and I know its limits*.
- **Unanswerable ≠ irrelevant**: "What is Orbitra's stock price?" retrieves pricing chunks at ~0.69 — lexically/semantically close, but they don't contain the answer. Only the LLM, instructed to refuse, can tell.
- **Test your grader**: the eval scorer is unit-tested; every reference answer is run through it (which surfaced a quirk in the question file: Q13's reference answer lacks its own key fact).
- **Eval split**: retrieval measured in-process (free, deterministic, no LLM); answers measured end-to-end through the HTTP API (tests the real system, costs tokens).
- **Seed via the public API**, not direct DB inserts: exercises the same validation and ingestion path as users, and is idempotent (skips existing user/docs).
- **asyncio gotcha**: a pooled async engine is bound to the event loop that created its connections; calling `asyncio.run()` repeatedly requires `engine.dispose()` between runs.

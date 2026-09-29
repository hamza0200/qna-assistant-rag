# 5. Engineering essentials

## Backend

- **Event loop:** one thread juggles many waiting tasks. **Never block it** — CPU work or blocking calls go to `asyncio.to_thread` (DocMind: PDF parsing, embeddings) or to worker processes.
- **Dependency injection:** `Depends(get_current_user)` / `Depends(get_db)`; tests swap them with `dependency_overrides`.
- **Status codes:** 201 created, **202 accepted (async work)**, 204 deleted, 401 not logged in, 403 not allowed, **404 for other users' data** (don't reveal it exists), 409 conflict, 413 too large, 415 wrong type, 422 invalid, 429 rate limited.
- **SSE vs WebSockets:** SSE = one-way over plain HTTP (streaming answers); WebSockets = two-way and stateful (chat apps, collaboration).
- **Idempotency:** repeating a request has the same effect; use an `Idempotency-Key` for POSTs such as payments.
- **Pagination:** offset (simple, slow on deep pages) vs cursor/keyset (fast, stable).

## Frontend

- **Server vs client components:** server = rendered on the server, no JS shipped; client (`"use client"`) = state, effects, events. DocMind's app pages are client components because the token lives in the browser.
- **SSG / SSR / CSR:** build time / per request / in the browser.
- **Keys:** stable IDs, never array indexes for changing lists. **Memo:** `memo` + `useCallback` so only the streaming message re-renders.
- **Stale closure (a real DocMind bug):** a state updater read a variable that was reassigned before it ran → answers stayed blank. Fix: copy into a `const`.
- **Streams:** `res.body.getReader()` + `TextDecoder({stream: true})` + buffer until a blank line. **Stop:** `AbortController`.
- **TypeScript:** strict mode, generics (`apiFetch<T>`), discriminated unions for SSE events.

## Databases

- **Indexes:** B-tree (equality/range, foreign keys), GIN (full text, JSONB), HNSW (vectors). Every index slows writes.
- **Transactions (ACID):** DocMind writes chunks + `ready` together. Postgres default isolation = Read Committed. Prefer constraints (unique email) over "check then insert".
- **N+1:** one query per item; fix with eager loading (`selectinload`).
- **Pooling:** reuse connections; PgBouncer at scale.
- **Migrations:** versioned (Alembic), expand/contract for zero downtime.
- **SQL vs NoSQL:** relational data with ownership chains and joins → Postgres; flexible documents at huge write scale → MongoDB. **JSONB** for data read as a unit (citations).

## Security

- **AuthN vs AuthZ:** who you are vs what you may do. Most breaches are AuthZ bugs.
- **IDOR:** changing an ID to reach someone else's data → owner check in every query, 404, tests.
- **Passwords:** slow salted hash (bcrypt/Argon2id), never reversible encryption.
- **JWT:** payload is readable; pin the algorithm; check expiry; revocation is hard.
- **CORS** stops *other websites* from reading your API through a user's browser — it is not authentication.
- **CSRF** matters with cookie auth (use SameSite + tokens); DocMind uses a header, so it isn't exposed.
- **XSS:** React escapes text; render Markdown without raw HTML; CSP.
- **Prompt injection (OWASP LLM01):** instructions hidden in data. DocMind's defence: "sources are untrusted data" rule, `<source>` delimiters, escaping fake tags, **no secrets and no tools** — so even a successful injection can't do much. Tested with a planted attack.
- **OWASP LLM Top 10 to name:** prompt injection, sensitive info disclosure, improper output handling, excessive agency, system prompt leakage, vector/embedding weaknesses, misinformation, unbounded consumption.

## Scale, reliability, DevOps

- **Latency:** everything except the LLM is milliseconds; **time to first token** is what users feel. Streaming hides generation time.
- **Scaling out:** stateless API pods + load balancer; move files to S3, limits to Redis, jobs to a queue.
- **Caching:** response, embedding, semantic (similar questions), provider prompt caching.
- **Cost:** skip the LLM when possible, cap tokens, route easy questions to a cheaper model, cache, per-user quotas.
- **Reliability:** timeouts everywhere; retry transient errors with exponential backoff + jitter (only before streaming starts); circuit breaker; fallback provider.
- **Observability:** JSON logs with request IDs; metrics (rate, errors, latency); tracing; AI-specific signals (refusal rate, zero-citation answers, tokens per user).
- **Docker:** multi-stage builds (small, non-root images); Compose for local; CI runs lint, migrations, tests, build.

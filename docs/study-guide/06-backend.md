# 6. Backend

## FastAPI in one paragraph

FastAPI is an ASGI web framework on top of Starlette. You declare routes as Python functions with type hints; FastAPI uses them to **validate input** (via Pydantic), **inject dependencies**, **serialize output** (`response_model`) and **generate OpenAPI docs** (`/docs`). It runs on an ASGI server (uvicorn) and supports both `async def` and plain `def` handlers.

## Async Python and the event loop

**Plain language:** one thread runs an *event loop* that juggles many tasks. When a task waits on I/O (`await db.execute(...)`, `await llm_stream`), it yields control so other tasks run meanwhile. That's why one process can hold hundreds of open SSE streams: they're mostly waiting on the network.

**The golden rule:** never block the loop. A CPU-heavy or blocking call inside `async def` (pypdf parsing, ONNX inference, `time.sleep`, `requests.get`) freezes *every* request on that worker.

| Work type | What to use | DocMind example |
|---|---|---|
| I/O-bound, async library available | `await` | asyncpg queries, Anthropic `AsyncAnthropic` stream |
| Blocking I/O or CPU-bound but releases the GIL | `await asyncio.to_thread(fn, ...)` | `parse_pdf`, `FastEmbedProvider._embed_sync` |
| Heavy pure-Python CPU work | process pool / separate worker service | (would be the ingestion workers at scale) |
| Sync route handler `def` | FastAPI runs it in a threadpool automatically | — |

**GIL note:** Python's Global Interpreter Lock lets only one thread run Python bytecode at a time, but native libraries (ONNX Runtime, NumPy, many I/O calls) release it — so threads give real parallelism for them. Pure-Python CPU work needs processes.

## Dependency injection

FastAPI's `Depends` builds per-request objects and passes them to handlers:

```python
async def get_current_user(
    credentials = Depends(_bearer),          # parses "Authorization: Bearer ..."
    db: AsyncSession = Depends(get_db),      # one session per request
) -> User: ...

@router.get("/documents")
async def list_documents(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)): ...
```

Benefits: handlers declare what they need; cross-cutting concerns (auth, DB sessions) live in one place; tests swap implementations with `app.dependency_overrides` — DocMind's tests replace the embedder and the LLM factory this way (`backend/tests/conftest.py`, `backend/tests/test_chat.py`). Dependencies with `yield` run cleanup code (closing the session) after the request.

## Pydantic validation

Request bodies are Pydantic models; invalid input never reaches your code — FastAPI returns 422. DocMind examples (`backend/app/schemas/`): `EmailStr` + lower-casing for emails, `Field(min_length=8, max_length=128)` plus a custom validator for bcrypt's 72-byte limit, `message: str = Field(min_length=1, max_length=4000)` with a "not blank" validator. Response models (`DocumentOut`) whitelist fields — `storage_path` is never serialized. Settings are validated too (`pydantic-settings` in `backend/app/core/config.py`), so a bad env var fails at startup.

## REST design and status codes

- Resources are nouns (`/documents`, `/conversations/{id}`); methods are verbs (GET read, POST create, DELETE remove, PUT replace, PATCH partial update).
- **Status codes used in DocMind:** 200 OK, 201 Created (register), **202 Accepted** (upload — processing continues asynchronously), 204 No Content (delete), 401 (no/invalid token), 404 (missing *or not yours*), 409 (email taken), 413 (too large), 415 (not a PDF), 422 (validation), 429 (rate limited, with `Retry-After`), 500 (generic), 503 (health: DB down).
- 401 vs 403: 401 = "who are you?" (not authenticated); 403 = "I know you, but no" (not authorized). DocMind returns 404 instead of 403 for other users' resources to avoid confirming they exist.
- Consistent error body: `{"error": {"code", "message"}}` — clients switch on `code`, show `message`.

## Pagination

Not needed for DocMind's list sizes, but know both styles:

- **Offset/limit** (`?limit=20&offset=40`): simple, supports "jump to page 7"; slow on deep pages (the DB still scans skipped rows) and unstable when rows are inserted meanwhile.
- **Cursor/keyset** (`?limit=20&after=<last created_at,id>`): `WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT 20` — uses an index, stable under inserts, O(1) per page; no random page jumps. Use for feeds, chat history, large tables.

## Error handling

Layers: validation (422) → domain errors (`AppError(status, code, message)` raised from services/routes) → a catch-all handler that logs the traceback and returns a generic 500 (`backend/app/core/errors.py`). Streaming adds a twist: after the 200 is sent, errors become an SSE `error` event with a stable code.

## Background jobs vs task queues

| | FastAPI `BackgroundTasks` (DocMind) | Task queue (Celery, RQ, Arq, SQS + workers) |
|---|---|---|
| Runs | in the same process after the response | in separate worker processes |
| Durability | lost on crash/restart | persisted in a broker; retried |
| Scaling | shares CPU with the API | workers scale independently |
| Extras | none | retries, scheduling, priorities, rate limits, dead-letter queues |
| Ops cost | zero | broker + workers + monitoring |

DocMind mitigates the durability gap by failing stale `processing` documents on startup (`fail_stale_processing_documents`).

## SSE vs WebSockets vs long polling

| | Server-Sent Events | WebSockets | Long polling |
|---|---|---|---|
| Direction | server → client | both ways | client asks, server holds until data |
| Protocol | plain HTTP response (`text/event-stream`) | upgraded TCP connection | plain HTTP |
| Auth / proxies | normal headers, works through most proxies (disable buffering) | custom handshake; sticky sessions for scale | normal |
| Best for | streaming LLM output, notifications | chat apps, collaboration, games | legacy fallback |

DocMind reads SSE with `fetch` + `ReadableStream` (not `EventSource`, which is GET-only and can't set `Authorization`). Implementation details: `media_type="text/event-stream"`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` (stops nginx buffering the whole stream), JSON-encode each `data:` so newlines in tokens don't break framing.

## Idempotency

An operation is **idempotent** if repeating it has the same effect as doing it once — GET, PUT, DELETE are by definition; POST usually isn't. Networks retry, users double-click, so for non-idempotent operations (payments, uploads) clients send an **`Idempotency-Key`** header; the server stores the key with the result and returns the stored result on a repeat instead of acting twice. In DocMind, `DELETE /documents/{id}` is idempotent in effect (second call → 404, nothing changes), and `scripts/seed.py` is written to be idempotent (skips the existing user and documents). Uploads aren't — a retry creates a duplicate document; an idempotency key or a content hash (`sha256` per user) would fix it.

## Other backend points DocMind demonstrates

- **Connection pooling:** one async engine per process with `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True` (`backend/app/db/session.py`).
- **Configuration:** 12-factor style — all config from environment, validated at startup.
- **Lifespan hook:** load the embedding model once at startup (in a thread), dispose the engine at shutdown (`backend/app/main.py`).
- **Middleware:** request ID + latency logging + security headers in one place.

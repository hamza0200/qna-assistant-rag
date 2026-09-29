# 2. Architecture walkthrough

![System architecture](diagrams/architecture.svg)

Three tiers: a **Next.js** frontend (static shell + client components), a **FastAPI** backend that owns all AI logic, and **PostgreSQL + pgvector** holding both relational data and embeddings. The only external call is to the LLM provider.

## Backend layering

| Layer | Path | Rule |
|---|---|---|
| Routes | `backend/app/api/routes/*.py` | HTTP only: validate input, check auth/ownership, choose status codes, frame SSE |
| Dependencies | `backend/app/api/deps.py` | `get_db` (one session per request), `get_current_user` (JWT → `User`) |
| Services | `backend/app/services/*.py` | Business logic; no HTTP objects |
| Data | `backend/app/db/models.py`, `session.py` | ORM models, async engine + pool |
| Core | `backend/app/core/*.py` | Config, security, logging, errors, rate limiting |

Why it matters: services can be unit-tested and reused (the eval script calls `rag.retrieve_for_turn` directly), and providers are interfaces (`EmbeddingProvider`, `LLMProvider`) chosen by configuration.

## Ingestion flow, step by step

![Ingestion flow](diagrams/ingestion.svg)

**1. Route.** `upload_documents` in `backend/app/api/routes/documents.py` — requires a JWT, rate-limited to 10 uploads/min per user, at most 10 files per request.

**2. Validation.** `backend/app/utils/upload_validation.py` checks extension, declared MIME type, size and magic bytes. The file is read with `upload.read(max_bytes + 1)` — enough to detect "too big" without reading an unbounded body. The whole batch is validated before anything is stored.

```python
if not filename.lower().endswith(".pdf"):
    raise AppError(415, "UNSUPPORTED_FILE_TYPE", ...)
if mime not in ALLOWED_MIME_TYPES:          # application/pdf
    raise AppError(415, "UNSUPPORTED_FILE_TYPE", ...)
if len(data) > max_bytes:
    raise AppError(413, "FILE_TOO_LARGE", ...)
if not data.startswith(PDF_MAGIC):          # b"%PDF-"
    raise AppError(415, "UNSUPPORTED_FILE_TYPE", "... not a valid PDF")
```

**3. Storage.** `save_upload` (`backend/app/utils/storage.py`) writes `<uuid4>.pdf`; reads resolve the path and refuse anything outside the upload root. The user's filename is sanitized and kept only for display.

**4. Response.** One `documents` row per file with `status=processing`; the endpoint returns **202 Accepted** and schedules `background.add_task(ingest_document, doc.id, embedder)`.

**5. Parse.** `parse_pdf` (`backend/app/services/pdf_parser.py`) runs in `asyncio.to_thread` because pypdf is CPU-bound. It normalizes whitespace but keeps newlines (table cells are line-separated in PDFs) and removes lines repeated on ≥ 60 % of pages (running headers).

**6. Chunk.** `chunk_pages` (`backend/app/services/chunker.py`) splits each page independently: paragraph → line → sentence → word → hard cut, then greedily merges pieces up to 800 characters, carrying ≤ 150 characters of whole trailing pieces into the next chunk.

**7. Embed.** Batches of 32 through `FastEmbedProvider.embed_documents`, also in a thread. The text embedded is `"<document title>\n<chunk>"`, so a question naming a document ("the vendor notes") matches its chunks.

**8. Store.** All chunks are inserted with one executemany `INSERT`, and `status='ready'` is set in the *same transaction*. Any exception rolls back and sets `status=failed` with a user-safe message.

**9. Poll.** The Documents page polls every 2 s *only while* something is processing.

## Chat flow, step by step

![Chat flow](diagrams/chat.svg)

**1. Client.** `useChatStream.send` (`frontend/src/hooks/useChatStream.ts`) POSTs with `fetch`, keeps an `AbortController` for Stop, and adds an optimistic user message plus an empty assistant message.

**2. Before streaming.** `chat()` in `backend/app/api/routes/chat.py` authenticates, validates (≤ 4,000 characters), rate-limits (20/min per user) and checks conversation ownership. Errors here are normal JSON with 4xx codes — once the 200 and headers are sent, failures can only be reported as an `error` event.

**3. Orchestration.** `answer_stream` (`backend/app/services/rag.py`) is an async generator of `(event, data)` pairs:

```python
async with SessionLocal() as db:
    history = await load_history(db, conv_id, s.history_messages)
    db.add(Message(conversation_id=conv_id, role=MessageRole.user,
                   content=inp.message))
    await db.commit()
    yield "meta", {"conversation_id": ..., "message_id": ...}
    retrieved = await retrieve_for_turn(db, embedder, inp, previous)

if not retrieved:
    yield "token", {"text": NO_CONTEXT_ANSWER}   # the LLM is not called
else:
    sources_text, sources = format_sources(retrieved, s.max_context_chars)
    messages = build_messages(inp.message, sources_text, history)
    async for text in llm.stream(SYSTEM_PROMPT, messages, usage):
        yield "token", {"text": text}
    citations = build_citations("".join(answer_parts), sources)
yield "citations", citations
yield "done", {}
```

**4. Retrieval.** `search_chunks` (`backend/app/services/retriever.py`):

```python
distance = Chunk.embedding.cosine_distance(query_vector)   # pgvector <=>
stmt = (
    select(Chunk, Document.filename, distance.label("distance"))
    .join(Document, Chunk.document_id == Document.id)
    .where(Document.user_id == user_id,
           Document.status == DocumentStatus.ready)
    .order_by(distance)
    .limit(top_k)
)
...
return [r for r in results if r.score >= min_similarity]  # 1 - distance
```

The user filter is *in the SQL*, so another user's text can never reach the prompt. The threshold is applied after `ORDER BY … LIMIT` so Postgres can use the HNSW index.

**5. Prompt.** `backend/app/services/prompts.py` builds numbered `<source id="1" file="…" page="3">` blocks, neutralizes delimiter look-alikes inside chunk text, and places the question *after* the sources.

**6. LLM.** `AnthropicProvider.stream` (`backend/app/services/llm.py`) streams text deltas and records token usage and timings.

**7. Citations.** The regex `\[(\d{1,2})\]` over the finished answer finds which sources were used; only those become chips, keeping their original numbers.

**8. Persist.** The assistant message and its citations (JSONB) are saved. On Stop/disconnect, the `finally` block saves the partial answer inside `anyio.CancelScope(shield=True)`.

**9. Render.** `MessageBubble` renders Markdown with `react-markdown` (no raw HTML), rewrites `[n]` into `#cite-n` links rendered as buttons, and shows `CitationChip`s that open `SourcePanel` (which fetches `GET /api/chunks/{id}`).

## The SSE contract

```
event: meta       data: {"conversation_id": "...", "message_id": "..."}
event: token      data: {"text": "partial text"}          (repeated)
event: citations  data: [{"index":1,"chunk_id":"...","filename":"...","page":3,"score":0.82,"snippet":"..."}]
event: error      data: {"code":"LLM_TIMEOUT","message":"..."}
event: done       data: {}
```

Why `meta` first: the client learns the conversation ID immediately (to update the URL and sidebar) even if the answer later fails. Why JSON in `data`: tokens can contain newlines, which would otherwise break SSE framing.

## Data model

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id uuid`, `email` (unique), `password_hash` | bcrypt hash includes salt + cost |
| `documents` | `user_id`, `filename`, `storage_path`, `page_count`, `chunk_count`, `status`, `error_message` | status enum `processing/ready/failed` |
| `chunks` | `document_id` (ON DELETE CASCADE), `chunk_index`, `page_number`, `content`, `token_count`, `embedding vector(384)` | HNSW index with `vector_cosine_ops`; B-tree on `document_id` |
| `conversations` | `user_id`, `title`, `updated_at` | sidebar sorted by `updated_at` |
| `messages` | `conversation_id`, `role`, `content`, `citations jsonb` | citations denormalized: always read with the message |

The first Alembic migration (`backend/alembic/versions/0001_initial_schema.py`) runs `CREATE EXTENSION IF NOT EXISTS vector` before creating the `vector(384)` column, and CI runs `alembic check` to fail if models and migrations drift apart.

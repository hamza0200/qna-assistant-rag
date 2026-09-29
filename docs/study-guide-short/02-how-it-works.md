# 2. How DocMind works

![System architecture](diagrams/architecture.svg)

**Three tiers:** Next.js frontend → FastAPI backend (all the AI logic) → PostgreSQL + pgvector (rows *and* vectors). The only external call is the LLM.

**Backend layers:** routes (HTTP only) → services (logic) → database. Providers are interfaces (`EmbeddingProvider`, `LLMProvider`), so Claude/OpenAI are swapped by config and tests use fakes.

## Upload → ingestion

![Ingestion flow](diagrams/ingestion.svg)

| Step | Where | Key point |
|---|---|---|
| Validate | `utils/upload_validation.py` | extension + MIME + `%PDF-` magic bytes + size, whole batch first |
| Store | `utils/storage.py` | `<uuid>.pdf` — user filename never used as a path |
| Respond | `routes/documents.py` | `202 Accepted`, `status=processing`, background task scheduled |
| Parse | `services/pdf_parser.py` | pypdf per page, in a thread (CPU-bound); strip repeated headers |
| Chunk | `services/chunker.py` | paragraph → line → sentence → word; 800/150; per page |
| Embed | `services/embeddings.py` | batches of 32, in a thread; title + chunk is embedded |
| Save | `services/ingestion.py` | chunks + `ready` in one transaction; errors → `failed` + message |

## Question → streamed answer

![Chat flow](diagrams/chat.svg)

1. **Before streaming:** JWT, validation, rate limit, conversation ownership → normal 4xx errors.
2. Save the user message → `meta` event.
3. **Retrieve** (`services/retriever.py`): `ORDER BY embedding <=> query LIMIT 5`, joined to the user's ready documents, then drop scores < 0.45. Follow-ups also search "previous question + question".
4. **Nothing left?** Send a fixed "not found" answer; **the LLM is not called**.
5. **Prompt** (`services/prompts.py`): system rules + history + numbered `<source>` blocks + question last.
6. **Stream** (`services/llm.py`): each text delta becomes a `token` event.
7. **Citations:** find `[n]` in the answer → send only those → `done`.
8. **Save** the answer. On Stop/disconnect, save the partial answer (in a shielded cancel scope).

**SSE events:** `meta` → `token` × N → `citations` → `done` (or `error` with a code such as `LLM_TIMEOUT`).

## Data model (5 tables)

`users` → `documents` → `chunks` (`embedding vector(384)`, HNSW index, `ON DELETE CASCADE`); `users` → `conversations` → `messages` (`citations` as JSONB). Every query joins back to `user_id` — that's the security model.

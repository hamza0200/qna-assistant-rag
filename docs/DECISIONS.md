# Architecture Decision Log

Each entry: **Context / Decision / Alternatives considered / Trade-offs**. Entries are appended as the project is built.

---

## ADR-001 — Repository root is the project root

**Context.** The spec's folder tree is rooted at `docmind-ai/`, but the repository was created as `qa-assistant/` with `CLAUDE.md` already at its root.
**Decision.** Treat the repository root as `docmind-ai/`; every path in the spec maps 1:1 onto the repo root.
**Alternatives considered.** Nesting everything under a `docmind-ai/` subfolder.
**Trade-offs.** Nesting would add a pointless level to every command (`cd docmind-ai && make up`) and split `CLAUDE.md` from the code it describes.

## ADR-002 — Configurable host ports

**Context.** Ports 5432, 8000 and 3000 are commonly in use on developer machines (they were on the build machine).
**Decision.** `docker-compose.yml` maps host ports from `DB_PORT`, `BACKEND_PORT`, `FRONTEND_PORT` (defaults 5433/8000/3000). Postgres defaults to 5433 on the host to avoid clashing with a local Postgres.
**Alternatives considered.** Hard-coded ports.
**Trade-offs.** Three more env vars, and `CORS_ORIGINS` / `NEXT_PUBLIC_API_URL` must be kept in sync with the chosen ports (documented in `.env.example`).

## ADR-003 — `bcrypt` directly instead of `passlib`

**Context.** The spec allows `passlib`/`bcrypt`. `passlib` is unmaintained (last release 2020) and emits errors against `bcrypt>=4.1`.
**Decision.** Call the `bcrypt` library directly in `backend/app/core/security.py`.
**Alternatives considered.** `passlib[bcrypt]` with a pinned old `bcrypt`; `argon2-cffi` (Argon2id, the current OWASP first choice).
**Trade-offs.** No algorithm-agility helpers from passlib (we would have to add rehash-on-login ourselves if we migrate to Argon2). bcrypt truncates passwords at 72 bytes, so we reject longer passwords explicitly.

## ADR-004 — Implied driver/adapter dependencies

**Context.** The fixed stack implies a few packages it doesn't name.
**Decision.** Added `asyncpg` (the async Postgres driver SQLAlchemy async needs), `pgvector` (Python adapter giving SQLAlchemy a `Vector` column type), `email-validator` (backs Pydantic's `EmailStr`). SSE is written by hand on `StreamingResponse` rather than adding `sse-starlette`.
**Alternatives considered.** `psycopg` 3 async; raw SQL for vector columns.
**Trade-offs.** asyncpg is the fastest and most common async driver; the SSE wire format is ~5 lines so a library adds little.

## ADR-005 — Tailwind CSS v4 (CSS-first config)

**Context.** The spec lists `tailwind.config.ts`, but the current `create-next-app` installs Tailwind v4, which configures themes in CSS (`@theme`) and no longer needs a JS config file.
**Decision.** Use Tailwind v4 with its CSS-first configuration in `src/app/globals.css`; no `tailwind.config.ts`.
**Alternatives considered.** Pin Tailwind v3 to match the spec literally.
**Trade-offs.** Deviates from the spec's file list but follows the tool's current default; pinning an old major version would be the less defensible choice.

## ADR-006 — Next.js standalone output and build-time API URL

**Context.** The browser calls the FastAPI backend directly. `NEXT_PUBLIC_*` variables are inlined into the JS bundle at `next build`.
**Decision.** `output: "standalone"` for a small runtime image; `NEXT_PUBLIC_API_URL` passed as a Docker build arg.
**Alternatives considered.** Proxying `/api/*` through Next.js rewrites (same origin, no CORS); a runtime `/config` endpoint.
**Trade-offs.** One image per environment (the URL is baked in). A Next proxy would remove CORS but adds a hop and can buffer SSE streams.

## ADR-007 — Chunking: ~800 chars, 150 overlap, recursive boundaries, never across pages

**Context.** Chunks are the unit of retrieval and citation. Too large and each embedding blurs several topics (and wastes prompt tokens); too small and a chunk lacks the context to answer anything.
**Decision.** `backend/app/services/chunker.py` splits recursively on paragraph → line → sentence → word boundaries, packs pieces up to 800 characters, and repeats up to 150 characters of whole trailing pieces at the start of the next chunk. Each page is chunked independently, so a chunk never spans two pages.
**Alternatives considered.** Fixed-size windows (cuts mid-sentence); token-based splitting with the LLM's tokenizer (provider-specific); semantic chunking with embeddings (slower, more complex); cross-page chunks.
**Trade-offs.** No cross-page chunks means every citation is exactly one page, which is simple and honest, but a sentence that continues onto the next page is split in two (overlap can't bridge pages). ~800 chars (~200 tokens) fits the 512-token window of `bge-small` comfortably. Overlap is in whole pieces, so a single very long sentence can produce a boundary without overlap.

## ADR-008 — Strip running headers; embed the document title with each chunk

**Context.** Every sample page starts with the same three header lines. Repeated boilerplate makes unrelated chunks look alike to the embedding model. Conversely, queries often name a document ("according to the vendor notes…") whose name never appears in the chunk body.
**Decision.** `pdf_parser.py` removes lines that repeat on ≥60% of a multi-page document's pages, plus bare page labels. `ingestion.py` embeds `"<document title>\n<chunk>"` (a contextual chunk header) while storing the chunk text verbatim.
**Alternatives considered.** Keep raw text; LLM-generated per-chunk context summaries ("contextual retrieval").
**Trade-offs.** Header detection can't work on single-page documents and could in theory drop a legitimately repeated line. LLM-generated context would be better still but costs an LLM call per chunk at ingestion.

## ADR-009 — FastAPI BackgroundTasks for ingestion (not Celery/Redis)

**Context.** Parsing and embedding take ~100 ms–seconds per document; the upload request shouldn't block on it.
**Decision.** Upload returns `202 Accepted` with `status=processing` and schedules `ingest_document` as a `BackgroundTask`. CPU-bound work (pypdf, ONNX inference) runs in `asyncio.to_thread` so the event loop keeps serving other requests. On startup, documents stuck in `processing` are marked `failed`.
**Alternatives considered.** Celery/RQ/Arq with Redis; a Postgres-backed job table (`SELECT … FOR UPDATE SKIP LOCKED`); synchronous processing inside the request.
**Trade-offs.** Zero extra infrastructure, but jobs live in process memory: no retries, no persistence across restarts (mitigated by the startup sweep), and heavy ingestion competes with API requests for the same CPU. At scale, move to a durable queue with separate worker processes.

## ADR-010 — Upload validation: extension + MIME + magic bytes + size, UUID storage names

**Context.** Uploads are the main untrusted-input surface. Extension and `Content-Type` are both client-controlled.
**Decision.** `backend/app/utils/upload_validation.py` checks all three plus a size limit enforced while reading (`read(max+1)`); a batch is validated completely before anything is stored. Files are saved as `<uuid>.pdf`; the original filename is sanitized and kept only for display.
**Alternatives considered.** Trust `Content-Type`; full PDF structural validation or antivirus scanning (e.g. ClamAV).
**Trade-offs.** Magic bytes prove "starts like a PDF", not "is a safe PDF"; pypdf still parses untrusted input (it runs in a background task, so failures only affect that document). Production would add malware scanning and store files in object storage.

## ADR-011 — Server-Sent Events over `fetch` (not WebSockets, not EventSource)

**Context.** Answers must stream token by token. Traffic is one-directional (server → client) per request, and the request needs a JSON body and an `Authorization` header.
**Decision.** `POST /api/chat` returns `text/event-stream` with typed events (`meta`, `token`, `citations`, `error`, `done`). The browser reads it with `fetch` + `ReadableStream` and a small incremental parser (`frontend/src/lib/sse.ts`); `AbortController` implements Stop.
**Alternatives considered.** WebSockets (bidirectional, stateful connections, needs its own auth handshake and sticky load balancing); the native `EventSource` API (GET only, no custom headers); long polling.
**Trade-offs.** SSE is plain HTTP: works through proxies/CDNs (with buffering disabled via `X-Accel-Buffering: no`), scales like any request, and is trivial to test. We lose EventSource's automatic reconnection (we don't need to resume a half-finished answer) and can't push unsolicited server messages — not needed here.

## ADR-012 — Provider-agnostic LLM wrapper; Anthropic default with effort and refusal fallback

**Context.** The spec requires Anthropic (default) and OpenAI, chosen by env var, with timeouts, retries and token logging.
**Decision.** `backend/app/services/llm.py` defines `LLMProvider.stream(system, messages, usage)`; `AnthropicProvider` and `OpenAIProvider` translate SDK exceptions into one `LLMError(code, message)` that becomes an SSE `error` event. Default model `claude-opus-5-5` with `effort: low` (short grounded answers don't need deep deliberation; lower latency and cost) and Anthropic's server-side refusal fallback (`fallbacks: "default"`), which reruns a classifier-declined request on a recommended model inside the same stream. Retries (exponential backoff) are left to the SDKs, which retry only before the stream starts; a mid-stream failure is surfaced, not retried, because the user has already seen tokens.
**Alternatives considered.** LangChain/LlamaIndex abstractions; a single provider; retrying mid-stream.
**Trade-offs.** A thin in-house interface is ~150 lines we fully understand and control, at the cost of re-implementing provider differences ourselves. The model name is configuration, never hard-coded in logic.

## ADR-013 — Citations: numbered sources, only the ones actually referenced

**Context.** FR5 requires citation chips; the spec prefers showing only sources actually used.
**Decision.** Sources are rendered as `<source id="n" file=… page=…>` blocks; the model cites `[n]` inline; after the stream, `rag.build_citations` parses `[n]` markers and emits only those, keeping the original numbers so inline markers match the chips. An answer that cites nothing (e.g. a "not found" reply) gets no chips.
**Alternatives considered.** Show all retrieved sources; provider-native citation features (e.g. Anthropic's document citations).
**Trade-offs.** Relies on the model following the citation format (verified in the eval). Provider-native citations are more precise but provider-specific and incompatible with our provider-agnostic wrapper.

## ADR-014 — Follow-ups: chat history in the prompt + dual retrieval

**Context.** FR7 requires the last N (6) messages as history. A follow-up like "And what uptime SLA does it include?" embeds poorly on its own.
**Decision.** The prompt includes the last 6 messages as plain chat turns (without their old source blocks) and fresh sources for the new question. Retrieval runs twice for follow-ups — the question alone, and the question prefixed with the previous user question — and merges by best score.
**Alternatives considered.** LLM query rewriting into a standalone question (stretch goal; costs an extra LLM call and latency); retrieval on the concatenation only (drags unrelated new questions toward the old topic).
**Trade-offs.** Two embeddings + two vector searches (~20 ms) instead of one; no extra LLM call.

## ADR-015 — Offline `fake` LLM provider for development and CI

**Context.** The full pipeline (SSE, citations, UI) should be demonstrable and testable without an API key or network.
**Decision.** `LLM_PROVIDER=fake` selects `FakeExtractiveProvider`, which streams the top source's text back as an "answer" with a `[1]` citation, clearly labelled "Offline demo mode". Backend tests use a separate scripted fake injected via dependency override.
**Alternatives considered.** Only mocks in unit tests; a local open-source model (Ollama).
**Trade-offs.** Not a real answer engine — it can't be used for the eval. It exists purely to exercise the plumbing.

## ADR-016 — `react-markdown` + `remark-gfm` for answers

**Context.** FR4 requires Markdown rendering; answers over tabular documents often contain tables.
**Decision.** `react-markdown` (pre-approved) with its `remark-gfm` plugin (tables, strikethrough). Inline `[n]` markers are rewritten to `#cite-n` links and rendered as buttons that open the source panel.
**Alternatives considered.** `dangerouslySetInnerHTML` with a Markdown-to-HTML library; plain text.
**Trade-offs.** react-markdown builds React elements and ignores raw HTML by default, so model output (which can be influenced by document content) can't inject script — important because the LLM is fed untrusted text.

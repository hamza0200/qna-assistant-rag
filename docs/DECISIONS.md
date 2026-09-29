# Architecture Decision Log

Each entry: **Context / Decision / Alternatives considered / Trade-offs**. Entries were appended in the order the decisions were made while building.

- [ADR-001 — Repository root is the project root](#adr-001--repository-root-is-the-project-root)
- [ADR-002 — Configurable host ports](#adr-002--configurable-host-ports)
- [ADR-003 — `bcrypt` directly instead of `passlib`](#adr-003--bcrypt-directly-instead-of-passlib)
- [ADR-004 — Implied driver/adapter dependencies](#adr-004--implied-driveradapter-dependencies)
- [ADR-005 — Tailwind CSS v4 (CSS-first config)](#adr-005--tailwind-css-v4-css-first-config)
- [ADR-006 — Next.js standalone output and build-time API URL](#adr-006--nextjs-standalone-output-and-build-time-api-url)
- [ADR-007 — Chunking: ~800 chars, 150 overlap, recursive boundaries, never across pages](#adr-007--chunking-800-chars-150-overlap-recursive-boundaries-never-across-pages)
- [ADR-008 — Strip running headers; embed the document title with each chunk](#adr-008--strip-running-headers-embed-the-document-title-with-each-chunk)
- [ADR-009 — FastAPI BackgroundTasks for ingestion (not Celery/Redis)](#adr-009--fastapi-backgroundtasks-for-ingestion-not-celeryredis)
- [ADR-010 — Upload validation: extension + MIME + magic bytes + size, UUID storage names](#adr-010--upload-validation-extension--mime--magic-bytes--size-uuid-storage-names)
- [ADR-011 — Server-Sent Events over `fetch` (not WebSockets, not EventSource)](#adr-011--server-sent-events-over-fetch-not-websockets-not-eventsource)
- [ADR-012 — Provider-agnostic LLM wrapper; Anthropic default with effort and refusal fallback](#adr-012--provider-agnostic-llm-wrapper-anthropic-default-with-effort-and-refusal-fallback)
- [ADR-013 — Citations: numbered sources, only the ones actually referenced](#adr-013--citations-numbered-sources-only-the-ones-actually-referenced)
- [ADR-014 — Follow-ups: chat history in the prompt + dual retrieval](#adr-014--follow-ups-chat-history-in-the-prompt--dual-retrieval)
- [ADR-015 — Offline `fake` LLM provider for development and CI](#adr-015--offline-fake-llm-provider-for-development-and-ci)
- [ADR-016 — `react-markdown` + `remark-gfm` for answers](#adr-016--react-markdown--remark-gfm-for-answers)
- [ADR-017 — JWT in memory + localStorage (not an httpOnly cookie)](#adr-017--jwt-in-memory--localstorage-not-an-httponly-cookie)
- [ADR-018 — Rate limiting per user (authenticated) or per IP (anonymous), in memory](#adr-018--rate-limiting-per-user-authenticated-or-per-ip-anonymous-in-memory)
- [ADR-019 — Security headers and a CSP on both apps](#adr-019--security-headers-and-a-csp-on-both-apps)
- [ADR-020 — Similarity threshold `MIN_SIMILARITY = 0.45`, `TOP_K = 5` (tuned with the eval)](#adr-020--similarity-threshold-minsimilarity--045-topk--5-tuned-with-the-eval)
- [ADR-021 — Eval design: retrieval in-process, answers over HTTP, string-match grading](#adr-021--eval-design-retrieval-in-process-answers-over-http-string-match-grading)
- [ADR-022 — FastAPI (Python) for the backend, not Node/NestJS](#adr-022--fastapi-python-for-the-backend-not-nodenestjs)
- [ADR-023 — Next.js App Router with client components for the app screens](#adr-023--nextjs-app-router-with-client-components-for-the-app-screens)
- [ADR-024 — pgvector inside Postgres, not a dedicated vector database](#adr-024--pgvector-inside-postgres-not-a-dedicated-vector-database)
- [ADR-025 — Local FastEmbed embeddings (`bge-small-en-v1.5`), not a hosted embeddings API](#adr-025--local-fastembed-embeddings-bge-small-en-v15-not-a-hosted-embeddings-api)
- [ADR-026 — Retrieval-Augmented Generation, not fine-tuning](#adr-026--retrieval-augmented-generation-not-fine-tuning)

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

## ADR-017 — JWT in memory + localStorage (not an httpOnly cookie)

**Context.** The SPA needs to send the token on every API call, including the streaming `fetch`, and survive page reloads.
**Decision.** Keep the JWT in a module variable and mirror it to `localStorage` (`frontend/src/lib/auth.ts`); send it as `Authorization: Bearer`. A 401 clears it; logging out in one tab logs out the others via the `storage` event.
**Alternatives considered.** httpOnly + `Secure` + `SameSite` cookie set by the backend (the production choice); memory-only (lost on refresh); refresh-token rotation.
**Trade-offs.** localStorage is readable by any script on the origin, so an XSS bug would expose the token. Mitigations here: React escapes output, Markdown is rendered without raw HTML, the CSP restricts `connect-src` to our own API (limiting exfiltration), and tokens expire after 60 minutes. An httpOnly cookie removes script access entirely but brings CSRF into scope (needs `SameSite` and/or CSRF tokens) and cross-origin cookie configuration between the frontend and API.

## ADR-018 — Rate limiting per user (authenticated) or per IP (anonymous), in memory

**Context.** Chat calls cost money; login is a brute-force target; uploads are CPU-heavy.
**Decision.** slowapi with limits from env (`/chat` 20/min, upload 10/min, `/auth/login` 5/min). The key is `user:<id>` when a valid JWT is present, else `ip:<addr>`. 429s use the standard error shape and include `Retry-After`.
**Alternatives considered.** Per-IP only (punishes users sharing an office NAT); an API gateway (nginx, Cloudflare, AWS API Gateway); Redis-backed counters.
**Trade-offs.** In-memory counters are per process: with N replicas the effective limit is N× the configured one and counters reset on restart. For horizontal scaling, point slowapi at Redis (`storage_uri`).

## ADR-019 — Security headers and a CSP on both apps

**Context.** Defence in depth against clickjacking, MIME sniffing and XSS.
**Decision.** The API sends `default-src 'none'` CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer` (it only serves JSON/SSE; `/docs` is exempt from the CSP and disabled in production). The frontend follows Next's no-nonce CSP recipe with `connect-src` limited to our API origin.
**Alternatives considered.** Nonce-based CSP via Next's `proxy.ts` (stricter `script-src`, but forces dynamic rendering of every page).
**Trade-offs.** `'unsafe-inline'` scripts are still allowed on the frontend; a nonce-based CSP would close that at the cost of static optimisation.

## ADR-020 — Similarity threshold `MIN_SIMILARITY = 0.45`, `TOP_K = 5` (tuned with the eval)

**Context.** The spec suggests 0.35 and asks for the value to be tuned on the eval set. The threshold decides when the LLM is skipped entirely ("not found" without a model call).
**Decision.** `scripts/eval.py --sweep` measured retrieval hit-rate for TOP_K ∈ {3, 5, 8} × MIN_SIMILARITY ∈ {0.35 … 0.6}, and a separate probe compared top-1 scores of answerable vs off-topic questions with `bge-small-en-v1.5`:
- Answerable questions: top-1 between **0.508** (Q7, "RPO and RTO" — acronyms) and 0.84.
- Off-topic probes ("capital of France", "sourdough bread", "World Cup"…): top-1 between **0.416 and 0.541**.
- Hit-rate is 21/21 up to 0.45, 20/21 at 0.5, 19/21 at 0.6; TOP_K 3/5/8 made no difference on this corpus.
The distributions overlap, so no threshold separates them. 0.45 keeps every answerable question (margin 0.058) and short-circuits the clearly off-topic ones (4 of 10 probes) without an LLM call; the rest are refused by the grounded prompt. TOP_K stays 5 to give multi-document questions room.
**Alternatives considered.** 0.35 (filters nothing with this model); ~0.52 (drops a real question); a reranker score threshold (cross-encoders give much better-calibrated relevance scores).
**Trade-offs.** Favours recall: a false "not found" is worse than an LLM call that ends in a refusal. The threshold is model-specific and must be re-tuned if the embedding model changes. Two in-domain refusal questions (Q20 stock price, Q21 London office) score like answerable ones (~0.69–0.74) — only the prompt can handle those.

## ADR-021 — Eval design: retrieval in-process, answers over HTTP, string-match grading

**Context.** §13 asks for retrieval hit-rate and answer accuracy against `test-questions.md`.
**Decision.** Retrieval is scored by calling `rag.retrieve_for_turn` (the chat route's own code path, including follow-up handling) as the demo user — cheap, deterministic, no API key. Answers are scored by streaming real `/api/chat` responses (so the whole system is under test) and checking key facts case-insensitively (word boundaries for short facts, thousands separators optional), refusal phrasing for refusal questions, and forbidden strings plus an "is USD 5" pattern for the injection question. The scorer has its own unit tests (`backend/tests/test_eval_scoring.py`), including "every reference answer passes its own scoring".
**Alternatives considered.** LLM-as-judge (better at paraphrase, but costs money, is itself non-deterministic and needs its own validation); exact-match answers.
**Trade-offs.** String matching can't credit a correct paraphrase ("two hours" vs "2 hours") and can be fooled by an answer that mentions a fact while getting it wrong; it is transparent and free. One quirk found: Q13's reference answer never literally contains its key fact "Bahrain".

## ADR-022 — FastAPI (Python) for the backend, not Node/NestJS

**Context.** The backend is mostly AI plumbing: PDF parsing, embeddings, vector search, LLM streaming.
**Decision.** Python 3.12 + FastAPI (async), Pydantic v2, SQLAlchemy 2 async.
**Alternatives considered.** Node with NestJS or Express (one language across the stack, excellent async I/O); Django (batteries included, but async support is partial).
**Trade-offs.** Python has the richest AI/ML ecosystem (local ONNX embeddings, pypdf, every LLM SDK ships Python first), and FastAPI gives typed request validation and OpenAPI docs for free. The cost is two languages in the repo and Python's GIL for CPU-bound work, which we push to threads (native code releases the GIL) or would move to worker processes at scale. NestJS would be the pick for a team that is TypeScript-only or where AI is a small part of the system.

## ADR-023 — Next.js App Router with client components for the app screens

**Context.** The spec fixes Next.js (App Router) + TypeScript. The screens are behind login and highly interactive (streaming chat, drag-and-drop).
**Decision.** App Router for routing, layouts and fonts; the authenticated pages are client components because the token lives in the browser and the UI is stateful. Server rendering is used for the root layout and static shell.
**Alternatives considered.** Pages Router; a plain Vite SPA; server components fetching data with a cookie-based session.
**Trade-offs.** With a localStorage token, server components can't fetch user data, so we don't benefit from RSC data fetching here. Moving auth to an httpOnly cookie would let server components render document lists and conversations on the server.

## ADR-024 — pgvector inside Postgres, not a dedicated vector database

**Context.** We need vector similarity search filtered by owner and document, alongside ordinary relational data.
**Decision.** Postgres 16 + pgvector with an HNSW index (`vector_cosine_ops`) on `chunks.embedding`.
**Alternatives considered.** Pinecone (managed, serverless), Qdrant/Weaviate/Milvus (self-hosted or managed, purpose-built), FAISS in process.
**Trade-offs.** One database means one backup/restore story, transactions that cover chunks and document status together, ownership filters expressed as normal SQL joins (hard to get wrong), and no data sync between two stores. Dedicated engines win at very large scale (hundreds of millions of vectors, sharding, quantization, advanced hybrid/filtered search, multi-tenancy features). Move when the vector workload needs to scale independently of the relational one, or recall/latency with filters degrades.

## ADR-025 — Local FastEmbed embeddings (`bge-small-en-v1.5`), not a hosted embeddings API

**Context.** Every chunk and every query needs an embedding.
**Decision.** FastEmbed (ONNX Runtime, CPU) with `BAAI/bge-small-en-v1.5` (384 dimensions), baked into the Docker image, behind an `EmbeddingProvider` interface.
**Alternatives considered.** OpenAI `text-embedding-3-small/large`, Voyage, Cohere; larger open models (bge-base/large, e5, gte).
**Trade-offs.** Free, private (documents never leave the server for embedding), no API key, ~10 ms per query on CPU, and small vectors (384 floats = 1.5 KB per chunk). Hosted models are generally more accurate, multilingual and have longer input windows, but add cost, latency, a network dependency and data-sharing questions. Switching is one class plus a migration (new dimension) and a full re-embed of existing chunks.

## ADR-026 — Retrieval-Augmented Generation, not fine-tuning

**Context.** The assistant must answer from each user's private, changing documents, with citations.
**Decision.** RAG: retrieve relevant chunks at question time and put them in the prompt.
**Alternatives considered.** Fine-tuning a model on the documents; long-context "stuff every document into the prompt".
**Trade-offs.** RAG updates instantly when documents change (no retraining), keeps each user's data separate by construction, and supports citations because we know exactly which text the answer was based on. Fine-tuning teaches style and format well but is poor at memorising facts reliably, can't cite, is expensive to redo per change, and would mix users' data into one model. Long-context stuffing works for a handful of small documents but costs more per question and scales poorly; RAG keeps the prompt to ~5 chunks.

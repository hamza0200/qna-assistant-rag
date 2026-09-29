# 3. Every decision and how to defend it

Each entry mirrors an ADR in `docs/DECISIONS.md`. In an interview, lead with the **why**, name the **alternative** you rejected and its cost, then show judgement with **when you'd choose differently**.

## Stack and architecture

### FastAPI (Python) instead of Node/NestJS — ADR-022

- **Why this:** the backend is mostly AI plumbing — PDF parsing, local ONNX embeddings, vector search, LLM SDKs — and Python has the deepest ecosystem for all of it. FastAPI gives async I/O, Pydantic validation and OpenAPI docs from type hints.
- **Why not the alternatives:** NestJS would unify the language with the frontend, but the Python AI libraries would need wrappers or microservices. Django's async story is partial and it brings an ORM/admin we don't need.
- **When I'd choose differently:** a TypeScript-only team, or a product where AI is a thin feature calling hosted APIs — then NestJS/Express and one language win.

### Next.js App Router with client components — ADR-023

- **Why this:** the spec fixes Next.js; the App Router gives layouts, route groups (`(auth)/login`), `next/font` and a static shell. The app screens are interactive (streaming, drag-and-drop), so they're client components.
- **Why not:** a plain Vite SPA would be simpler but lose server rendering for public pages and the framework conventions interviewers expect.
- **When differently:** with cookie-based auth, I'd render document lists and conversation history in server components and stream them — less client JS, faster first paint.

### pgvector inside Postgres instead of a vector database — ADR-024

- **Why this:** one datastore — transactions cover chunks and document status together, ownership filters are plain SQL joins, one backup story, no sync between stores. HNSW gives fast approximate search.
- **Why not:** Pinecone/Qdrant/Weaviate add infrastructure and a consistency problem (vectors and rows in different systems) for a scale we don't have.
- **When differently:** hundreds of millions of vectors, heavy filtered search, a need to scale vector search independently of OLTP, or built-in features like quantization and multi-tenancy isolation.

### Local FastEmbed embeddings instead of a hosted API — ADR-025

- **Why this:** free, private (document text never leaves the server for embedding), no API key, ~10 ms per query on CPU, 384-d vectors (1.5 KB each). Behind an `EmbeddingProvider` interface.
- **Why not:** OpenAI/Voyage/Cohere embeddings are usually more accurate and multilingual, but add per-token cost, latency, a network dependency and data-processing agreements.
- **When differently:** multilingual corpora, long chunks, or when eval shows retrieval quality is the bottleneck. Switching = new class + migration for the new dimension + re-embedding everything.

### RAG instead of fine-tuning — ADR-026

- **Why this:** documents change per user and per day; RAG updates instantly, isolates users' data by construction, and supports citations because we know exactly which text was used.
- **Why not:** fine-tuning is good at style/format, poor at reliably memorising facts, can't cite, is costly to redo, and would mix every user's data into one model. Long-context "stuff everything in" is expensive per question and doesn't scale past a few documents.
- **When differently:** fine-tune (or use a smaller fine-tuned model) for a fixed output format, domain tone, or classification at high volume — often *combined* with RAG.

### Provider-agnostic LLM wrapper — ADR-012

- **Why this:** `LLMProvider.stream(system, messages, usage)` isolates SDK differences; Anthropic and OpenAI are swapped by `LLM_PROVIDER`. SDK errors are normalized into `LLMError(code, message)` → a stable SSE `error` event. Default `claude-opus-5-5` with `effort: low` (short grounded answers don't need deep reasoning) and server-side refusal fallback.
- **Why not:** LangChain/LlamaIndex would give this abstraction plus much more we don't need, with more indirection to debug and faster-moving APIs.
- **When differently:** complex agent/tool pipelines or many integrations, where a framework's ready-made components save real time.

### Offline `fake` LLM provider — ADR-015

- **Why this:** demo and test the whole pipeline (SSE, citations, UI) with no API key or network; clearly labelled "Offline demo mode".
- **Why not:** only mocking in unit tests leaves the UI and deployment path unexercised without a key.
- **When differently:** if an open-source model via Ollama is acceptable for demos, it gives *real* answers offline.

## Ingestion

### Chunking: ~800 chars, 150 overlap, recursive, per page — ADR-007

- **Why this:** ~200 tokens is focused enough for a sharp embedding yet large enough to hold a fact with its context; overlap rescues facts that straddle a boundary; recursive boundaries avoid mid-sentence cuts. Per-page chunks make every citation exactly one page.
- **Why not:** fixed windows cut sentences; semantic chunking costs embeddings at split time; cross-page chunks make citations ambiguous.
- **When differently:** long technical documents (larger chunks + parent-document retrieval), code (split by syntax), or tables (keep rows together / convert to Markdown).

### Strip running headers; embed the title with each chunk — ADR-008

- **Why this:** the same header on every page makes unrelated chunks look similar; prepending the document title lets "according to the vendor notes…" find the right document.
- **Why not:** raw text is simpler but measurably noisier; LLM-generated per-chunk context ("contextual retrieval") costs an LLM call per chunk.
- **When differently:** high-value corpora where better recall justifies ingestion cost.

### BackgroundTasks instead of Celery/Redis — ADR-009

- **Why this:** zero extra infrastructure; `202 Accepted` + polling; CPU work in threads; stale `processing` rows are failed on startup.
- **Why not:** Celery/RQ/Arq add Redis and worker processes — correct at scale, overkill for a one-day build.
- **When differently:** multiple replicas, large files, retries, prioritisation, or ingestion starving API traffic — move to a durable queue with separate autoscaled workers.

### Upload validation and UUID storage names — ADR-010

- **Why this:** extension and MIME are client-controlled; magic bytes check the content; size is enforced while reading; UUID filenames rule out path traversal.
- **Why not:** trusting `Content-Type` alone is trivially bypassed.
- **When differently:** public uploads at scale — add malware scanning (ClamAV/cloud AV), store in S3 with presigned URLs, and parse in an isolated sandbox.

## Retrieval and chat

### SSE over fetch (not WebSockets, not EventSource) — ADR-011

- **Why this:** one-way server → client streaming per request; plain HTTP (proxies, load balancers, auth headers work normally); trivial to test.
- **Why not:** WebSockets are bidirectional and stateful (sticky sessions, custom auth handshake) — unnecessary. `EventSource` can't POST or send `Authorization`.
- **When differently:** collaborative/real-time features (typing indicators, server push outside a request) → WebSockets.

### Similarity threshold 0.45, TOP_K 5 — ADR-020

- **Why this:** measured. Answerable questions scored 0.508–0.84 top-1; off-topic probes 0.416–0.541. 0.45 keeps every answerable question and skips the LLM for clearly off-topic ones.
- **Why not 0.35 (spec default):** filters nothing with this model. **Why not ~0.52:** drops a real question (Q7).
- **When differently:** with a cross-encoder reranker, whose scores are much better calibrated, I'd threshold on the reranker score instead.

### Citations only for sources actually referenced — ADR-013

- **Why this:** chips must mean "this answer relied on this passage"; showing every retrieved chunk implies support that isn't there.
- **Why not:** provider-native citations are more precise but tie us to one provider.
- **When differently:** single-provider system where exact quote spans matter (legal, medical) → native citations.

### Follow-ups: history + dual retrieval — ADR-014

- **Why this:** "And what SLA does *it* include?" embeds poorly alone; a second search with the previous question prefixed recovers context, and merging with the plain search keeps unrelated new questions unbiased. No extra LLM call.
- **Why not:** LLM query rewriting is better but adds a model call (latency + cost) before retrieval.
- **When differently:** longer multi-turn sessions or ambiguous pronouns → rewrite with a small, fast model.

### react-markdown + remark-gfm — ADR-016

- **Why this:** Markdown and tables render as React elements; raw HTML in model output is not executed (the model is fed untrusted text, so its output is untrusted too).
- **Why not:** `dangerouslySetInnerHTML` with a Markdown-to-HTML converter would need sanitisation (DOMPurify) and one mistake is XSS.

## Security and operations

### bcrypt directly, not passlib — ADR-003

- **Why this:** passlib is unmaintained and breaks with modern bcrypt. Direct `bcrypt` is ~5 lines. Cost factor configurable (12 in prod, 4 in tests).
- **When differently:** new systems could choose Argon2id (OWASP's first choice; memory-hard, resists GPU cracking).

### JWT in localStorage, not an httpOnly cookie — ADR-017

- **Why this:** simple for an SPA that calls a separate API origin and streams with `fetch`; survives refresh.
- **Why not (the honest trade-off):** any XSS can read localStorage. Mitigations: React escaping, no raw HTML rendering, CSP with `connect-src` limited to our API, 60-minute expiry.
- **When differently (production):** httpOnly + Secure + SameSite cookie (JS can't read it) plus CSRF protection, short-lived access token + rotating refresh token.

### Rate limiting per user/IP in memory — ADR-018

- **Why this:** protects cost (chat), CPU (upload) and credentials (login) with one decorator each; per-user keys don't punish shared office IPs.
- **When differently:** multiple replicas → Redis-backed counters or limits at the gateway (nginx/Cloudflare/API Gateway).

### Security headers + CSP on both apps — ADR-019

- **Why this:** cheap defence in depth: no framing (clickjacking), no MIME sniffing, strict CSP on a JSON-only API, `connect-src` restriction on the frontend.
- **When differently:** nonce-based CSP via Next's `proxy.ts` removes `'unsafe-inline'` at the cost of dynamic rendering.

### Smaller implementation decisions

- **Repo root = project root (ADR-001)** and **configurable host ports (ADR-002)**: practical — ports 5432/8000/3000 are often taken.
- **Implied dependencies (ADR-004):** `asyncpg` (driver), `pgvector` (SQLAlchemy type), `email-validator`; SSE written by hand instead of `sse-starlette`.
- **Tailwind v4 CSS-first config (ADR-005):** the current default; no `tailwind.config.ts`.
- **Next standalone output + build-time API URL (ADR-006):** small runtime image; `NEXT_PUBLIC_*` is inlined at build.
- **Eval design (ADR-021):** retrieval measured in-process through the production function, answers end-to-end through HTTP, string-match grading that is itself unit-tested.

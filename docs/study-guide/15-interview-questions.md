# 15. Likely interview questions with model answers

Answer shape: **one-sentence answer → one level deeper → example from DocMind or a trade-off.** Keep each under a minute unless asked to go deeper.

## AI and LLMs

**1. What is RAG and why use it?**
Retrieve relevant passages from your own data at question time and put them in the prompt so the model answers from them. It gives fresh, private, citable knowledge without retraining. In DocMind: embed question → pgvector top-5 for this user → numbered sources in the prompt → streamed answer with `[n]` citations.

**2. What is an embedding?**
A vector representation of text where semantic similarity becomes geometric closeness. DocMind uses `bge-small-en-v1.5` (384 dims), normalized, so cosine similarity equals the dot product.

**3. Cosine vs dot product vs Euclidean?**
Cosine measures angle (ignores length), dot product includes magnitude, L2 is straight-line distance. On unit-normalized vectors they produce the same ranking; cosine is the default for text. The pgvector index operator class must match the query operator.

**4. How did you choose chunk size and overlap?**
~800 characters (~200 tokens) with 150 overlap, recursive on natural boundaries, never across pages. Small enough for a focused embedding, big enough to hold a fact with context; overlap saves boundary-straddling facts; per-page keeps citations exact. I'd tune it with the eval set if retrieval degraded.

**5. How do you stop hallucinations?**
Layers: don't call the LLM when retrieval finds nothing; instruct it to answer only from sources and say "not found"; require citations and show only cited sources so users can verify; low-randomness settings; evaluate with refusal questions. No single measure is enough; the goal is to make unsupported claims rare *and* visible.

**6. What is a similarity threshold, and how did you pick yours?**
A minimum score below which retrieved chunks are discarded. I measured: answerable questions scored 0.508–0.84 top-1, off-topic ones 0.416–0.541 — overlapping — so 0.45 keeps every answerable question and filters clearly off-topic ones; the prompt handles the rest.

**7. What's hybrid search and RRF?**
Combine keyword search (BM25/full-text: exact terms, acronyms) with vector search (meaning), merging result lists by Reciprocal Rank Fusion: score = Σ 1/(60 + rank). It fixes dense retrieval's blind spot — DocMind's weakest question is the acronym "RPO/RTO".

**8. What does a reranker do?**
A cross-encoder scores (query, chunk) pairs jointly — much more accurate than comparing separately computed embeddings, but too slow for the whole corpus. Retrieve 20–50 with vectors, rerank to the top 3–5.

**9. Bi-encoder vs cross-encoder?**
Bi-encoder: embed query and document independently → precompute document vectors → fast ANN search. Cross-encoder: process them together → better relevance → only feasible on a short candidate list.

**10. How do you evaluate a RAG system?**
Separately: retrieval (hit-rate@k, recall, MRR) and generation (correctness, faithfulness to sources, citation accuracy, refusal correctness, safety). DocMind's eval runs 22 labelled questions: retrieval in-process, answers end-to-end over HTTP, string-match grading that is itself unit-tested.

**11. What is LLM-as-judge and what are its pitfalls?**
Using a model to grade outputs against a rubric or reference. Scales to paraphrases. Pitfalls: position/verbosity/self-preference bias, cost, non-determinism — validate against human labels, use explicit rubrics, keep deterministic checks where possible.

**12. Explain temperature.**
It scales the next-token distribution: low = deterministic and focused, high = diverse and error-prone. For grounded Q&A, keep randomness low. Some newest models replace sampling parameters with an "effort" setting — DocMind uses `effort: low`.

**13. What is a context window and why not just put all documents in it?**
The token limit for input + output. Stuffing everything costs more per question, raises latency, degrades accuracy on long inputs ("lost in the middle"), and stops working once the corpus is larger than the window. RAG sends ~5 relevant chunks.

**14. Fine-tuning vs RAG vs prompting?**
Prompting for behaviour, RAG for knowledge (fresh, private, citable), fine-tuning for style/format/narrow tasks at scale. Fine-tuning is bad at reliably injecting facts and can't cite. They combine.

**15. What is function/tool calling?**
The model outputs a structured request to call one of your declared tools with JSON arguments; your code validates, authorizes and executes it, then returns the result. The model never executes anything — and tools must enforce the user's permissions themselves.

**16. When would you build an agent?**
When the steps depend on intermediate results and can't be fixed in advance. Otherwise prefer a single call or a fixed workflow — cheaper, faster, more predictable. With agents: allow-listed tools, step and budget limits, human approval for risky actions, audit logs.

**17. How do you get reliable JSON out of an LLM?**
Use the provider's structured outputs / strict tool schemas to enforce a JSON Schema; otherwise validate with Pydantic/Zod and retry with the error. Keep schemas small and fields explicit.

**18. Open-source or hosted models?**
Hosted for frontier quality and zero ops; open-weights for data residency, fixed costs at high steady volume, and full control. DocMind mixes: local open-source embeddings (cheap, private) and a hosted LLM for answers.

**19. How do you stream LLM responses to a browser?**
Server: iterate the provider's stream and forward each delta as an SSE `token` event. Client: `fetch` + `ReadableStream` + an incremental parser (EventSource can't POST or send auth headers), `AbortController` for Stop.

**20. What's query rewriting?**
Transforming the user's question before retrieval: standalone rewrites for follow-ups, multi-query, HyDE, decomposition. DocMind does a cheap version: for follow-ups it searches both the question and "previous question + question" and merges.

## Backend

**21. Why FastAPI?**
Async I/O for many concurrent streams, Pydantic validation and OpenAPI from type hints, dependency injection, and Python's AI ecosystem. Trade-off vs NestJS: two languages in the stack.

**22. What happens if you call a blocking function inside `async def`?**
It blocks the event loop — every request on that worker stalls. Use async libraries, `asyncio.to_thread` for blocking/CPU work that releases the GIL (DocMind: pypdf, ONNX embeddings), or a process pool/worker for pure-Python CPU work.

**23. Explain FastAPI dependency injection.**
`Depends(fn)` resolves per-request values (DB session, current user) and passes them to handlers; dependencies can depend on others and clean up with `yield`. Tests replace them with `app.dependency_overrides` — DocMind swaps in a fake LLM and embedder.

**24. Why return 202 for uploads?**
The resource is accepted but processing continues asynchronously; the client polls `GET /documents/{id}` until `ready`/`failed`. 201 would imply the work is complete.

**25. 401 vs 403 vs 404 for another user's document?**
401 = not authenticated, 403 = authenticated but not allowed. DocMind returns 404 for other users' resources so the API doesn't confirm the ID exists.

**26. BackgroundTasks vs a task queue?**
BackgroundTasks run in-process after the response: zero infrastructure but no durability, retries or independent scaling. A queue (Celery/SQS + workers) adds all three at the cost of running a broker. DocMind uses BackgroundTasks and fails stale jobs on restart; I'd switch at scale.

**27. SSE vs WebSockets?**
SSE is one-way server→client over plain HTTP — perfect for token streaming, works with normal auth and load balancers. WebSockets are bidirectional and stateful — for collaborative or real-time apps.

**28. What is idempotency and where does it matter?**
Doing an operation twice has the same effect as once. Matters for retries: GET/PUT/DELETE are idempotent; for POSTs like payments or uploads use an `Idempotency-Key` header and store the result.

**29. Offset vs cursor pagination?**
Offset is simple and allows page jumps but is slow on deep pages and unstable under inserts. Cursor (keyset) uses an indexed `WHERE (created_at, id) < …` — fast and stable; no random access.

**30. How do you handle errors consistently?**
One error shape (`{"error": {code, message}}`), domain exceptions mapped to status codes, validation errors summarized without echoing input, and a catch-all that logs the traceback and returns a generic 500. For streams, an `error` event after the 200.

**31. How do you handle a client disconnecting mid-stream?**
Starlette cancels the response generator; closing the provider stream stops generation and billing. DocMind saves the partial answer in a `finally` block inside `anyio.CancelScope(shield=True)`, because anyio re-cancels any await inside a cancelled scope.

## Frontend

**32. Server vs client components?**
Server components render on the server and ship no JS — good for data fetching and static content; client components (`"use client"`) handle state, effects and events. DocMind's authenticated pages are client components because the token lives in the browser.

**33. SSR vs SSG vs CSR?**
SSG renders at build time (fastest, same for everyone), SSR per request on the server (personalized, SEO), CSR in the browser after load (interactive apps behind login). DocMind: static shells + CSR data fetching.

**34. Why do list keys matter?**
React matches old and new children by key; unstable keys (array index in a changing list) attach state and DOM to the wrong items and cause extra work. Use stable IDs.

**35. How do you avoid unnecessary re-renders?**
Keep state local, memoize expensive children (`memo`), stabilize callbacks/objects (`useCallback`/`useMemo`), split contexts, virtualize long lists. DocMind memoizes `MessageBubble` so only the streaming message re-renders per token.

**36. What's a stale closure?**
A callback that captured an old value (or a mutable variable that changed before it ran). DocMind had one: a state updater read `assistantId` after it had been reassigned. Fix: capture into a `const`, use functional updates, or refs.

**37. How do you consume a streamed response in the browser?**
`res.body.getReader()`, decode with `TextDecoder({stream: true})` (handles split UTF-8), buffer until event boundaries, parse frames, update state per event; `AbortController` to cancel.

**38. Where would you store the JWT?**
Ideally an httpOnly, Secure, SameSite cookie (JS can't read it; add CSRF protection). DocMind uses memory + localStorage for simplicity and mitigates XSS with escaping, no raw HTML, CSP `connect-src`, and short expiry.

**39. TypeScript: what's a discriminated union and why use it?**
A union of object types sharing a literal field (`event: "token" | "citations" …`); switching on that field narrows the type. DocMind types SSE events this way so each `case` gets the right `data` type.

**40. Which state management would you use?**
Local state and custom hooks first; context for low-frequency globals; Zustand/Redux for complex shared client state; TanStack Query for server state (caching, polling, retries) — it would replace DocMind's manual polling.

**41. What accessibility work did you do?**
Labels, visible focus, keyboard submit (Enter/Shift+Enter, IME-safe), `role="alert"`, `aria-live`, `aria-expanded/pressed/current`, roles on groups, progress bar semantics, reduced motion, text not just color for statuses.

## Databases

**42. Why pgvector instead of Pinecone?**
One datastore: transactions across chunks and status, ownership filters as SQL joins, one backup story, no sync. Move to a dedicated vector DB at hundreds of millions of vectors or when vector load must scale independently.

**43. HNSW vs IVFFlat?**
HNSW is a layered proximity graph: great recall/speed, handles inserts, more memory, slower builds. IVFFlat clusters vectors into lists and searches the nearest few: faster build, less memory, needs data before building and loses recall as data drifts. DocMind uses HNSW.

**44. What's the N+1 problem?**
One query for a list plus one per item for related data. Fix with eager loading (`selectinload`/joins). Async SQLAlchemy forbids lazy loads, surfacing it as an error.

**45. Explain transaction isolation levels.**
Read Committed (Postgres default: no dirty reads), Repeatable Read (stable snapshot), Serializable (as if sequential; retry on conflict). Many races are better solved with constraints — DocMind's unique email index plus catching `IntegrityError`.

**46. Why is connection pooling important?**
Connections are expensive to open and Postgres handles hundreds, not thousands. A pool reuses them; at scale add PgBouncer because total = replicas × pool size.

**47. When would you use JSONB?**
Variable-shaped data read as a unit (DocMind's message citations). Not for things you filter, join or constrain on — those deserve columns.

**48. What indexes does DocMind have and why?**
Unique B-tree on `users.email`; B-trees on every foreign key (`documents.user_id`, `chunks.document_id`, …) for joins and cascades; HNSW with `vector_cosine_ops` on `chunks.embedding` for ANN search.

**49. How do you run migrations safely?**
Versioned (Alembic), reviewed, run before new code takes traffic; expand/contract for zero downtime; `CREATE INDEX CONCURRENTLY`; CI checks models match migrations (`alembic check`).

**50. SQL or NoSQL for this app?**
SQL: strongly relational ownership chains, cascades, joins inside the retrieval query, transactions, and pgvector. MongoDB fits document-shaped data with evolving schemas and heavy horizontal write scale.

## Security

**51. What is prompt injection and how did you defend against it?**
Text that tries to override the model's instructions — here *indirectly*, inside an uploaded document. Defences: untrusted-data rule in the system prompt, `<source>` delimiters, escaping delimiter look-alikes, no secrets in context, no tools, output never executed, and tests plus an eval question on a planted attack.

**52. What's IDOR and how did you prevent it?**
Accessing another user's object by changing an ID. Every query includes the owner condition (joins for child objects), 404 not 403, UUIDs as defence in depth, and tests for documents, chunks, conversations and retrieval filters.

**53. How do you store passwords?**
Slow salted hashes — bcrypt (cost 12) in DocMind; Argon2id is the current first choice. Reject >72-byte passwords for bcrypt. Never encrypt reversibly, never fast hashes.

**54. What are JWT pitfalls?**
Payload is readable; must pin the algorithm (`alg: none`/key confusion); must verify `exp`; revocation is hard (short expiry, denylist, refresh rotation); storage trade-offs (localStorage vs httpOnly cookie).

**55. Is CORS a security feature?**
It stops other websites from reading your API's responses through a victim's browser. It does not authenticate anyone and doesn't stop non-browser clients. DocMind allows only the frontend origin.

**56. Why isn't DocMind vulnerable to CSRF?**
Auth is a bearer header that another origin's JavaScript can't attach. With cookie auth you need SameSite cookies and/or CSRF tokens.

**57. How do you validate uploads?**
Extension + declared MIME + magic bytes + size limit while reading; store under a generated name; parse in the background so failures are contained; in production add malware scanning and object storage.

**58. How do you keep secrets out of the codebase?**
Environment variables from a git-ignored `.env`, `.env.example` with placeholders, secrets manager in production, secret scanning in CI, no secrets in the frontend bundle or in prompts (tested).

**59. What's in the OWASP Top 10 for LLMs?**
Prompt injection, sensitive information disclosure, supply chain, data/model poisoning, improper output handling, excessive agency, system prompt leakage, vector/embedding weaknesses, misinformation, unbounded consumption.

**60. How do you rate-limit, and what breaks with multiple servers?**
slowapi decorators: per user when authenticated, per IP otherwise; 429 + `Retry-After`. In-memory counters are per process, so with N replicas limits multiply — move counters to Redis or the gateway.

## Architecture and system design

**61. Walk me through a request.**
Use the chat flow: auth/validation → save user message → `meta` → embed + vector search scoped to the user → threshold → prompt with sources → stream tokens → citations → done → persist. Mention what happens on no context, errors and Stop.

**62. How would you scale DocMind 100×?**
Stateless API pods, S3 + presigned uploads, queue + autoscaled ingestion workers, embedding service, partitioned pgvector or a dedicated vector DB, read replicas, Redis for limits/cache, hybrid search + reranker, LLM fallback and quotas, OpenTelemetry.

**63. How would you add multi-tenancy (companies)?**
`tenant_id` on every row, tenant resolution once per request, Postgres Row-Level Security as a safety net, tenant-scoped vector filters and cache keys, per-tenant quotas; silo databases for enterprise.

**64. Why a provider-agnostic LLM layer?**
Swap providers by config, fall back on outages, compare models on the eval, avoid lock-in; the rest of the app depends on one small interface.

**65. What would you monitor in production?**
TTFT and total latency percentiles, error rates by code, tokens and cost per tenant, refusal rate, zero-citation answers, retrieval score drift, ingestion failures, queue depth, concurrent streams.

**66. What are the main trade-offs you made?**
Simplicity over scale (BackgroundTasks, in-memory limits, local files, localStorage JWT) — each documented with its production replacement in `docs/DECISIONS.md`.

## DevOps

**67. Why multi-stage Docker builds?**
Build tools stay in the builder stage; the runtime image has only the app and its dependencies — smaller, faster to pull, less attack surface. DocMind also bakes the embedding model into the image.

**68. What does your CI do?**
Backend: ruff, black, migrations + `alembic check` on a pgvector service container, pytest. Frontend: npm ci, ESLint, Prettier, tsc, Vitest, `next build`. Same commands as `make lint`/`make test`.

**69. Trunk-based development vs Git Flow?**
Trunk-based: short-lived branches merged often behind CI and feature flags — continuous delivery. Git Flow: long-lived develop/release branches — scheduled, versioned releases. Most web teams prefer trunk-based.

**70. How would you deploy this?**
Frontend on Vercel or a CDN; backend containers on Cloud Run/ECS Fargate with min instances; managed Postgres with pgvector; S3; secrets manager; CD pipeline building SHA-tagged images, migrating, deploying to staging, smoke-testing and promoting.

**71. How do you handle config across environments?**
Same image everywhere, config from environment variables validated at startup, secrets from a manager; remember `NEXT_PUBLIC_*` are build-time.

## Tricky follow-ups

**72. "What if the PDF is scanned?"**
There's no text layer, so pypdf returns nothing — DocMind marks it `failed` with "No extractable text (the PDF may be scanned images)". Fix: detect low text density per page and run OCR (Tesseract/ocrmypdf locally, or a cloud OCR/document AI service), keep page numbers, and flag OCR confidence; for complex layouts, a vision-capable model can extract tables.

**73. "How do you handle a 500-page document?"**
Ingestion already streams page by page; at that size move it to a queue worker, process pages in batches with progress updates (`processed_pages`), embed in larger batches (or on a GPU), bulk insert in chunks, and make the job resumable. For retrieval, 500 pages is ~1,500 chunks — fine for ANN; add section-aware chunking and metadata (chapter) so citations stay meaningful, and consider parent-document retrieval for context.

**74. "How do you stop hallucinations?"** (the short version)
Retrieve well, refuse when retrieval is empty, instruct the model to use only sources and say what's missing, require citations and show them, keep randomness low, evaluate refusal and faithfulness continuously. You reduce and expose hallucinations; you can't prove their absence.

**75. "How would you add multi-language support?"**
Swap to a multilingual embedding model (e.g. multilingual-e5/bge-m3 or a hosted multilingual model) and re-embed; detect the query language; instruct the model to answer in the user's language while citing original passages; language-aware keyword search (per-language `tsvector` configs); translate the UI (i18n); add non-English questions to the eval set.

**76. "How do you handle PII?"**
Minimize (don't collect what you don't need), classify documents, restrict access (per-user retrieval already), redact PII from logs and analytics (DocMind never logs document contents), encrypt at rest and in transit, check the LLM provider's retention/zero-data-retention terms and DPA, support deletion (document delete cascades to chunks and file), optionally detect/redact PII before sending text to the LLM (Presidio), and audit access.

**77. "What if two sources contradict each other?"**
The prompt tells the model to say which source says what and prefer authoritative documents (policies, product guides) over informal notes — exactly the vendor-notes injection scenario. Longer term: store document metadata (type, date, owner) and rank by recency/authority.

**78. "What if the answer spans two pages?"**
Chunks never cross pages, so both pages' chunks must be retrieved — TOP_K 5 usually covers it and the model cites both. If it becomes a problem: allow a small cross-page overlap chunk, or retrieve neighbouring chunks (chunk_index ± 1) of each hit.

**79. "Your eval says 100% retrieval — is it good?"**
On 22 questions and 5 documents, it shows the pipeline works, not that it generalizes. I'd grow the set with real user questions, harder cases (acronyms, tables, multi-hop), more documents that compete for similarity, and track it over time.

**80. "Why not LangChain?"**
For this scope, a few hundred lines of explicit code are easier to understand, debug and defend in an interview; frameworks shine with many integrations, complex agent graphs or standard components you'd otherwise rebuild.

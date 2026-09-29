# 3. The decisions that matter

For each: **why this**, the **alternative**, and **when I'd switch**. Say all three and you sound senior.

| Decision | Why this | Alternative (cost) | When I'd switch |
|---|---|---|---|
| **FastAPI (Python)** | Best AI ecosystem; async; validation + docs from type hints | NestJS (one language, but AI libs are Python-first) | TypeScript-only team, AI is a thin API call |
| **pgvector in Postgres** | One datastore: transactions, user filter as a SQL join, one backup | Pinecone/Qdrant (sync between two stores, more infra) | 100M+ vectors or vector load must scale separately |
| **Local embeddings (FastEmbed)** | Free, private, no key, fast, small vectors | OpenAI/Voyage embeddings (cost, data leaves server) | Multilingual or eval shows retrieval is the bottleneck |
| **RAG, not fine-tuning** | Fresh, per-user, citable facts; no retraining | Fine-tuning (bad at facts, can't cite, mixes users' data) | Need a fixed style/format at high volume — combine both |
| **Chunks 800/150, per page** | Focused embeddings, boundary overlap, exact page citations | Fixed windows (cut sentences), semantic chunking (costly) | Long manuals → larger chunks + parent retrieval |
| **Threshold 0.45 (measured)** | Keeps all answerable questions (lowest 0.508), filters clearly off-topic | 0.35 filters nothing; 0.52 drops a real question | A reranker gives calibrated scores to threshold on |
| **SSE via fetch** | One-way streaming over plain HTTP; auth header; Stop via abort | WebSockets (stateful, overkill); EventSource (GET only, no headers) | Real-time two-way features |
| **BackgroundTasks** | No extra infra; `202` + polling | Celery/SQS workers (durable, retries, more ops) | Multiple servers, big files, need retries |
| **Provider-agnostic LLM wrapper** | Swap Claude/OpenAI by config; one error model | LangChain (more abstraction than needed) | Many integrations / agent graphs |
| **Cite only referenced sources** | A chip means "this answer used this passage" | Show all retrieved (implies false support) | Single provider with native citations |
| **JWT in localStorage** | Simple for an SPA on a separate API origin | httpOnly cookie (no JS access, but needs CSRF protection) | Production: cookie + refresh tokens |
| **Rate limits in memory** | One decorator per route; per user, not per IP | Redis / API gateway | More than one backend replica |

**The honest summary:** every simplification (background tasks, localStorage token, in-memory limits, local files) has a documented production replacement (queue, cookie, Redis, S3) in `docs/DECISIONS.md`.

# 10. Performance and scalability

## Latency budget of a RAG request

Where the time goes in one DocMind chat turn (typical orders of magnitude; the `chat_turn` log line records the real values):

| Step | Typical time | Notes |
|---|---|---|
| Auth + validation + DB lookups | 2–10 ms | pooled connections |
| Embed the question (bge-small, CPU) | ~5–20 ms | runs in a thread |
| Vector search (HNSW, top-5) | ~1–10 ms | index in memory |
| Build prompt | < 1 ms | |
| **LLM time to first token** | **~0.5–2 s** | dominated by provider queueing + prefill of the prompt |
| LLM generation | ~1–10 s | proportional to output tokens |
| Persist messages | ~5 ms | after streaming |

**Lesson:** everything except the LLM is noise. Streaming hides generation time (users read as it writes), so the number that matters is **time to first token (TTFT)**. Levers: shorter prompts (fewer, tighter chunks), a faster model or lower effort, prompt caching of the static prefix, geographic proximity to the provider — and skipping the LLM entirely when retrieval finds nothing (DocMind does).

## Caching

| Cache | Key | Saves | Watch out for |
|---|---|---|---|
| **HTTP / CDN** | URL | static frontend assets | cache-busting on deploy (Next hashes filenames) |
| **Response cache** | exact question + user + doc set | a whole LLM call | invalidate when documents change; per-user keys |
| **Embedding cache** | hash of text + model | re-embedding repeated queries/chunks | model version in the key |
| **Semantic cache** | embedding of the question; hit if similarity > ~0.95 | LLM calls for paraphrased repeats ("price of Business?" ≈ "how much is Business?") | false hits on questions that differ in one crucial word; must be per-tenant |
| **Prompt caching (provider)** | identical prompt prefix | input-token cost and prefill latency for the static part (system prompt, tool definitions) | prefix must be byte-identical; put volatile content last |
| **Application cache (Redis)** | e.g. user → documents list | DB reads | invalidation |

## Batching

Do many items per call: DocMind embeds chunks 32 at a time (ONNX runs batches far more efficiently than one-by-one) and inserts all chunks in one executemany statement. Other forms: provider **batch APIs** (asynchronous, typically ~50% cheaper) for offline jobs like re-embedding or bulk evaluation; micro-batching requests in an embedding service.

## Horizontal scaling and stateless services

Scale *out* by running more identical API instances behind a load balancer. That only works if instances are **stateless** — any request can hit any instance. DocMind's state audit:

| State | Today | Stateless version |
|---|---|---|
| Sessions | JWT (already stateless) | — |
| Uploaded files | local Docker volume | S3/GCS object storage (presigned uploads) |
| Rate-limit counters | in memory | Redis |
| Background jobs | in-process | queue + worker fleet |
| Embedding model | loaded per process (~130 MB) | fine per instance, or a shared embedding service (GPU) |

SSE streams are long-lived connections: configure load-balancer idle timeouts (> max answer time), and scale on concurrent connections, not just CPU.

## Queues

Decouple producers from consumers: the API enqueues "ingest document X" and returns; workers pull at their own pace. Benefits: absorbs spikes (a customer uploads 10,000 PDFs), retries with backoff, dead-letter queues for poison messages, independent autoscaling on queue depth, and the API stays responsive. Tools: SQS, RabbitMQ, Redis Streams, Kafka (for event streams), with Celery/Arq/Dramatiq on top.

## Load balancing

Distribute requests across instances: round-robin, least-connections (good for long-lived SSE), or hashing (session affinity — avoid needing it). Health checks route around bad instances — DocMind's `/api/health` returns 503 when the DB is unreachable so an instance is taken out of rotation. Layer 7 (HTTP) balancers can also terminate TLS, route by path, and apply rate limits/WAF rules.

## Database read replicas

Send reads (document lists, conversation history) to replicas, writes to the primary. Caveat: **replication lag** — a user uploads then immediately lists documents and doesn't see the new one. Fixes: read-your-writes (route a user's reads to the primary for a few seconds after they write), or read from the primary for freshness-critical queries. Also: PgBouncer for connection counts, partitioning `chunks` by tenant/hash for very large tables.

## CDN

Serve static assets (JS, CSS, fonts, images) from edge locations near users — lower latency, less load on origin. Next.js standalone output + a CDN in front (or Vercel/CloudFront). API responses are per-user and not cached at the CDN.

## Cost control for LLM usage

- **Don't call the LLM when you don't need to** — DocMind's no-context short-circuit.
- **Model routing:** a small/fast model for easy or high-volume questions, a frontier model for hard ones (route by classifier, question length, or retrieval confidence). Measure first — a strong model at low effort is often as cheap overall because it needs fewer retries.
- **Token limits:** cap `max_tokens`, cap context (DocMind: 12,000 chars, 6 history messages), trim chunks, avoid resending long history (summarize old turns).
- **Caching:** prompt caching for the static prefix; semantic cache for repeated questions.
- **Batch APIs** for offline work.
- **Guardrails on spend:** per-user quotas and rate limits, provider spend limits per key, alerting on tokens/day, logging `input_tokens`/`output_tokens` per request (DocMind logs them) so you can attribute cost.

# 7. System design in one hour

## The framework (use it for any design question)

1. **Requirements:** what it does + scale, latency, availability, security, cost. Ask questions.
2. **Estimates:** users, requests/second, data size.
3. **API + data model:** the few key endpoints and tables.
4. **Boxes and arrows:** walk one request through.
5. **Deep dives:** the 2–3 hardest parts.
6. **Bottlenecks, failures, trade-offs, monitoring.**

## Practice: scale DocMind to 100k users and 10M documents

![Scaled DocMind](diagrams/sd-scale.svg)

**Estimates.** 10M docs × 20 pages × 3 chunks ≈ **600M chunks** → 384 × 4 bytes each ≈ **~920 GB of vectors** (half that with 16-bit `halfvec`). Too big for one Postgres node. Chat load is modest (~7 questions/s at peak); LLM cost and time to first token matter more.

**Design.**

- CDN for the frontend; **stateless API pods** behind a load balancer.
- **Uploads straight to S3** (presigned URLs) → **queue** → **autoscaled ingestion workers** → **embedding service** (GPU batches or a hosted API).
- **Vectors:** pgvector **partitioned by tenant** (with 16-bit vectors) *or* a dedicated vector DB (Qdrant/Pinecone) kept in sync via an outbox table.
- Postgres primary + **read replicas**; PgBouncer; **Redis** for rate limits and caches.
- **Better retrieval:** hybrid search + reranker.
- **LLM layer:** circuit breaker, fallback provider, prompt caching, model routing, per-tenant token quotas.
- **Observability:** traces, time to first token, refusal rate, tokens per tenant, queue depth.

**Bottlenecks → fixes.** Vector memory → partitioning/quantization/vector DB. Bulk imports → GPU workers, per-tenant fairness. Filtered search recall for small tenants → partition or exact search. Provider limits → quotas and fallback. Deletion at scale → delete across S3, vectors and rows, with an audit trail.

## Two more to sketch on paper

**AI support chatbot with tools.** RAG over help articles + narrow allow-listed tools (`get_order`, `track_shipment`, `create_return`, `issue_refund`). Validate arguments, **authorize against the logged-in customer** (never trust the model), confirm or hand to a human for risky actions, limit steps per turn, audit log, human handoff with a summary.

**Multi-tenant SaaS.** Pool (shared tables + `tenant_id` + **Postgres Row-Level Security**) by default; schema-per-tenant or **database-per-tenant** for enterprise customers. Tenant-scoped vector filters and cache keys, per-tenant keys (KMS), quotas and cross-tenant tests.

# 14. System design practice

A reliable structure for any design question (~35–45 minutes):

1. **Clarify requirements** — functional (what it does) and non-functional (scale, latency, availability, security, cost). Ask; don't assume.
2. **Estimate** — users, requests/sec, data size. Rough numbers drive every later choice.
3. **API and data model** — the few key endpoints and tables.
4. **High-level design** — boxes and arrows; walk one request through it.
5. **Deep dives** — the 2–3 hardest parts (the interviewer often picks).
6. **Bottlenecks, failure modes, trade-offs** — and what you'd monitor.

## (a) Scale DocMind to 100k users and 10M documents

![Scaled DocMind](diagrams/sd-scale.svg)

**Requirements.** 100k registered users, ~10k daily active, peak ~200 concurrent chats; 10M documents × ~20 pages average; answers start streaming in < 2 s (p95); ingest a normal PDF within a minute; strict tenant isolation; 99.9% availability.

**Estimates.**

- Chunks: 10M docs × 20 pages × ~3 chunks/page ≈ **600M chunks**.
- Vectors: 600M × 384 dims × 4 bytes ≈ **920 GB** raw float32 (≈ 460 GB as `halfvec`); HNSW graph overhead on top. Text ≈ 600M × 800 B ≈ 480 GB. This no longer fits one Postgres node comfortably.
- Chat QPS: 200 concurrent streams × 1 question/30 s ≈ 7 questions/s peak — low; LLM cost and TTFT matter more than throughput.
- Ingestion: bursty (a customer migrating 50k PDFs); embedding throughput is the bottleneck.

**Design.**

- **Frontend** on a CDN (static shell), API behind a load balancer.
- **Stateless API pods** (autoscaled on CPU + concurrent connections); JWT auth; Redis for rate limits, short-lived caches and a semantic cache.
- **Uploads** go straight to **S3 with presigned URLs** (the API never proxies file bytes), then a message on a **queue**.
- **Ingestion workers** autoscale on queue depth: parse → chunk → call an **embedding service** (GPU pool running bge, or a hosted embedding API) in large batches → write vectors. Retries with backoff, dead-letter queue, per-tenant fairness so one big customer doesn't starve others. OCR path for scanned PDFs.
- **Vector storage:** either (1) pgvector **partitioned** by tenant hash across several Postgres nodes (Citus or application-level sharding), HNSW per partition, `halfvec` to halve memory; or (2) a dedicated vector DB (Qdrant/Pinecone) with tenant namespaces, keeping Postgres for relational data. With (2), sync via an outbox table + consumer so deletes never leave orphaned vectors.
- **Postgres** primary + read replicas for conversation history; PgBouncer.
- **Retrieval upgrades at this scale:** hybrid (BM25 + vectors, RRF), reranker on top-50, per-tenant filtered search tested for recall.
- **LLM layer:** provider abstraction with a circuit breaker and cross-provider fallback; prompt caching for the static system prompt; model routing (a small model for simple questions); per-tenant token quotas.
- **Observability:** OpenTelemetry traces across API → retrieval → LLM; dashboards for TTFT, refusal rate, tokens/tenant, queue depth, ingestion failures.

**Bottlenecks and trade-offs.**

- Vector index memory → partitioning, quantization, or a dedicated vector DB (trade: consistency and ops complexity).
- Embedding throughput during bulk imports → GPU batch workers, or a hosted API (trade: cost, data leaves the VPC).
- Filtered ANN recall for small tenants inside a big shared index → partition by tenant or exact search for small tenants.
- LLM provider limits → quotas, fallback provider, queue non-interactive work.
- Deletes/GDPR at scale → hard delete across S3, vectors, rows; audit.

## (b) AI customer-support chatbot with tool calling

![Support chatbot](diagrams/sd-support.svg)

**Requirements.** A chat widget on a retailer's website answers product/policy questions (from help-centre articles) and handles account actions: order status, shipment tracking, returns, small refunds. Escalate to a human when needed. ~50k conversations/day. Actions must be correct and authorized; everything auditable.

**Key design points.**

- **Knowledge answers via RAG** over help-centre articles (the DocMind pipeline), with citations.
- **Actions via tool calling.** Tools are narrow, typed and allow-listed: `get_order(order_id)`, `track_shipment(order_id)`, `create_return(order_id, items, reason)`, `issue_refund(order_id, amount)`, `create_ticket(summary)`. The orchestrator runs the loop: model proposes a tool call → **validate arguments against the schema** → **authorize against the logged-in customer** (the order must belong to *this* customer — the model's word is never trusted) → execute → return a compact result → model continues.
- **Guardrails:** refunds above a threshold, or anything irreversible, require confirmation ("Refund $42.10 to your Visa ending 4242?") or a human; iteration limit per turn; per-conversation budget; PII redaction in logs; prompt-injection defences (tool results and web content are data too).
- **Human handoff:** triggered by low confidence, user request, sentiment, or policy; the agent sees the transcript and a model-written summary.
- **State:** conversations and tool calls stored for audit and analytics; session tied to the customer's authenticated identity.
- **Evaluation:** a scenario suite (happy paths, refusals, adversarial prompts, wrong-customer order IDs), tool-call accuracy, resolution rate, escalation rate, CSAT.

**Trade-offs.** Agent autonomy vs control (fixed workflows for refunds, freer model reasoning for Q&A); a bigger model for planning vs a cheaper one for simple FAQs (routing); latency of multi-step tool loops (stream partial text, run independent tools in parallel).

## (c) Multi-tenant SaaS with per-tenant data isolation

![Multi-tenant isolation](diagrams/sd-multitenant.svg)

**Requirements.** Companies (tenants) sign up; each has users with roles; data must never leak across tenants; some enterprise customers demand stronger isolation (own database, own encryption keys, data residency).

**Isolation models.**

| Model | How | Pros | Cons |
|---|---|---|---|
| **Pool** (shared tables) | `tenant_id` on every row + **Postgres Row-Level Security** | cheapest, simplest ops, easy analytics | noisy neighbours; one bug could leak (RLS mitigates) |
| **Bridge** (schema per tenant) | same DB, `SET search_path` per request | stronger separation, per-tenant restore | migrations × N schemas, connection pooling harder |
| **Silo** (DB per tenant) | separate database/cluster | strongest isolation, per-tenant keys, residency, independent scaling | expensive, heavy ops at scale |

Common answer: **pool by default, silo for enterprise tiers** — the same code with a tenant → connection router.

**Enforcement in depth.**

1. **Tenant resolution** once per request (subdomain or JWT claim), cross-checked — a JWT for tenant A on tenant B's host is rejected.
2. **Explicit `tenant_id`** passed through services; repository helpers that *require* it.
3. **Row-Level Security** as the safety net: `ALTER TABLE documents ENABLE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON documents USING (tenant_id = current_setting('app.tenant_id')::uuid);` with `SET LOCAL app.tenant_id = …` at the start of each transaction — even a forgotten `WHERE` can't leak.
4. **Vectors and caches are tenant-scoped too** — tenant filter inside every vector query, tenant in every cache key (a shared semantic cache is a cross-tenant leak waiting to happen), per-tenant object-storage prefixes.
5. **Per-tenant encryption keys** (KMS, envelope encryption) for enterprise; crypto-shredding for deletion.
6. **Tests:** cross-tenant tests for every endpoint (DocMind's IDOR tests, generalized), plus RLS tests.

**Other concerns.** Per-tenant rate limits and quotas (noisy neighbours); tenant-aware observability; RBAC within a tenant (admin/member/viewer); billing metered per tenant (tokens, storage); tenant offboarding and data export; data residency by routing tenants to regional deployments.

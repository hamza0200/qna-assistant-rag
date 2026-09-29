# 5. Vector databases

## The problem they solve

Given a query vector, find the *k* stored vectors closest to it. Exact search compares against every vector — O(N·d) per query. At a few thousand chunks (DocMind's sample: 32) that's instant; at 100 million 384-d vectors it's ~150 GB of floats to scan per query. **Approximate Nearest Neighbour (ANN)** indexes trade a little accuracy (*recall*) for orders-of-magnitude speed.

## pgvector internals

- A Postgres extension adding the `vector(n)` type (also `halfvec` for 16-bit floats, `bit` for binary, `sparsevec`), distance operators (`<->` L2, `<#>` negative inner product, `<=>` cosine, `<+>` L1) and two index types.
- Vectors are stored in table pages like any column (384 floats × 4 bytes ≈ 1.5 KB per row), so they get MVCC, WAL, replication, backups and transactions for free.
- Enable with `CREATE EXTENSION vector` — DocMind's first migration does this.
- Query shape that uses an index: `ORDER BY embedding <=> $1 LIMIT k`. The index must match the operator (`vector_cosine_ops` for `<=>`).

```sql
CREATE INDEX ix_chunks_embedding_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops);

SELECT c.*, d.filename, c.embedding <=> $1 AS distance
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE d.user_id = $2 AND d.status = 'ready'
ORDER BY c.embedding <=> $1
LIMIT 5;
```

## HNSW vs IVFFlat

**HNSW (Hierarchical Navigable Small World)** — a multi-layer graph. Upper layers are sparse "highways" with long links; the bottom layer contains every vector with short links. Search starts at the top, greedily walks toward the query, and drops a layer each time it can't get closer — like zooming in on a map.

- Build parameters: `m` (links per node, default 16) and `ef_construction` (candidate list while building, default 64). Higher = better recall, bigger/slower index build.
- Query parameter: `hnsw.ef_search` (default 40) — the candidate list size at query time; raise it for better recall at some latency cost.
- Pros: excellent speed/recall trade-off, no training step, handles inserts well. Cons: more memory, slower builds.

**IVFFlat (Inverted File)** — k-means clusters the vectors into `lists` buckets; a query searches only the `probes` nearest buckets.

- Must be built **after** data exists (centroids come from the data); recall degrades as data drifts from the original clusters.
- Rules of thumb: `lists ≈ rows/1000` (up to 1M rows), `probes ≈ sqrt(lists)`.
- Pros: faster build, less memory. Cons: generally lower recall at the same speed; needs periodic rebuilds.

**Choice for DocMind:** HNSW — data arrives continuously (uploads), no training step, best default recall.

## ANN trade-offs and filtering

- **Recall vs latency vs memory** is the triangle every ANN index balances; measure recall against exact search on a sample.
- **Filtered search pitfall:** with a selective `WHERE user_id = …`, the index may return the global top 40 candidates (ef_search), then the filter removes most of them, leaving fewer than *k* results. Mitigations: raise `ef_search`; pgvector's iterative index scans (0.8+) keep scanning until enough rows pass the filter; partition by tenant; or for small tenants let Postgres use a B-tree on `user_id` then exact-scan their few thousand vectors (often faster than ANN anyway).
- **Quantization:** store `halfvec` (2× smaller) or binary vectors (32× smaller) for a first pass, then re-rank with full precision.
- **Dimension:** smaller models (384-d) are cheaper to store and search; larger (1,024–3,072-d) often retrieve better. Some models support truncating dimensions (Matryoshka embeddings).

## When to move to Pinecone / Qdrant / Weaviate / Milvus

Stay on pgvector while: the corpus is up to tens of millions of vectors, you value transactions and SQL joins with relational data, and vector search load is moderate.

Move when:

- **Scale:** hundreds of millions+ vectors, or indexes that no longer fit in memory on one Postgres node.
- **Independent scaling:** vector QPS grows much faster than OLTP traffic — you don't want ANN queries fighting your transactional workload.
- **Features:** built-in hybrid search, advanced filtering with predictable recall, quantization/tiered storage, multi-tenancy namespaces, managed sharding and replication.
- **Ops preference:** a managed serverless service (Pinecone) instead of tuning Postgres.

Cost of moving: two sources of truth (sync on every insert/delete — use an outbox/CDC pattern), authorization filters duplicated in metadata, and another system to secure and monitor.

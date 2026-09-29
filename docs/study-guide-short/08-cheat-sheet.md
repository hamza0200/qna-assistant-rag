# 8. One-page cheat sheet

<div class="cheat" markdown="1">

**Pitch:** Upload PDFs, ask questions, get streamed answers that cite document + page, and an honest "not found" when the documents don't say. RAG with FastAPI + pgvector + local embeddings + Claude; Next.js frontend; hardened and tested.

| Pipeline | Numbers |
|---|---|
| Parse | pypdf page by page; strip running headers; scanned → `failed` |
| Chunk | 800 chars, 150 overlap, recursive (¶ → line → sentence → word), never across pages |
| Embed | `bge-small-en-v1.5`, 384-d, normalized, batch 32, local ONNX; query prefix instruction |
| Store | Postgres 16 + pgvector, HNSW `vector_cosine_ops`, one transaction with `status=ready` |
| Retrieve | `<=>` cosine distance, user filter in SQL, TOP_K 5, MIN_SIMILARITY 0.45 |
| Prompt | system rules + last 6 messages + `<source id file page>` blocks (≤ 12k chars) + question last |
| Generate | `claude-opus-5-5`, effort low, max_tokens 1024, 60 s timeout, 2 retries before stream, refusal fallback |
| Stream | SSE: meta → token… → citations → done / error; fetch + ReadableStream + AbortController |
| Cite | parse `[n]`, show only cited sources, chip opens `/api/chunks/{id}` |

**Limits:** chat 20/min/user · upload 10/min/user, 20 MB, 10 files · login 5/min/IP · question ≤ 4,000 chars · JWT 60 min · bcrypt cost 12.

**Quality:** 113 tests (100 backend, 13 frontend) · eval 22 questions · retrieval hit-rate 21/21 · threshold measured: answerable 0.508–0.84 vs off-topic 0.416–0.541 (overlap).

**Key terms (one line each):**

- **RAG** — retrieve relevant text, then generate from it. **Grounding** — answer only from provided sources.
- **Embedding** — meaning as a vector. **Cosine** — angle-based similarity; = dot product on unit vectors.
- **HNSW** — layered graph ANN index; `m`, `ef_construction`, `ef_search`. **IVFFlat** — cluster buckets; `lists`, `probes`.
- **Hybrid + RRF** — keyword + vector, merge by 1/(60 + rank). **Reranker** — cross-encoder on top-k.
- **Prompt injection** — instructions hidden in data; defend with delimiters, untrusted-data rule, least privilege.
- **IDOR** — access by changing an ID; fix with ownership in every query, 404, tests.
- **SSE** — one-way HTTP stream; **WebSocket** — two-way stateful connection.
- **202 Accepted** — async processing; **idempotency key** — safe retries of POST.
- **Event loop** — never block it; `asyncio.to_thread` for CPU/blocking work.
- **N+1** — fix with eager loading. **ACID**; Postgres default isolation = Read Committed.
- **TTFT** — time to first token, the latency that users feel with streaming.

**Talking points (have a story for each):**

1. Measured the threshold instead of guessing — and found that a threshold can't detect unanswerable-but-on-topic questions.
2. Prompt injection is contained by design: no secrets, no tools, per-user data, output never executed — plus tests and an eval question.
3. Stop button end to end: AbortController → server cancellation → provider stream closed → partial answer saved in a shielded scope.
4. Stale-closure bug caught by an end-to-end test, not unit tests.
5. Every simplification has a documented production path: BackgroundTasks → queue, localStorage → httpOnly cookie, in-memory limits → Redis, local files → S3.

**Next steps:** answer eval with live model → hybrid search → reranker → query rewriting → durable queue → cookie auth → OCR → feedback + semantic cache.

**Your questions for them:** How do you evaluate AI features? Path from prototype to production? Biggest technical challenge this year?

</div>

# 17. "If I had more time" list

Ordered roughly by value for effort.

1. **Run the full answer eval with a real model and publish the numbers** — retrieval is measured (21/21); answer accuracy and injection resistance on the live model are the missing half.
2. **Hybrid search (Postgres full-text + vectors, merged with RRF)** — fixes dense retrieval's weakness on acronyms and codes ("RPO/RTO", "VLT-409"), the lowest-scoring retrieval in the eval.
3. **Cross-encoder reranker** — better precision in the top 5 and well-calibrated scores, which makes the "not found" threshold far more reliable than raw cosine similarity.
4. **Standalone-question rewriting for follow-ups** — more robust than prefixing the previous question once conversations get long or pronouns get ambiguous.
5. **Durable ingestion queue with retries (Arq/Celery + Redis) and separate workers** — BackgroundTasks lose work on restart and compete with chat traffic for CPU.
6. **httpOnly cookie sessions with refresh-token rotation** — removes JWT access from JavaScript, the main XSS risk of the current design.
7. **LLM-as-judge faithfulness scoring in the eval** — string matching can't credit paraphrases or catch unsupported claims that happen to contain a key fact.
8. **OCR fallback for scanned PDFs** — today they fail with a clear message; many real-world documents are scans.
9. **Per-answer feedback (thumbs up/down) stored in the DB** — turns real usage into new eval questions and a quality metric.
10. **Semantic cache (per user)** — skips LLM calls for repeated or paraphrased questions; cheap cost and latency win.
11. **Cross-provider fallback with a circuit breaker** — the provider interface is ready; a failing provider should flip traffic automatically.
12. **Redis-backed rate limits and S3 file storage** — prerequisites for running more than one backend replica.
13. **Playwright end-to-end tests in CI (with the fake provider)** — the browser flows were verified by hand-run scripts; they should guard every PR.
14. **Content hash on upload** — detects duplicate uploads and makes retries idempotent.
15. **OpenTelemetry traces and a metrics dashboard** — time to first token, refusal rate and tokens per user as first-class SLIs.
16. **Nonce-based CSP** — remove `'unsafe-inline'` scripts on the frontend.
17. **Document metadata and authority ranking** — dates and document types so contradictions resolve toward the newest, most authoritative source.

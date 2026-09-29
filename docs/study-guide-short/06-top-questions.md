# 6. The 35 most likely questions

Answer aloud, under a minute each.

## About the project

**1. Walk me through what happens when I ask a question.** Auth and validation → save the question → embed it → pgvector search over *my* chunks → drop weak matches → if nothing is left, a fixed "not found" (no LLM call) → otherwise a prompt with numbered sources → stream tokens over SSE → send the citations the answer used → save the answer.

**2. What was the hardest part?** Getting "honest" answers: I measured that similarity scores for answerable and off-topic questions overlap, so the threshold only catches clearly off-topic questions and the prompt must handle the rest. Plus making Stop work end to end.

**3. How do you know it works?** 113 automated tests (security, streaming, refusals, injection) and an eval of 22 labelled questions — retrieval finds the right source for 21 of 21.

**4. What would you do next?** Hybrid search, a reranker, follow-up question rewriting, a durable ingestion queue, cookie-based auth, OCR.

**5. What would you change for production?** Queue + workers, S3, Redis for rate limits, httpOnly cookie auth, tracing and dashboards, a secrets manager, cross-provider fallback.

## AI / LLM

**6. What is RAG, and why not fine-tune?** Retrieve relevant text and answer from it: fresh, private, citable. Fine-tuning teaches style, not reliable facts, can't cite, and would mix users' data.

**7. What's an embedding? Why cosine?** Meaning as a vector. Cosine compares direction; on normalized vectors it ranks the same as the dot product.

**8. How did you choose chunk size?** ~800 characters (~200 tokens) + 150 overlap, split on natural boundaries, never across pages. Focused, enough context, exact page citations.

**9. How do you stop hallucinations?** Don't call the LLM without context; "only from sources, say what's missing"; mandatory citations shown to the user; low randomness; refusal questions in the eval.

**10. How did you pick the similarity threshold?** Measured: answerable 0.508–0.84, off-topic 0.416–0.541. 0.45 keeps every real question.

**11. What's hybrid search?** Keyword (exact terms) + vector (meaning), merged by rank with RRF. It fixes acronyms like "RPO/RTO", my weakest eval question.

**12. What does a reranker do?** A cross-encoder scores (question, chunk) pairs together — more accurate; run it on the top 20–50 candidates.

**13. How do you evaluate a RAG app?** Retrieval (hit-rate@k) and answers (facts, faithfulness, citations, refusals, injection) separately, on a versioned set, after every change. LLM-as-judge for paraphrases, validated against humans.

**14. What is prompt injection, and how did you defend?** Instructions hidden in data. Untrusted-data rule, `<source>` delimiters, escaped fake tags, and least privilege: no secrets in the prompt, no tools, per-user data, output never executed. Tested with a planted attack.

**15. Tool calling and agents?** The model requests a function call; my code validates, authorizes and runs it. Agents loop over this — only when steps can't be fixed in advance, with limits and approvals.

**16. How do you control LLM cost?** Skip calls when possible, cap context and output tokens, cache, route to cheaper models, per-user quotas, and log tokens per request.

## Backend

**17. Why FastAPI?** Async, validation and docs from type hints, and Python's AI ecosystem.

**18. What if you call blocking code in `async def`?** It freezes every request on that worker. Use `to_thread` or worker processes.

**19. Why 202 for uploads?** Accepted; processing continues in the background; the client polls for `ready`/`failed`.

**20. SSE or WebSockets?** SSE: one-way over plain HTTP, ideal for token streaming. WebSockets: two-way, stateful.

**21. BackgroundTasks vs a queue?** In-process and simple vs durable, retried and independently scaled. I'd switch at scale.

**22. What happens when the user presses Stop?** The fetch aborts → the server cancels the stream → the provider stream closes (no more tokens billed) → the partial answer is saved in a shielded scope.

## Frontend

**23. Server vs client components?** Server: no JS shipped, fetches on the server. Client: interactivity. My pages are client components because the token is in the browser.

**24. How do you read a stream in the browser?** `getReader()` + `TextDecoder({stream: true})` + buffer events until a blank line; `AbortController` to cancel.

**25. How do you avoid re-renders while streaming?** Memoize message components, stable callbacks, keep state local.

**26. Tell me about a bug you found.** A stale closure: a state updater read a variable reassigned before React ran it, so answers stayed blank. An end-to-end test caught it; fix: capture into a `const`.

## Databases

**27. Why pgvector and not Pinecone?** One datastore, transactions, user filters as joins, no syncing. Switch at hundreds of millions of vectors.

**28. HNSW vs IVFFlat?** Graph vs clusters. HNSW has better recall and handles inserts; IVFFlat builds faster but needs data first.

**29. What's N+1?** One query per list item; fix with eager loading.

**30. Isolation levels?** Read Committed (default), Repeatable Read, Serializable. Many races are better solved with a unique constraint.

## Security

**31. What's IDOR, and how did you prevent it?** Changing an ID to reach others' data → owner check inside every query, 404, UUIDs, tests for each resource.

**32. How do you store passwords?** bcrypt (cost 12), salted, slow; Argon2id is the modern first choice.

**33. JWT pitfalls?** Readable payload, pin the algorithm (`alg: none` attack), check expiry, revocation is hard, storage trade-offs.

**34. CORS, CSRF, XSS in one breath?** CORS = other sites can't read my API via your browser; CSRF = forged cookie requests (not an issue with header tokens); XSS = injected script (React escaping, no raw HTML, CSP).

## Tricky follow-ups

**35. Quick answers:**
- *Scanned PDF?* No text layer → marked `failed` today; add OCR (Tesseract or a cloud OCR service) with page numbers.
- *500-page document?* Queue worker, page batches with progress, larger embedding batches, section-aware chunking; retrieval is still fine (~1,500 chunks).
- *Multi-language?* Multilingual embedding model + re-embed, answer in the user's language, language-aware keyword search, non-English eval questions.
- *PII?* Minimize, per-user access, never log contents, encrypt, check provider data retention, deletion that cascades, optional PII redaction before the LLM.
- *Conflicting sources?* The prompt says who says what and prefers authoritative documents; later, rank by date/authority metadata.

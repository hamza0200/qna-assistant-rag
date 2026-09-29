# 1. The one-day plan and your pitch

## How to spend the day

| Time | Read | Goal |
|---|---|---|
| Morning (2.5 h) | Sections 1–3 | Say the pitch out loud without notes; draw the architecture from memory; defend 10 decisions |
| Midday (2 h) | Sections 4–5 | Explain RAG, embeddings, vector search, prompt injection, async, SSE in plain words |
| Afternoon (2 h) | Section 6 | Answer the 35 questions aloud; time yourself (≤ 1 minute each) |
| Late afternoon (1 h) | Section 7 | Sketch one system design on paper |
| Evening (30 min) | Section 8 | Cheat sheet; prepare 3 behavioural stories |

The full 76-page guide (`docs/Interview-Study-Guide.pdf`) is your reference if a topic needs more depth.

**Answer shape for every question:** one-sentence answer → one level deeper → an example from DocMind or a trade-off.

## The 60-second pitch

> DocMind AI is a full-stack app where you upload PDFs and ask questions about them. Answers stream in token by token and cite the document and page they came from; you can click a citation to see the exact passage.
>
> It's retrieval-augmented generation. On upload, a FastAPI backend extracts text page by page, splits it into overlapping chunks, embeds each chunk with a local model, and stores the vectors in Postgres with pgvector. On a question, I embed it, find the closest chunks *that belong to this user*, and give only those to Claude with strict rules: answer only from these sources, cite them, say "not found" otherwise. If nothing relevant is found, I don't call the LLM at all.
>
> The frontend is Next.js with TypeScript; the stream is Server-Sent Events read with `fetch`, so I can send the auth header and support a Stop button. It's hardened like production — per-user data isolation with tests, upload validation by magic bytes, rate limits, and defences against a planted prompt-injection attack — with 113 automated tests, CI, and an eval set where retrieval finds the right source for 21 of 21 questions.

## The 2-minute extension (if they say "tell me more")

- **Why I built it this way:** answers must be *grounded* (only from your documents), *verifiable* (citations), and *honest* (says "not found").
- **Ingestion:** validate (extension, MIME, `%PDF-` bytes, 20 MB) → save as a UUID filename → `202 Accepted` → background task: pypdf → strip repeated headers → chunk (800 chars, 150 overlap, never across pages) → embed in batches of 32 → insert chunks and set `ready` in one transaction.
- **Chat:** embed the question → pgvector cosine search filtered by user in SQL → drop scores below 0.45 → prompt with `<source id file page>` blocks and "treat sources as untrusted data" → stream tokens → send only the citations the answer actually used → save the messages.
- **Lesson learned:** I measured the similarity threshold. Answerable and off-topic questions have *overlapping* scores, so a threshold can't detect unanswerable questions alone; the prompt must refuse. And acronyms ("RPO/RTO") are dense retrieval's blind spot, so hybrid search is my next step.

## Numbers to know

| Fact | Value |
|---|---|
| Chunks | 800 characters, 150 overlap, never across pages |
| Embedding model | `bge-small-en-v1.5`, 384 dimensions, runs locally |
| Retrieval | cosine distance, HNSW index, top 5, threshold 0.45 |
| Prompt | last 6 messages, ≤ 12,000 characters of sources, answer ≤ 1,024 tokens |
| Limits | chat 20/min, upload 10/min, login 5/min, question ≤ 4,000 chars |
| Tests | 100 backend + 13 frontend |
| Eval | 22 questions; retrieval 21/21 |

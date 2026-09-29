# 1. Project elevator pitch

## How to use this guide

Read sections 1–3 until you can say them without notes: they are *your* project. Sections 4–13 are the fundamentals interviewers probe, always tied back to DocMind's code. Section 14 is system-design practice, 15–16 are question banks, 17 is your "next steps" story, and 18 is the page to read in the lift on the way in.

A pattern that works in interviews: **answer in one sentence, then go one level deeper, then offer a trade-off.** "We used pgvector. It keeps vectors next to the relational data so ownership filters are a normal SQL join. The trade-off is it won't scale as far as a dedicated vector database — I'd move once we pass tens of millions of vectors or need independent scaling."

## The 60-second version

> DocMind AI is a full-stack app where you upload PDFs and ask questions about them. Answers stream in token by token and cite the document and page they came from — you can click a citation to see the exact passage.
>
> Under the hood it's retrieval-augmented generation. When a PDF is uploaded, a FastAPI backend extracts the text page by page, splits it into overlapping chunks, turns each chunk into a vector with a local embedding model, and stores it in Postgres with pgvector. When you ask a question, I embed the question, find the closest chunks *that belong to you*, and give only those to Claude with strict instructions: answer only from these sources, cite them, and say "I couldn't find it" otherwise. If nothing relevant is found, I don't call the LLM at all.
>
> The frontend is Next.js with TypeScript; the stream is Server-Sent Events read with `fetch` so I can send the auth header and support a Stop button. I hardened it the way I would for production: per-user data isolation with tests for IDOR, upload validation by magic bytes, rate limits, and defences against prompt injection — one of the test documents contains a planted "ignore all previous instructions" attack. Everything runs with `make up`, has 113 automated tests, CI, and an evaluation set where retrieval finds the right source for 21 of 21 questions.

## The 3-minute version

**The problem.** Teams have knowledge locked in PDFs — handbooks, policies, product guides. Keyword search misses paraphrases; a general chatbot doesn't know your documents and will confidently make things up. I wanted answers that are *grounded* (only from your documents), *verifiable* (every claim cites a page), and *honest* (says "not found" rather than guessing).

**Ingestion.** Upload goes to `POST /api/documents`. I validate three ways — extension, MIME type, and the `%PDF-` magic bytes — because the first two are client-controlled. Files are saved under a UUID name, never the user's filename, which kills path traversal. The endpoint returns `202 Accepted` and a background task does the work: pypdf extracts text per page, I strip running headers that repeat on every page, then a recursive chunker splits on paragraphs, lines, sentences, words — about 800 characters with 150 of overlap, and never across a page boundary so every citation is exactly one page. FastEmbed's `bge-small` model embeds the chunks in batches of 32, and everything is inserted in one transaction together with the `ready` status.

**Question answering.** `POST /api/chat` streams SSE events: `meta`, many `token`s, `citations`, `done`. I embed the question with the instruction prefix the BGE model card recommends, run a cosine-distance search with an HNSW index, filtered by the user's documents in the SQL itself, and drop anything below a similarity threshold I tuned with the eval set. The prompt wraps each chunk in `<source id file page>` tags and the system prompt says those are untrusted data, not instructions. The model cites `[1]`, `[2]`; after streaming I parse which numbers it actually used and send only those as citation chips. Follow-up questions work because I include the last six messages and run a second retrieval with the previous question for context.

**Engineering quality.** The LLM sits behind a provider interface — Claude by default, OpenAI by config, plus an offline fake for demos and CI. Provider errors map to stable error codes sent as an SSE `error` event. If the user presses Stop, the fetch is aborted, the server cancels the model stream, and the partial answer is saved inside a shielded cancel scope. There are JSON logs with request IDs recording retrieval latency, time to first token and token usage.

**What I learned / would do next.** Measuring beat guessing: the embedding model's scores for off-topic and on-topic questions overlap, so a threshold alone can't detect unanswerable questions — the prompt has to. And dense retrieval is weakest on acronyms like "RPO/RTO", which is exactly why hybrid search with BM25 is my next step, followed by a reranker.

## Numbers to have ready

| Fact | Value |
|---|---|
| Chunk size / overlap | 800 / 150 characters, never across pages |
| Embedding model | `BAAI/bge-small-en-v1.5`, 384 dimensions, local ONNX |
| Retrieval | cosine distance `<=>`, HNSW index, `TOP_K=5`, `MIN_SIMILARITY=0.45` |
| History | last 6 messages |
| Context budget | ≤ 12,000 characters of sources; answer `max_tokens` 1,024 |
| Rate limits | chat 20/min/user, upload 10/min/user, login 5/min/IP |
| Tests | 100 backend + 13 frontend |
| Eval | 22 questions; retrieval hit-rate 21/21 (100%) |
| Sample corpus | 5 PDFs, 12 pages → 32 chunks, ingested in ~0.5 s |

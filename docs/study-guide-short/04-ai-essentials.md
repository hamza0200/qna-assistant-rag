# 4. AI essentials

**Tokens.** Models read sub-word pieces (~4 characters each in English). You pay per token (output costs more than input), limits are in tokens, and latency grows with output length.

**Context window.** The total tokens the model can see (prompt + answer). Bigger isn't free: cost, latency, and worse use of information in the middle of long prompts. DocMind sends ~5 chunks, 6 history messages, ≤ 1,024 answer tokens.

**Temperature.** Low = focused and deterministic, high = varied and error-prone. Use low for factual Q&A. Newer models may replace it with an "effort" setting (DocMind: `effort: low`).

**Embeddings.** Text → vector; similar meaning → close vectors. **Cosine similarity** = angle; on normalized vectors it ranks the same as dot product and L2. BGE models want an instruction prefix on *queries* only.

**RAG in five steps.** Ingest (parse, chunk, embed, store) → retrieve (embed question, nearest neighbours + filters) → augment (prompt with numbered sources) → generate (stream, cite) → post-process (citations, save, log).

**Chunking.** Too big = blurry embeddings and wasted tokens; too small = no context. Recursive splitting on natural boundaries + overlap is the solid default.

**Hybrid search + RRF.** Keyword search finds exact terms (acronyms, codes); vectors find meaning. Merge the two ranked lists with Reciprocal Rank Fusion: score = Σ 1 / (60 + rank).

**Reranking.** A cross-encoder reads question and chunk *together* — far more accurate than vector similarity, too slow for everything. Retrieve 20–50, rerank to 5.

**Query rewriting.** Turn "and what about Enterprise?" into a standalone question before retrieval (or DocMind's cheap version: also search with the previous question).

**Hallucination.** Fluent content not supported by sources. Reduce it: skip the LLM when nothing is retrieved, "answer only from sources / say what's missing", require citations, low randomness, evaluate refusals. You reduce and expose hallucinations; you can't eliminate them.

**Prompt engineering.** Clear role, explicit rules, delimiters separating instructions from data, question last, a defined output format, edge cases handled (missing, partial, conflicting info), and a version number — prompts are code.

**Tool calling.** The model asks your code to run a declared function with JSON arguments; *your code* validates, authorizes and runs it. **Agents** are an LLM in a loop of tool calls — use only when steps can't be fixed in advance; add limits and human approval for risky actions.

**Structured outputs.** Enforce a JSON Schema via the API, or validate with Pydantic/Zod and retry.

**Fine-tuning vs RAG vs prompting.** Prompting = behaviour; RAG = knowledge; fine-tuning = style/format/narrow tasks at scale.

**Evaluation.** Measure retrieval (hit-rate@k) and generation (correct facts, faithfulness, citations, correct refusals, injection resistance) separately. LLM-as-judge scales but is biased — validate it against human labels.

**Vector indexes.** **HNSW:** layered graph, great recall, handles inserts, more memory (DocMind's choice). **IVFFlat:** clusters, faster to build, needs data first, lower recall. Both are *approximate* — you trade a little accuracy for a lot of speed.

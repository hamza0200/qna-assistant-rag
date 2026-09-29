# 4. AI / LLM fundamentals

## Tokens

**Plain language:** models don't read characters or words; they read *tokens* — chunks of text from a fixed vocabulary (often sub-words). "unbelievable" might be `un` + `believ` + `able`. English averages roughly **4 characters or ¾ of a word per token**.

**Why it matters:** you pay per token (input and output are priced separately; output is usually 4–5× more expensive), limits are in tokens, and latency grows with output tokens (generation is sequential). Tokenizers differ between providers and even model generations, so exact counts need the provider's tokenizer or token-counting endpoint.

**In DocMind:** `estimate_tokens` in `backend/app/services/chunker.py` uses `ceil(len/4)` — good enough for budgeting and logs; the real usage is read from the provider response (`final.usage.input_tokens / output_tokens`) and logged per chat turn.

## Context window

The maximum number of tokens a model can consider at once: system prompt + history + retrieved sources + the answer it writes. Current frontier models offer very large windows (hundreds of thousands to ~1M tokens), but **bigger isn't free**: cost scales with input tokens, latency rises, and models are measurably worse at using information buried in the middle of very long prompts ("lost in the middle").

**In DocMind:** we cap sources at ~12,000 characters (`MAX_CONTEXT_CHARS`), include only the last 6 messages, and cap the answer at 1,024 tokens (`LLM_MAX_TOKENS`). That keeps each request small, fast and cheap regardless of how many documents a user has.

## Temperature and sampling

At each step the model outputs a probability distribution over the next token. **Temperature** reshapes it: low (→ 0) makes the most likely token dominate (more deterministic, focused); high flattens it (more varied, creative, more errors). **Top-p** (nucleus) samples only from the smallest set of tokens whose probabilities add to *p*. For factual Q&A you want low randomness.

**Worth knowing:** some of the newest models (including recent Claude models) no longer accept sampling parameters and instead expose an **effort** control that trades reasoning depth for speed and cost. DocMind sets `output_config.effort = "low"` for short grounded answers (`backend/app/services/llm.py`).

## Embeddings and vector similarity

**Plain language:** an embedding model turns text into a list of numbers (a vector) such that texts with similar *meaning* end up close together. "How much is the Business plan?" lands near a chunk saying "The Business plan costs USD 29…", even with few shared words.

**Similarity measures:**

| Measure | Formula (intuition) | Notes |
|---|---|---|
| Cosine similarity | angle between vectors; 1 = same direction | ignores length; the standard for text |
| Dot product | sum of element-wise products | = cosine when vectors are unit length; fastest |
| Euclidean (L2) | straight-line distance | sensitive to magnitude |

If vectors are **normalized** (length 1) — as FastEmbed's are — cosine, dot product and L2 rank results identically. pgvector operators: `<=>` cosine distance (1 − similarity), `<#>` negative inner product, `<->` L2 distance. The index must be built for the operator you query with (`vector_cosine_ops` in `backend/alembic/versions/0001_initial_schema.py`).

**Asymmetric retrieval:** BGE models are trained so that *queries* should be prefixed with an instruction ("Represent this sentence for searching relevant passages: ") while *passages* are not — `FastEmbedProvider.QUERY_PREFIX` in `backend/app/services/embeddings.py`.

**Calibration:** raw similarity isn't a probability. With `bge-small`, even "What is the capital of France?" scores ~0.42 against our HR/product documents and good matches score 0.7–0.84 — which is why the threshold had to be measured (ADR-020).

## RAG end to end

**Retrieval-Augmented Generation** = look up relevant text first, then ask the model to answer *using that text*.

1. **Ingest:** extract text → clean → chunk → embed → store (vector + text + metadata such as page).
2. **Retrieve:** embed the question → nearest-neighbour search (+ filters: owner, document) → optionally rerank → keep top-k above a threshold.
3. **Augment:** build a prompt with instructions, the numbered sources, chat history and the question.
4. **Generate:** stream the answer; the model cites sources.
5. **Post-process:** extract citations, check/format, persist, log metrics.

**Why RAG works:** the model's reasoning and language ability come from pretraining; the *facts* come from your documents at question time — fresh, private, and citable.

**Failure modes to name:** retrieval misses (wrong chunks → confident wrong answer or unnecessary refusal), chunk boundaries cutting facts, stale indexes, prompt injection via documents, context overflow, and the model ignoring the sources.

## Chunking strategies

| Strategy | Idea | Good for |
|---|---|---|
| Fixed-size window | every N chars/tokens with overlap | simple, uniform text |
| Recursive (DocMind) | split on paragraph → line → sentence → word, merge up to N | general prose, PDFs |
| Structure-aware | by headings/sections/Markdown/HTML elements | manuals, docs sites |
| Semantic | split where embedding similarity between sentences drops | topic-shifting text |
| Parent–child | embed small chunks, return their larger parent section | precise retrieval + enough context |
| Late / contextual | add document-level context to each chunk before embedding | ambiguous chunks ("it", "the plan") |

DocMind uses recursive splitting per page plus a lightweight contextual header (the document title is embedded with each chunk).

## Reranking

Vector search uses a **bi-encoder**: query and chunk are embedded *separately*, so it's fast (pre-computed chunk vectors) but coarse. A **cross-encoder reranker** reads query and chunk *together* and outputs a relevance score — much more accurate, but too slow to run over the whole corpus. Standard pattern: retrieve top 20–50 with vectors (high recall), rerank to the best 3–5 (high precision). Reranker scores are also far better calibrated, which makes a "not relevant enough → refuse" threshold reliable.

## Hybrid search and Reciprocal Rank Fusion

Dense vectors capture meaning but miss **exact tokens** — acronyms, codes, names ("RPO", "VLT-409"). Keyword search (BM25 / Postgres full-text `tsvector`) nails exact terms but misses paraphrases. **Hybrid search** runs both and merges.

Scores from the two systems aren't comparable, so merge by **rank** with RRF:

```
RRF(d) = Σ over result lists  1 / (k + rank_in_list(d))      # k ≈ 60
```

A document ranked 1st in either list gets 1/61 ≈ 0.016; appearing in both lists adds up. In Postgres: a generated `tsvector` column with a GIN index, `ts_rank` for the keyword list, `<=>` for the vector list, fused in SQL or Python. This is DocMind's top "next step" — the weakest eval question (Q7, "RPO and RTO") is exactly an acronym query.

## Query rewriting

Users ask follow-ups ("and what about Enterprise?") or messy questions. Techniques:

- **Standalone rewrite:** an LLM rewrites the follow-up into a self-contained question using the history.
- **Multi-query:** generate several paraphrases, retrieve for each, fuse (RRF).
- **HyDE:** generate a hypothetical answer and embed *that* (answers look more like passages than questions do).
- **Decomposition:** split multi-part questions ("price *and* SLA") into sub-queries.

DocMind uses a cheap, LLM-free version for follow-ups: a second search with the previous question prepended, merged with the plain search (`retrieve_for_turn` in `backend/app/services/rag.py`).

## Hallucination and grounding

A **hallucination** is fluent, confident content not supported by the input or reality. Causes: the model fills gaps with plausible text; missing or wrong retrieved context; ambiguous questions; pressure to always answer.

How DocMind reduces it:

1. **Skip the LLM** when nothing relevant is retrieved — a deterministic "not found".
2. **Grounding instructions:** answer only from sources; say what's missing; flag false premises ("London office" isn't in the documents).
3. **Citations required** for every claim, and only referenced sources are shown — users can verify in one click.
4. **Low effort / no creativity** settings; short answers.
5. **Evaluation** with refusal questions (Q20, Q21) to measure it.

Beyond this: faithfulness checks (a second model verifies each claim against sources), constrained output formats, and abstaining when retrieval confidence is low.

## Prompt engineering

Principles that show up in `backend/app/services/prompts.py`:

- **Clear role and task**, then explicit rules — positive ("cite every factual claim") more than negative.
- **Separate instructions from data** with delimiters (`<source>` tags) and say explicitly that the data is untrusted.
- **Structure the input**: sources first, question last (models attend well to the end of the prompt).
- **Specify output format**: `[n]` citation markers, concise, Markdown only when useful.
- **Handle edge cases in the prompt**: missing info, partial info, conflicting sources, false premises.
- **Version prompts** (`PROMPT_VERSION`) and change them only with an eval run — prompts are code.

Few-shot examples (showing input → ideal output) are the next lever when instructions alone don't produce the format you want.

## Function / tool calling

The application describes **tools** (name, description, JSON Schema for arguments). The model can respond with a structured request — "call `get_order_status` with `{"order_id": "A123"}`" — instead of text. **Your code** executes the tool and sends the result back; the loop continues until the model answers in text. The model never executes anything itself.

Key points: validate arguments against the schema before running; tools are an authorization boundary (a tool must check the *user's* permissions, not trust the model); keep tool results small and relevant; set iteration limits.

## Agents

An **agent** is an LLM in a loop: decide → call tools → observe results → decide again, until the goal is met. Useful when steps can't be specified in advance (research, multi-step support cases, coding). Costs: more tokens, more latency, less predictability, bigger attack surface (excessive agency). Rule of thumb: use the simplest thing that works — a single call, then a fixed workflow (like DocMind's retrieve → generate pipeline), and an agent only when the path genuinely depends on intermediate results. Guardrails: allow-listed tools, human approval for risky actions, budgets and step limits, audit logs.

## Structured outputs (JSON)

When code consumes the model's output, ask for JSON matching a schema. Modern APIs can **enforce** a JSON Schema (structured outputs / strict tool schemas), which removes parsing failures; otherwise validate with Pydantic/Zod and retry on failure. DocMind streams prose for humans, but citations could have been returned as structured data — we parse `[n]` markers instead so the answer can stream naturally.

## Fine-tuning vs RAG vs prompting

| Need | Best first tool |
|---|---|
| Answer from private/changing facts, with citations | **RAG** |
| Change behaviour/format with a few rules | **Prompting** (+ few-shot examples) |
| Consistent style, domain jargon, a narrow task at high volume/low latency | **Fine-tuning** (often of a smaller model) |
| Teach new *knowledge* reliably | RAG — fine-tuning memorises facts unreliably and can't cite |

They combine: a fine-tuned small model that follows your answer format, fed by RAG.

## Open-source vs hosted models

| | Hosted API (Claude, GPT) | Open-weights (Llama, Mistral, Qwen…) self-hosted |
|---|---|---|
| Quality | frontier | good and improving; smaller models lag on hard reasoning |
| Ops | none | GPUs, serving (vLLM/TGI), scaling, monitoring |
| Cost | per token; no fixed cost | fixed GPU cost; cheap at high, steady volume |
| Data | leaves your infra (check retention/DPAs) | stays in your VPC |
| Control | provider changes/deprecations | pin exact weights; fine-tune freely |

DocMind is a hybrid: open-source embeddings locally (cheap, private), hosted LLM for generation (quality).

## Evaluating LLM applications

Evaluate the **retriever** and the **generator** separately — otherwise you can't tell which one failed.

- **Retrieval:** *hit-rate@k* (is a relevant chunk in the top-k?), recall@k, MRR (how high is the first relevant result?), nDCG. DocMind: 21/21 hit-rate@5 at document and page level.
- **Generation:** *answer correctness* (key facts present — DocMind's string match), *faithfulness/groundedness* (is every claim supported by the retrieved sources?), *answer relevance*, *citation accuracy*, *refusal correctness* on unanswerable questions, *safety* (injection resistance).
- **LLM-as-judge:** a strong model grades answers against a rubric or reference. Scales to paraphrases string matching can't handle. Pitfalls: position and verbosity bias, self-preference, cost, non-determinism — so validate the judge against human labels on a sample, use clear rubrics and pairwise comparisons, and keep deterministic checks where you can.
- **Process:** a versioned eval set (DocMind: `sample-docs/test-questions.md`), run on every prompt/model/chunking change, track metrics over time, and add real failing questions from production feedback.

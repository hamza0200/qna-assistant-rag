# 12. Testing

## The test pyramid

| Level | What | Speed | DocMind |
|---|---|---|---|
| **Unit** | one function/class in isolation | ms | chunker, PDF parser, sanitizers, JWT/bcrypt helpers, SSE parser, citation linking, eval scorer |
| **Integration / API** | several components with real infrastructure | 10–100 ms | FastAPI app in-process via `httpx.ASGITransport` against a real Postgres + pgvector `_test` database, with the LLM and embedder mocked |
| **End-to-end** | the running system through the UI | seconds | headless Chrome scripts during development: register/login, upload + polling, chat streaming, citations, Stop, reload |
| **Evaluation** | quality of AI output on a labelled set | minutes, costs tokens | `scripts/eval.py` on 22 questions |

Many fast tests at the bottom, few slow ones at the top. **111 automated tests**: 98 backend (`pytest`) + 13 frontend (`vitest` + Testing Library), all running in CI.

## Mocking the LLM

Never call a real LLM in unit/integration tests: slow, costly, flaky, non-deterministic. DocMind injects a scripted fake through FastAPI's dependency overrides (`backend/tests/test_chat.py`):

```python
class FakeLLM(LLMProvider):
    def __init__(self, tokens=None, fail_with=None):
        self.tokens = tokens or ["The Business plan costs ", "USD 29 [1]."]
        self.fail_with, self.calls = fail_with, []

    async def stream(self, system, messages, usage=None):
        self.calls.append((system, messages))   # record what the model saw
        for t in self.tokens:
            yield t
        if self.fail_with:
            raise self.fail_with

app.dependency_overrides[get_llm_factory] = lambda: (lambda: llm)
```

Recording the calls lets tests assert on **what the model would see** (sources wrapped in delimiters, history included, injection text only inside `<source>`) and **whether it was called at all** (`assert fake_llm.calls == []` for the no-context path). Provider error mapping is tested by patching the SDK stream to raise real `anthropic.APITimeoutError` / `RateLimitError` objects. Embeddings use a deterministic hashed bag-of-words `FakeEmbedder` (`backend/tests/helpers.py`) so texts sharing words are similar — retrieval behaviour is testable without the model.

## Testing streams

- **Backend:** read the whole SSE response, parse frames, assert the **order** (`meta` → `token`… → `citations` → `done`), the concatenated text, and the citations. Error path: `meta` → `token` → `error`. Stop/disconnect: iterate the `answer_stream` generator, `break` after two tokens, `aclose()` it, and assert the partial answer was persisted.
- **Frontend:** `src/lib/sse.test.ts` feeds the parser events split at arbitrary chunk boundaries, CRLF line endings, a trailing event with no blank line, and a multi-byte UTF-8 character split across two chunks.

## Security tests worth copying

IDOR for every resource type (documents, chunks, conversations, and retrieval via `document_ids`), JWT attacks (expired, wrong key, `alg: none`), upload spoofing (renamed executable with `application/pdf`), path-traversal filenames, oversized files, a bad file in a batch rejecting the whole batch, rate limits (per user, with a second user unaffected), CORS origins, generic 500s that don't leak exception text, and prompt-injection containment.

## Evaluation sets

An eval set is a versioned list of questions with expected answers, key facts and expected sources, covering question *types*: fact, table, multi-document, reasoning, refusal, injection, follow-up (`sample-docs/test-questions.md`). Measure retrieval and generation separately; run it after every change to prompts, models, chunking or thresholds; grow it with real failures.

**Grade the grader:** DocMind's scorer is unit-tested (`backend/tests/test_eval_scoring.py`), including "every reference answer passes its own scoring" — which exposed a quirk: Q13's reference answer doesn't literally contain its own key fact ("Bahrain").

## Results so far (`docs/EVAL_RESULTS.md`)

| Metric | Result |
|---|---|
| Retrieval hit-rate — expected document(s) in top-5 | **21/21 (100%)** |
| Retrieval hit-rate — expected page(s) in top-5 | **21/21 (100%)** |
| Answer accuracy | pending: requires an LLM API key (`make eval`) — target ≥ 85% |

Settings: `TOP_K=5`, `MIN_SIMILARITY=0.45` (tuned with `eval.py --sweep`: 21/21 up to 0.45, 20/21 at 0.5, 19/21 at 0.6; TOP_K 3/5/8 identical on this corpus).

Findings: the weakest retrieval is Q7 ("What are the RPO and RTO?", top-1 similarity 0.508) — an acronym query, dense retrieval's blind spot. The refusal questions (stock price, London office) retrieve on-topic chunks at ~0.69–0.74, so only the prompt can make the model refuse them.

## What I'd improve

- Run the answer eval with a real model and track it in CI on a schedule (nightly), with a budget.
- Add an **LLM-as-judge** faithfulness column (is every sentence supported by the cited source?), validated against manual labels.
- Hybrid search + reranker, then re-run the sweep; add more acronym, table and multi-hop questions.
- Measure citation accuracy (does `[n]` actually support the sentence it's attached to?).
- Promote the headless-Chrome scripts to Playwright tests in CI with the `fake` provider.
- Property-based tests for the chunker (Hypothesis: no text lost, size limits always hold).

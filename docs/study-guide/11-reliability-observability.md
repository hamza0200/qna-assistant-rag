# 11. Reliability and observability

## Timeouts

Every network call needs a deadline, or one slow dependency ties up workers until everything stalls. DocMind: the LLM client has `timeout=LLM_TIMEOUT_SECONDS` (60 s); the DB pool pre-pings connections; the health check fails fast. For streams, think in two numbers: time to first byte and idle time between chunks. Timeouts should be shorter the closer you are to the user (edge < service < database) so upstream layers don't give up after downstream work is wasted.

## Retries with exponential backoff and jitter

Retry only **transient** failures (connection errors, 408, 409, 429, 5xx) — never 400/401/404. Wait `base × 2^attempt` plus random **jitter** so thousands of clients don't retry in lockstep (thundering herd), honour `Retry-After`, and cap attempts. Only retry **idempotent** operations (or use idempotency keys).

DocMind: the Anthropic/OpenAI SDKs retry up to `LLM_MAX_RETRIES` (2) with exponential backoff — **before** the stream starts. Once tokens have reached the user, retrying would duplicate text, so a mid-stream failure becomes an SSE `error` event (`LLM_UNAVAILABLE`, `LLM_TIMEOUT`, …) and the partial answer is saved.

## Circuit breakers

If a dependency is failing, stop hammering it. A breaker tracks failures: **closed** (normal) → too many failures → **open** (fail fast, don't call) → after a cool-down → **half-open** (let a few trial requests through) → close on success. Benefits: protects the struggling dependency, frees your workers, gives instant errors instead of slow timeouts, and is the natural place to trigger a fallback. Not implemented in DocMind (single provider call per request); libraries: `pybreaker`, `aiobreaker`, or a service mesh.

## Fallbacks between LLM providers

Options, from simplest:

1. **Same provider, different model** — DocMind enables Anthropic's server-side refusal fallback (`fallbacks: "default"`), which reruns a classifier-declined request on a recommended model inside the same stream.
2. **Cross-provider failover** — because `LLMProvider` is an interface, a `FallbackProvider([anthropic, openai])` can try the second provider when the first fails *before streaming starts*, ideally driven by a circuit breaker.
3. **Degraded mode** — when all providers are down, return retrieved passages without a generated answer ("Here are the most relevant passages…"); DocMind's offline `fake` provider is essentially this.

Caveats: prompts may need per-provider tuning; evaluate both paths; watch data-processing agreements for each provider.

## Structured logging

JSON lines, one event per line, with consistent fields — machine-searchable in Loki/CloudWatch/Datadog. DocMind (`backend/app/core/logging.py`) adds a `request_id` from a `ContextVar` to every line and returns it as `X-Request-ID`. A chat turn logs:

```json
{"msg": "chat_turn", "request_id": "cbfcf462…", "completed": true, "llm_called": true,
 "chunks_retrieved": 5, "chunks_in_prompt": 5, "citations": 1,
 "llm_model": "claude-opus-5-5", "input_tokens": 2143, "output_tokens": 88,
 "llm_first_token_ms": 812.4, "llm_total_ms": 2410.9, "total_ms": 2466.0}
```

Rules: log events and IDs, not payloads — never passwords, tokens, or document contents (privacy + cost); log at the boundary (request in/out) and at decisions (retrieval result, LLM call).

## Metrics and tracing

- **Metrics** (Prometheus/OpenTelemetry): counters and histograms aggregated over time — request rate, error rate, latency percentiles (p50/p95/p99), queue depth. The "RED" method for services: **R**ate, **E**rrors, **D**uration; "USE" for resources: **U**tilization, **S**aturation, **E**rrors.
- **Tracing** (OpenTelemetry → Jaeger/Tempo/Datadog): one trace per request with spans for each step (embed → search → LLM → persist) — shows exactly where a slow request spent its time, across services. DocMind's request ID is the poor man's version; OTel's `traceparent` header is the standard.
- **Alerts** on symptoms users feel (error rate, TTFT p95), not every cause.

## What to monitor in an AI app

| Area | Signals |
|---|---|
| Latency | time to first token (p50/p95), total answer time, retrieval latency, ingestion duration per page |
| Quality | refusal rate ("not found" answers), answers with zero citations, retrieval top-score distribution drift, thumbs-down rate, periodic eval-set score |
| Cost | input/output tokens per request/user/day, spend per model, cache hit rate |
| Reliability | provider error rates by code (429/5xx/timeout), fallback activations, stream aborts, ingestion failure rate by reason (scanned PDF, encrypted) |
| Safety | detected injection attempts, refusals by category, rate-limit hits, unusual per-user volume |
| Capacity | concurrent SSE connections, queue depth, DB connections, embedding throughput |

The quality signals are what make AI apps different: the system can be up and fast while the answers silently get worse (a model update, a new document type, a drifted index). Track them like SLIs.

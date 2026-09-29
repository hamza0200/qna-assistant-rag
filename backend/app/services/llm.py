"""Provider-agnostic LLM streaming.

The RAG layer depends only on `LLMProvider.stream()`; Anthropic and OpenAI are
interchangeable implementations chosen by the LLM_PROVIDER env var. Provider
SDK errors are translated into one `LLMError` with a stable `code`, which the
chat route forwards to the browser as an SSE `error` event.

Reliability:
- Timeouts: every request has a client-side timeout (LLM_TIMEOUT_SECONDS).
- Retries: both SDKs retry connection errors, 408/409/429 and 5xx with
  exponential backoff + jitter (LLM_MAX_RETRIES). Retries happen only before
  the stream starts — once tokens have reached the user, a retry would
  duplicate text, so mid-stream failures surface as an error event instead.
"""

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """A provider failure, normalized. `message` is safe to show to end users."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LLMUsage:
    """Filled in by `stream()` once the response completes (if the provider reports it)."""

    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None
    first_token_ms: float | None = None
    total_ms: float | None = None


Message = dict[str, str]  # {"role": "user"|"assistant", "content": "..."}


class LLMProvider(ABC):
    @abstractmethod
    def stream(
        self, system: str, messages: list[Message], usage: LLMUsage | None = None
    ) -> AsyncIterator[str]:
        """Yield answer text deltas as they are generated."""


# --------------------------------------------------------------------------- Anthropic


class AnthropicProvider(LLMProvider):
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, settings: Settings) -> None:
        from anthropic import AsyncAnthropic

        if not settings.anthropic_api_key:
            raise LLMError("LLM_NOT_CONFIGURED", "The AI provider is not configured on the server.")
        self.settings = settings
        self.client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def _request_params(self, system: str, messages: list[Message]) -> dict[str, Any]:
        s = self.settings
        params: dict[str, Any] = {
            "model": s.llm_model,
            "max_tokens": s.llm_max_tokens,  # hard cap on answer length (cost + latency control)
            "system": system,
            "messages": messages,
        }
        if s.llm_effort:
            # Effort trades reasoning depth for latency/cost; RAG answers over a
            # handful of short sources don't need deep deliberation.
            params["output_config"] = {"effort": s.llm_effort}
        if s.llm_fallbacks_enabled:
            # If a safety classifier declines, Anthropic re-runs the request on a
            # recommended fallback model inside the same stream.
            params["betas"] = [self.FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    async def stream(
        self, system: str, messages: list[Message], usage: LLMUsage | None = None
    ) -> AsyncIterator[str]:
        import anthropic

        usage = usage if usage is not None else LLMUsage()
        params = self._request_params(system, messages)
        started = time.perf_counter()
        api = self.client.beta.messages if "betas" in params else self.client.messages
        try:
            async with api.stream(**params) as stream:
                async for text in stream.text_stream:
                    if usage.first_token_ms is None:
                        usage.first_token_ms = round((time.perf_counter() - started) * 1000, 1)
                    yield text
                final = await stream.get_final_message()
        except anthropic.APITimeoutError as exc:
            raise LLMError(
                "LLM_TIMEOUT", "The AI provider took too long to respond. Please try again."
            ) from exc
        except anthropic.RateLimitError as exc:
            raise LLMError(
                "LLM_RATE_LIMITED", "The AI provider is busy right now. Please try again shortly."
            ) from exc
        except anthropic.AuthenticationError as exc:
            logger.error("llm_auth_failed")
            raise LLMError(
                "LLM_NOT_CONFIGURED", "The AI provider rejected the server's credentials."
            ) from exc
        except anthropic.NotFoundError as exc:  # usually a wrong LLM_MODEL name
            logger.error("llm_model_not_found", extra={"model": self.settings.llm_model})
            raise LLMError("LLM_NOT_CONFIGURED", "The configured AI model isn't available.") from exc
        except anthropic.BadRequestError as exc:
            logger.error("llm_bad_request", extra={"detail": str(exc)[:500]})
            if "credit balance" in str(exc).lower():
                raise LLMError(
                    "LLM_BILLING",
                    "The AI provider account has run out of credits. Ask the administrator to top up.",
                ) from exc
            raise LLMError("LLM_BAD_REQUEST", "The AI provider rejected the request.") from exc
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            raise LLMError("LLM_UNAVAILABLE", "The AI provider is unavailable. Please try again.") from exc

        usage.model = final.model
        usage.input_tokens = final.usage.input_tokens
        usage.output_tokens = final.usage.output_tokens
        usage.stop_reason = final.stop_reason
        usage.total_ms = round((time.perf_counter() - started) * 1000, 1)
        if final.stop_reason == "refusal":
            # Every model in the fallback chain declined; partial text must not be treated as an answer.
            raise LLMError("LLM_REFUSED", "The AI model declined to answer this request.")


# --------------------------------------------------------------------------- OpenAI


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI

        if not settings.openai_api_key:
            raise LLMError("LLM_NOT_CONFIGURED", "The AI provider is not configured on the server.")
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    async def stream(
        self, system: str, messages: list[Message], usage: LLMUsage | None = None
    ) -> AsyncIterator[str]:
        import openai

        usage = usage if usage is not None else LLMUsage()
        started = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.llm_model,
                max_completion_tokens=self.settings.llm_max_tokens,
                messages=[{"role": "system", "content": system}, *messages],  # type: ignore[list-item]
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in response:
                if chunk.usage:
                    usage.input_tokens = chunk.usage.prompt_tokens
                    usage.output_tokens = chunk.usage.completion_tokens
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    usage.stop_reason = choice.finish_reason
                if choice.delta.content:
                    if usage.first_token_ms is None:
                        usage.first_token_ms = round((time.perf_counter() - started) * 1000, 1)
                    yield choice.delta.content
                usage.model = chunk.model
        except openai.APITimeoutError as exc:
            raise LLMError(
                "LLM_TIMEOUT", "The AI provider took too long to respond. Please try again."
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMError(
                "LLM_RATE_LIMITED", "The AI provider is busy right now. Please try again shortly."
            ) from exc
        except openai.AuthenticationError as exc:
            logger.error("llm_auth_failed")
            raise LLMError(
                "LLM_NOT_CONFIGURED", "The AI provider rejected the server's credentials."
            ) from exc
        except (openai.APIConnectionError, openai.APIStatusError) as exc:
            raise LLMError("LLM_UNAVAILABLE", "The AI provider is unavailable. Please try again.") from exc
        usage.total_ms = round((time.perf_counter() - started) * 1000, 1)
        if usage.stop_reason == "content_filter":
            raise LLMError("LLM_REFUSED", "The AI model declined to answer this request.")


# --------------------------------------------------------------------------- offline fake


class FakeExtractiveProvider(LLMProvider):
    """Offline stand-in for local development and CI (LLM_PROVIDER=fake). Not for production.

    Streams the first sentences of source [1] back as the "answer", so the full
    pipeline (retrieval, SSE, citations, UI) can be exercised with no API key.
    """

    _SOURCE_1 = re.compile(r'<source id="1"[^>]*>\n(.*?)\n</source>', re.DOTALL)

    async def stream(
        self, system: str, messages: list[Message], usage: LLMUsage | None = None
    ) -> AsyncIterator[str]:
        match = self._SOURCE_1.search(messages[-1]["content"])
        excerpt = " ".join(match.group(1).split())[:300] if match else ""
        text = f"(Offline demo mode, no LLM) The most relevant passage says: {excerpt} [1]"
        for word in text.split(" "):
            await asyncio.sleep(0.02)
            yield word + " "
        if usage is not None:
            usage.model, usage.stop_reason = "fake-extractive", "end_turn"


# --------------------------------------------------------------------------- factory


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Process-wide client (reuses HTTP connections across requests)."""
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings)
    if settings.llm_provider == "fake":
        return FakeExtractiveProvider()
    return AnthropicProvider(settings)

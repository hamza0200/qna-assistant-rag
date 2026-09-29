"""Embedding providers.

`EmbeddingProvider` is the interface the rest of the app depends on, so the
local FastEmbed model can be swapped for a hosted API (e.g. OpenAI embeddings)
by adding one class — as long as the vector dimension in the DB matches.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (may use a different prompt than passages)."""


class FastEmbedProvider(EmbeddingProvider):
    """Local ONNX embeddings via FastEmbed (no API key, no per-call cost).

    Model inference is CPU-bound and synchronous, so calls run in a worker
    thread (`asyncio.to_thread`) to avoid blocking the event loop — otherwise
    one large upload would stall every other request, including streaming chats.
    """

    # BGE v1.5 model card: prefix *queries* (not passages) with this instruction
    # for short-query -> passage retrieval. FastEmbed doesn't add it for this model.
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str, dim: int, batch_size: int, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding  # heavy import, deferred

        self.dim = dim
        self.batch_size = batch_size
        self._model = TextEmbedding(model_name, cache_dir=cache_dir)
        logger.info("embedding_model_loaded", extra={"model": model_name})

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        # FastEmbed returns L2-normalized vectors, so cosine similarity == dot product.
        return [vec.tolist() for vec in self._model.embed(texts, batch_size=self.batch_size)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(self._embed_sync, [self.QUERY_PREFIX + text])
        return vectors[0]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Process-wide singleton: the model is loaded once (at startup), not per request."""
    s = get_settings()
    return FastEmbedProvider(
        s.embedding_model, s.embedding_dim, s.embedding_batch_size, s.embedding_cache_dir
    )

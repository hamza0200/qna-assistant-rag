"""Application settings loaded from environment variables.

Why pydantic-settings: one typed, validated object for all config means a
typo'd or missing env var fails loudly at startup instead of at request time.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "DocMind AI"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    # Comma-separated list in env, e.g. "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://docmind:docmind@localhost:5433/docmind"
    db_pool_size: int = 10
    db_max_overflow: int = 5

    # --- Auth ---
    jwt_secret: str = Field(default="change-me-in-env", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Uploads ---
    upload_dir: str = "./storage/uploads"
    max_upload_mb: int = 20

    # --- RAG ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_batch_size: int = 32
    embedding_cache_dir: str | None = None
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 5
    min_similarity: float = 0.35
    history_messages: int = 6
    max_context_chars: int = 12000

    # --- LLM ---
    # "fake" = offline extractive stand-in for local dev/CI without an API key.
    llm_provider: Literal["anthropic", "openai", "fake"] = "anthropic"
    llm_model: str = "claude-opus-5-5"
    # Anthropic "effort" (thinking depth / token spend). Empty = provider default.
    llm_effort: str = "low"
    # Anthropic server-side refusal fallback (routes a declined request to another model).
    llm_fallbacks_enabled: bool = True
    llm_max_tokens: int = 1024
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # --- Rate limits (slowapi syntax) ---
    rate_limit_enabled: bool = True
    rate_limit_chat: str = "20/minute"
    rate_limit_upload: str = "10/minute"
    rate_limit_login: str = "5/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env is read once per process)."""
    return Settings()

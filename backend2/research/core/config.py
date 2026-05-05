"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""

    # API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None    # primary
    tavily_api_key_2: Optional[str] = None  # fallback 1
    tavily_api_key_3: Optional[str] = None  # fallback 2
    langsmith_api_key: Optional[str] = None

    # LLM provider: "anthropic" or "openai"
    llm_provider: str = "openai"

    # Anthropic model names
    default_model: str = "claude-3-5-haiku-20241022"
    sonnet_model: str = "claude-3-5-sonnet-20241022"
    opus_model: str = "claude-3-opus-20240229"

    # OpenAI model names (used when llm_provider="openai")
    # All tiers point at gpt-4o-mini during debug — see note on llm_provider.
    openai_haiku_model: str = "gpt-4o-mini"
    openai_sonnet_model: str = "gpt-4o-mini"
    openai_opus_model: str = "gpt-4o-mini"

    # Budget Configuration
    default_budget_usd: float = 3.0
    max_budget_usd: float = 5.0

    # Search Configuration
    tavily_max_results: int = 10
    tavily_news_days: int = 90
    searxng_url: str = "http://localhost:8888"  # local Docker SearXNG instance

    # Cache Configuration
    cache_ttl_seconds: int = 300  # 5 minutes
    cache_dir: str = "~/.research/cache"

    # Development
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra keys in .env without crashing — repo-root .env may carry
        # keys for other tools (groq, perplexity, etc.) that aren't relevant
        # to this Settings class.
        extra = "ignore"


# Global settings instance
settings = Settings()


# Export provider API keys to os.environ so downstream SDKs (CrewAI's native
# OpenAI/Anthropic providers, litellm, openai-python, etc.) can read them
# directly from process env. pydantic-settings loads from .env but does not
# propagate to os.environ on its own.
import os as _os
if settings.openai_api_key and not _os.environ.get("OPENAI_API_KEY"):
    _os.environ["OPENAI_API_KEY"] = settings.openai_api_key
if settings.anthropic_api_key and not _os.environ.get("ANTHROPIC_API_KEY"):
    _os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

# Defensive: force stdout/stderr to UTF-8 on Windows so structlog / print()
# can emit unicode (>=, arrows, em-dashes) without crashing on cp1252. Must
# happen before any crew code runs since structlog captures stdout at import.
import sys as _sys
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(_sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

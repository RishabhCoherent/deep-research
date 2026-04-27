"""Model router for selecting appropriate LLM models.

Default max_tokens per model class:
  haiku  → 2,000  (small classification / JSON tasks; bumped for gpt-4o-mini JSON-mode overhead)
  sonnet → 4,000  (full-text generation, multi-step tool use)
  opus   → 4,000  (deep reasoning; use sparingly)

When llm_provider="openai" (current debug default), all three tiers map to
whatever is configured in settings.openai_*_model — currently all gpt-4o-mini.

Pass max_tokens explicitly when a sub-agent needs a different cap.
"""

from langchain_core.rate_limiters import InMemoryRateLimiter
from research.core.config import settings

# Anthropic rate limiter — 0.15 req/s keeps well under tier-1 API limits.
_ANTHROPIC_RATE_LIMITER = InMemoryRateLimiter(
    requests_per_second=0.15, check_every_n_seconds=0.5, max_bucket_size=1
)
# OpenAI rate limiter — gpt-4o-mini has 3,500 RPM but with many parallel agents
# we can still bunch. 2 req/s (~120 RPM) is safe and avoids 429s at scale.
_OPENAI_RATE_LIMITER = InMemoryRateLimiter(
    requests_per_second=2.0, check_every_n_seconds=0.1, max_bucket_size=4
)


def _is_openai() -> bool:
    return settings.llm_provider.lower() == "openai"


def haiku(max_tokens: int = 2_000):
    """Return the fast/cheap model (Haiku or gpt-4o-mini)."""
    if _is_openai():
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_haiku_model,
            openai_api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=max_tokens,
            max_retries=4,
            rate_limiter=_OPENAI_RATE_LIMITER,
        )
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=settings.default_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=max_tokens,
        max_retries=8,
        rate_limiter=_ANTHROPIC_RATE_LIMITER,
    )


def sonnet(max_tokens: int = 4_000):
    """Return the mid-tier model (Sonnet or gpt-4o-mini in debug)."""
    if _is_openai():
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_sonnet_model,
            openai_api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=max_tokens,
            max_retries=4,
            rate_limiter=_OPENAI_RATE_LIMITER,
        )
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=settings.sonnet_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=max_tokens,
        rate_limiter=_ANTHROPIC_RATE_LIMITER,
    )


def opus(max_tokens: int = 4_000):
    """Return the high-reasoning model (Opus or gpt-4o-mini in debug)."""
    if _is_openai():
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_opus_model,
            openai_api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=max_tokens,
            max_retries=4,
            rate_limiter=_OPENAI_RATE_LIMITER,
        )
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=settings.opus_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=max_tokens,
        rate_limiter=_ANTHROPIC_RATE_LIMITER,
    )

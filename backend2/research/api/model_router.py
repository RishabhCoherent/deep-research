"""Model router for selecting appropriate LLM models.

Default max_tokens per model class:
  haiku  → 1,000  (small classification / JSON tasks)
  sonnet → 4,000  (full-text generation, multi-step tool use)
  opus   → 4,000  (deep reasoning; use sparingly)

Pass max_tokens explicitly when a sub-agent needs a different cap.
"""

from langchain_anthropic import ChatAnthropic
from research.core.config import settings


def haiku(max_tokens: int = 1_000):
    """Return Haiku model instance.

    Args:
        max_tokens: Hard cap on output tokens (default 1,000).
                    Raise to 2,000–4,000 for sub-agents that emit large JSON lists.
    """
    return ChatAnthropic(
        model=settings.default_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=max_tokens,
    )


def sonnet(max_tokens: int = 4_000):
    """Return Sonnet model instance.

    Args:
        max_tokens: Hard cap on output tokens (default 4,000).
                    Lower to ~1,500 for simple classification tasks to save cost.
    """
    return ChatAnthropic(
        model=settings.sonnet_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=max_tokens,
    )


def opus(max_tokens: int = 4_000):
    """Return Opus model instance.

    Args:
        max_tokens: Hard cap on output tokens (default 4,000).
    """
    return ChatAnthropic(
        model=settings.opus_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=max_tokens,
    )

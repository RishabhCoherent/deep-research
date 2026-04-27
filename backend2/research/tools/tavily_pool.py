"""Tavily API key pool with automatic rotation on quota/rate-limit errors.

Holds up to 3 keys (TAVILY_API_KEY, TAVILY_API_KEY_2, TAVILY_API_KEY_3).
When a search fails with a quota or rate-limit error, the pool rotates to
the next key and retries transparently. All other errors are re-raised.

Usage (internal — called by research_search and web_search):
    from research.tools.tavily_pool import tavily_pool
    response = tavily_pool.search(query="...", search_depth="advanced", max_results=5)
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Substrings that indicate a quota / rate-limit failure from Tavily
_QUOTA_SIGNALS = ("429", "402", "quota", "rate limit", "rate_limit",
                  "exceeded", "credit", "usage limit", "too many requests")


class TavilyKeyPool:
    """Round-robin key pool that rotates on quota exhaustion."""

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._idx: int = 0
        self._loaded: bool = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        from research.core.config import settings
        candidates = [
            settings.tavily_api_key,
            settings.tavily_api_key_2,
            settings.tavily_api_key_3,
        ]
        seen: set[str] = set()
        for k in candidates:
            if k and k.strip().startswith("tvly-") and k not in seen:
                self._keys.append(k.strip())
                seen.add(k)
        self._loaded = True
        log.info("tavily_pool.loaded", keys=len(self._keys))

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return bool(self._keys)

    def _current_key(self) -> str:
        return self._keys[self._idx]

    def _rotate(self) -> bool:
        """Move to next key. Returns False if we've tried all keys."""
        next_idx = (self._idx + 1) % len(self._keys)
        if next_idx == self._idx:
            return False
        self._idx = next_idx
        log.warning("tavily_pool.rotated",
                    new_index=self._idx,
                    key_prefix=self._current_key()[:16] + "...")
        return True

    def _is_quota_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(signal in msg for signal in _QUOTA_SIGNALS)

    def search(self, **kwargs: Any) -> dict:
        """Call TavilyClient.search() with automatic key rotation on quota errors.

        Passes all kwargs directly to TavilyClient.search().
        Returns the raw Tavily response dict on success.
        Returns {"results": [], "error": "..."} when all keys are exhausted.
        Raises on non-quota errors (network, bad query, etc.).
        """
        self._ensure_loaded()

        if not self._keys:
            return {
                "results": [],
                "error": "No Tavily API keys configured (TAVILY_API_KEY not set).",
            }

        tried: set[int] = set()
        while self._idx not in tried:
            tried.add(self._idx)
            try:
                from tavily import TavilyClient
                client = TavilyClient(api_key=self._current_key())
                return client.search(**kwargs)
            except Exception as exc:
                if self._is_quota_error(exc):
                    log.warning("tavily_pool.quota_error",
                                key_index=self._idx,
                                error=str(exc)[:120])
                    if not self._rotate():
                        break  # no more keys to try
                else:
                    raise  # network error, bad query — let caller handle it

        return {
            "results": [],
            "error": "All Tavily API keys exhausted or rate-limited.",
        }


# Module-level singleton — index persists across calls within a process
tavily_pool = TavilyKeyPool()

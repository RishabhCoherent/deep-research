"""
Tavily API Key Manager.

Rotates through multiple API keys with:
- Round-robin rotation on each request
- Auto-cooldown on 429 rate limit (65s)
- Thread-safe for parallel LangGraph execution
- Usage tracking per key
"""

import os
import time
import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KeyState:
    """Tracks the state of a single API key."""
    key: str
    request_count: int = 0
    error_count: int = 0
    cooldown_until: float = 0.0  # Unix timestamp when cooldown expires
    last_used: float = 0.0


class TavilyKeyManager:
    """Manages multiple Tavily API keys with rotation and cooldown."""

    def __init__(self):
        self._keys: list[KeyState] = []
        self._lock = threading.Lock()
        self._current_index = 0
        self._load_keys()

    def _load_keys(self):
        """Load keys from environment variables."""
        # Priority 1: TAV_API_KEYS (comma-separated)
        multi_keys = os.getenv("TAV_API_KEYS", "")
        if multi_keys:
            for k in multi_keys.split(","):
                k = k.strip()
                if k:
                    self._keys.append(KeyState(key=k))

        # Priority 2: TAVILY_API_KEY (single)
        single_key = os.getenv("TAVILY_API_KEY", "") or os.getenv("TAV_API_KEY", "")
        if single_key and not any(ks.key == single_key for ks in self._keys):
            self._keys.append(KeyState(key=single_key.strip()))

        if self._keys:
            logger.info(f"Tavily Key Manager initialized with {len(self._keys)} keys")
        else:
            logger.warning("No Tavily API keys found")

    @property
    def has_keys(self) -> bool:
        return len(self._keys) > 0

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    @property
    def available_keys(self) -> int:
        """Count of keys not currently in cooldown."""
        now = time.time()
        return sum(1 for ks in self._keys if ks.cooldown_until <= now)

    def get_key(self) -> str | None:
        """Get the next available API key (round-robin, skip cooled-down keys).

        Returns None if no keys available.
        """
        if not self._keys:
            return None

        with self._lock:
            now = time.time()
            attempts = 0

            while attempts < len(self._keys):
                ks = self._keys[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._keys)

                if ks.cooldown_until <= now:
                    ks.request_count += 1
                    ks.last_used = now
                    return ks.key

                attempts += 1

            # All keys in cooldown — return the one with earliest cooldown expiry
            earliest = min(self._keys, key=lambda k: k.cooldown_until)
            wait_time = earliest.cooldown_until - now
            if wait_time > 0:
                logger.warning(f"All {len(self._keys)} keys in cooldown. "
                               f"Shortest wait: {wait_time:.1f}s")
            earliest.request_count += 1
            earliest.last_used = now
            return earliest.key

    def report_rate_limit(self, key: str, cooldown_seconds: float = 65.0):
        """Mark a key as rate-limited with a cooldown period."""
        with self._lock:
            for ks in self._keys:
                if ks.key == key:
                    ks.cooldown_until = time.time() + cooldown_seconds
                    ks.error_count += 1
                    available = self.available_keys
                    logger.info(f"Key ...{key[-6:]} rate-limited for {cooldown_seconds}s. "
                                f"Available keys: {available}/{len(self._keys)}")
                    break

    def report_error(self, key: str):
        """Track a non-rate-limit error for a key."""
        with self._lock:
            for ks in self._keys:
                if ks.key == key:
                    ks.error_count += 1
                    break

    def get_stats(self) -> dict:
        """Get usage statistics for all keys."""
        now = time.time()
        return {
            "total_keys": len(self._keys),
            "available_keys": sum(1 for ks in self._keys if ks.cooldown_until <= now),
            "cooled_down_keys": sum(1 for ks in self._keys if ks.cooldown_until > now),
            "total_requests": sum(ks.request_count for ks in self._keys),
            "total_errors": sum(ks.error_count for ks in self._keys),
        }


# Global singleton instance
_manager: TavilyKeyManager | None = None


def get_tavily_manager() -> TavilyKeyManager:
    """Get or create the global TavilyKeyManager singleton."""
    global _manager
    if _manager is None:
        _manager = TavilyKeyManager()
    return _manager

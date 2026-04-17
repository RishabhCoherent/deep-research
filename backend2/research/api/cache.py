"""Caching utilities for prompt caching and response caching."""

from typing import Dict, Any, Optional
import hashlib
import json
from pathlib import Path
import tempfile


def cache_control_for_system():
    """Return cache control configuration for system prompts."""
    return {
        "type": "ephemeral",
        "ttl": 300  # 5 minutes
    }


def get_cache_key(query: str, extra_params: Optional[Dict[str, Any]] = None) -> str:
    """Generate cache key for search queries."""
    cache_data = {"query": query}
    if extra_params:
        cache_data.update(extra_params)
    
    cache_str = json.dumps(cache_data, sort_keys=True)
    return hashlib.sha256(cache_str.encode()).hexdigest()


def get_cache_dir() -> Path:
    """Get cache directory path."""
    cache_dir = Path.home() / ".research" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_tavily_cache_dir() -> Path:
    """Get Tavily-specific cache directory."""
    cache_dir = get_cache_dir() / "tavily"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

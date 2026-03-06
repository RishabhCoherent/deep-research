"""Quick test for source_classifier — verifies caching and classification logic."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.source_classifier import (
    _extract_domain, _get_cached, _domain_cache,
    _KNOWN_PRIMARY_DOMAINS, classify_sources, get_cache_stats,
)
from tools.citation import BANNED_DOMAINS


def test_domain_extraction():
    """Test _extract_domain works correctly."""
    assert _extract_domain("https://www.reuters.com/article/foo") == "reuters.com"
    assert _extract_domain("https://grandviewresearch.com/report/123") == "grandviewresearch.com"
    assert _extract_domain("https://sec.gov/cgi-bin/browse-edgar") == "sec.gov"
    assert _extract_domain("") == ""
    print("  [PASS] Domain extraction")


def test_known_primary_domains():
    """Known primary domains should be cached as primary without LLM call."""
    # Clear cache for this test
    _domain_cache.clear()

    assert _get_cached("reuters.com") == "primary"
    assert _get_cached("sec.gov") == "primary"
    assert _get_cached("nature.com") == "primary"
    assert _get_cached("wikipedia.org") == "primary"
    print("  [PASS] Known primary domains")


def test_banned_domains_cached_as_competitor():
    """Hardcoded banned domains should be cached as competitor."""
    _domain_cache.clear()

    # These should be in BANNED_DOMAINS
    for domain in ["grandviewresearch.com", "mordorintelligence.com", "marketsandmarkets.com"]:
        if any(domain in b or b in domain for b in BANNED_DOMAINS):
            result = _get_cached(domain)
            assert result == "competitor", f"Expected {domain} to be competitor, got {result}"
    print("  [PASS] Banned domains cached as competitor")


def test_unknown_domain_returns_none():
    """Unknown domains should return None (need LLM classification)."""
    _domain_cache.clear()

    assert _get_cached("somerandomblog.com") is None
    assert _get_cached("newresearchfirm.io") is None
    print("  [PASS] Unknown domains return None")


def test_cache_stats():
    """Cache stats should reflect cached entries."""
    _domain_cache.clear()

    # Cache a few
    _get_cached("reuters.com")
    _get_cached("sec.gov")

    # Force-add a competitor
    for domain in BANNED_DOMAINS:
        if "grandview" in domain:
            _get_cached("grandviewresearch.com")
            break

    stats = get_cache_stats()
    assert stats["total_cached"] >= 2
    assert stats["primary"] >= 2
    print(f"  [PASS] Cache stats: {stats}")


def test_classify_sources_all_cached():
    """When all sources are cached, classify_sources should not need LLM."""
    _domain_cache.clear()

    results = [
        {"url": "https://www.reuters.com/article/test", "title": "Reuters Article"},
        {"url": "https://sec.gov/filing/123", "title": "SEC Filing"},
    ]

    classifications = asyncio.run(classify_sources(results))
    assert classifications["https://www.reuters.com/article/test"] == "primary"
    assert classifications["https://sec.gov/filing/123"] == "primary"
    print("  [PASS] All-cached classification (no LLM call)")


if __name__ == "__main__":
    print("Testing source_classifier.py...\n")

    test_domain_extraction()
    test_known_primary_domains()
    test_banned_domains_cached_as_competitor()
    test_unknown_domain_returns_none()
    test_cache_stats()
    test_classify_sources_all_cached()

    print("\nAll tests passed!")

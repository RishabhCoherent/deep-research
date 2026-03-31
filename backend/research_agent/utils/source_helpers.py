"""Source-related helpers — tier labels, publisher inference."""

from __future__ import annotations

from urllib.parse import urlparse

TIER_LABELS = {1: "[T1 GOLD]", 2: "[T2 RELIABLE]", 3: "[T3]"}
TIER_LABELS_SHORT = {1: "T1", 2: "T2", 3: "T3"}


def format_tier(tier: int, short: bool = False) -> str:
    """Format source tier as a display label."""
    labels = TIER_LABELS_SHORT if short else TIER_LABELS
    return labels.get(tier, "[T3]")


def infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Unknown"
    except Exception:
        return "Unknown"

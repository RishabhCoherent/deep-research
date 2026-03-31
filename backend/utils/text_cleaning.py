"""Text cleaning, LLM response handling, source helpers, and competitor scrubbing."""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urlparse

from tools.citation import check_text_for_banned_citations

logger = logging.getLogger(__name__)


# ── LLM response extraction ──────────────────────────────────────────────────


def get_content(response) -> str:
    """Safely extract string content from an LLM response.

    Some models return response.content as a list of content blocks
    (dicts with 'text' keys) instead of a plain string.
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", str(block)))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def strip_preamble(draft: str) -> str:
    """Remove any meta-commentary before the first ## heading."""
    lines = draft.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("# "):
            stripped = "\n".join(lines[i:]).strip()
            if stripped != draft.strip():
                logger.info(f"[Output] Stripped {i} lines of preamble before first heading")
            return stripped
    return draft


# ── Source helpers ────────────────────────────────────────────────────────────


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


# ── Date helpers ──────────────────────────────────────────────────────────────


def date_vars() -> dict:
    """Return common date template variables."""
    today = date.today()
    return {
        "current_date": today.strftime("%B %d, %Y"),
        "current_year": str(today.year),
        "last_year": str(today.year - 1),
        "next_year": str(today.year + 1),
    }


# ── Competitor scrubbing ──────────────────────────────────────────────────────


_COMPETITOR_PHRASES = [
    "according to marketsandmarkets", "according to markets and markets",
    "according to mordor intelligence", "according to grand view research",
    "according to fortune business insights", "according to allied market research",
    "according to emergen research", "according to precedence research",
    "according to transparency market research", "according to frost & sullivan",
    "according to technavio", "according to euromonitor", "according to mintel",
    "according to statista", "according to imarc", "according to gartner",
    "according to idc", "according to verified market research",
    "according to future market insights", "according to expert market research",
    "according to ken research", "according to p&s intelligence",
    "according to fact.mr", "according to persistence market research",
    "according to straits research", "according to coherent market insights",
    "according to data bridge", "according to polaris market research",
    "according to skyquest", "according to astute analytica",
    "a report by marketsandmarkets", "a report by mordor intelligence",
    "a report by grand view research", "a study by marketsandmarkets",
    "marketsandmarkets estimates", "mordor intelligence estimates",
    "grand view research estimates", "marketsandmarkets projects",
    "mordor intelligence projects", "grand view research projects",
    "marketsandmarkets report", "mordor intelligence report",
    "grand view research report", "fortune business insights report",
]


def _scrub_competitor_mentions(draft: str) -> str:
    """Remove sentences that attribute data to competitor research firms."""
    lines = draft.split("\n")
    cleaned_lines = []

    for line in lines:
        line_lower = line.lower()
        has_competitor = False
        for phrase in _COMPETITOR_PHRASES:
            if phrase in line_lower:
                has_competitor = True
                logger.info(f"[Scrub] Removed competitor mention: '{phrase}' in line")
                break

        if has_competitor:
            sentences = re.split(r'(?<=[.!?])\s+', line)
            clean_sentences = []
            for sent in sentences:
                sent_lower = sent.lower()
                if not any(p in sent_lower for p in _COMPETITOR_PHRASES):
                    clean_sentences.append(sent)
            if clean_sentences:
                cleaned_lines.append(" ".join(clean_sentences))
        else:
            cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)

    remaining = check_text_for_banned_citations(result)
    if remaining:
        logger.warning(f"[Scrub] Remaining competitor names in draft: {remaining}")

    return result

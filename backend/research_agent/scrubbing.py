"""
Competitor mention scrubbing — removes sentences attributing data to
competitor research firms from generated report text.
"""

from __future__ import annotations

import logging
import re

from tools.citation import check_text_for_banned_citations

logger = logging.getLogger(__name__)

# Phrases that identify competitor research firm attributions in report text.
# These are checked case-insensitively against the final draft.
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
    """Remove sentences that attribute data to competitor research firms.

    Uses two passes:
    1. Remove sentences containing known competitor attribution phrases
    2. Check for any remaining banned source names (log warning but don't break flow)
    """
    lines = draft.split("\n")
    cleaned_lines = []

    for line in lines:
        line_lower = line.lower()
        # Check if this line contains a competitor attribution
        has_competitor = False
        for phrase in _COMPETITOR_PHRASES:
            if phrase in line_lower:
                has_competitor = True
                logger.info(f"[Scrub] Removed competitor mention: '{phrase}' in line")
                break

        if has_competitor:
            # Try to remove just the offending sentence, not the whole line
            # Split by sentence boundaries and keep clean sentences
            sentences = re.split(r'(?<=[.!?])\s+', line)
            clean_sentences = []
            for sent in sentences:
                sent_lower = sent.lower()
                if not any(p in sent_lower for p in _COMPETITOR_PHRASES):
                    clean_sentences.append(sent)
            if clean_sentences:
                cleaned_lines.append(" ".join(clean_sentences))
            # else: entire line was competitor content, skip it
        else:
            cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)

    # Final check — log any remaining banned names (from citation.py's full list)
    remaining = check_text_for_banned_citations(result)
    if remaining:
        logger.warning(f"[Scrub] Remaining competitor names in draft: {remaining}")

    return result

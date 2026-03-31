"""Report outline generation and parsing utilities."""

from __future__ import annotations

import logging
import re

from utils.text_cleaning import get_content

logger = logging.getLogger(__name__)


async def generate_report_outline(topic: str, llm, brief: str = "") -> str:
    """Generate a shared report outline for all layers.

    First runs a quick web search to disambiguate the topic.
    Returns a plain-text outline or empty string on failure.
    """
    from prompts import REPORT_OUTLINE_PROMPT
    from utils.cost_tracker import track
    from tools.search import search

    try:
        topic_context = ""
        try:
            results = await search(topic, max_results=3, include_news=False)
            if results:
                snippets = []
                for r in results[:3]:
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    if title or snippet:
                        snippets.append(f"- {title}: {snippet[:150]}")
                if snippets:
                    topic_context = (
                        "\n\nWeb search context (use this to understand what this topic/market "
                        "actually refers to — do NOT confuse with similar-sounding markets):\n"
                        + "\n".join(snippets)
                    )
                    logger.info(f"[Outline] Topic context from {len(snippets)} search results")
        except Exception as e:
            logger.warning(f"[Outline] Topic disambiguation search failed: {e}")

        brief_context = ""
        if brief:
            brief_context = (
                "\n\nCLIENT BRIEF (use these instructions to guide section planning — "
                "adapt the report structure to match the client's requirements):\n\n"
                + brief
            )

        prompt_content = REPORT_OUTLINE_PROMPT.format(topic=topic) + topic_context + brief_context

        messages = [
            {"role": "system", "content": "You are a research planning expert. Follow the output format exactly."},
            {"role": "user", "content": prompt_content},
        ]
        response = await llm.ainvoke(messages)
        track("outline", response)
        content = get_content(response).strip()
        if "Sections:" in content and "Report type:" in content:
            logger.info(f"[Outline] Generated for: {topic[:60]}")
            return content
        logger.warning("[Outline] Unexpected format, skipping")
    except Exception as e:
        logger.warning(f"[Outline] Generation failed: {e}")
    return ""


def parse_outline_type(outline: str) -> str:
    """Extract report type from the outline text.

    Parses 'Report type: PEST Analysis' -> 'PEST Analysis'.
    """
    for line in outline.splitlines():
        m = re.match(r"Report\s+type:\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def parse_outline_sections(outline: str) -> list[str]:
    """Extract section names from the outline text.

    Parses lines like '1. Political Factors -- trade policy...' into ['Political Factors', ...].
    """
    sections = []
    for line in outline.splitlines():
        m = re.match(r"\d+\.\s+(.+?)(?:\s*[—–-]\s+.*)?$", line.strip())
        if m:
            sections.append(m.group(1).strip())
    return sections


def compute_depth_targets(
    section_count: int,
    total_claims: int,
) -> dict:
    """Compute word count targets based on topic complexity."""
    effective_sections = max(section_count + 3, int(section_count * 1.5))
    base_total = effective_sections * 500

    if total_claims > 30:
        claim_mult = 1.2
    elif total_claims > 15:
        claim_mult = 1.0
    else:
        claim_mult = 0.9

    target = int(base_total * claim_mult)
    target = max(2500, min(target, 6000))
    per_section = target // max(effective_sections, 1)

    return {
        "target_words": target,
        "per_section_words": per_section,
        "expand_threshold": int(target * 0.75),
        "editorial_min": int(target * 0.5),
    }

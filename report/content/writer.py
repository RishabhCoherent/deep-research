"""
LLM content writer — generates text using prompts + research context.

Uses config.get_llm() for OpenAI models.
"""

from __future__ import annotations
import logging
import re

from config import get_llm
from report.content.prompts import WRITER_SYSTEM, WRITER_MINI_SYSTEM
from tools.citation import check_text_for_banned_citations

logger = logging.getLogger(__name__)


async def write_section(
    user_prompt: str,
    role: str = "writer",
    system_prompt: str = WRITER_SYSTEM,
) -> str:
    """Generate content using LLM.

    Args:
        user_prompt: Formatted user prompt with data context.
        role: LLM role for config.get_llm() (writer, analyst, organizer).
        system_prompt: System prompt.

    Returns:
        Generated text content.
    """
    llm = get_llm(role)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = llm.invoke(messages)
        content = response.content

        # Check for banned sources in output
        banned = check_text_for_banned_citations(content)
        if banned:
            logger.warning(f"Banned sources detected in output: {banned}")
            # Remove mentions of banned sources
            for firm in banned:
                content = re.sub(
                    rf'\b{re.escape(firm)}\b',
                    'industry analysis',
                    content,
                    flags=re.IGNORECASE,
                )

        return content.strip()

    except Exception as e:
        logger.error(f"LLM write failed: {e}")
        return ""


async def write_light(user_prompt: str) -> str:
    """Generate content using the lighter model (gpt-4o-mini). For templates, appendix."""
    return await write_section(
        user_prompt,
        role="organizer",  # uses gpt-4o-mini
        system_prompt=WRITER_MINI_SYSTEM,
    )


async def compress_insights_for_sidebar(insights: list) -> list:
    """Compress data insight sentences to 80-90 chars each for sidebar display.

    Makes a single LLM call to rewrite all insights concisely while
    preserving key numbers. Falls back to originals on any failure.
    """
    if not insights:
        return insights

    numbered = "\n".join(f"{i + 1}. {ins}" for i, ins in enumerate(insights))
    prompt = (
        "Rewrite each market insight below as ONE concise sentence of 80-90 characters maximum. "
        "Keep the key numbers intact. Return ONLY the numbered list (1. ... 2. ... 3. ...), nothing else.\n\n"
        + numbered
    )

    try:
        result = await write_section(prompt, role="organizer", system_prompt=WRITER_MINI_SYSTEM)
        lines = []
        for line in result.strip().splitlines():
            line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            if line:
                lines.append(line)
        if len(lines) == len(insights):
            return lines
    except Exception as e:
        logger.warning(f"compress_insights_for_sidebar failed: {e}")

    return insights


async def write_batch(
    items: dict[str, str],
    role: str = "writer",
    system_prompt: str = WRITER_SYSTEM,
) -> dict[str, str]:
    """Write content for multiple items via a single LLM call.

    Args:
        items: {"item_name": "formatted_prompt"} — prompts for each item.
            For batch calls, the prompts should be combined into one.

    Returns:
        {"item_name": "generated_content"} — parsed from LLM response.
    """
    # For batch calls, we send one combined prompt
    if not items:
        return {}

    if len(items) == 1:
        name, prompt = next(iter(items.items()))
        result = await write_section(prompt, role, system_prompt)
        return {name: result}

    # Single combined prompt
    combined_prompt = "\n\n".join(
        f"=== {name} ===\n{prompt}" for name, prompt in items.items()
    )
    combined_prompt += "\n\nWrite content for ALL items above, separated by the === headers."

    result = await write_section(combined_prompt, role, system_prompt)

    # Parse response back into per-item sections
    parsed = _parse_batch_response(result, list(items.keys()))
    return parsed


def _parse_batch_response(text: str, item_names: list[str]) -> dict[str, str]:
    """Parse a batch LLM response into per-item sections.

    Looks for ### headers or === markers to split content.
    """
    result = {}

    # Try splitting by ### headers matching item names
    for i, name in enumerate(item_names):
        # Find section for this item
        pattern = rf'###?\s*{re.escape(name)}(.*?)(?=###?\s*(?:{"|".join(re.escape(n) for n in item_names[i+1:])})|$)'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            result[name] = match.group(1).strip()

    # Fallback: split by === markers
    if not result:
        parts = re.split(r'===\s*.*?\s*===', text)
        for i, name in enumerate(item_names):
            if i + 1 < len(parts):
                result[name] = parts[i + 1].strip()

    # Fallback: split evenly
    if not result and text:
        chunk_size = len(text) // max(len(item_names), 1)
        for i, name in enumerate(item_names):
            start = i * chunk_size
            end = start + chunk_size if i < len(item_names) - 1 else len(text)
            result[name] = text[start:end].strip()

    return result

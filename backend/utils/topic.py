"""Topic interpretation and scope generation utilities."""

from __future__ import annotations

import logging

from utils.text_cleaning import get_content

logger = logging.getLogger(__name__)


async def interpret_topic(topic: str, llm, brief: str = "") -> str:
    """Disambiguate an ambiguous or colloquial user topic before research begins.

    Uses a web search + LLM call to understand what the user actually means,
    then returns a clarified topic string. Returns the original topic on failure.
    """
    from prompts import TOPIC_INTERPRETATION_PROMPT
    from utils.cost_tracker import track
    from tools.search import search

    try:
        search_context = ""
        try:
            results = await search(topic, max_results=5, include_news=False)
            if results:
                snippets = []
                for r in results[:5]:
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    if title or snippet:
                        snippets.append(f"- {title}: {snippet[:150]}")
                if snippets:
                    search_context = (
                        "\n\nWeb search results for the raw topic:\n"
                        + "\n".join(snippets)
                    )
        except Exception as e:
            logger.warning(f"[Interpret] Topic search failed: {e}")

        brief_section = ""
        if brief:
            brief_section = f"\n\nCLIENT'S ADDITIONAL BRIEF:\n{brief}"

        search_section = ""
        if search_context:
            search_section = f"\n\nWEB SEARCH CONTEXT:{search_context}"

        prompt_content = TOPIC_INTERPRETATION_PROMPT.format(
            topic=topic,
            brief_section=brief_section,
            search_context=search_section,
        )

        messages = [
            {"role": "system", "content": (
                "You are a research brief interpreter. Read the client's topic carefully, "
                "consider what they actually mean, and output ONLY in the exact format requested."
            )},
            {"role": "user", "content": prompt_content},
        ]
        response = await llm.ainvoke(messages)
        track("interpret", response)
        content = get_content(response).strip()

        clarified = ""
        changed = False
        interpretation = ""
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.startswith("CLARIFIED_TOPIC:"):
                clarified = line_s.split(":", 1)[1].strip()
            elif line_s.startswith("TOPIC_CHANGED:"):
                changed = "YES" in line_s.upper()
            elif line_s.startswith("INTERPRETATION:"):
                interpretation = line_s.split(":", 1)[1].strip()

        if clarified and changed:
            logger.info(
                f"[Interpret] Topic reinterpreted: '{topic}' -> '{clarified}' "
                f"(reason: {interpretation[:100]})"
            )
            return clarified
        else:
            logger.info(f"[Interpret] Topic confirmed as clear: '{topic}'")
            return topic

    except Exception as e:
        logger.warning(f"[Interpret] Topic interpretation failed (non-fatal): {e}")
    return topic


async def generate_topic_scope(topic: str, llm) -> str:
    """Auto-generate scope boundaries for a research topic.

    Returns a multi-line scope string, or empty string on failure.
    """
    from prompts import SCOPE_DEFINITION_PROMPT
    from utils.cost_tracker import track
    from tools.search import search

    try:
        search_context = ""
        try:
            results = await search(topic, max_results=5, include_news=False)
            if results:
                snippets = []
                for r in results[:5]:
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    if title or snippet:
                        snippets.append(f"- {title}: {snippet[:150]}")
                if snippets:
                    search_context = (
                        "\n\nWeb search context:\n" + "\n".join(snippets)
                    )
        except Exception as e:
            logger.warning(f"[Scope] Topic search failed: {e}")

        prompt_content = SCOPE_DEFINITION_PROMPT.format(topic=topic) + search_context

        messages = [
            {"role": "system", "content": (
                "You are a scope-definition expert. Output ONLY the scope "
                "definition in the exact format requested. Be specific and "
                "practical — name real adjacent products/markets to exclude."
            )},
            {"role": "user", "content": prompt_content},
        ]
        response = await llm.ainvoke(messages)
        track("scope", response)
        content = get_content(response).strip()

        if "IN-SCOPE" in content and "OUT-OF-SCOPE" in content:
            logger.info(f"[Scope] Generated for: {topic[:60]}")
            return content
        logger.warning("[Scope] Unexpected format, skipping")
    except Exception as e:
        logger.warning(f"[Scope] Generation failed: {e}")
    return ""

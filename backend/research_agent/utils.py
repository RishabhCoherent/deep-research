"""
Shared utilities for the research agent pipeline.

- get_content: safe LLM response text extraction
- extract_json / extract_json_scores: robust JSON parsing from LLM output
- strip_preamble: remove meta-commentary before first heading
- infer_publisher: extract publisher name from URL
- generate_report_outline: shared outline generation for all layers
- parse_outline_sections / parse_outline_type: outline text parsing
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


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


def extract_json(text: str):
    """Robustly extract JSON (object or array) from LLM output.

    Tries multiple strategies in order:
    1. Direct parse
    2. Extract from markdown code block
    3. Brace/bracket matching for outermost JSON structure
    4. Fix trailing commas and retry
    """
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown code block
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: find outermost JSON structure with bracket matching
    # Try both { } (object) and [ ] (array)
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        first = text.find(open_ch)
        if first == -1:
            continue

        depth = 0
        in_string = False
        escape_next = False
        last = -1

        for i in range(first, len(text)):
            ch = text[i]

            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    last = i
                    break

        if last != -1:
            candidate = text[first:last + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # Strategy 4: fix trailing commas
                fixed = re.sub(r",\s*([\]}])", r"\1", candidate)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

    logger.debug(f"All JSON extraction strategies failed for: {text[:200]}...")
    return None


def extract_json_scores(text: str) -> dict:
    """Extract evaluation scores specifically -- falls back to regex per-field extraction.

    Returns a dict like {"factual_density": {"score": 7, "justification": "..."}, ...}
    """
    result = extract_json(text)
    if isinstance(result, dict) and result:
        return result

    # Regex fallback for score objects
    dims = ["factual_density", "source_grounding", "analytical_depth",
            "specificity", "insight_quality", "completeness"]
    scores = {}
    for dim in dims:
        # Pattern: "dim_name": {"score": N, "justification": "..."}
        pattern = rf'"{dim}"\s*:\s*\{{\s*"score"\s*:\s*(\d+)\s*,\s*"justification"\s*:\s*"([^"]*)"'
        m = re.search(pattern, text)
        if m:
            scores[dim] = {"score": int(m.group(1)), "justification": m.group(2)}
        else:
            # Simpler: just grab the score near the dimension name
            m2 = re.search(rf'"{dim}"[^{{]*?"score"\s*:\s*(\d+)', text, re.DOTALL)
            if m2:
                scores[dim] = {"score": int(m2.group(1)), "justification": ""}

    if scores:
        logger.info(f"[extract_json_scores] Recovered {len(scores)}/6 scores via regex fallback")
    return scores


def strip_preamble(draft: str) -> str:
    """Remove any meta-commentary before the first ## heading.

    The agent sometimes produces preamble like:
      "I can't run more queries. Below is an improved PEST that retains..."
      "Here is the final report:"
      "Budget exhausted. Writing report now."

    All legitimate report content starts with a ## heading. Any text before
    the first ## is meta-commentary and must be stripped.
    """
    lines = draft.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("# "):
            stripped = "\n".join(lines[i:]).strip()
            if stripped != draft.strip():
                logger.info(f"[Output] Stripped {i} lines of preamble before first heading")
            return stripped
    # No ## heading found — return as-is (let evaluator penalise it)
    return draft


def infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Unknown"
    except Exception:
        return "Unknown"


# ─── Topic interpretation ────────────────────────────────────────────────────


async def interpret_topic(topic: str, llm, brief: str = "") -> str:
    """Disambiguate an ambiguous or colloquial user topic before research begins.

    Uses a web search + LLM call to understand what the user actually means,
    then returns a clarified topic string. Returns the original topic on failure.
    """
    from research_agent.prompts import TOPIC_INTERPRETATION_PROMPT
    from research_agent.cost import track
    from tools.search import search

    try:
        # Web search for context on the raw topic
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

        # Parse the response
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
                f"[Interpret] Topic reinterpreted: '{topic}' → '{clarified}' "
                f"(reason: {interpretation[:100]})"
            )
            return clarified
        elif clarified:
            logger.info(f"[Interpret] Topic confirmed as clear: '{topic}'")
            return clarified

        logger.warning("[Interpret] Could not parse response, using original topic")
    except Exception as e:
        logger.warning(f"[Interpret] Topic interpretation failed (non-fatal): {e}")
    return topic


# ─── Topic scope definition ──────────────────────────────────────────────────


async def generate_topic_scope(topic: str, llm) -> str:
    """Auto-generate scope boundaries for a research topic.

    Uses a cheap LLM call + web search to produce IN-SCOPE / OUT-OF-SCOPE
    boundaries that prevent scope drift (e.g., "whiskey cask market" drifting
    into whiskey brands/bottles).

    Returns a multi-line scope string, or empty string on failure.
    """
    from research_agent.prompts import SCOPE_DEFINITION_PROMPT
    from research_agent.cost import track
    from tools.search import search

    try:
        # Quick web search for topic context
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

        # Validate: must contain both IN-SCOPE and OUT-OF-SCOPE
        if "IN-SCOPE" in content and "OUT-OF-SCOPE" in content:
            logger.info(f"[Scope] Generated for: {topic[:60]}")
            return content
        logger.warning("[Scope] Unexpected format, skipping")
    except Exception as e:
        logger.warning(f"[Scope] Generation failed: {e}")
    return ""


# ─── Report outline utilities ─────────────────────────────────────────────────


async def generate_report_outline(topic: str, llm, brief: str = "") -> str:
    """Generate a shared report outline for all layers.

    First runs a quick web search to disambiguate the topic — this ensures the
    LLM understands niche/ambiguous topics before generating the outline.

    Returns a plain-text outline like:
      Report type: PEST Analysis
      Sections:
      1. Political Factors — trade policy, regulation, geopolitical risk
      2. Economic Factors — macro conditions, consumer spending, input costs
      ...

    Returns empty string on failure.
    """
    from research_agent.prompts import REPORT_OUTLINE_PROMPT
    from research_agent.cost import track
    from tools.search import search

    try:
        # Quick web search to disambiguate the topic before planning
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

    Parses 'Report type: PEST Analysis' → 'PEST Analysis'.
    Returns empty string if not found.
    """
    for line in outline.splitlines():
        m = re.match(r"Report\s+type:\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def parse_outline_sections(outline: str) -> list[str]:
    """Extract section names from the outline text.

    Parses lines like '1. Political Factors — trade policy...' into ['Political Factors', ...].
    """
    sections = []
    for line in outline.splitlines():
        m = re.match(r"\d+\.\s+(.+?)(?:\s*[—–-]\s+.*)?$", line.strip())
        if m:
            sections.append(m.group(1).strip())
    return sections

"""
Shared utilities for the research agent pipeline.

- get_content: safe LLM response text extraction
- extract_json / extract_json_scores: robust JSON parsing from LLM output
- strip_preamble: remove meta-commentary before first heading
- infer_publisher: extract publisher name from URL
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

"""
Shared utilities for the multi-layer research agent.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


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

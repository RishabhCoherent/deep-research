"""
Layer 0 — Baseline: Single LLM prompt, no research.

This is the control group. It shows what the LLM can produce purely from
its parametric knowledge, without any web research or multi-step processing.
An experienced researcher would never do this — it's the "just ask ChatGPT" approach.
"""

from __future__ import annotations

import logging
import time

from config import get_llm, get_model_tier
from research_agent.types import ResearchResult
from research_agent.prompts import LAYER0_SYSTEM, LAYER0_USER
from research_agent.cost import track

logger = logging.getLogger(__name__)


async def run(topic: str) -> ResearchResult:
    """Generate a baseline analysis using a single LLM call."""
    logger.info(f"[Layer 0] Baseline generation for: {topic}")
    start = time.time()

    llm = get_llm("writer")

    messages = [
        {"role": "system", "content": LAYER0_SYSTEM},
        {"role": "user", "content": LAYER0_USER.format(topic=topic)},
    ]

    try:
        response = llm.invoke(messages)
        track("L0 baseline", response)
        content = response.content.strip()
    except Exception as e:
        logger.error(f"[Layer 0] LLM call failed: {e}")
        content = f"Error: {e}"

    elapsed = time.time() - start
    logger.info(f"[Layer 0] Done in {elapsed:.1f}s — {len(content.split())} words")

    return ResearchResult(
        layer=0,
        topic=topic,
        content=content,
        sources=[],
        metadata={"method": "single_prompt", "tier": get_model_tier()},
        elapsed_seconds=elapsed,
    )

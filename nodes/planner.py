"""
Research Planner node.

Takes the market topic and generates a structured research plan:
11 sub-section configs, each with tailored search queries.
"""

import json
import logging

from config import get_llm, SUBSECTIONS
from prompts.planner import PLANNER_SYSTEM, PLANNER_USER
from state import PipelineState

logger = logging.getLogger(__name__)


def planner_node(state: PipelineState) -> dict:
    """Generate sub-section configs with targeted search queries."""
    logger.info(f"Planning research for: {state['topic']}")

    llm = get_llm("planner")

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": PLANNER_USER.format(
            topic=state["topic"],
            report_context=state.get("report_context", ""),
        )},
    ]

    response = llm.invoke(messages)
    content = response.content

    # Parse JSON from response (handle markdown code blocks)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    try:
        subsection_configs = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.warning("Failed to parse planner response as JSON, using defaults")
        # Fallback: use default configs with generic queries
        subsection_configs = []
        for s in SUBSECTIONS:
            subsection_configs.append({
                "id": s["id"],
                "name": s["name"],
                "description": f"{s['name']} analysis for {state['topic']}",
                "query_hints": [
                    f"{state['topic']} {s['name'].lower()} 2024 2025",
                    f"{state['topic']} {s['name'].lower()} analysis",
                    f"{state['topic']} {s['name'].lower()} Reuters Bloomberg",
                    f"{state['topic']} market {s['name'].lower()} site:sec.gov OR site:fda.gov",
                ],
            })

    logger.info(f"Planned {len(subsection_configs)} sub-sections")
    return {
        "subsection_configs": subsection_configs,
        "status": "researching",
    }

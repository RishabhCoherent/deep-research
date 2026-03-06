"""
Analyst node.

Takes organized data and enriches it with analytical insights:
key findings, impact assessments, pattern identification.
"""

import json
import logging

from config import get_llm
from prompts.analyst import ANALYST_SYSTEM, ANALYST_PROMPTS, DEFAULT_ANALYST_PROMPT
from state import SubSectionWorkerState

logger = logging.getLogger(__name__)


def analyst_node(state: SubSectionWorkerState) -> dict:
    """Analyze organized data and add strategic insights."""
    subsection_id = state["subsection_id"]
    subsection_name = state["subsection_name"]
    organized_data = state.get("organized_data", {})

    logger.info(f"Analyzing: {subsection_name}")

    llm = get_llm("analyst")

    # Select the appropriate prompt template
    prompt_template = ANALYST_PROMPTS.get(subsection_id, DEFAULT_ANALYST_PROMPT)

    # Format organized data as readable string
    data_str = json.dumps(organized_data, indent=2, default=str)

    prompt = prompt_template.format(
        topic=state["topic"],
        subsection_name=subsection_name,
        organized_data=data_str,
    )

    messages = [
        {"role": "system", "content": ANALYST_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    response = llm.invoke(messages)
    content = response.content

    # Parse JSON
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    try:
        analysis = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse analyst response for {subsection_id}, using raw text")
        analysis = {
            "key_findings": [content[:500]],
            "analysis_notes": content,
        }

    # Enrich the organized data with analyst insights
    updated_data = dict(organized_data)
    updated_data["key_findings"] = analysis.get("key_findings", [])
    updated_data["analysis_notes"] = analysis.get("analysis_notes", "")

    logger.info(f"Analysis complete for {subsection_name}: {len(updated_data['key_findings'])} findings")

    return {"organized_data": updated_data}

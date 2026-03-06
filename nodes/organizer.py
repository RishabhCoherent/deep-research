"""
Data Organizer node.

Takes raw search results and citations for a sub-section,
organizes them into a structured SubSectionData ready for the writer.
"""

import json
import logging

from config import get_llm
from prompts.organizer import ORGANIZER_SYSTEM, ORGANIZER_PROMPT
from state import SubSectionWorkerState

logger = logging.getLogger(__name__)


def organizer_node(state: SubSectionWorkerState) -> dict:
    """Organize raw research data into structured format."""
    subsection_id = state["subsection_id"]
    subsection_name = state["subsection_name"]
    logger.info(f"Organizing data for: {subsection_name}")

    llm = get_llm("organizer")
    citations = state.get("citations", [])
    search_results = state.get("search_results", [])

    # Build raw data string from all collected data
    raw_data_parts = []
    for sr in search_results:
        if isinstance(sr, dict):
            raw_data_parts.append(f"- [{sr.get('source', 'web')}] {sr.get('title', '')}: {sr.get('snippet', '')}")

    # Build citation reference table
    citation_table_parts = []
    for c in citations:
        if isinstance(c, dict):
            citation_table_parts.append(
                f"{c.get('id', '?')}: {c.get('title', 'Unknown')} ({c.get('publisher', 'Unknown')}, {c.get('date', 'n.d.')}) - {c.get('url', '')}"
            )

    raw_data = "\n".join(raw_data_parts) if raw_data_parts else "No raw data collected."
    citation_table = "\n".join(citation_table_parts) if citation_table_parts else "No citations available."

    messages = [
        {"role": "system", "content": ORGANIZER_SYSTEM},
        {"role": "user", "content": ORGANIZER_PROMPT.format(
            subsection_name=subsection_name,
            topic=state["topic"],
            subsection_id=subsection_id,
            raw_data=raw_data,
            citation_table=citation_table,
        )},
    ]

    response = llm.invoke(messages)
    content = response.content

    # Parse JSON
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    try:
        organized = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse organizer response for {subsection_id}, using fallback")
        organized = {
            "subsection_id": subsection_id,
            "subsection_name": subsection_name,
            "raw_facts": [sr.get("snippet", "") for sr in search_results if isinstance(sr, dict)][:10],
            "statistics": [],
            "company_actions": [],
            "regulatory_info": [],
            "citation_ids": [c.get("id", "") for c in citations if isinstance(c, dict)],
        }

    # Ensure required fields exist
    organized.setdefault("subsection_id", subsection_id)
    organized.setdefault("subsection_name", subsection_name)
    organized.setdefault("raw_facts", [])
    organized.setdefault("statistics", [])
    organized.setdefault("company_actions", [])
    organized.setdefault("regulatory_info", [])
    organized.setdefault("citation_ids", [])
    organized.setdefault("analysis_notes", "")
    organized.setdefault("key_findings", [])

    logger.info(f"Organized {subsection_name}: {len(organized['raw_facts'])} facts, "
                f"{len(organized['statistics'])} stats, {len(organized['citation_ids'])} citations")

    return {"organized_data": organized}

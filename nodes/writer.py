"""
Section Writer node.

Takes organized + analyzed data and writes publication-quality prose
with inline citations using sub-section-specific templates.
"""

import json
import logging

from config import get_llm
from prompts.writer import WRITER_SYSTEM, WRITER_TEMPLATES, DEFAULT_WRITER_TEMPLATE
from state import SubSectionWorkerState

logger = logging.getLogger(__name__)


def _build_citation_table(citations: list[dict]) -> str:
    """Build a readable citation reference table for the writer."""
    lines = []
    for c in citations:
        if isinstance(c, dict):
            lines.append(
                f"{c.get('id', '?')}: {c.get('title', 'Unknown')} "
                f"({c.get('publisher', 'Unknown')}, {c.get('date', 'n.d.')}) — {c.get('url', '')}"
            )
    return "\n".join(lines) if lines else "No citations available."


def _format_list(items: list, default: str = "No data available.") -> str:
    """Format a list of items as bullet points."""
    if not items:
        return default
    return "\n".join(f"- {item}" for item in items)


def writer_node(state: SubSectionWorkerState) -> dict:
    """Write one sub-section using organized data and citations."""
    subsection_id = state["subsection_id"]
    subsection_name = state["subsection_name"]
    organized_data = state.get("organized_data", {})
    citations = state.get("citations", [])
    review_feedback = state.get("review_feedback")

    logger.info(f"Writing: {subsection_name}")

    llm = get_llm("writer")

    # Build template variables
    facts = _format_list(organized_data.get("raw_facts", []))
    statistics = _format_list(organized_data.get("statistics", []))
    company_actions = _format_list(organized_data.get("company_actions", []))
    regulatory_info = _format_list(organized_data.get("regulatory_info", []))
    key_findings = _format_list(organized_data.get("key_findings", []))
    analysis_notes = organized_data.get("analysis_notes", "No analysis available.")
    citation_table = _build_citation_table(citations)

    # Select template
    template = WRITER_TEMPLATES.get(subsection_id, DEFAULT_WRITER_TEMPLATE)

    user_prompt = template.format(
        topic=state["topic"],
        subsection_name=subsection_name,
        facts=facts,
        statistics=statistics,
        company_actions=company_actions,
        regulatory_info=regulatory_info,
        key_findings=key_findings,
        analysis_notes=analysis_notes,
        citation_table=citation_table,
    )

    # If this is a rewrite, include the review feedback
    if review_feedback and isinstance(review_feedback, dict) and not review_feedback.get("passed", True):
        feedback_text = "\n\n## REVIEWER FEEDBACK (address these issues):\n"
        for issue in review_feedback.get("issues", []):
            feedback_text += f"- {issue}\n"
        for issue in review_feedback.get("citation_issues", []):
            feedback_text += f"- CITATION: {issue}\n"
        for suggestion in review_feedback.get("suggestions", []):
            feedback_text += f"- SUGGESTION: {suggestion}\n"
        user_prompt += feedback_text

    messages = [
        {"role": "system", "content": WRITER_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    response = llm.invoke(messages)
    content = response.content

    # Extract citation IDs used in the text
    import re
    citation_ids_used = list(set(re.findall(r'\[src_[a-z]{3}_\d{3}\]', content)))
    citation_ids_used = [cid.strip("[]") for cid in citation_ids_used]

    # Extract tables (markdown tables)
    tables = []
    lines = content.split("\n")
    table_lines = []
    in_table = False
    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
        elif in_table:
            if table_lines:
                tables.append("\n".join(table_lines))
                table_lines = []
            in_table = False
    if table_lines:
        tables.append("\n".join(table_lines))

    word_count = len(content.split())

    written_section = {
        "subsection_id": subsection_id,
        "subsection_name": subsection_name,
        "content": content,
        "tables": tables,
        "citation_ids_used": citation_ids_used,
        "word_count": word_count,
    }

    logger.info(f"Written {subsection_name}: {word_count} words, {len(citation_ids_used)} citations used")

    return {"written_section": written_section}

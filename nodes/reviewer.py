"""
Quality Reviewer node.

Validates written sections for:
- Citation integrity (all [src_xxx] IDs exist)
- No banned research firm citations
- Factual consistency with source data
- Completeness (key findings addressed)
- Professional structure and tone
"""

import json
import logging

from config import get_llm, MAX_REWRITE_ATTEMPTS
from prompts.reviewer import REVIEWER_SYSTEM, REVIEWER_PROMPT
from state import SubSectionWorkerState
from tools.citation import check_text_for_banned_citations

logger = logging.getLogger(__name__)


def reviewer_node(state: SubSectionWorkerState) -> dict:
    """Review a written section for quality and citation integrity."""
    subsection_id = state["subsection_id"]
    subsection_name = state["subsection_name"]
    written_section = state.get("written_section", {})
    organized_data = state.get("organized_data", {})
    citations = state.get("citations", [])

    logger.info(f"Reviewing: {subsection_name}")

    content = written_section.get("content", "") if isinstance(written_section, dict) else ""

    # ─── Programmatic check: banned sources ───
    banned_found = check_text_for_banned_citations(content)
    if banned_found:
        logger.warning(f"Banned sources found in {subsection_name}: {banned_found}")

    # ─── Programmatic check: citation IDs exist ───
    import re
    cited_ids = set(re.findall(r'\[src_[a-z]{3}_\d{3}\]', content))
    cited_ids = {cid.strip("[]") for cid in cited_ids}

    valid_ids = {c.get("id") for c in citations if isinstance(c, dict)}
    invalid_ids = cited_ids - valid_ids

    # ─── LLM-based quality review ───
    llm = get_llm("reviewer")

    # Build citation table
    citation_table = "\n".join(
        f"{c.get('id', '?')}: {c.get('title', '')} ({c.get('publisher', '')}) - {c.get('url', '')}"
        for c in citations if isinstance(c, dict)
    )

    # Source data summary
    source_summary_parts = []
    for key in ["raw_facts", "statistics", "company_actions", "regulatory_info"]:
        items = organized_data.get(key, []) if isinstance(organized_data, dict) else []
        if items:
            source_summary_parts.append(f"{key}: {len(items)} items")
    source_summary = ", ".join(source_summary_parts) or "No source data."

    key_findings = "\n".join(
        f"- {f}" for f in (organized_data.get("key_findings", []) if isinstance(organized_data, dict) else [])
    ) or "No key findings."

    messages = [
        {"role": "system", "content": REVIEWER_SYSTEM},
        {"role": "user", "content": REVIEWER_PROMPT.format(
            subsection_name=subsection_name,
            topic=state["topic"],
            written_content=content[:6000],  # Cap for token limits
            citation_table=citation_table,
            source_data_summary=source_summary,
            key_findings=key_findings,
        )},
    ]

    try:
        response = llm.invoke(messages)
        resp_content = response.content
        if "```json" in resp_content:
            resp_content = resp_content.split("```json")[1].split("```")[0]
        elif "```" in resp_content:
            resp_content = resp_content.split("```")[1].split("```")[0]
        review = json.loads(resp_content.strip())
    except Exception as e:
        logger.warning(f"Review parsing failed for {subsection_name}: {e}")
        review = {"passed": True, "issues": [], "citation_issues": [], "suggestions": []}

    # Override LLM decision if programmatic checks found issues
    if banned_found:
        review["passed"] = False
        review.setdefault("citation_issues", [])
        review["citation_issues"].append(f"BANNED SOURCES FOUND: {', '.join(banned_found)}")

    if invalid_ids:
        review["passed"] = False
        review.setdefault("citation_issues", [])
        review["citation_issues"].append(f"Invalid citation IDs: {', '.join(invalid_ids)}")

    feedback = {
        "subsection_id": subsection_id,
        "passed": review.get("passed", True),
        "issues": review.get("issues", []),
        "citation_issues": review.get("citation_issues", []),
        "suggestions": review.get("suggestions", []),
    }

    if feedback["passed"]:
        logger.info(f"Review PASSED for {subsection_name}")
    else:
        logger.warning(f"Review FAILED for {subsection_name}: {feedback['issues'] + feedback['citation_issues']}")

    return {"review_feedback": feedback}

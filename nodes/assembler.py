"""
Assembler node.

Combines all completed sub-sections into the final Section 3 markdown
with a formatted bibliography.
"""

import logging

from config import SUBSECTION_ORDER
from state import PipelineState

logger = logging.getLogger(__name__)


def assembler_node(state: PipelineState) -> dict:
    """Combine all completed sub-sections into final Section 3 output."""
    sections = state.get("completed_sections", [])
    all_citations = state.get("all_citations", [])

    logger.info(f"Assembling {len(sections)} sub-sections with {len(all_citations)} total citations")

    # Sort sections by canonical order
    def sort_key(s):
        sid = s.get("subsection_id", "") if isinstance(s, dict) else ""
        try:
            return SUBSECTION_ORDER.index(sid)
        except ValueError:
            return 99

    sorted_sections = sorted(sections, key=sort_key)

    # Build final markdown
    parts = ["# Section 3: Key Industry Insights\n"]

    for i, section in enumerate(sorted_sections, 1):
        if isinstance(section, dict):
            name = section.get("subsection_name", f"Sub-section {i}")
            content = section.get("content", "")
            tables = section.get("tables", [])

            parts.append(f"## 3.{i} {name}\n")
            parts.append(content)
            parts.append("")

    final_section = "\n".join(parts)

    # Build bibliography from all citations used
    all_used_ids = set()
    for section in sorted_sections:
        if isinstance(section, dict):
            all_used_ids.update(section.get("citation_ids_used", []))

    bib_entries = []
    seen_urls = set()
    for citation in all_citations:
        if isinstance(citation, dict):
            cid = citation.get("id", "")
            url = citation.get("url", "")
            if cid in all_used_ids and url not in seen_urls:
                seen_urls.add(url)
                entry = (
                    f"[{cid}] {citation.get('title', 'Unknown')}. "
                    f"{citation.get('publisher', 'Unknown')}. "
                    f"{citation.get('date', 'n.d.')}. "
                    f"{url}"
                )
                bib_entries.append(entry)

    bibliography = "## References\n\n" + "\n\n".join(sorted(bib_entries)) if bib_entries else ""

    # Stats
    total_words = sum(
        section.get("word_count", 0)
        for section in sorted_sections
        if isinstance(section, dict)
    )

    logger.info(f"Assembly complete: {len(sorted_sections)} sections, "
                f"{total_words} words, {len(bib_entries)} citations")

    return {
        "final_section": final_section,
        "citation_bibliography": bibliography,
        "status": "done",
    }

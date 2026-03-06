"""
CitationManager — tracks all citations across the report, builds bibliography.

Wraps tools/citation.py for validation and ID generation.
"""

from __future__ import annotations
import logging

from tools.citation import (
    generate_citation_id,
    validate_citation,
    check_text_for_banned_citations,
)

logger = logging.getLogger(__name__)


class CitationManager:
    """Manages all citations for a single report generation run."""

    def __init__(self):
        self._citations: list[dict] = []
        self._url_index: dict[str, str] = {}  # url → citation_id (dedup)
        self._section_counters: dict[str, int] = {}  # section_id → next index

    def add(
        self,
        url: str,
        title: str,
        publisher: str = "",
        date: str = "",
        snippet: str = "",
        section_id: str = "gen",
    ) -> str | None:
        """Add a citation. Returns citation_id, or None if banned source."""
        if not validate_citation(url, title, publisher):
            logger.debug(f"Blocked banned source: {url}")
            return None

        # Dedup by URL
        if url in self._url_index:
            return self._url_index[url]

        # Generate ID
        idx = self._section_counters.get(section_id, 0)
        self._section_counters[section_id] = idx + 1
        cid = generate_citation_id(section_id, idx)

        citation = {
            "id": cid,
            "url": url,
            "title": title,
            "publisher": publisher,
            "date": date,
            "snippet": snippet,
            "section_id": section_id,
        }
        self._citations.append(citation)
        self._url_index[url] = cid
        return cid

    def get_citation_table(self, section_id: str | None = None) -> str:
        """Build a citation reference table (for LLM context).

        If section_id is given, filter to that section.
        """
        entries = self._citations
        if section_id:
            entries = [c for c in entries if c["section_id"] == section_id]

        lines = []
        for c in entries:
            date_str = c["date"] or "n.d."
            lines.append(
                f"{c['id']}: {c['title']} ({c['publisher']}, {date_str}) - {c['url']}"
            )
        return "\n".join(lines)

    def get_all_ids(self) -> set[str]:
        """Get all citation IDs."""
        return {c["id"] for c in self._citations}

    def get_bibliography_entries(self, used_ids: set[str] | None = None) -> list[str]:
        """Build bibliography entries, optionally filtered to used IDs."""
        entries = []
        seen_urls = set()

        for c in self._citations:
            if used_ids and c["id"] not in used_ids:
                continue
            if c["url"] in seen_urls:
                continue
            seen_urls.add(c["url"])

            date_str = c["date"] or "n.d."
            entry = (
                f"[{c['id']}] {c['title']}. "
                f"{c['publisher']}. {date_str}. {c['url']}"
            )
            entries.append(entry)

        return sorted(entries)

    @property
    def count(self) -> int:
        return len(self._citations)

    @property
    def citations(self) -> list[dict]:
        return self._citations

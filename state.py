"""
State definitions for the Section 3 pipeline.

Two-level state:
- PipelineState: outer orchestrator (planner → fan-out → assemble)
- SubSectionWorkerState: inner per-subsection (research → organize → analyze → write → review)
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from pydantic import BaseModel, Field


# ─── Pydantic Models ───────────────────────────────────────────────────────────


class Citation(BaseModel):
    """A single source citation tracked end-to-end through the pipeline."""
    id: str                          # e.g. "src_mkt_001"
    url: str
    title: str
    source_type: str                 # sec_filing, fda_database, news_article, annual_report,
                                     # journal, gov_database, investor_presentation, press_release,
                                     # clinical_trial, patent_filing
    publisher: str                   # e.g. "Reuters", "FDA", "WHO"
    date: Optional[str] = None       # Publication date if known
    snippet: str                     # The exact text/data extracted from this source
    is_valid: bool = True            # Set False if reviewer flags it


class SearchResult(BaseModel):
    """Raw search result from web search tools."""
    query: str
    title: str
    url: str
    snippet: str
    source: str                      # "searxng", "duckduckgo"


class ResearchQuery(BaseModel):
    """A planned search query targeting a specific sub-section."""
    subsection_id: str               # e.g. "market_dynamics"
    query: str
    intent: str                      # What data point this query aims to find
    priority: int = 1                # 1=high, 2=medium, 3=low


class SubSectionData(BaseModel):
    """Organized data for one sub-section, ready for the writer."""
    subsection_id: str
    subsection_name: str
    raw_facts: list[str] = Field(default_factory=list)
    statistics: list[str] = Field(default_factory=list)
    company_actions: list[str] = Field(default_factory=list)
    regulatory_info: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    analysis_notes: str = ""
    key_findings: list[str] = Field(default_factory=list)


class WrittenSection(BaseModel):
    """Output from the Writer for one sub-section."""
    subsection_id: str
    subsection_name: str
    content: str                     # Markdown with inline citations [src_xxx]
    tables: list[str] = Field(default_factory=list)
    citation_ids_used: list[str] = Field(default_factory=list)
    word_count: int = 0


class ReviewFeedback(BaseModel):
    """Reviewer's assessment of a written section."""
    subsection_id: str
    passed: bool
    issues: list[str] = Field(default_factory=list)
    citation_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# ─── LangGraph State Schemas ──────────────────────────────────────────────────


class SubSectionWorkerState(TypedDict):
    """State for a single sub-section being processed through the
    research → organize → analyze → write → review pipeline."""
    topic: str
    subsection_id: str
    subsection_name: str

    # Research phase
    research_queries: list         # list[ResearchQuery dict]
    search_results: Annotated[list, operator.add]
    citations: Annotated[list, operator.add]

    # Organize phase
    organized_data: Optional[dict]  # SubSectionData as dict

    # Write phase
    written_section: Optional[dict]  # WrittenSection as dict

    # Review phase
    review_feedback: Optional[dict]  # ReviewFeedback as dict

    # Control
    research_iteration: int
    max_research_iterations: int
    rewrite_count: int


class WorkerOutput(TypedDict):
    """Minimal output schema for subsection workers.

    Only contains the Annotated accumulator keys so that 11 parallel
    workers can merge their results without conflicting on plain keys
    like 'topic'.
    """
    completed_sections: Annotated[list, operator.add]
    all_citations: Annotated[list, operator.add]


class PipelineState(TypedDict):
    """Top-level state for the entire Section 3 pipeline."""
    # Input
    topic: str
    report_context: str

    # Planner output
    subsection_configs: list       # list of dicts: {id, name, description, query_hints}

    # Aggregated results from fan-out workers
    completed_sections: Annotated[list, operator.add]
    all_citations: Annotated[list, operator.add]

    # Final output
    final_section: str
    citation_bibliography: str

    # Control
    status: str

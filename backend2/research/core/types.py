"""Core types for the multi-agent research system."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field
from operator import add


class IntentKind(StrEnum):
    """Classification of research intent."""
    MARKET_SIZING = "market_sizing"
    COMPETITIVE = "competitive"
    TREND = "trend"
    REGULATORY = "regulatory"
    TECHNOLOGY = "technology"
    GEOGRAPHIC = "geographic"


class AngleKind(StrEnum):
    """Different analyst angles for query refinement."""
    SIZE_SEGMENTATION = "size_segmentation"
    DRIVERS_CONSTRAINTS = "drivers_constraints"
    COMPETITIVE_SHARE = "competitive_share"
    OUTLOOK_SCENARIOS = "outlook_scenarios"


class AuthorityTier(StrEnum):
    """Source authority tier for citation ranking."""
    GOVERNMENT     = "government"
    MULTILATERAL   = "multilateral"
    INDUSTRY_BODY  = "industry_body"
    TIER1_MEDIA    = "tier1_media"
    ANALYST_FIRM   = "analyst_firm"
    TRADE_PRESS    = "trade_press"
    BLOG           = "blog"


class Variant(BaseModel):
    """A refined query variant."""
    text: str = Field(..., max_length=280)
    angle: AngleKind


class ScoredVariant(BaseModel):
    """A variant with clarity scores."""
    variant: Variant
    specificity: float = Field(..., ge=0, le=10)
    scope_clarity: float = Field(..., ge=0, le=10)
    answerability: float = Field(..., ge=0, le=10)
    composite: float = Field(..., ge=0, le=10)  # weighted avg: 0.4/0.3/0.3
    reason: str


class QuestionCategory(StrEnum):
    """Category of a research sub-question."""
    SIZE         = "size"
    SEGMENTATION = "segmentation"
    DRIVERS      = "drivers"
    CONSTRAINTS  = "constraints"
    COMPETITIVE  = "competitive"
    GEOGRAPHY    = "geography"
    OUTLOOK      = "outlook"
    REGULATORY   = "regulatory"
    VALUE_CHAIN  = "value_chain"
    MACRO        = "macro"
    SUBSTITUTION = "substitution"
    TECHNOLOGY   = "technology"


class SubQuestionDraft(BaseModel):
    """Intermediate shape used by 2a and 2b (pre-scoring)."""
    text: str = Field(..., max_length=240)
    category: QuestionCategory
    metric_hint: str | None = Field(default=None, max_length=80)
    geography: str | None   = Field(default=None, max_length=60)
    time_frame: str | None  = Field(default=None, max_length=60)
    source: str             = Field(default="decomposer")


class SubQuestion(BaseModel):
    """Final shape written to RunState.sub_questions."""
    text: str = Field(..., max_length=240)
    category: QuestionCategory
    metric_hint: str | None = None
    geography: str | None   = None
    time_frame: str | None  = None
    source: str
    info_value:    float = Field(..., ge=0, le=10)
    answerability: float = Field(..., ge=0, le=10)
    composite:     float = Field(..., ge=0, le=10)  # 0.6*info_value + 0.4*answerability
    reason: str = Field(..., max_length=200)


class Citation(BaseModel):
    """Source citation with authority tier."""
    url: str
    title: str | None = None
    publisher: str | None = None
    published: str | None = None   # ISO date string, e.g. "2026-03-12"
    accessed: str | None = None    # ISO datetime string
    authority_tier: AuthorityTier = AuthorityTier.BLOG


class NumericClaim(BaseModel):
    """A numeric claim with citation."""
    metric: str
    value: float | str
    unit: str
    as_of: str | None = None
    scope: str | None = None
    raw_excerpt: str               # verbatim sentence from source passage
    citation: Citation


class Observation(BaseModel):
    """A cross-agent scratchpad observation."""
    section: str = Field(..., pattern=r"^(topic|market_context|news)$")
    key: str = Field(..., max_length=120)
    value: str = Field(..., max_length=400)
    citation: Citation | None = None
    written_by: str = "unknown"


class SearchQuery(BaseModel):
    """A single Tavily search query."""
    text: str = Field(..., max_length=200)
    time_window_days: int | None = Field(default=None, ge=1, le=3650)
    site_filter: str | None = Field(default=None, max_length=80)


class PlannedSearch(BaseModel):
    """A sub-question mapped to 1-2 search queries."""
    sub_question_text: str = Field(..., max_length=240)
    queries: list[SearchQuery] = Field(..., min_length=1, max_length=2)
    rationale: str = Field(..., max_length=200)


class Passage(BaseModel):
    """A fetched web passage with metadata."""
    url: str
    title: str | None = None
    publisher: str | None = None
    published: str | None = None
    accessed: str                  # ISO datetime string (set at fetch time)
    authority_tier: AuthorityTier = AuthorityTier.BLOG
    text: str = Field(..., max_length=20_000)
    related_sub_questions: list[str] = Field(default_factory=list)


class Footnote(BaseModel):
    """Numbered inline citation in a narrative."""
    n: int = Field(..., ge=1, le=99)
    citation: Citation


class ChainNode(BaseModel):
    """A single node in a value chain (upstream/midstream/downstream)."""
    stage: str = Field(..., pattern=r"^(upstream|midstream|downstream)$")
    name: str = Field(..., max_length=120)
    role: str = Field(..., max_length=200)
    approx_share: float | None = Field(default=None, ge=0, le=100)
    geography: str | None = Field(default=None, max_length=120)


class SubstituteEntry(BaseModel):
    """A substitute product / technology for the target market."""
    name: str = Field(..., max_length=120)
    maturity: str = Field(..., pattern=r"^(lab|pilot|early_commercial|mature)$")
    threat_level: str = Field(..., pattern=r"^(low|medium|high)$")
    rationale: str = Field(..., max_length=400)


class ImpactItem(BaseModel):
    """A parent-market force and its measured impact on the child market."""
    force: str = Field(..., max_length=160)
    direction: str = Field(..., pattern=r"^(positive|negative|mixed)$")
    magnitude: str = Field(..., max_length=200)
    mechanism: str = Field(..., max_length=300)
    evidence: list[Citation]


class NewsEvent(BaseModel):
    """A recent news event affecting the child or parent market."""
    headline: str = Field(..., max_length=300)
    date: date
    category: str = Field(..., pattern=r"^(m_and_a|earnings|product|partnership|investment|other)$")
    summary: str = Field(..., max_length=500)
    impact: str = Field(..., pattern=r"^(positive|negative|neutral|mixed)$")
    magnitude: str = Field(..., pattern=r"^(low|medium|high)$")
    source: Citation


class RegulatoryChange(BaseModel):
    """A regulatory action affecting the market."""
    regulator: str = Field(..., max_length=200)
    action: str = Field(..., max_length=400)
    effective_date: date | None = None
    impact_summary: str = Field(..., max_length=400)
    estimated_cost_impact: str | None = None
    source: Citation


class Disruption(BaseModel):
    """A geopolitical supply-chain disruption event."""
    upstream_node: str = Field(..., max_length=200)
    event: str = Field(..., max_length=400)
    severity: str = Field(..., pattern=r"^(watch|elevated|critical)$")
    supply_chain_path: str = Field(..., max_length=300)
    evidence: list[Citation]


class Conflict(BaseModel):
    """Resolution of conflicting claims."""
    chosen: NumericClaim
    rejected: list[tuple[NumericClaim, str]]  # (claim, reason)


class Causation(BaseModel):
    """Explanation of why values changed."""
    metric: str
    delta_pct: float
    drivers: list[dict]  # {description: str, citations: list[Citation]}


class ResearchBrief(BaseModel):
    """Final research brief output."""
    run_id: str
    original_query: str
    chosen_query: str
    intent: IntentKind
    query_variants: list[ScoredVariant]
    topic_claims: list[NumericClaim] = Field(default_factory=list)
    market_claims: list[NumericClaim] = Field(default_factory=list)
    news_claims: list[NumericClaim] = Field(default_factory=list)
    validated_claims: list[NumericClaim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    causations: list[Causation] = Field(default_factory=list)
    narrative: str = ""
    cost_usd: float = 0.0


class RunState(TypedDict):
    """Shared state across all agents."""
    # Core inputs
    run_id: str
    original_query: str
    
    # Agent 1 outputs
    intent: IntentKind
    query_variants: list[ScoredVariant]
    chosen_query: str
    
    # Agent 2 outputs
    sub_questions: list[SubQuestion]
    
    # Scratchpad (appended by Agents 3/4/5 in parallel)
    scratchpad_notes: Annotated[list[Observation], add]

    # Agent 3 outputs (parallel)
    topic_claims: Annotated[list[NumericClaim], add]
    topic_narrative: str
    
    # Agent 4 outputs (parallel)
    market_claims: Annotated[list[NumericClaim], add]
    market_narrative: str
    
    # Agent 5 outputs (parallel)
    news_claims: Annotated[list[NumericClaim], add]
    news_narrative: str
    
    # Agent 6 outputs
    consolidated_report: str
    
    # Agent 7 outputs
    validated_claims: list[NumericClaim]
    conflicts: list[Conflict]
    
    # Agent 8 outputs
    causations: list[Causation]
    
    # Cross-cutting
    cost_usd: float

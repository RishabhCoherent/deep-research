"""Core types for the multi-agent research system."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field, field_validator
from operator import add


class IntentKind(StrEnum):
    """Classification of research intent."""
    MARKET_SIZING = "market_sizing"
    COMPETITIVE = "competitive"
    TREND = "trend"
    REGULATORY = "regulatory"
    TECHNOLOGY = "technology"
    GEOGRAPHIC = "geographic"
    GENERAL = "general"


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
    UNKNOWN        = "unknown"


class Variant(BaseModel):
    """A refined query variant."""
    text: str = Field(..., max_length=280)
    angle: AngleKind

    @field_validator("text")
    @classmethod
    def _max_35_words(cls, v: str) -> str:
        word_count = len(v.split())
        assert word_count <= 35, f"variant must be ≤35 words, got {word_count}"
        return v


class ScoredVariant(BaseModel):
    """A variant with clarity scores."""
    variant: Variant
    specificity: float = Field(..., ge=0, le=10)
    scope_clarity: float = Field(..., ge=0, le=10)
    answerability: float = Field(..., ge=0, le=10)
    composite: float = Field(..., ge=0, le=10)  # weighted avg: 0.4/0.3/0.3
    reason: str

    @field_validator("specificity", "scope_clarity", "answerability", "composite", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        return _normalise_score(v)


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
    geography: str | None   = Field(default=None, max_length=120)
    time_frame: str | None  = Field(default=None, max_length=60)
    source: str             = Field(default="decomposer")


def _normalise_score(v: float | int) -> float:
    """Clamp LLM scores to [0, 10]. If on a 0-20 scale, halve it first."""
    v = float(v)
    if v > 10:
        v = v / 2.0   # 0-20 → 0-10
    return max(0.0, min(10.0, v))


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

    @field_validator("info_value", "answerability", "composite", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        return _normalise_score(v)


class Citation(BaseModel):
    """Source citation with authority tier."""
    url: str
    title: str | None = None
    publisher: str | None = None
    published: str | None = None   # ISO date string, e.g. "2026-03-12"
    accessed: str | None = None    # ISO datetime string
    authority_tier: AuthorityTier = AuthorityTier.BLOG


class NumericClaim(BaseModel):
    """A numeric claim with citation.

    The `qualifiers` dict is a Wikidata-style open dict of (key, value) string
    pairs that contextualise the claim along multiple dimensions (subject,
    metric_kind, segment, geography, fiscal_period, ...). It's used by the
    dimensional clusterer to group claims that measure the same thing.

    Suggested keys (the LLM extractor populates whichever apply):
      subject, metric_kind, segment, scope, geography, as_of,
      fiscal_period, fiscal_basis, reporting_standard, measurement_basis,
      is_forecast — plus any topic-specific keys named by the topic profile's
      `key_dimensions` (trial_phase, drug, endpoint, country, vehicle_class,
      industry, role_type, ...).
    """
    metric: str
    value: float | str
    unit: str
    as_of: str | None = None
    scope: str | None = None
    raw_excerpt: str               # verbatim sentence from source passage
    citation: Citation
    qualifiers: dict[str, str] = Field(default_factory=dict)


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

    @field_validator("time_window_days", mode="before")
    @classmethod
    def _coerce_zero_to_none(cls, v):
        # LLMs often emit 0 to mean "no window"; treat as None.
        if v == 0 or v == "0":
            return None
        return v


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
    accessed: str = ""              # ISO datetime string; defaults to empty if LLM omits it
    authority_tier: AuthorityTier = AuthorityTier.BLOG
    text: str = Field(default="", max_length=20_000)
    related_sub_questions: list[str] = Field(default_factory=list)

    @field_validator("accessed", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


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


class ConflictCandidate(BaseModel):
    """A group of ≥2 claims on the same metric flagged for resolution."""
    metric: str
    scope: str | None = None
    claims: list[NumericClaim]
    max_diff_pct: float = 0.0
    recency_winner_idx: int | None = None


class RangeValue(BaseModel):
    """Used when two finalist claims are within 5% — emit range not point."""
    low: float
    high: float
    unit: str


class Theme(BaseModel):
    """A named analyst theme grouping related claims and observations."""
    name: str = Field(..., max_length=80)
    summary: str = Field(..., max_length=300)
    claims: list[NumericClaim] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)


class FrameworkRow(BaseModel):
    """One row of an analytical framework table (e.g., one row of a 2x4 matrix)."""
    label: str = Field(..., max_length=120)
    cells: list[str] = Field(default_factory=list)   # cells[i] aligns with FrameworkTable.headers[i+1]


class FrameworkTable(BaseModel):
    """An analytical framework rendered as a markdown table.

    Headers is the column header list (first column is implicitly the row label).
    Rows are FrameworkRow objects. Used by L3-style 'Funding Reality Check',
    'Risk Assessment 4x4', 'Applications Taxonomy', etc.
    """
    title: str = Field(..., max_length=120)
    headers: list[str] = Field(default_factory=list)   # e.g., ["Segment", "Size", "Growth", "Risk"]
    rows: list[FrameworkRow] = Field(default_factory=list)


class CausalChainRow(BaseModel):
    """One row of a cause -> effect -> implication table."""
    cause: str = Field(..., max_length=200)
    effect: str = Field(..., max_length=200)
    implication: str = Field(..., max_length=200)


class CaseStudy(BaseModel):
    """A short concrete case study illustrating a section's thesis.

    150-300 words of company-specific or jurisdiction-specific evidence.
    """
    title: str = Field(..., max_length=120)
    body: str = Field(..., max_length=2000)


class OutlineSection(BaseModel):
    """One section of the structured outline produced by the compose-outline pass.

    `prose` is empty after pass 1; pass 2 (premium writer) fills it. Frameworks,
    causal chains, and case studies are produced in pass 1 with a reasoning
    model and used as scaffolding (and rendered verbatim) by pass 2.
    """
    heading: str = Field(..., max_length=120)
    thesis: str = Field(..., max_length=400)
    framework_table: FrameworkTable | None = None
    causal_chain_rows: list[CausalChainRow] = Field(default_factory=list)
    case_studies: list[CaseStudy] = Field(default_factory=list)
    evidence_ids_to_cite: list[str] = Field(default_factory=list)
    prose: str = ""   # filled by compose-prose pass


class ReportOutline(BaseModel):
    """The structured outline produced by the outline pass of compose.

    The renderer reads this when rendering the markdown brief: each section's
    framework_table / causal_chain_rows / case_studies are rendered as proper
    markdown tables / quoted blocks; contrarian_claims become the dedicated
    'Contrarian View' section; key_stats is the mandatory-stats list the prose
    pass HAD to inject.
    """
    sections: list[OutlineSection] = Field(default_factory=list)
    contrarian_claims: list[str] = Field(default_factory=list)
    key_stats: list[str] = Field(default_factory=list)
    target_word_count: int = 2000


class ConsolidatedReport(BaseModel):
    """Output of Agent 6 — normalised claims, clustered themes, structured outline,
    and a bottom-up narrative composed from the outline.

    `outline` is the new field added in Phase 4a — it carries the L3-grade
    structural sophistication (per-section thesis + framework tables + causal
    chains + case studies + so-what callouts + contrarian view). The renderer
    falls back to the legacy `narrative` + `themes` rendering when outline is
    None (graceful for older runs in checkpoints).
    """
    claims: list[NumericClaim] = Field(default_factory=list)
    themes: list[Theme] = Field(default_factory=list)
    narrative: str = ""
    footnotes: list[Footnote] = Field(default_factory=list)
    outline: ReportOutline | None = None


class Conflict(BaseModel):
    """Resolution of conflicting claims."""
    chosen: NumericClaim
    rejected: list[tuple[NumericClaim, str]]  # (claim, reason)


class VerifiedClaim(BaseModel):
    """One factual claim extracted from the composed brief, classified by the
    verifier as verified / uncertain / fabricated."""
    text: str = Field(..., max_length=200)
    status: str   # "verified" | "uncertain" | "fabricated"


class VerificationResult(BaseModel):
    """Output of the a8.5 verifier — measures how grounded the brief is in
    the evidence the rest of the pipeline produced.

    grounding_score = verified / total. 0 = nothing grounded; 1 = everything
    grounded. < 0.7 typically means the brief was forced to fabricate due to
    evidence scarcity (the upstream a3 didn't produce enough claims for the
    target word count).
    """
    grounding_score: float = 0.0
    total_claims: int = 0
    verified_claims: int = 0
    fabricated: list[str] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list)


class Driver(BaseModel):
    """A causal driver for a metric change, with evidence citations."""
    name: str = Field(..., max_length=120)
    description: str = Field(..., max_length=300)
    evidence: list[Citation]              # ≥2 citations, ≥2 domains after validation
    confidence: str = Field(default="medium", pattern=r"^(high|medium|low)$")


class Causation(BaseModel):
    """Explanation of why a metric changed."""
    metric: str
    delta_pct: float
    prior: NumericClaim | None = None
    current: NumericClaim | None = None
    drivers: list[Driver] = Field(default_factory=list)
    confidence: str = Field(default="low", pattern=r"^(high|medium|low)$")


class Delta(BaseModel):
    """A detected metric change between two dated claims."""
    metric: str
    prior: NumericClaim
    current: NumericClaim
    delta_pct: float
    window_start: date | None = None     # as_of of prior claim
    window_end: date | None = None       # as_of of current claim


class CausationDraft(BaseModel):
    """Pre-validation causation; drivers may not yet pass ≥2-citation rule."""
    metric: str
    prior: NumericClaim
    current: NumericClaim
    delta_pct: float
    candidate_drivers: list[Driver] = Field(default_factory=list)


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

    # Agent 0 output (topic profile — generated once at run start, parameterises
    # every downstream crew so the same code works for market / clinical /
    # policy / social-science topics without per-domain hardcoding). Carried as
    # a dict (TopicProfile.model_dump()) for TypedDict friendliness; downstream
    # code rehydrates with TopicProfile(**state["topic_profile"]).
    topic_profile: dict | None

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
    consolidated: ConsolidatedReport | None
    
    # Agent 7 outputs
    validated_claims: list[NumericClaim]
    conflicts: list[Conflict]

    # Agent 6.5 (dimensional clustering) output. Each entry is a
    # `research.clustering.ClusteredEstimate` dumped via .model_dump() — kept
    # as dicts in RunState for TypedDict friendliness; the renderer
    # rehydrates with ClusteredEstimate(**d) when needed.
    dimensional_clusters: list[dict]

    # Agent 8 outputs
    causations: list[Causation]

    # Agent 8.5 (verifier) output — fact-checks the composed brief against
    # the validated_claims + dimensional_clusters. None until a8.5 runs.
    verification: dict | None

    # Cross-cutting
    cost_usd: float

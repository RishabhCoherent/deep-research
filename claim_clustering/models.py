"""Pydantic data model for claim clustering — qualifier-based (Wikidata-style).

A claim is:
    (value, unit_family, qualifiers, raw_text, source, rank)

Where `qualifiers` is an OPEN dictionary of (key, value) strings that
contextualise the claim. Two claims belong to the same cluster iff their
descriptors describe the same measurement AND their qualifier sets do not
contradict on any shared key.

Hard constraints that survive:
    - `unit_family` never mixes across families (% can't cluster with $)

Everything else (subject, metric_kind, segment, scope, as_of, fiscal_period,
reporting_standard, measurement_basis, ...) flows through `qualifiers` and is
LLM-populated per-claim. This mirrors Wikidata's qualifier model where each
statement carries whatever qualifiers matter for that fact.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Enums / controlled vocabularies ─────────────────────────────────────────

SourceTier = Literal[
    "government", "multilateral", "industry_body", "tier1_media",
    "analyst_firm", "trade_press", "blog", "unknown",
]

# Unit family is the ONE hard categorical that the clusterer respects: claims
# in different unit families never merge regardless of descriptor similarity
# or qualifier overlap.
UnitFamily = Literal[
    "USD", "EUR", "GBP", "INR", "CNY", "JPY",
    "percent", "units", "usd_per_unit", "ratio", "unknown",
]

# Wikidata-style rank. Future-use; all extracted claims default to "normal".
ClaimRank = Literal["preferred", "normal", "deprecated"]


# ── Raw claim ───────────────────────────────────────────────────────────────

class RawClaim(BaseModel):
    """A single data point extracted verbatim from ONE source.

    Clustering-relevant fields:
        raw_text          - verbatim excerpt from the source
        value             - normalised numeric value
        unit_family       - hard categorical
        qualifiers        - open dict of (key, value) strings that describe
                            WHAT is being measured (subject, metric_kind,
                            segment, as_of, fiscal_period, ...)
        descriptor        - LLM-written sentence (filled in describe phase)
        descriptor_embedding - vector (filled in embed phase)
    """
    # Provenance
    source_url: str
    source_domain: str
    source_title: Optional[str] = None
    source_tier: SourceTier = "unknown"
    published_at: Optional[str] = None

    # Raw excerpt (most important field — describer + judge read this)
    raw_text: str = Field(..., max_length=600)

    # Value (HARD — used for aggregation)
    value_raw: str
    value: float
    unit_raw: str
    unit_family: UnitFamily
    unit_magnitude_hint: Optional[str] = None

    # OPEN qualifier dict (replaces the old entity/metric/segment/... fields).
    # Suggested keys (enforced in extractor prompt, not in the schema):
    #   subject, metric_kind, segment, scope, geography, as_of,
    #   fiscal_period, fiscal_basis, reporting_standard, measurement_basis,
    #   is_forecast
    # The LLM may add new keys for topic-specific dimensions.
    qualifiers: dict[str, str] = Field(default_factory=dict)

    # Wikidata-style rank (preferred / normal / deprecated). Extraction always
    # emits "normal"; future: manual review UI can promote/deprecate.
    rank: ClaimRank = "normal"

    # Populated by describe + embed phases
    descriptor: str = ""
    descriptor_embedding: list[float] = Field(default_factory=list)

    # Confidence
    extractor_confidence: float = 0.7

    # Topic relevance (filled by relevance.py after extraction). Cosine
    # similarity between the topic profile and this claim's descriptor.
    # is_topic_relevant is the boolean cutoff using the run's threshold;
    # claims below threshold are surfaced in an "out-of-scope" section
    # rather than dropped silently.
    topic_relevance: Optional[float] = None
    is_topic_relevant: bool = True

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v):
        if isinstance(v, str):
            try:
                return float(v.replace(",", "").strip())
            except ValueError:
                return 0.0
        return v

    @field_validator("qualifiers", mode="before")
    @classmethod
    def _coerce_qualifier_values(cls, v):
        # Coerce any non-string qualifier value to str so the schema is stable
        if not isinstance(v, dict):
            return {}
        out: dict[str, str] = {}
        for key, val in v.items():
            if val is None:
                continue
            out[str(key)] = str(val)
        return out


# ── Cluster dimension ───────────────────────────────────────────────────────

class ClaimDimension(BaseModel):
    """Canonical handle for a cluster.

    `descriptor` is the LLM-written sentence describing what the cluster
    measures. `unit_family` is the hard unit-space constraint.
    `qualifier_summary` aggregates the qualifier values observed across all
    member claims, keyed by qualifier name.
    """
    descriptor: str = Field(..., max_length=400)
    unit_family: UnitFamily

    # For each qualifier key seen in any member claim, the set of distinct
    # values. Used by the visualiser to render cluster tags and by the
    # aggregator to identify time-series sibling clusters.
    qualifier_summary: dict[str, list[str]] = Field(default_factory=dict)

    def short_label(self, max_len: int = 90) -> str:
        return self.descriptor if len(self.descriptor) <= max_len else self.descriptor[:max_len - 1] + "…"


# ── Aggregated cluster ──────────────────────────────────────────────────────

class ClusteredEstimate(BaseModel):
    """A group of RawClaims sharing a ClaimDimension, with aggregate stats."""
    dimension: ClaimDimension
    claims: list[RawClaim]

    n_claims: int
    n_unique_sources: int
    values: list[float]

    mean: float
    weighted_mean: float
    median: float

    stddev: float
    min_value: float
    max_value: float
    pct_spread: float

    consensus_level: Literal["high", "medium", "low", "contested", "single_source"]
    outlier_claim_indices: list[int]

    trend_slope_pct_per_year: Optional[float] = None

    # Sibling-family id filled by aggregator.link_time_series (qualifier set
    # modulo the as_of qualifier, lowercased).
    family_id: Optional[str] = None

    @property
    def canonical_unit(self) -> str:
        fam = self.dimension.unit_family
        if fam in ("USD", "EUR", "GBP", "INR", "CNY", "JPY"):
            return f"{fam}_B"
        if fam == "units":
            return "units_M"
        return fam


# ── Topic profile (run-level) ───────────────────────────────────────────────

class TopicProfile(BaseModel):
    """Per-run topic profile generated by topic_profiler.py.

    The schema fields are universal: every research topic has *some* expected
    metrics, *some* relevant dimensions, *some* signals of relevance and
    irrelevance. The values are LLM-generated per topic at the start of each
    run and threaded through the pipeline as parameterized context. Nothing
    in this schema is domain-specific; the codebase contains no enum or
    synonym table that constrains what these strings can be.

    Used by:
      query_expander  - guides query generation toward `expected_metric_kinds`
      extractor       - shown to the LLM as topic context (examples, not enum)
      relevance gate  - embedded and compared against each claim's descriptor
      visualise       - shown via --show-profile so the user sees what the run
                        is optimising for
    """
    topic_subject: str
    topic_domain: str
    expected_metric_kinds: list[str] = Field(default_factory=list)
    key_dimensions: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    expected_unit_families: list[str] = Field(default_factory=list)
    profile_reasoning: str = ""

    def to_user_message_block(self) -> str:
        """Render as a compact context block for injection into LLM user
        messages downstream. Kept human-readable for debugging."""
        lines = [
            f"TOPIC: {self.topic_subject}",
            f"DOMAIN: {self.topic_domain}",
            f"EXPECTED METRICS (examples — not exhaustive, coin new labels if needed): "
            f"{', '.join(self.expected_metric_kinds) or '(none generated)'}",
            f"KEY DIMENSIONS to track: {', '.join(self.key_dimensions) or '(none)'}",
        ]
        if self.positive_signals:
            lines.append(f"RELEVANT-CONTENT SIGNALS: {', '.join(self.positive_signals[:8])}")
        if self.negative_signals:
            lines.append(f"OFF-TOPIC SIGNALS: {', '.join(self.negative_signals[:8])}")
        return "\n".join(lines)


# ── Top-level run artefact ──────────────────────────────────────────────────

class ClusteringRun(BaseModel):
    """Everything produced by one end-to-end run."""
    topic: str
    started_at: str
    finished_at: str
    n_sources_searched: int
    n_sources_with_claims: int
    n_raw_claims: int
    n_dimensions: int
    estimates: list[ClusteredEstimate]

    # Cost accounting (filled by pipeline stages)
    cost_extract_usd: float = 0.0
    cost_describe_usd: float = 0.0
    cost_embed_usd: float = 0.0
    cost_judge_usd: float = 0.0
    cost_validate_usd: float = 0.0
    cost_total_usd: float = 0.0

    # Auditing
    search_calls: int = 0
    scrape_bytes: int = 0
    n_judge_calls: int = 0

    # Topic-relevance gate output. The TopicProfile generated for this run is
    # carried so the HTML viewer can show what the run was optimised for.
    # off_topic_claims is the bucket of claims that scored below the relevance
    # threshold — surfaced in the visualiser's "Out-of-scope findings" section
    # rather than dropped silently.
    topic_profile: Optional["TopicProfile"] = None
    off_topic_claims: list[RawClaim] = Field(default_factory=list)

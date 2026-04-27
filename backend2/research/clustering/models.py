"""Internal models for backend2's clustering library.

This module is INTERNAL — callers should use the public API in
backend2.research.clustering.cluster_numeric_claims (which takes a list of
`research.core.types.NumericClaim` and returns a list of `ClusteredEstimate`).

The internal `RawClaim` shape mirrors the Wikidata-style qualifier-based model
that the dimensional clusterer was designed around. The bridge from
NumericClaim -> RawClaim happens in adapter.py.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


SourceTier = Literal[
    "government", "multilateral", "industry_body", "tier1_media",
    "analyst_firm", "trade_press", "blog", "unknown",
]

# Unit family is the ONE hard categorical that the clusterer respects: claims
# in different unit families never merge regardless of descriptor similarity
# or qualifier overlap.
UnitFamily = Literal[
    "USD", "EUR", "GBP", "INR", "CNY", "JPY",
    "percent", "units", "usd_per_unit", "ratio",
    "months", "days", "score", "count", "unknown",
]

ClaimRank = Literal["preferred", "normal", "deprecated"]


class RawClaim(BaseModel):
    """Internal shape used by the dimensional clusterer.

    Adapted from a backend2 NumericClaim via adapter.numeric_to_raw() — most
    callers should never see this type directly.
    """
    source_url: str
    source_domain: str
    source_title: Optional[str] = None
    source_tier: SourceTier = "unknown"
    published_at: Optional[str] = None

    raw_text: str = Field(..., max_length=600)

    value_raw: str
    value: float
    unit_raw: str
    unit_family: UnitFamily
    unit_magnitude_hint: Optional[str] = None

    qualifiers: dict[str, str] = Field(default_factory=dict)
    rank: ClaimRank = "normal"

    descriptor: str = ""
    descriptor_embedding: list[float] = Field(default_factory=list)

    extractor_confidence: float = 0.7

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
        if not isinstance(v, dict):
            return {}
        out: dict[str, str] = {}
        for key, val in v.items():
            if val is None:
                continue
            out[str(key)] = str(val)
        return out


class ClaimDimension(BaseModel):
    """Canonical handle for a cluster."""
    descriptor: str = Field(..., max_length=400)
    unit_family: UnitFamily
    qualifier_summary: dict[str, list[str]] = Field(default_factory=dict)

    def short_label(self, max_len: int = 90) -> str:
        return self.descriptor if len(self.descriptor) <= max_len else self.descriptor[:max_len - 1] + "..."


class ClusteredEstimate(BaseModel):
    """A group of claims sharing a dimension, with aggregate stats. PUBLIC.

    This is what `cluster_numeric_claims()` returns. Backend2's report
    renderer reads `dimension.descriptor`, `weighted_mean`, `n_unique_sources`,
    `consensus_level`, and `pct_spread` to render a cluster summary.
    """
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
    family_id: Optional[str] = None

    @property
    def canonical_unit(self) -> str:
        fam = self.dimension.unit_family
        if fam in ("USD", "EUR", "GBP", "INR", "CNY", "JPY"):
            return f"{fam}_B"
        if fam == "units":
            return "units_M"
        return fam

"""Adapter: backend2 NumericClaim -> internal RawClaim.

The dimensional clusterer was designed around a Wikidata-style open
qualifier dict. Backend2's NumericClaim has a flat `metric` + `as_of` shape
plus an optional `qualifiers` dict (added in Phase 3b-3). This adapter
bridges the two:

  - subject defaults to "global" if not set in qualifiers (legacy claims)
  - metric_kind defaults to a snake_case version of `metric` (legacy claims)
  - as_of, scope inherit from top-level NumericClaim fields if not in qualifiers
  - unit is heuristically classified into a UnitFamily

This is a pure-Python transformation; no I/O, no LLM calls.
"""
from __future__ import annotations

import re
from typing import Iterable

from research.core.types import NumericClaim, AuthorityTier
from .canonicalise import canonicalise_qualifiers
from .models import RawClaim, SourceTier, UnitFamily


# ── Authority tier mapping (NumericClaim.citation.authority_tier -> SourceTier) ─

_AUTHORITY_TO_SOURCE_TIER: dict[AuthorityTier, SourceTier] = {
    AuthorityTier.GOVERNMENT:    "government",
    AuthorityTier.MULTILATERAL:  "multilateral",
    AuthorityTier.INDUSTRY_BODY: "industry_body",
    AuthorityTier.TIER1_MEDIA:   "tier1_media",
    AuthorityTier.ANALYST_FIRM:  "analyst_firm",
    AuthorityTier.TRADE_PRESS:   "trade_press",
    AuthorityTier.BLOG:          "blog",
    AuthorityTier.UNKNOWN:       "unknown",
}


# ── Unit family inference (lightweight; the LLM extractor should ideally set
# unit cleanly, but legacy claims have free-form `unit` strings). ───────────

_CURRENCY_PATTERNS = [
    (re.compile(r"\b(usd|us\$|\$|dollars?)\b", re.I), "USD"),
    (re.compile(r"\b(eur|€|euros?)\b", re.I), "EUR"),
    (re.compile(r"\b(gbp|£|pounds?)\b", re.I), "GBP"),
    (re.compile(r"\b(inr|₹|rs|rupees?)\b", re.I), "INR"),
    (re.compile(r"\b(cny|rmb|yuan|renminbi)\b", re.I), "CNY"),
    (re.compile(r"\b(jpy|¥|yen)\b", re.I), "JPY"),
]
_PERCENT_RE = re.compile(r"%|\bpercent\b|\bpct\b|\bpp\b", re.I)
_MONTHS_RE  = re.compile(r"\bmonths?\b", re.I)
_DAYS_RE    = re.compile(r"\bdays?\b", re.I)
_RATIO_RE   = re.compile(r"\bratio\b|\bhazard ratio\b|\bodds ratio\b", re.I)
_SCORE_RE   = re.compile(r"\bscore\b|\bindex\b", re.I)
_COUNT_RE   = re.compile(
    r"\b(units?|count|registrations?|patients?|trials?|stations?|"
    r"vehicles?|cars?|users?|subscribers?)\b", re.I)


def _infer_unit_family(unit: str, value: object) -> UnitFamily:
    """Classify a free-form unit string into the closed UnitFamily set."""
    blob = (unit or "").strip()
    if not blob:
        return "unknown"
    for pat, fam in _CURRENCY_PATTERNS:
        if pat.search(blob):
            return fam   # type: ignore[return-value]
    if _PERCENT_RE.search(blob):
        return "percent"
    if _MONTHS_RE.search(blob):
        return "months"
    if _DAYS_RE.search(blob):
        return "days"
    if _RATIO_RE.search(blob):
        return "ratio"
    if _SCORE_RE.search(blob):
        return "score"
    if _COUNT_RE.search(blob):
        return "count"
    return "unknown"


def _coerce_value(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        # Strip leading currency / trailing units; keep the first numeric token
        s = v.replace(",", "").strip()
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return 0.0
    return 0.0


def _metric_to_snake_case(metric: str) -> str:
    """Crude fallback: turn 'Five-year survival rate' -> 'five_year_survival_rate'.
    Used only when a NumericClaim was emitted without an explicit metric_kind
    qualifier (legacy a3 extractor output). New extractor output should set
    qualifiers['metric_kind'] directly so this function isn't called.
    """
    s = (metric or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "unknown_metric"


def numeric_to_raw(nc: NumericClaim) -> RawClaim:
    """Convert one NumericClaim to one RawClaim for clustering."""
    qualifiers = dict(nc.qualifiers or {})

    # Provide top-level NumericClaim fields as qualifier fallbacks if missing.
    if "as_of" not in qualifiers and nc.as_of:
        qualifiers["as_of"] = str(nc.as_of)
    if "scope" not in qualifiers and nc.scope:
        qualifiers["scope"] = str(nc.scope)
    if "metric_kind" not in qualifiers:
        qualifiers["metric_kind"] = _metric_to_snake_case(nc.metric)
    if "subject" not in qualifiers:
        # Default to "global" only when the claim genuinely doesn't name an
        # entity; the new extractor should populate this from document_frame.
        qualifiers["subject"] = "global"

    qualifiers = canonicalise_qualifiers(qualifiers)

    cit = nc.citation
    domain = ""
    if cit.url:
        m = re.match(r"https?://([^/]+)/?", cit.url)
        if m:
            domain = m.group(1).lower().lstrip("www.")

    source_tier = _AUTHORITY_TO_SOURCE_TIER.get(cit.authority_tier, "unknown")

    return RawClaim(
        source_url=cit.url,
        source_domain=domain,
        source_title=cit.title,
        source_tier=source_tier,
        published_at=cit.published,
        raw_text=(nc.raw_excerpt or "")[:600],
        value_raw=str(nc.value),
        value=_coerce_value(nc.value),
        unit_raw=nc.unit,
        unit_family=_infer_unit_family(nc.unit, nc.value),
        qualifiers=qualifiers,
    )


def numeric_claims_to_raw(claims: Iterable[NumericClaim]) -> list[RawClaim]:
    return [numeric_to_raw(c) for c in claims if c is not None]

"""Qualifier canonicalisation for the clusterer.

This is a slimmed port of claim_clustering/canonicalise.py — only the
qualifier-key/value canonicalisation that the hash clusterer needs. The
GPU/EV/NVIDIA hardcoded synonym tables (`_ENTITY_ALIASES`, `_SEGMENT_SYNONYMS`)
are intentionally NOT brought over; they were domain-leaky in the prior
codebase. Backend2 relies on the LLM (a3 extractor + topic_profile context)
to produce already-canonical qualifier values per topic.

Public:
  canonicalise_qualifiers(dict) -> dict   # alias keys, normalise values
  canonical_qualifier_key(key) -> str     # used by callers that need lookups
  canonical_time_period(tp) -> str        # FY / Q1-Q4 / H1-H2 / etc.
"""
from __future__ import annotations

from typing import Optional


# ── Qualifier-key aliases (open vocabulary; unknown keys pass through) ─────

_QUALIFIER_KEY_ALIASES = {
    # subject / entity
    "entity": "subject", "company": "subject", "who": "subject",
    "player": "subject", "firm": "subject", "organization": "subject",
    "organisation": "subject", "actor": "subject",
    # metric kind
    "metric": "metric_kind", "measure": "metric_kind", "quantity": "metric_kind",
    "indicator": "metric_kind", "what": "metric_kind",
    # segment / sub-scope
    "sub_market": "segment", "submarket": "segment", "product": "segment",
    "product_type": "segment", "slice": "segment", "category": "segment",
    "cohort": "segment", "subpopulation": "segment",
    # scope
    "market_scope": "scope", "coverage": "scope", "audience": "scope",
    # geography
    "region": "geography", "country": "geography", "territory": "geography",
    "market": "geography",
    # as_of
    "year": "as_of", "date": "as_of", "when": "as_of", "period_end": "as_of",
    "reporting_date": "as_of",
    # fiscal period
    "fy": "fiscal_period", "period": "fiscal_period", "quarter": "fiscal_period",
    "half": "fiscal_period", "time_period": "fiscal_period",
    # fiscal basis
    "basis": "fiscal_basis", "calendar_or_fiscal": "fiscal_basis",
    # reporting standard
    "standard": "reporting_standard", "accounting_standard": "reporting_standard",
    "gaap_ifrs": "reporting_standard",
    # measurement basis
    "nominal_real": "measurement_basis", "inflation_adjusted": "measurement_basis",
    "constant_vs_nominal": "measurement_basis",
    # forecast flag
    "forecast": "is_forecast", "projection": "is_forecast",
    "is_projection": "is_forecast", "projected": "is_forecast",
}


# ── Time-period canonicalisation ───────────────────────────────────────────

_VALID_TIME_PERIODS = {"FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2",
                       "month", "point", "ytd", "ttm", "unknown"}


def canonical_time_period(tp_raw: Optional[str]) -> str:
    """Map various time-period phrasings to canonical TimePeriod values."""
    if not tp_raw:
        return "FY"
    s = str(tp_raw).strip().lower().replace(" ", "")
    if s.upper() in _VALID_TIME_PERIODS:
        return s.upper() if s.upper() != "FY" else "FY"
    aliases = {
        "fullyear": "FY", "full-year": "FY", "annual": "FY", "yearly": "FY",
        "calendar": "FY", "calendaryear": "FY",
        "firstquarter": "Q1", "1q": "Q1", "q1": "Q1",
        "secondquarter": "Q2", "2q": "Q2", "q2": "Q2",
        "thirdquarter": "Q3", "3q": "Q3", "q3": "Q3",
        "fourthquarter": "Q4", "4q": "Q4", "q4": "Q4",
        "firsthalf": "H1", "1h": "H1", "h1": "H1",
        "secondhalf": "H2", "2h": "H2", "h2": "H2",
        "year-to-date": "ytd", "yeartodate": "ytd",
        "trailing12months": "ttm", "ttm": "ttm",
        "snapshot": "point", "asof": "point", "endof": "point",
    }
    return aliases.get(s, "unknown")


# Known keys where we canonicalise the VALUE. Keys not in this map pass
# through with only trimming + quote-stripping. Note: unlike claim_clustering,
# we do NOT canonicalise `subject` or `segment` values here — backend2
# trusts the LLM (steered by topic_profile) to emit already-canonical strings.
_QUALIFIER_VALUE_CANONICALISERS = {
    "fiscal_period":  lambda v: canonical_time_period(v),
    "is_forecast":    lambda v: "true" if str(v).strip().lower() in
                               ("true", "yes", "1", "y", "forecast", "projection") else "false",
}


def canonical_qualifier_key(k: str) -> str:
    """Map a qualifier key to its canonical form. Unknown keys pass through."""
    if not k:
        return ""
    norm = k.strip().lower().replace("-", "_").replace(" ", "_")
    return _QUALIFIER_KEY_ALIASES.get(norm, norm)


def canonical_qualifier_value(key: str, value: str) -> str:
    if value is None:
        return ""
    s = str(value).strip().strip('"').strip("'")
    fn = _QUALIFIER_VALUE_CANONICALISERS.get(key)
    if fn is None:
        return s
    try:
        out = fn(s)
        return str(out) if out is not None else s
    except Exception:
        return s


def canonicalise_qualifiers(raw: dict) -> dict[str, str]:
    """Apply key- and value-canonicalisation to a raw qualifier dict.

    Drops empty values and `currency` (redundant with unit_family).
    Later keys overwrite earlier ones on key collisions after aliasing.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if v is None or v == "":
            continue
        ck = canonical_qualifier_key(k)
        if not ck or ck == "currency":
            continue
        cv = canonical_qualifier_value(ck, v)
        if not cv:
            continue
        out[ck] = cv
    return out

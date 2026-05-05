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
    # `crore`/`lakh`/`rs`/`rupees` strongly imply INR even without an
    # explicit currency symbol — match these BEFORE the `$` family to
    # avoid an Indian "Rs 5 crore" being mis-tagged as something else.
    (re.compile(r"\b(inr|₹|rs\.?|rupees?|crore|cr|lakhs?|lac)\b", re.I), "INR"),
    (re.compile(r"\b(usd|us\$|\$|dollars?)\b", re.I), "USD"),
    (re.compile(r"\b(eur|€|euros?)\b", re.I), "EUR"),
    (re.compile(r"\b(gbp|£|pounds?)\b", re.I), "GBP"),
    (re.compile(r"\b(cny|rmb|yuan|renminbi)\b", re.I), "CNY"),
    (re.compile(r"\b(jpy|¥|yen)\b", re.I), "JPY"),
]
_PERCENT_RE = re.compile(r"%|\bpercent\b|\bpct\b|\bpp\b|\bbasis points?\b|\bbps\b", re.I)
_MONTHS_RE  = re.compile(r"\bmonths?\b", re.I)
_DAYS_RE    = re.compile(r"\bdays?\b|\bweeks?\b|\byears?\b", re.I)
_RATIO_RE   = re.compile(r"\bratio\b|\bhazard ratio\b|\bodds ratio\b|\bx$|\b\dx\b", re.I)
_SCORE_RE   = re.compile(r"\bscore\b|\bindex\b|\brating\b", re.I)
# Wider count vocabulary: jobs, headcount, distilleries, fabs, projects,
# wafers, capacity expressed in countables, etc. The clusterer treats `count`
# as a real unit family so cross-source consensus on, e.g., "152 distilleries"
# can form. Previously these all fell into `unknown` and never merged.
_COUNT_RE   = re.compile(
    r"\b("
    r"units?|count|number|"
    r"jobs?|employees?|headcount|workforce|"
    r"registrations?|patients?|subjects?|trials?|cohort|"
    r"stations?|vehicles?|cars?|fleet|"
    r"users?|subscribers?|customers?|members?|"
    r"distilleries|distillery|fabs?|plants?|factories|factory|projects?|"
    r"wafers?|chips?|bottles?|barrels?|"
    r"companies|firms|brands?|startups?|"
    r"deals?|transactions?|filings?|patents?|trademarks?"
    r")\b",
    re.I,
)


def _infer_unit_family(unit: str, value: object) -> UnitFamily:
    """Classify a free-form unit string into the closed UnitFamily set.

    Order matters:
      1. currencies first (INR takes `crore`/`lakh`/`rs`/`rupees`)
      2. percent
      3. count BEFORE months/days — so "wafers/month" and "chips per day"
         classify as count (throughput) rather than duration.
      4. months/days only when the unit is actually expressing a duration
      5. ratio / score / unknown
    """
    blob = (unit or "").strip()
    if not blob:
        return "unknown"
    for pat, fam in _CURRENCY_PATTERNS:
        if pat.search(blob):
            return fam   # type: ignore[return-value]
    if _PERCENT_RE.search(blob):
        return "percent"
    # Throughputs ("X per Y" / "X/Y") are countable — must precede months/days
    # so "wafers/month" doesn't get tagged as a duration.
    if _COUNT_RE.search(blob) or "/" in blob or " per " in blob.lower():
        # Confirm the count regex actually matches (or there's a clear
        # countable noun on the throughput's left side).
        if _COUNT_RE.search(blob):
            return "count"
    if _MONTHS_RE.search(blob):
        return "months"
    if _DAYS_RE.search(blob):
        return "days"
    if _RATIO_RE.search(blob):
        return "ratio"
    if _SCORE_RE.search(blob):
        return "score"
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


# ── Numeric-claim sanity filter ─────────────────────────────────────────────
#
# The a5 news/regulatory crews push categorical "events" through the same
# NumericClaim schema with `value="positive/high"` or `value="qualitative"`.
# Those have no numeric content and pollute clusters with value=0 entries
# whose unit_family="unknown". The clusterer should never see them.

_NON_NUMERIC_UNIT_TOKENS = {
    "impact_magnitude", "qualitative", "policy", "category",
    "severity", "event", "news", "n/a", "na", "unknown",
}


def _looks_numeric(value, unit_raw: str) -> bool:
    """Decide whether a NumericClaim carries an actual measurement.
    Categorical strings ('positive/high'), qualitative descriptions, and
    obvious placeholder units are filtered out before clustering."""
    # If the value is a non-numeric string, skip
    if isinstance(value, str):
        s = value.strip().lower()
        if not s:
            return False
        # Reject strings that are clearly categorical (slash-separated tags
        # or multi-word descriptions with no embedded numbers)
        if "/" in s and not re.search(r"\d", s):
            return False
        if not re.search(r"\d", s):
            return False
    elif not isinstance(value, (int, float)):
        return False
    # Reject claims whose unit is a categorical placeholder
    u = (unit_raw or "").strip().lower()
    if u in _NON_NUMERIC_UNIT_TOKENS:
        return False
    return True


# ── Implausibility detection / corrective rescale ───────────────────────────
#
# Currency claims should land in BILLIONS after `_apply_magnitude`. When the
# upstream extractor pre-expands a magnitude into the raw value (e.g. reads
# "₹1 Lakh Cr" and stores `value=1e11, unit="INR"` with no magnitude word),
# our adapter has no signal to know the value is in absolute units. The
# visualiser then renders "INR 100000000000.00B" — wildly off. We catch this
# by sanity-checking the post-rescale magnitude: any currency value whose
# magnitude is implausible-for-billions (≥ 1e6 = $1 quadrillion of billions)
# is divided down to the billions scale.

_CURRENCY_FAMILIES = ("USD", "EUR", "GBP", "INR", "CNY", "JPY")
_BILLIONS_IMPLAUSIBILITY_THRESHOLD = 1e6   # > 1M billions = > $1 quadrillion


def _correct_implausible_currency(value: float, unit_family: str) -> tuple[float, bool]:
    """If `value` is impossibly large for a currency expressed in billions,
    assume it was stored in raw absolute units and rescale to billions.
    Returns (corrected_value, was_corrected)."""
    if unit_family not in _CURRENCY_FAMILIES:
        return value, False
    if abs(value) < _BILLIONS_IMPLAUSIBILITY_THRESHOLD:
        return value, False
    return value / 1e9, True


# ── Magnitude normalisation ───────────────────────────────────────────────
#
# Backend2's a3 extractor leaves `value` paired with whatever magnitude word
# the source used (e.g. value=8339.4, unit="million USD"). The clusterer
# groups by `unit_family` (USD), so without rescaling, $56.51 billion gets
# averaged with $8339.4 million as if they were the same — we get a meaningless
# 4197.95 mean and `consensus_level: contested`.
#
# We rescale CURRENCY-family claims so `value` is always in BILLIONS of the
# stated currency (the convention the React renderer assumes). Non-currency
# families (count, percent, ratio, months, days) keep their natural scale —
# the magnitude word still gets stripped from `unit_raw` so descriptors are
# stable across "1.35 billion bottles" vs "1.35 bottles" claims, but the
# numeric value is converted to absolute units (e.g. 1.35 billion bottles →
# 1.35e9) so cross-source aggregation is honest.

_MAGNITUDE_WORDS = {
    # Western magnitudes — units expressed in billions
    "trillion": 1_000.0,    # in billions
    "trn":      1_000.0,
    "tn":       1_000.0,
    "billion":  1.0,
    "bn":       1.0,
    "b":        1.0,
    "million":  0.001,
    "mn":       0.001,
    "mm":       0.001,
    "m":        0.001,
    "thousand": 0.000_001,
    "k":        0.000_001,
    # Indian magnitudes (1 crore = 10⁷ = 0.01 billion; 1 lakh = 10⁵ = 0.0001 bn).
    # Without these, "₹91,000 crore" (~$11B) was being stored as 91,000 INR
    # — three orders of magnitude smaller than reality.
    "crore":    0.01,
    "cr":       0.01,
    "lakh":     0.0001,
    "lac":      0.0001,
    "lakhs":    0.0001,
    "lakh crore": 100.0,   # written sometimes as "5 lakh crore" = 5 × 10¹²
}

_NON_CURRENCY_ABS_MULT = {
    "trillion": 1e12, "trn": 1e12, "tn": 1e12,
    "billion": 1e9,   "bn": 1e9,   "b": 1e9,
    "million": 1e6,   "mn": 1e6,   "mm": 1e6,   "m": 1e6,
    "thousand": 1e3,  "k": 1e3,
    # Indian-magnitude support for non-currency cells too (e.g. "5 crore tonnes")
    "crore":    1e7,
    "cr":       1e7,
    "lakh":     1e5,
    "lac":      1e5,
    "lakhs":    1e5,
    "lakh crore": 1e12,
}

# Multi-word "lakh crore" must come BEFORE single-word alternation so the regex
# greedy-matches the compound first; word-boundary handles the rest.
_MAGNITUDE_RE = re.compile(
    r"\b(lakh\s+crore|trillion|billion|million|thousand|crore|lakhs?|lac|trn|bn|mn|mm|tn)\b",
    re.IGNORECASE,
)


def _detect_magnitude(unit_raw: str) -> tuple[str | None, str]:
    """Return (magnitude_token, unit_with_magnitude_stripped). magnitude_token
    is the lowercase magnitude word found, or None. Multi-word tokens like
    "lakh crore" are normalised to single-space form so the lookup table
    (keyed by "lakh crore") matches.
    """
    if not unit_raw:
        return None, ""
    m = _MAGNITUDE_RE.search(unit_raw)
    if not m:
        return None, unit_raw
    # Normalise whitespace in the captured token: "lakh  crore" → "lakh crore"
    token = " ".join(m.group(1).lower().split())
    # Treat plural "lakhs" as the same as "lakh" for table lookup
    if token == "lakhs":
        token = "lakh"
    stripped = (unit_raw[:m.start()] + unit_raw[m.end():]).strip()
    stripped = re.sub(r"\s{2,}", " ", stripped)
    return token, stripped


def _apply_magnitude(value: float, unit_raw: str,
                     unit_family: str) -> tuple[float, str, str | None]:
    """Rescale `value` into a clusterer-comparable scale based on the magnitude
    word in `unit_raw`. Returns (new_value, cleaned_unit_raw, magnitude_hint).

    Currency families: rescale to BILLIONS. (Frontend's `_formatValue` formats
    USD-family values as `${v.toFixed(2)}B`, so this is the canonical scale.)
    Non-currency: rescale to absolute units (so "1.35 billion bottles" becomes
    1.35e9).
    """
    if not unit_raw:
        return value, unit_raw or "", None

    token, stripped = _detect_magnitude(unit_raw)
    if token is None:
        return value, unit_raw, None

    if unit_family in ("USD", "EUR", "GBP", "INR", "CNY", "JPY"):
        mult = _MAGNITUDE_WORDS.get(token, 1.0)
        return value * mult, stripped or unit_raw, token
    # Non-currency families: rescale to absolute units.
    abs_mult = _NON_CURRENCY_ABS_MULT.get(token, 1.0)
    return value * abs_mult, stripped or unit_raw, token


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

    raw_value = _coerce_value(nc.value)
    unit_family = _infer_unit_family(nc.unit, nc.value)
    norm_value, cleaned_unit, mag_hint = _apply_magnitude(
        raw_value, nc.unit, unit_family,
    )

    # Sanity check: detect upstream "pre-expanded" magnitudes where the LLM
    # extractor inlined the magnitude into the value field but stripped the
    # magnitude word from the unit. Without this, a claim like
    # `value=1e11, unit="INR"` (extractor read "₹1 Lakh Cr" and expanded it)
    # would render as "INR 100000000000.00B" — nine orders of magnitude off.
    norm_value, was_corrected = _correct_implausible_currency(norm_value, unit_family)
    if was_corrected and mag_hint is None:
        mag_hint = "auto-rescaled-from-absolute"

    return RawClaim(
        source_url=cit.url,
        source_domain=domain,
        source_title=cit.title,
        source_tier=source_tier,
        published_at=cit.published,
        raw_text=(nc.raw_excerpt or "")[:600],
        value_raw=str(nc.value),
        value=norm_value,
        unit_raw=cleaned_unit,
        unit_family=unit_family,
        unit_magnitude_hint=mag_hint,
        qualifiers=qualifiers,
    )


def numeric_claims_to_raw(claims: Iterable[NumericClaim]) -> list[RawClaim]:
    """Adapt a list of NumericClaims to the clusterer's RawClaim shape.

    Filters out non-numeric claims (categorical "events" with string values
    like 'positive/high' / 'qualitative') so they never reach clustering —
    they were polluting clusters with value=0 unit_family="unknown" entries.
    """
    out: list[RawClaim] = []
    for c in claims:
        if c is None:
            continue
        if not _looks_numeric(c.value, c.unit):
            continue
        out.append(numeric_to_raw(c))
    return out

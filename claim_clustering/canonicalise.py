"""Deterministic normalisation: units, magnitudes, entity aliases.

The LLM extractor produces roughly-structured claims. This module turns those
into strictly canonical form so the tuple-key clusterer can match them.

Functions:
    normalise_value_unit(value, unit_raw, magnitude_hint) -> (value_canon, unit_family)
    canonical_entity(entity_raw)                          -> str
    canonical_segment(segment_raw)                        -> str | None
    currency_to_usd(amount, currency_family)              -> float  (approximate)

Canonical scales:
    currency (USD/EUR/...)  -> billions (USD_B, EUR_B, ...)
    percent                 -> 0-100
    units                   -> millions (units_M)
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from .models import UnitFamily


# ── Magnitude suffixes ──────────────────────────────────────────────────────

# Multiplier to apply to the raw number BEFORE converting to the canonical
# scale (e.g. billions for currency). If the raw number is already in the unit
# listed in `unit_raw`, the hint tells us how to scale.
_MAGNITUDE = {
    # Western
    "trillion": 1e12, "tn": 1e12, "t": 1e12,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mn": 1e6, "mm": 1e6, "m": 1e6,
    "thousand": 1e3, "k": 1e3,
    # Indian (crore = 10M, lakh = 100K)
    "crore": 1e7, "cr": 1e7,
    "lakh": 1e5, "lac": 1e5,
    # no suffix
    "": 1.0, "one": 1.0, "unit": 1.0, "units": 1.0,
}

# Approximate USD conversion rates. These are intentionally static and
# coarse - currency-family mixing in a single cluster is flagged as such and
# should always be treated as approximate.
_CURRENCY_TO_USD = {
    "USD": 1.00,
    "EUR": 1.08,
    "GBP": 1.27,
    "INR": 0.012,     # 1 INR ≈ 0.012 USD
    "CNY": 0.14,
    "JPY": 0.0068,
}


# ── Unit family detection ───────────────────────────────────────────────────

_CURRENCY_PATTERNS = [
    # $ / € / £ / ₹ / ¥ need non-word-boundary match (they're punctuation)
    (re.compile(r"(?:\busd\b|us\$|\$|\bdollars?\b)", re.I), "USD"),
    (re.compile(r"(?:\beur\b|€|\beuros?\b)", re.I), "EUR"),
    (re.compile(r"(?:\bgbp\b|£|\bpounds?\b)", re.I), "GBP"),
    # Note: 'crore' and 'lakh' are MAGNITUDES, not currency markers. Do not
    # include them here or "1.2 crore vehicles" would be misclassified as INR.
    (re.compile(r"(?:\binr\b|\brs\.?\b|\brupees?\b|₹)", re.I), "INR"),
    (re.compile(r"(?:\bcny\b|\brmb\b|\byuan\b|\brenminbi\b)", re.I), "CNY"),
    (re.compile(r"(?:\bjpy\b|\byen\b)", re.I), "JPY"),
]

_PERCENT_RE = re.compile(r"%|percent|pct|\bpp\b", re.I)
# Only treat "per unit" as a price if the context also mentions currency.
_PRICE_PER_UNIT_RE = re.compile(
    r"(?:\$|usd|eur|€|gbp|£|inr|rs\.?|₹|cny|¥|yuan|jpy)\s*/\s*\w+"
    r"|(?:dollars?|euros?|pounds?|rupees?|yen|yuan)\s+per\s+\w+",
    re.I,
)
# Generic "per X" suffix without currency = technical rate (e.g. 150 kW/station)
# - NOT a price. Route to unknown so it doesn't pollute currency clusters.
_COUNT_SUBJECT_RE = re.compile(
    r"\b(units?|shipments?|devices?|stations?|chargers?|gpus?|cards?|"
    r"vehicles?|cars?|trucks?|users?|subscribers?|people|households?|jobs?|"
    r"plants?|factories|sites?)\b",
    re.I,
)


def detect_unit_family(unit_raw: str, value_raw: str = "") -> UnitFamily:
    """Infer the canonical unit family from the raw unit string + value text.

    Checked in priority order: explicit currency -> percent -> price -> units -> unknown.
    """
    blob = f"{unit_raw} {value_raw}".strip()
    if not blob:
        return "unknown"

    # Technical physical units (kW, MW, kWh, km, mph, RPM, etc.) go straight to
    # "unknown" - they are spec sheets, not market data.
    if re.search(r"\b(k|m|g|t)?(w|wh|va|hz|b(ps|/s)?|pa|psi|bar)\b|"
                 r"\b(rpm|dpi|fps|kph|mph|km|miles?)\b", blob, re.I):
        return "unknown"

    # percent first - "10%" wins over any other interpretation
    if _PERCENT_RE.search(blob):
        return "percent"
    # price-per-unit (explicit currency + per unit)
    if _PRICE_PER_UNIT_RE.search(blob):
        return "usd_per_unit"
    # currencies (must check BEFORE units, since "50 crore rupees" is currency,
    # and "5 billion dollars worth of vehicles" is currency not units)
    for pattern, family in _CURRENCY_PATTERNS:
        if pattern.search(blob):
            return family  # type: ignore[return-value]
    # counts / unit-subject nouns
    if _COUNT_SUBJECT_RE.search(blob):
        return "units"
    if re.search(r"\bratio\b|\bx\b|multiplier", blob, re.I):
        return "ratio"
    return "unknown"


def extract_magnitude(text: str) -> Tuple[float, str]:
    """Find a magnitude keyword in text and return (multiplier, keyword_used).

    e.g. "1.2 billion" -> (1e9, "billion")
         "50 crore"    -> (1e7, "crore")
         "82"          -> (1.0, "")
    """
    low = text.lower()
    # longer suffixes first so "trillion" wins over "t"
    for key in sorted(_MAGNITUDE.keys(), key=len, reverse=True):
        if not key:
            continue
        if re.search(rf"\b{re.escape(key)}\b", low):
            return _MAGNITUDE[key], key
    return 1.0, ""


# ── Main entry: normalise (value, unit) into canonical (value, family) ──────

def normalise_value_unit(
    value: float,
    unit_raw: str,
    value_raw: str = "",
    magnitude_hint: Optional[str] = None,
    convert_to_usd: bool = False,
) -> Tuple[float, UnitFamily]:
    """Return (canonical_value, unit_family).

    Currency families are converted to BILLIONS of that currency (USD_B etc.).
    If `convert_to_usd=True`, also cross-convert to USD billions using the
    static rate table - useful when you want every cluster on a single axis.

    Percent is normalised to the 0-100 scale regardless of raw form (0.82
    becomes 82; 82% stays 82).

    units are normalised to MILLIONS of units.

    Double-scaling guard: LLMs sometimes emit BOTH the full-precision value
    (e.g. 110_600_000_000) AND a magnitude_hint ("billion"). We detect this
    by comparing the input `value` magnitude to the hint: if `value` already
    looks scaled (>= 1e6 for large hints) we ignore the hint.
    """
    family = detect_unit_family(unit_raw, value_raw)

    # Determine the candidate multiplier from explicit hint or scan of value_raw.
    if magnitude_hint:
        hint_multiplier = _MAGNITUDE.get(magnitude_hint.lower().strip(), 1.0)
    else:
        hint_multiplier, _ = extract_magnitude(f"{value_raw} {unit_raw}")

    # Sanity guard: a human never writes "110600000000 billion" - if the value
    # field is already in the millions-plus range AND we're about to multiply
    # by >= 1_000_000, the LLM double-reported. Trust the value, drop the hint.
    if hint_multiplier >= 1_000_000 and abs(value) >= 1_000_000:
        multiplier = 1.0
    elif hint_multiplier >= 1_000 and abs(value) >= 1_000_000_000:
        # even "thousand" hint on a billion-scale value is wrong
        multiplier = 1.0
    else:
        multiplier = hint_multiplier

    raw = value * multiplier

    if family in ("USD", "EUR", "GBP", "INR", "CNY", "JPY"):
        # Scale to billions
        canon = raw / 1e9
        # Sanity ceiling: no single market is worth > 500T in any currency.
        # A canon value beyond that is almost certainly a unit bug. Set to 0
        # so clustering + aggregation treats it as the sentinel zero.
        if abs(canon) > 500_000:   # 500 trillion in billions
            canon = 0.0
        if convert_to_usd and family != "USD":
            canon = canon * _CURRENCY_TO_USD[family]
            family = "USD"  # type: ignore[assignment]
        return canon, family  # type: ignore[return-value]

    if family == "percent":
        # Accept "0.82" or "82%" - assume >1 is already percent-scale
        pct = raw * 100 if 0 < raw <= 1.0 else raw
        # A percent value over ~300% is nearly always a CAGR-misread; null-out
        if abs(pct) > 300:
            pct = 0.0
        return pct, family

    if family == "units":
        return raw / 1e6, family

    if family in ("usd_per_unit", "ratio", "unknown"):
        return raw, family

    return raw, family


# ── Entity canonicalisation ─────────────────────────────────────────────────

# Common alias -> canonical name. Case-insensitive match. Extend as needed.
_ENTITY_ALIASES = {
    "nvidia": "NVIDIA", "nvda": "NVIDIA",
    "amd": "AMD", "advanced micro devices": "AMD",
    "intel": "Intel", "intc": "Intel",
    "tesla": "Tesla", "tsla": "Tesla",
    "apple": "Apple", "aapl": "Apple",
    "microsoft": "Microsoft", "msft": "Microsoft",
    "google": "Google", "alphabet": "Google", "googl": "Google",
    "meta": "Meta", "facebook": "Meta",
    "amazon": "Amazon", "aws": "Amazon",
    # Regions
    "us": "United States", "u.s.": "United States", "usa": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "britain": "United Kingdom",
    "eu": "European Union", "e.u.": "European Union", "eu-27": "European Union",
    "worldwide": "global", "world": "global", "international": "global",
    "globally": "global",
}


def canonical_entity(entity_raw: str) -> str:
    """Map entity to a canonical name; unknowns pass through with trimming."""
    if not entity_raw:
        return "global"
    low = entity_raw.strip().lower()
    return _ENTITY_ALIASES.get(low, entity_raw.strip())


# ── Segment canonicalisation ────────────────────────────────────────────────

# Segments are domain-specific and hard to exhaustively enumerate. We do
# light normalisation: trim, lowercase key, replace spaces with underscores,
# collapse known synonyms.
_SEGMENT_SYNONYMS = {
    "discrete gpu": "discrete_GPU", "dgpu": "discrete_GPU", "add-in board": "discrete_GPU",
    "integrated gpu": "integrated_GPU", "igpu": "integrated_GPU",
    "data center gpu": "datacenter_GPU", "dc gpu": "datacenter_GPU",
    "consumer gpu": "consumer_GPU", "gaming gpu": "consumer_GPU",
    "ev charging": "EV_charging", "electric vehicle charging": "EV_charging",
    "fast charging": "fast_charging", "ultra fast charging": "ultra_fast_charging",
}


def canonical_segment(segment_raw: Optional[str]) -> Optional[str]:
    if not segment_raw:
        return None
    low = segment_raw.strip().lower().replace("_", " ")
    if low in _SEGMENT_SYNONYMS:
        return _SEGMENT_SYNONYMS[low]
    # Default canonicalisation: strip punctuation, underscore-join
    cleaned = re.sub(r"[^a-z0-9\s]", "", low).strip()
    return cleaned.replace(" ", "_") if cleaned else None


# ── Convenience: build canonical tuple from a RawClaim-like dict ────────────

_VALID_TIME_PERIODS = {"FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2",
                       "month", "point", "ytd", "ttm", "unknown"}


def canonical_time_period(tp_raw: Optional[str]) -> str:
    """Map various time-period phrasings to canonical TimePeriod values."""
    if not tp_raw:
        return "FY"
    s = str(tp_raw).strip().lower().replace(" ", "")
    # Exact matches
    if s.upper() in _VALID_TIME_PERIODS:
        return s.upper() if s.upper() != "FY" else "FY"
    # Common variants
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


# ── Qualifier-key / value canonicalisation (Wikidata-style open vocabulary) ─

# Aliases: incoming qualifier keys from the LLM -> canonical names. Case- and
# punctuation-insensitive match. Unknown keys pass through unchanged (open
# vocabulary — LLM may emit topic-specific qualifiers we don't anticipate).
_QUALIFIER_KEY_ALIASES = {
    # subject / entity
    "entity": "subject", "company": "subject", "who": "subject",
    "player": "subject", "firm": "subject", "organization": "subject",
    "organisation": "subject", "actor": "subject",
    # metric kind
    "metric": "metric_kind", "measure": "metric_kind", "quantity": "metric_kind",
    "indicator": "metric_kind", "what": "metric_kind",
    # segment
    "sub_market": "segment", "submarket": "segment", "product": "segment",
    "product_type": "segment", "slice": "segment", "category": "segment",
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

# Known keys where we canonicalise the VALUE (not just the key). Keys not in
# this map pass through with only basic trimming + lowercasing of whitespace.
_QUALIFIER_VALUE_CANONICALISERS = {
    "subject":        lambda v: canonical_entity(v),
    "segment":        lambda v: canonical_segment(v) or v,
    "fiscal_period":  lambda v: canonical_time_period(v),
    "is_forecast":    lambda v: "true" if str(v).strip().lower() in
                               ("true", "yes", "1", "y", "forecast", "projection") else "false",
}


def canonical_qualifier_key(k: str) -> str:
    """Map a qualifier key to its canonical form. Unknown keys pass through
    (open-vocabulary — we don't want to silently drop topic-specific keys)."""
    if not k:
        return ""
    norm = k.strip().lower().replace("-", "_").replace(" ", "_")
    return _QUALIFIER_KEY_ALIASES.get(norm, norm)


def canonical_qualifier_value(key: str, value: str) -> str:
    """Normalise a qualifier VALUE. For well-known keys we apply a specific
    canonicaliser (e.g. company aliases, fiscal-period aliases). For unknown
    keys we just trim + strip surrounding quotes.
    """
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
    """Apply key- and value-canonicalisation to a raw qualifier dict emitted
    by the LLM. Drops empty values and `currency` (redundant with unit_family).
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
            # currency is already implied by unit_family; ignore to keep
            # qualifiers deduplicated
            continue
        cv = canonical_qualifier_value(ck, v)
        if not cv:
            continue
        out[ck] = cv
    return out

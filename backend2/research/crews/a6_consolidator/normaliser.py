"""Deterministic unit normalisation and claim deduplication for Agent 6.

No LLM calls. All logic is regex + lookup table — fully testable.
"""

from __future__ import annotations

import re
from research.core.types import NumericClaim


# ── Unit normalisation ────────────────────────────────────────────────────

_BILLION_RE  = re.compile(r"^([\$€£¥]?\s*)([\d.]+)\s*[Bb](illion)?$")
_TRILLION_RE = re.compile(r"^([\$€£¥]?\s*)([\d.]+)\s*[Tt](rillion)?$")
_MILLION_RE  = re.compile(r"^([\$€£¥]?\s*)([\d.]+)\s*[Mm](illion)?$")
_PCT_RE      = re.compile(r"^([\d.]+)\s*%$")
_CAGR_RE     = re.compile(r"^([\d.]+)\s*%\s*CAGR$", re.I)

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}

_UNIT_ALIASES: dict[str, str] = {
    "usd billion": "USD billion",
    "$ billion": "USD billion",
    "$b": "USD billion",
    "bn usd": "USD billion",
    "billion usd": "USD billion",
    "usd trillion": "USD trillion",
    "$ trillion": "USD trillion",
    "trillion usd": "USD trillion",
    "usd million": "USD million",
    "$ million": "USD million",
    "mn usd": "USD million",
    "million usd": "USD million",
    "gwh": "GWh",
    "twh": "TWh",
    "mwh": "MWh",
    "kwh": "kWh",
    "usd/kwh": "USD/kWh",
    "$/kwh": "USD/kWh",
    "%": "%",
    "percent": "%",
    "percentage points": "pp",
    "pps": "pp",
    "metric tonnes": "metric tonnes",
    "metric tons": "metric tonnes",
    "mt": "metric tonnes",
    "kt": "kilotonnes",
}


def normalise_unit(raw_unit: str) -> str:
    """Canonicalise a unit string using the alias table."""
    return _UNIT_ALIASES.get(raw_unit.strip().lower(), raw_unit.strip())


def normalise_value_string(raw_value: str) -> tuple[float | str, str]:
    """Parse a combined value+unit string like '$132B' into (132.0, 'USD billion').

    Returns the original string unchanged if no pattern matches.
    """
    s = raw_value.strip()

    # $132B / $132 billion
    m = _BILLION_RE.match(s)
    if m:
        sym, num = m.group(1).strip(), m.group(2)
        currency = _CURRENCY_SYMBOLS.get(sym, "USD") if sym else "USD"
        return float(num), f"{currency} billion"

    # $132T / $132 trillion
    m = _TRILLION_RE.match(s)
    if m:
        sym, num = m.group(1).strip(), m.group(2)
        currency = _CURRENCY_SYMBOLS.get(sym, "USD") if sym else "USD"
        return float(num), f"{currency} trillion"

    # $132M / $132 million
    m = _MILLION_RE.match(s)
    if m:
        sym, num = m.group(1).strip(), m.group(2)
        currency = _CURRENCY_SYMBOLS.get(sym, "USD") if sym else "USD"
        return float(num), f"{currency} million"

    # 38% CAGR
    m = _CAGR_RE.match(s)
    if m:
        return float(m.group(1)), "% CAGR"

    # 38%
    m = _PCT_RE.match(s)
    if m:
        return float(m.group(1)), "%"

    return raw_value, raw_value


def normalise_claim(claim: NumericClaim) -> NumericClaim:
    """Return a copy of the claim with unit canonicalised.

    If value is a string that embeds a unit (e.g. '$132B'), parse it out.
    """
    norm_unit = normalise_unit(claim.unit)

    if isinstance(claim.value, str):
        parsed_value, parsed_unit = normalise_value_string(claim.value)
        if parsed_unit != claim.value:
            norm_unit = parsed_unit
            return claim.model_copy(update={"value": parsed_value, "unit": norm_unit})

    return claim.model_copy(update={"unit": norm_unit})


# ── Deduplication ─────────────────────────────────────────────────────────

def _claim_key(c: NumericClaim) -> tuple:
    return (
        c.metric.lower().strip(),
        str(c.value).lower().strip(),
        c.unit.lower().strip(),
    )


def dedupe_claims(claims: list[NumericClaim]) -> list[NumericClaim]:
    """Remove exact duplicates — same (metric, value, unit) regardless of source.

    First occurrence (highest-authority source, since claims are fed in priority order)
    is kept; subsequent exact duplicates are dropped.
    Note: near-duplicates with different units are left for Agent 7 conflict resolution.
    """
    seen: set[tuple] = set()
    result: list[NumericClaim] = []
    for claim in claims:
        key = _claim_key(claim)
        if key not in seen:
            seen.add(key)
            result.append(claim)
    return result


def normalise_and_dedupe(claims: list[NumericClaim]) -> list[NumericClaim]:
    """Normalise units then deduplicate. Used by 6a before theme clustering."""
    normed = [normalise_claim(c) for c in claims]
    return dedupe_claims(normed)

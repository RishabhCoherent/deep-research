"""Pure-Python deterministic descriptor generator for the clusterer.

Format: "<subject> <metric_kind> [in <segment>] [(<scope>)] [for <as_of>]
         [(forecast)]"
"""
from __future__ import annotations

from .models import RawClaim


def describe_claim_template(claim: RawClaim) -> str:
    """Render a deterministic descriptor sentence from a claim's qualifiers.

    Identical qualifier dicts always produce identical strings -- enables
    exact-match clustering. Missing metric_kind surfaces visibly as
    "[unknown metric]" instead of being labelled "value" silently.
    """
    q = claim.qualifiers or {}
    subject = (q.get("subject") or "unknown subject").strip()
    metric = (q.get("metric_kind") or "[unknown metric]").replace("_", " ").strip()

    parts: list[str] = [subject, metric]

    seg = q.get("segment")
    if seg:
        parts.append(f"in {seg.replace('_', ' ')}")

    scope = q.get("scope")
    if scope:
        parts.append(f"({scope})")

    geo = q.get("geography")
    if geo and geo.lower() != subject.lower():
        parts.append(f"in {geo}")

    as_of = q.get("as_of")
    if as_of:
        fp = q.get("fiscal_period", "FY")
        if fp and fp != "FY":
            parts.append(f"as of {fp} {as_of}")
        else:
            parts.append(f"for {as_of}")

    if str(q.get("is_forecast", "")).lower() in ("true", "yes", "1"):
        parts.append("(forecast)")

    rep_std = q.get("reporting_standard")
    if rep_std:
        parts.append(f"[{rep_std}]")

    return " ".join(p for p in parts if p)[:400]


def describe_claims_template(claims: list[RawClaim]) -> list[RawClaim]:
    """Free, deterministic descriptor pass. Mutates each claim in-place."""
    for c in claims:
        c.descriptor = describe_claim_template(c)
    return claims

"""Generate canonical 'what is being measured' descriptors for raw claims.

Pure Python, free, deterministic. Identical qualifier dicts always produce
identical descriptor strings — perfect for downstream cosine + hash clustering
because exact-match descriptors collapse cleanly.

The historical LLM describer path (gpt-4o for natural-language descriptors)
was deleted in Phase 3a — empirically the template version produced
equivalent or better cluster quality at zero cost. Re-add via git history if
you ever need it back.

`_price_for_model` is kept here because the clusterer / validator / pipeline
all import their cost constants from this module — moving them would be a
larger refactor than is justified.
"""
from __future__ import annotations

from .models import RawClaim


# ── Pricing for cost accounting (used by clusterer/validator/pipeline) ─────

_GPT4O_INPUT_PER_M = 2.50
_GPT4O_OUTPUT_PER_M = 10.00
_GPT4O_MINI_INPUT_PER_M = 0.15
_GPT4O_MINI_OUTPUT_PER_M = 0.60


def _price_for_model(model: str) -> tuple[float, float]:
    """(input_per_M, output_per_M) USD."""
    m = model.lower()
    if "gpt-4o-mini" in m or "4o-mini" in m:
        return _GPT4O_MINI_INPUT_PER_M, _GPT4O_MINI_OUTPUT_PER_M
    if "gpt-4o" in m or "4o" in m:
        return _GPT4O_INPUT_PER_M, _GPT4O_OUTPUT_PER_M
    # Conservative default
    return _GPT4O_INPUT_PER_M, _GPT4O_OUTPUT_PER_M


# ── Template describer (the only one we ship) ──────────────────────────────

def describe_claim_template(claim: RawClaim) -> str:
    """Pure-Python deterministic descriptor — free, identical for identical inputs.

    Format: "<subject> <metric_kind> [in <segment>] [(<scope>)] [for <as_of>]
             [(forecast)]"

    Examples:
      qualifiers={subject: NVIDIA, metric_kind: market_share, segment: discrete_GPU,
                  as_of: 2024, fiscal_period: Q3}
        -> "NVIDIA market share in discrete GPU as of Q3 2024"
      qualifiers={subject: global, metric_kind: market_size, as_of: 2030,
                  is_forecast: true}
        -> "global market size for 2030 (forecast)"

    Identical qualifier dicts always produce identical strings — perfect for
    clustering because the embedder/cosine path will then collapse exact-match
    descriptors into the same cluster, AND the qualifier-hash path will too.
    """
    q = claim.qualifiers or {}
    subject = (q.get("subject") or "unknown subject").strip()
    # Fallback marker is intentionally visible so missing-metric_kind clusters
    # surface in the UI instead of being silently labeled "value".
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


def describe_claims_template(
    claims: list[RawClaim],
    *,
    on_progress=None,
) -> tuple[list[RawClaim], float]:
    """Free, deterministic descriptor pass. Returns (claims, 0.0)."""
    log = on_progress or (lambda _msg: None)
    if not claims:
        return claims, 0.0
    n_filled = 0
    for c in claims:
        c.descriptor = describe_claim_template(c)
        if c.descriptor:
            n_filled += 1
    log(f"[describer/template] {n_filled} descriptors generated (no LLM, $0.00)")
    return claims, 0.0

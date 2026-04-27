"""Agent 8c — Evidence Validator. Pure Python, zero LLM calls.

The ≥2-citation rule and independence check are enforced here, not in a prompt.
This is the primary anti-hallucination safeguard for Agent 8.
"""

from __future__ import annotations

from urllib.parse import urlparse

from research.core.types import Driver, Causation, CausationDraft


# ── Domain helpers ────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    """Extract the registrable hostname from a URL. Falls back to the raw string."""
    try:
        hostname = urlparse(url).hostname or url
        # Strip leading "www."
        return hostname.removeprefix("www.")
    except Exception:
        return url


# ── Single-driver validation ──────────────────────────────────────────────

def validate_driver(driver: Driver) -> tuple[Driver | None, str]:
    """Return (validated_driver, drop_reason).

    Returns (None, reason) if the driver is dropped.
    Returns (updated_driver, '') if the driver is kept.

    Validation rules (in order):
      1. ≥2 citations (hard minimum).
      2. ≥2 distinct domains (independence check).
      3. Confidence scoring:
           high   = ≥3 citations from ≥3 distinct authority tiers.
           medium = all other passing drivers.
    """
    # Rule 1: minimum 2 citations
    if len(driver.evidence) < 2:
        return None, f"only {len(driver.evidence)} citation(s), need ≥2"

    # Rule 2: at least 2 distinct domains
    domains = {_domain(c.url) for c in driver.evidence}
    if len(domains) < 2:
        return None, f"all citations from same domain ({next(iter(domains))})"

    # Rule 3: assign confidence
    tiers = {c.authority_tier for c in driver.evidence}
    if len(driver.evidence) >= 3 and len(tiers) >= 3:
        confidence = "high"
    else:
        confidence = "medium"

    return driver.model_copy(update={"confidence": confidence}), ""


# ── Draft → Causation ─────────────────────────────────────────────────────

def validate_causation(draft: CausationDraft) -> Causation:
    """Apply evidence validation rules to all candidate drivers.

    Drivers that fail are silently dropped.
    If all drivers fail, the Causation is returned with drivers=[] and
    confidence="low" — never backfilled with a fabricated story.
    """
    valid_drivers: list[Driver] = []

    for driver in draft.candidate_drivers:
        validated, _ = validate_driver(driver)
        if validated is not None:
            valid_drivers.append(validated)

    # Overall confidence = max across kept drivers
    if not valid_drivers:
        overall = "low"
    elif any(d.confidence == "high" for d in valid_drivers):
        overall = "high"
    else:
        overall = "medium"

    return Causation(
        metric=draft.metric,
        prior=draft.prior,
        current=draft.current,
        delta_pct=draft.delta_pct,
        drivers=valid_drivers,
        confidence=overall,
    )


def validate_all(drafts: list[CausationDraft]) -> list[Causation]:
    """Validate all drafts. Always returns same length list (empty drivers allowed)."""
    return [validate_causation(d) for d in drafts]

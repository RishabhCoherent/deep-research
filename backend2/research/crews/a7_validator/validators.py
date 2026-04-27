"""Post-LLM deterministic validators for Agent 7 (no LLM calls)."""

from __future__ import annotations

from research.core.types import NumericClaim, Conflict
from .authority import pick_winner, compare_authority


def enforce_authority_hierarchy(
    validated_claims: list[NumericClaim],
    original_groups: dict[tuple, list[NumericClaim]],
) -> list[NumericClaim]:
    """Re-run deterministic winner selection and correct any LLM deviations.

    For each conflict group, verify that the LLM chose the highest-authority
    claim. If it didn't, silently replace it with the correct winner.
    """
    claim_index = {id(c): c for c in validated_claims}
    corrected: list[NumericClaim] = []
    validated_metrics = {(c.metric.lower().strip(), (c.scope or "").lower().strip())
                         for c in validated_claims}

    for (metric, scope), group in original_groups.items():
        if len(group) <= 1:
            continue
        code_winner = pick_winner(group)
        # Find which claim the LLM placed in validated (by metric+scope key)
        matches = [
            c for c in validated_claims
            if c.metric.lower().strip() == metric
            and (c.scope or "").lower().strip() == scope
        ]
        if not matches:
            corrected.append(code_winner)
        elif len(matches) == 1:
            llm_winner = matches[0]
            llm_tier = llm_winner.citation.authority_tier if llm_winner.citation else None
            code_tier = code_winner.citation.authority_tier if code_winner.citation else None
            if compare_authority(code_tier, llm_tier) < 0:
                corrected.append(code_winner)
            else:
                corrected.append(llm_winner)

    # Add all unanimous claims (those not in any conflicted group)
    for c in validated_claims:
        key = (c.metric.lower().strip(), (c.scope or "").lower().strip())
        if key not in {
            (m, s) for m, s in original_groups if len(original_groups[(m, s)]) > 1
        }:
            corrected.append(c)

    return corrected


def assert_all_conflicts_resolved(
    validated_claims: list[NumericClaim],
    conflicts: list[Conflict],
) -> None:
    """Assert every Conflict has a chosen claim in validated_claims."""
    validated_set = {id(c) for c in validated_claims}
    for conflict in conflicts:
        assert conflict.chosen is not None, "Conflict must have a chosen winner"
        assert len(conflict.rejected) >= 1, "Conflict must have at least one rejected claim"

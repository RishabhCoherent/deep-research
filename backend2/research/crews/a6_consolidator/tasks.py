"""CrewAI tasks for Agent 6 - Consolidator. Sequential: 6a → 6b → 6c."""

from crewai import Task
from .schemas import NormalisedClaims, ThemeBundle, ConsolidatedNarrative


def build_tasks(normaliser, clusterer, builder):
    """Build three sequential tasks for Agent 6."""

    t_normalise = Task(
        description=(
            "Merge all numeric claims from Agents 3, 4, and 5. "
            "Normalise units to canonical form. Remove exact duplicates. "
            "Leave near-duplicates with different values intact for Agent 7. "
            "all_claims_json={all_claims_json}"
        ),
        expected_output="JSON matching NormalisedClaims: {claims: [NumericClaim, ...]}.",
        agent=normaliser,
        output_pydantic=NormalisedClaims,
    )

    t_cluster = Task(
        description=(
            "Group normalised claims and scratchpad observations into 5-8 analyst themes. "
            "Every theme must have at least 1 claim. "
            "normalised_claims_json={normalised_claims_json}, "
            "observations_json={observations_json}"
        ),
        expected_output="JSON matching ThemeBundle: {themes: [5-8 Theme objects]}.",
        agent=clusterer,
        context=[t_normalise],
        output_pydantic=ThemeBundle,
    )

    t_narrate = Task(
        description=(
            "Write an 800-1500 word bottom-up narrative. "
            "One ## section per theme. Executive Summary section LAST. "
            "Cite with [N] footnotes. "
            "chosen_query={chosen_query}, intent={intent}, themes_json={themes_json}"
        ),
        expected_output=(
            "JSON matching ConsolidatedNarrative: "
            "{narrative: '800-1500 word text with [N] refs', footnotes: [Footnote, ...]}."
        ),
        agent=builder,
        context=[t_normalise, t_cluster],
        output_pydantic=ConsolidatedNarrative,
    )

    return t_normalise, t_cluster, t_narrate

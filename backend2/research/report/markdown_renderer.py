"""Markdown renderer for the final research brief.

Takes the full RunState (or a ResearchBrief) and renders a structured
Markdown document with all sections populated.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from research.core.types import (
    RunState, Causation, Conflict, ConsolidatedReport, NumericClaim,
)

if TYPE_CHECKING:
    pass


# ── Section renderers ──────────────────────────────────────────────────────

def _render_header(state: RunState) -> str:
    today = date.today().isoformat()
    return (
        f"# Research Brief\n\n"
        f"**Query:** {state.get('chosen_query', state.get('original_query', ''))}\n\n"
        f"**Date:** {today}  |  **Run ID:** {state.get('run_id', 'N/A')}\n\n"
        f"---\n"
    )


def _render_consolidated(consolidated: ConsolidatedReport | None) -> str:
    """Render a6's output.

    Phase 4a: when `outline` is present, the narrative is a full L3-grade
    markdown document (Executive Summary + thesis sections with frameworks /
    causal chains / case studies / Contrarian View / Sources & References
    rendered verbatim by the prose pass). We render it as-is and let the LLM
    output drive the structure. Footnotes are appended only when the prose
    didn't already include a `## Sources & References` heading.

    Pre-Phase-4a: legacy single-pass narrative is wrapped in `## Summary`
    and footnotes are appended.
    """
    if not consolidated or not consolidated.narrative:
        return "## Summary\n\n*No consolidated narrative available.*\n\n"

    has_outline = consolidated.outline is not None and bool(consolidated.outline.sections)
    narrative = consolidated.narrative
    has_sources_already = (
        "## Sources & References" in narrative
        or "## Sources" in narrative
        or "## References" in narrative
    )

    if has_outline:
        # Outline-driven prose already starts with ## Executive Summary and
        # includes all structural sections — render verbatim.
        lines = [narrative]
    else:
        lines = ["## Summary\n", narrative]

    if consolidated.footnotes and not has_sources_already:
        lines.append("\n\n## Sources & References\n")
        for fn in consolidated.footnotes:
            url = fn.citation.url if fn.citation else "#"
            title = (fn.citation.title or url) if fn.citation else url
            lines.append(f"[{fn.n}] {title} — <{url}>")

    return "\n".join(lines) + "\n\n"


def _render_claims(claims: list[NumericClaim], heading: str) -> str:
    if not claims:
        return ""
    lines = [f"## {heading}\n"]
    for c in claims[:20]:
        cite = f"([{c.citation.authority_tier}]({c.citation.url}))" if c.citation else ""
        lines.append(f"- **{c.metric}**: {c.value} {c.unit}  {cite}")
    if len(claims) > 20:
        lines.append(f"- *…and {len(claims) - 20} more*")
    return "\n".join(lines) + "\n\n"


def _render_conflicts(conflicts: list[Conflict]) -> str:
    if not conflicts:
        return ""
    lines = ["## Resolved Conflicts\n"]
    for i, c in enumerate(conflicts[:10], 1):
        winner = c.chosen
        lines.append(
            f"**{i}. {winner.metric}** → chosen: {winner.value} {winner.unit} "
            f"({winner.citation.authority_tier if winner.citation else '?'})"
        )
        for rejected, reason in c.rejected:
            lines.append(
                f"   - ~~{rejected.value} {rejected.unit}~~ — {reason}"
            )
    return "\n".join(lines) + "\n\n"


def _render_causations(causations: list[Causation]) -> str:
    if not causations:
        return ""
    lines = ["## Causal Analysis\n"]
    for caus in causations:
        sign = "▲" if caus.delta_pct >= 0 else "▼"
        lines.append(f"### {caus.metric} ({sign}{abs(caus.delta_pct):.1f}%)\n")

        if caus.prior and caus.current:
            lines.append(
                f"**{caus.prior.value} {caus.prior.unit}** "
                f"({caus.prior.as_of or '?'}) → "
                f"**{caus.current.value} {caus.current.unit}** "
                f"({caus.current.as_of or '?'})\n"
            )

        if not caus.drivers:
            lines.append(
                "*Insufficient causal evidence found. "
                "No drivers with ≥2 independent citations.*\n"
            )
        else:
            for d in caus.drivers:
                conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(d.confidence, "⚪")
                lines.append(f"**{conf_emoji} {d.name}** ({d.confidence} confidence)")
                lines.append(f"   {d.description}")
                for ev in d.evidence:
                    title = ev.title or ev.url
                    lines.append(f"   - [{ev.authority_tier}] [{title}]({ev.url})")
                lines.append("")

    return "\n".join(lines) + "\n"


def _render_verification(verification: dict | None) -> str:
    """Render the a8.5 verifier output as a footer block.

    Surfaces grounding_score and warns when < 0.7. When fabricated claims
    were detected, lists them so the user can audit. Non-blocking — the
    brief is still readable; this just adds context.
    """
    if not verification or not isinstance(verification, dict):
        return ""
    score = float(verification.get("grounding_score") or 0.0)
    total = int(verification.get("total_claims") or 0)
    verified = int(verification.get("verified_claims") or 0)
    fabricated = verification.get("fabricated") or []
    uncertain = verification.get("uncertain") or []
    if total == 0:
        return ""

    badge = "[GREEN] HIGH" if score >= 0.85 \
        else ("[YELLOW] MODERATE" if score >= 0.7 else "[RED] LOW")

    lines = [
        "## Brief Grounding Check\n",
        f"**Grounding score:** {score:.0%} ({verified} of {total} factual "
        f"claims directly supported by evidence) — {badge}\n",
    ]
    if score < 0.7:
        lines.append(
            "_Below 0.7 grounding indicates the prose pass had thin "
            "evidence to ground against and may have included LLM-generated "
            "specifics not in the source set. Treat the unverified items "
            "below with caution._\n"
        )
    if fabricated:
        lines.append("### Likely fabricated\n")
        for c in fabricated[:10]:
            lines.append(f"- {c}")
        if len(fabricated) > 10:
            lines.append(f"- _...and {len(fabricated) - 10} more_")
        lines.append("")
    if uncertain:
        lines.append("### Uncertain (plausible but not directly stated)\n")
        for c in uncertain[:10]:
            lines.append(f"- {c}")
        if len(uncertain) > 10:
            lines.append(f"- _...and {len(uncertain) - 10} more_")
        lines.append("")
    return "\n".join(lines) + "\n\n"


def _format_cluster_value(unit_family: str, value: float) -> str:
    """Render the weighted-mean value with a domain-appropriate unit + scale."""
    if unit_family in ("USD", "EUR", "GBP", "INR", "CNY", "JPY"):
        symbol = {"USD": "$", "EUR": "EUR ", "GBP": "GBP ", "INR": "INR ",
                  "CNY": "CNY ", "JPY": "JPY "}.get(unit_family, f"{unit_family} ")
        # Auto-pick magnitude scale: B if >=1, M if >=0.001, else K
        if value >= 1.0:
            return f"{symbol}{value:.2f}B"
        if value >= 0.001:
            return f"{symbol}{value*1000:.2f}M"
        if value >= 0.000001:
            return f"{symbol}{value*1_000_000:.2f}K"
        return f"{symbol}{value*1_000_000_000:,.0f}"
    if unit_family == "percent":
        return f"{value:.1f}%"
    if unit_family == "months":
        return f"{value:.1f} months"
    if unit_family == "days":
        return f"{value:.1f} days"
    if unit_family == "ratio":
        return f"{value:.3f}"
    if unit_family == "score":
        return f"{value:.2f}"
    if unit_family == "count":
        return f"{value:,.0f}"
    return f"{value:.3g} {unit_family}"


def _render_dimensional_clusters(clusters: list[dict]) -> str:
    """Render the a6.5 dimensional clustering output.

    Each cluster groups numeric claims that measure the same dimension. The
    summary shows weighted_mean (tier-weighted across sources), spread,
    consensus level, and source count.
    """
    if not clusters:
        return ""
    # Sort: prefer multi-source + high-consensus clusters at the top
    _consensus_rank = {"high": 0, "medium": 1, "low": 2, "contested": 3, "single_source": 4}
    multi_source = [c for c in clusters if c.get("n_unique_sources", 0) >= 2]
    single = [c for c in clusters if c.get("n_unique_sources", 0) < 2]
    multi_source.sort(key=lambda c: (
        _consensus_rank.get(c.get("consensus_level", "single_source"), 5),
        -c.get("n_claims", 0),
    ))

    lines = [
        "## Dimensional Clusters\n",
        "_Numeric claims grouped by what they measure (subject + metric + "
        "segment + time slice). Each cluster's summary value is a tier-weighted "
        "mean across sources._\n",
    ]

    if multi_source:
        lines.append(f"### Multi-source consensus ({len(multi_source)})\n")
        for c in multi_source[:30]:
            dim = c.get("dimension", {})
            descriptor = dim.get("descriptor", "(no descriptor)")
            unit_family = dim.get("unit_family", "unknown")
            wmean = float(c.get("weighted_mean", 0.0))
            n_claims = c.get("n_claims", 0)
            n_sources = c.get("n_unique_sources", 0)
            consensus = c.get("consensus_level", "?")
            spread = c.get("pct_spread", 0.0)
            trend = c.get("trend_slope_pct_per_year")
            value_disp = _format_cluster_value(unit_family, wmean)
            trend_part = f" — trend {'+' if trend >= 0 else ''}{trend}%/yr" if trend is not None else ""
            lines.append(
                f"- **{descriptor}** -> {value_disp} "
                f"_(n={n_claims} from {n_sources} sources, "
                f"consensus={consensus}, spread={spread*100:.0f}%{trend_part})_"
            )

    n_single = len(single)
    if n_single:
        lines.append(f"\n### Single-source data points ({n_single})\n")
        for c in single[:15]:
            dim = c.get("dimension", {})
            descriptor = dim.get("descriptor", "(no descriptor)")
            unit_family = dim.get("unit_family", "unknown")
            wmean = float(c.get("weighted_mean", 0.0))
            value_disp = _format_cluster_value(unit_family, wmean)
            lines.append(f"- {descriptor}: {value_disp}")
        if n_single > 15:
            lines.append(f"- _...and {n_single - 15} more_")

    return "\n".join(lines) + "\n\n"


def _render_themes(consolidated: ConsolidatedReport | None) -> str:
    if not consolidated or not consolidated.themes:
        return ""
    lines = ["## Research Themes\n"]
    for t in consolidated.themes:
        lines.append(f"### {t.name}")
        lines.append(f"_{t.summary}_\n")
        for c in t.claims[:4]:
            lines.append(f"- {c.metric}: **{c.value} {c.unit}**")
        if len(t.claims) > 4:
            lines.append(f"- *…{len(t.claims) - 4} more claims*")
        lines.append("")
    return "\n".join(lines) + "\n"


# ── Main renderer ──────────────────────────────────────────────────────────

def render_markdown(state: RunState) -> str:
    """Render the complete research brief from a final RunState."""
    parts: list[str] = []

    parts.append(_render_header(state))
    parts.append(_render_consolidated(state.get("consolidated")))
    # Dimensional clusters live as a quantitative appendix AFTER the L3-grade
    # prose. The prose itself already weaves multi-source consensus values
    # into the analyst narrative — the appendix gives the full quantitative
    # view for readers who want to audit the numbers.
    parts.append(_render_dimensional_clusters(state.get("dimensional_clusters", [])))
    # Themes are now redundant when an outline is present (already in prose).
    # Render only as fallback for legacy runs.
    consolidated = state.get("consolidated")
    if not (consolidated and getattr(consolidated, "outline", None)):
        parts.append(_render_themes(consolidated))
    parts.append(_render_causations(state.get("causations", [])))
    parts.append(_render_conflicts(state.get("conflicts", [])))
    parts.append(_render_claims(state.get("validated_claims", []), "Validated Claims"))
    parts.append(_render_verification(state.get("verification")))

    return "".join(parts)


def render_to_file(state: RunState, output_path: str) -> None:
    """Write the markdown brief to a file."""
    content = render_markdown(state)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content

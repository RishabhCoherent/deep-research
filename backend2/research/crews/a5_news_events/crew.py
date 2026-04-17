"""CrewAI crew orchestration for Agent 5 - News & Events Researcher."""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process

from research.core.types import IntentKind, SubQuestion, NumericClaim, Observation
from research.core.errors import CrewFailure
from research.tools.web_search import reset_news_counter, get_news_call_count

from .agents import build_agents
from .tasks import build_tasks
from .schemas import EventBundle, RegulatoryBundle, GeopoliticalBundle, A5Output
from .validators import (
    filter_recent_events,
    filter_disruptions_with_evidence,
    filter_claims_with_citations,
    assert_narrative_word_count,
)

log = structlog.get_logger(__name__)


def build_a5_crew():
    hunter, tracker, scanner = build_agents()
    t_events, t_regulatory, t_geopolitical = build_tasks(hunter, tracker, scanner)
    return Crew(
        agents=[hunter, tracker, scanner],
        tasks=[t_events, t_regulatory, t_geopolitical],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


def _claims_from_bundles(
    events: EventBundle,
    regulatory: RegulatoryBundle,
    geo: GeopoliticalBundle,
) -> list[NumericClaim]:
    """Extract any embedded NumericClaims from event bundles (regulatory cost impacts)."""
    claims: list[NumericClaim] = []
    for change in regulatory.changes:
        if change.estimated_cost_impact and change.source:
            claims.append(NumericClaim(
                metric=f"Regulatory cost impact: {change.regulator}",
                value=change.estimated_cost_impact,
                unit="qualitative",
                raw_excerpt=change.action[:200],
                citation=change.source,
            ))
    return claims


def _narrative_from_bundles(
    events: EventBundle,
    regulatory: RegulatoryBundle,
    geo: GeopoliticalBundle,
    chosen_query: str,
) -> str:
    """Assemble a structured news narrative from the three bundles."""
    lines: list[str] = []

    lines.append(f"## Recent Events: {chosen_query}\n")

    if events.events:
        lines.append("### Market Events (Last 90 Days)")
        for e in events.events[:6]:
            sign = "▲" if e.impact == "positive" else ("▼" if e.impact == "negative" else "►")
            lines.append(f"- **{e.headline}** ({e.date}, {sign} {e.magnitude}): {e.summary}")
        lines.append("")

    if regulatory.changes:
        lines.append("### Regulatory Changes")
        for r in regulatory.changes:
            cost = f" Cost impact: {r.estimated_cost_impact}." if r.estimated_cost_impact else ""
            eff = f" Effective {r.effective_date}." if r.effective_date else ""
            lines.append(f"- **{r.regulator}**: {r.action}{eff}{cost} {r.impact_summary}")
        lines.append("")

    if geo.disruptions:
        lines.append("### Geopolitical Supply-Chain Risks")
        for d in geo.disruptions:
            sev_emoji = {"watch": "⚠", "elevated": "🔶", "critical": "🔴"}.get(d.severity, "⚠")
            lines.append(
                f"- {sev_emoji} **{d.upstream_node}** ({d.severity.upper()}): "
                f"{d.event} Path: {d.supply_chain_path}"
            )

    return "\n".join(lines)


async def run_a5(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
) -> A5Output:
    """Run Agent 5 - News & Events Researcher. Fully autonomous.

    Returns A5Output with validated claims, narrative, and scratchpad observations.
    5a and 5b run concurrently; 5c runs after both complete.
    """
    reset_news_counter()

    crew = build_a5_crew()
    result = await crew.kickoff_async(
        inputs={
            "chosen_query": chosen_query,
            "intent":       intent.value,
        }
    )

    events: EventBundle        = result.tasks_output[0].pydantic
    regulatory: RegulatoryBundle = result.tasks_output[1].pydantic
    geo: GeopoliticalBundle    = result.tasks_output[2].pydantic

    if any(x is None for x in [events, regulatory, geo]):
        raise CrewFailure("Agent 5 returned one or more unparseable sub-agent outputs.")

    # ── Post-LLM deterministic validation ────────────────────────────────
    recent_events   = filter_recent_events(events.events)
    valid_disruptions = filter_disruptions_with_evidence(geo.disruptions)
    raw_claims      = _claims_from_bundles(events, regulatory, geo)
    valid_claims    = filter_claims_with_citations(raw_claims)

    dropped = (len(events.events) - len(recent_events)) + (len(geo.disruptions) - len(valid_disruptions))
    if dropped:
        log.warning("a5_news_events.dropped", dropped=dropped)

    narrative = _narrative_from_bundles(
        EventBundle(events=recent_events),
        regulatory,
        GeopoliticalBundle(disruptions=valid_disruptions,
                           scratchpad_writes=geo.scratchpad_writes),
        chosen_query,
    )

    try:
        assert_narrative_word_count(narrative, lo=100, hi=1200)
    except AssertionError as exc:
        log.warning("a5_news_events.narrative_word_count_failed", error=str(exc))

    log.info("a5_news_events.done",
             events=len(recent_events),
             regulatory=len(regulatory.changes),
             disruptions=len(valid_disruptions),
             claims=len(valid_claims),
             news_calls=get_news_call_count(),
             narrative_words=len(narrative.split()))

    return A5Output(
        claims=valid_claims,
        narrative=narrative,
        scratchpad_writes=geo.scratchpad_writes,
    )

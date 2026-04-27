"""CrewAI crew orchestration for Agent 5 - News & Events Researcher.

Architecture (3 isolated crews):
  Phase 1a — event_hunter (Haiku):        market/M&A/product news → EventBundle
  Phase 1b — regulatory_tracker (Haiku):  policy/tariff/subsidy news → RegulatoryBundle
  1a and 1b run concurrently via asyncio.gather().
  Phase 2  — geopolitical_scanner (Sonnet): upstream disruptions → GeopoliticalBundle

Narrative is assembled deterministically in Python — no LLM call needed.
"""

from __future__ import annotations

import asyncio
import json
import structlog

from crewai import Crew, Process, Task

from research.core.types import IntentKind, SubQuestion, NumericClaim, Observation
from research.tools.web_search import reset_news_counter, get_news_call_count

from .agents import build_agents
from .schemas import EventBundle, RegulatoryBundle, GeopoliticalBundle, A5Output
from .validators import (
    filter_recent_events,
    filter_disruptions_with_evidence,
    filter_claims_with_citations,
    assert_narrative_word_count,
)

log = structlog.get_logger(__name__)


# ── Phase 1a: event_hunter ────────────────────────────────────────────────────

def _build_events_crew(hunter) -> Crew:
    task = Task(
        description=(
            "Find significant news/events from the last 90 days that are "
            "relevant to the topic profile below. The KIND of news to look "
            "for depends on the domain: market topics want company / product "
            "/ M&A / earnings / investment news; clinical topics want trial "
            "readouts / drug approvals / safety signals / publications; "
            "policy topics want legislation / agency rulings / programme "
            "launches; social-science topics want major studies / surveys / "
            "policy interventions. Use the topic profile to choose categories "
            "appropriate to the domain — do NOT default to market-research "
            "categories when the profile says the topic isn't market research. "
            "intent={intent}, chosen_query={chosen_query}\n\n"
            "{topic_profile_block}"
        ),
        expected_output="JSON matching EventBundle: {events: [NewsEvent, ...]}.",
        agent=hunter,
        output_pydantic=EventBundle,
    )
    return Crew(agents=[hunter], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Phase 1b: regulatory_tracker ─────────────────────────────────────────────

def _build_regulatory_crew(tracker) -> Crew:
    task = Task(
        description=(
            "Find regulatory / policy / official-guidance changes from the "
            "last 90 days that are relevant to the topic profile below. The "
            "kind of regulator depends on the domain: market topics watch "
            "antitrust / tariff / subsidy bodies; clinical topics watch FDA / "
            "EMA / NICE / CADTH; policy topics watch the relevant ministry "
            "or regulator named in the profile; social-science topics may "
            "have very few formal regulatory changes (return an empty list "
            "if none apply). Use the topic profile's domain to pick the "
            "right authority sources — do NOT default to tariff / antitrust "
            "for clinical or social-science topics. "
            "intent={intent}, chosen_query={chosen_query}\n\n"
            "{topic_profile_block}"
        ),
        expected_output="JSON matching RegulatoryBundle: {changes: [RegulatoryChange, ...]}.",
        agent=tracker,
        output_pydantic=RegulatoryBundle,
    )
    return Crew(agents=[tracker], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Phase 2: geopolitical_scanner ─────────────────────────────────────────────

def _build_geo_crew(scanner) -> Crew:
    task = Task(
        description=(
            "Find supply / availability / disruption events that could "
            "affect the topic. For market topics with a value chain in "
            "scratchpad section 'market_context': read upstream nodes and "
            "search for sanctions / conflicts / shortages on each. For "
            "clinical topics: focus on drug-supply shortages, manufacturing "
            "recalls, trial-site disruptions. For policy topics: focus on "
            "implementation delays, programme funding cuts, jurisdictional "
            "challenges. For social-science topics: this category often "
            "doesn't apply — return an empty disruptions list if so. "
            "Read whichever scratchpad sections are populated; do NOT "
            "require 'market_context' to exist. Write any elevated/critical "
            "findings to scratchpad section='news'. "
            "intent={intent}, chosen_query={chosen_query}\n\n"
            "{topic_profile_block}"
        ),
        expected_output=(
            "JSON matching GeopoliticalBundle: "
            "{disruptions: [Disruption, ...], scratchpad_writes: [Observation, ...]}."
        ),
        agent=scanner,
        output_pydantic=GeopoliticalBundle,
    )
    return Crew(agents=[scanner], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_a5(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
    topic_profile=None,   # research.core.topic_profile.TopicProfile | None
) -> A5Output:
    """Run Agent 5 - News & Events Researcher (3 isolated phases, 1a+1b concurrent).

    `topic_profile` (optional) is rendered into every task description as a
    TOPIC PROFILE block so the event hunter, regulatory tracker, and
    geopolitical scanner all understand what KIND of news/regulation/disruption
    is relevant for this topic — without baking market-research vocabulary
    into the prompts.
    """
    reset_news_counter()

    if topic_profile is not None:
        topic_profile_block = (
            "TOPIC PROFILE (use as the domain anchor — pick news / regulator / "
            "disruption categories appropriate to this domain):\n"
            + topic_profile.to_user_message_block()
        )
    else:
        topic_profile_block = "TOPIC PROFILE: (none provided)"

    hunter, tracker, scanner = build_agents()
    inputs_base = {
        "chosen_query":        chosen_query,
        "intent":              intent.value,
        "topic_profile_block": topic_profile_block,
    }

    # ── Phase 1a + 1b: concurrent ────────────────────────────────────────────
    events_result, regulatory_result = await asyncio.gather(
        _run_events(hunter, inputs_base),
        _run_regulatory(tracker, inputs_base),
    )
    events: EventBundle       = events_result
    regulatory: RegulatoryBundle = regulatory_result

    log.info("a5_news_events.phase1_done",
             events=len(events.events), regulatory=len(regulatory.changes))

    # ── Phase 2: geopolitical (sequential, uses scratchpad from A4b) ─────────
    geo: GeopoliticalBundle = await _run_geo(scanner, inputs_base)

    log.info("a5_news_events.phase2_done",
             disruptions=len(geo.disruptions), scratchpad_writes=len(geo.scratchpad_writes))

    # ── Post-LLM deterministic validation ─────────────────────────────────────
    recent_events      = filter_recent_events(events.events)
    valid_disruptions  = filter_disruptions_with_evidence(geo.disruptions)
    raw_claims         = _claims_from_bundles(events, regulatory, geo)
    valid_claims       = filter_claims_with_citations(raw_claims)

    dropped = (len(events.events) - len(recent_events)) + (len(geo.disruptions) - len(valid_disruptions))
    if dropped:
        log.warning("a5_news_events.dropped", dropped=dropped)

    narrative = _narrative_from_bundles(
        EventBundle(events=recent_events),
        regulatory,
        GeopoliticalBundle(disruptions=valid_disruptions, scratchpad_writes=geo.scratchpad_writes),
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


# ── Phase runners with isolated error handling ────────────────────────────────

async def _run_events(hunter, inputs: dict) -> EventBundle:
    try:
        r = await _build_events_crew(hunter).kickoff_async(inputs=inputs)
        result = r.tasks_output[0].pydantic
        if result is None:
            result = _repair_events(Exception(r.tasks_output[0].raw or ""))
        return result
    except Exception as exc:
        log.warning("a5_news_events.events_failed_trying_repair", error=str(exc)[:200])
        return _repair_events(exc)


async def _run_regulatory(tracker, inputs: dict) -> RegulatoryBundle:
    try:
        r = await _build_regulatory_crew(tracker).kickoff_async(inputs=inputs)
        result = r.tasks_output[0].pydantic
        if result is None:
            result = _repair_regulatory(Exception(r.tasks_output[0].raw or ""))
        return result
    except Exception as exc:
        log.warning("a5_news_events.regulatory_failed_trying_repair", error=str(exc)[:200])
        return _repair_regulatory(exc)


async def _run_geo(scanner, inputs: dict) -> GeopoliticalBundle:
    try:
        r = await _build_geo_crew(scanner).kickoff_async(inputs=inputs)
        result = r.tasks_output[0].pydantic
        if result is None:
            result = _repair_geo(Exception(r.tasks_output[0].raw or ""))
        return result
    except Exception as exc:
        log.warning("a5_news_events.geo_failed_trying_repair", error=str(exc)[:200])
        return _repair_geo(exc)


# ── Deterministic narrative assembly ──────────────────────────────────────────

def _claims_from_bundles(
    events: EventBundle,
    regulatory: RegulatoryBundle,
    geo: GeopoliticalBundle,
) -> list[NumericClaim]:
    """Distil events / regulatory / geo bundles into NumericClaim objects so
    A6/A7/A8 can cluster and cross-reference them. Events and disruptions are
    inherently qualitative, so we encode magnitude/severity as the value with
    a qualitative unit label.
    """
    claims: list[NumericClaim] = []

    # 5a — each news event becomes a qualitative claim keyed by category
    for e in events.events:
        if not e.source:
            continue
        claims.append(NumericClaim(
            metric=f"News event ({e.category}): {e.headline[:120]}",
            value=f"{e.impact}/{e.magnitude}",
            unit="impact_magnitude",
            as_of=str(e.date) if e.date else None,
            raw_excerpt=e.summary[:200],
            citation=e.source,
        ))

    # 5b — regulatory changes: keep the cost-impact claim (if present) and
    # also emit a qualitative claim for every change so A6 has coverage
    for change in regulatory.changes:
        if not change.source:
            continue
        if change.estimated_cost_impact:
            claims.append(NumericClaim(
                metric=f"Regulatory cost impact: {change.regulator}",
                value=change.estimated_cost_impact,
                unit="qualitative",
                as_of=str(change.effective_date) if change.effective_date else None,
                raw_excerpt=change.action[:200],
                citation=change.source,
            ))
        claims.append(NumericClaim(
            metric=f"Regulatory action: {change.regulator}",
            value=change.action[:80],
            unit="policy",
            as_of=str(change.effective_date) if change.effective_date else None,
            raw_excerpt=change.impact_summary[:200] or change.action[:200],
            citation=change.source,
        ))

    # 5c — geopolitical disruptions: qualitative claim keyed by upstream node
    for d in geo.disruptions:
        if not d.evidence:
            continue
        claims.append(NumericClaim(
            metric=f"Supply disruption: {d.upstream_node}",
            value=d.severity,
            unit="severity",
            raw_excerpt=d.event[:200],
            citation=d.evidence[0],
        ))

    return claims


def _narrative_from_bundles(
    events: EventBundle,
    regulatory: RegulatoryBundle,
    geo: GeopoliticalBundle,
    chosen_query: str,
) -> str:
    lines: list[str] = [f"## Recent Events: {chosen_query}\n"]

    # Section headers are intentionally generic — works for market, clinical,
    # policy, social-science topics alike. The event hunter / regulatory
    # tracker / geo scanner each pick domain-appropriate items per the topic
    # profile they were given upstream.
    if events.events:
        lines.append("### Recent Events (Last 90 Days)")
        for e in events.events[:6]:
            sign = "(+)" if e.impact == "positive" else ("(-)" if e.impact == "negative" else "(~)")
            lines.append(f"- **{e.headline}** ({e.date}, {sign} {e.magnitude}): {e.summary}")
        lines.append("")

    if regulatory.changes:
        lines.append("### Regulatory / Policy Changes")
        for r in regulatory.changes:
            cost = f" Cost impact: {r.estimated_cost_impact}." if r.estimated_cost_impact else ""
            eff = f" Effective {r.effective_date}." if r.effective_date else ""
            lines.append(f"- **{r.regulator}**: {r.action}{eff}{cost} {r.impact_summary}")
        lines.append("")

    if geo.disruptions:
        lines.append("### Disruptions / Supply Risks")
        for d in geo.disruptions:
            sev_label = {"watch": "[!]", "elevated": "[!!]", "critical": "[!!!]"}.get(d.severity, "[!]")
            lines.append(
                f"- {sev_label} **{d.upstream_node}** ({d.severity.upper()}): "
                f"{d.event} Path: {d.supply_chain_path}"
            )

    return "\n".join(lines)


# ── Repair helpers ─────────────────────────────────────────────────────────────

def _extract_raw(exc: Exception) -> str:
    from pydantic import ValidationError as PydanticVE
    if isinstance(exc, PydanticVE):
        for err in exc.errors():
            val = err.get("input")
            if isinstance(val, str) and "{" in val:
                return val
    return str(exc)


def _try_repair(raw: str) -> dict | list | None:
    import json_repair
    try:
        start = raw.find("{")
        if start == -1:
            start = raw.find("[")
        if start != -1:
            return json.loads(json_repair.repair_json(raw[start:]))
    except Exception:
        pass
    return None


def _repair_events(exc: Exception) -> EventBundle:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return EventBundle.model_validate(data if isinstance(data, dict) else {"events": data})
        except Exception:
            pass
    return EventBundle(events=[])


def _repair_regulatory(exc: Exception) -> RegulatoryBundle:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return RegulatoryBundle.model_validate(data if isinstance(data, dict) else {"changes": data})
        except Exception:
            pass
    return RegulatoryBundle(changes=[])


def _repair_geo(exc: Exception) -> GeopoliticalBundle:
    data = _try_repair(_extract_raw(exc))
    if isinstance(data, dict):
        try:
            return GeopoliticalBundle.model_validate(data)
        except Exception:
            pass
    return GeopoliticalBundle(disruptions=[], scratchpad_writes=[])

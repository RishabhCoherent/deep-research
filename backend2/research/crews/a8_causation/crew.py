"""CrewAI crew orchestration for Agent 8 - Causation / Reasoning.

Crew: 2 isolated single-task crews (8a Haiku + 8b Sonnet) + 1 pure Python step (8c).
8c (evidence_validator) enforces the ≥2-citation rule — no LLM can override it.
"""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process, Task

from research.core.types import NumericClaim, Observation, Causation, CausationDraft

from .agents import build_agents
from .schemas import DeltaBundle, CorrelatedEvents, A8Output
from .delta_detector import detect_deltas
from .evidence_validator import validate_all

log = structlog.get_logger(__name__)


# ── Phase builders ────────────────────────────────────────────────────────────

def _build_delta_crew(detector) -> Crew:
    task = Task(
        description=(
            "Identify validated claims that appear at two different dates. "
            "Compute delta_pct for each metric pair. "
            "Sort by abs(delta_pct) descending. "
            "validated_claims_json={validated_claims_json}, "
            "precomputed_deltas_json={precomputed_deltas_json}"
        ),
        expected_output="JSON matching DeltaBundle: {deltas: [Delta, ...]}.",
        agent=detector,
        output_pydantic=DeltaBundle,
    )
    return Crew(agents=[detector], tasks=[task], process=Process.sequential, verbose=False, memory=False)


def _build_correlate_crew(correlator) -> Crew:
    task = Task(
        description=(
            "For each delta, read ALL available scratchpad sections first "
            "(common section names: 'topic', 'news', 'market_context' — only "
            "the ones that are populated). Then search for causal events "
            "within each delta's time window. Each Driver must have at least "
            "2 citations from 2 independent domains. Hard cap: 5 total "
            "searches. chosen_query={chosen_query}, deltas_json={deltas_json}"
        ),
        expected_output=(
            "JSON matching CorrelatedEvents: "
            "{causations: [CausationDraft with candidate_drivers]}."
        ),
        agent=correlator,
        output_pydantic=CorrelatedEvents,
    )
    return Crew(agents=[correlator], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_a8(
    *,
    validated_claims: list[NumericClaim],
    news_narrative: str,
    scratchpad_notes: list[Observation],
    chosen_query: str,
) -> A8Output:
    """Run Agent 8 - Causation / Reasoning.

    Flow:
      1. detect_deltas() — deterministic pre-processing
      2. 8a delta_detector (Haiku) — semantic fuzzy matching for edge cases
      3. 8b event_correlator (Sonnet) — search for causal events, ≤5 searches
      4. validate_all() — pure Python ≥2-citation rule (8c)
    """
    if not validated_claims:
        log.warning("a8_causation.no_validated_claims")
        return A8Output(causations=[])

    # ── Pre-compute (deterministic) ─────────────────────────────────────
    precomputed_deltas = detect_deltas(validated_claims)
    validated_json = json.dumps([c.model_dump() for c in validated_claims], default=str)
    precomputed_json = json.dumps([d.model_dump() for d in precomputed_deltas], default=str)

    detector, correlator = build_agents()

    # ── Phase 1: delta detection (Haiku, no tools) ────────────────────────
    bundle = DeltaBundle(deltas=precomputed_deltas)
    try:
        r1 = await _build_delta_crew(detector).kickoff_async(inputs={
            "validated_claims_json":   validated_json,
            "precomputed_deltas_json": precomputed_json,
        })
        result = r1.tasks_output[0].pydantic
        if result is None:
            result = _repair_bundle(Exception(r1.tasks_output[0].raw or ""), precomputed_deltas)
        bundle = result
    except Exception as exc:
        log.warning("a8_causation.delta_failed_using_precomputed", error=str(exc)[:200])
        bundle = DeltaBundle(deltas=precomputed_deltas)

    log.info("a8_causation.deltas_found", count=len(bundle.deltas))

    if not bundle.deltas:
        log.info("a8_causation.no_deltas_skipping_correlator")
        return A8Output(causations=[])

    deltas_json = json.dumps([d.model_dump() for d in bundle.deltas], default=str)

    # ── Phase 2: event correlation (Sonnet, web_search, max_iter=6) ───────
    correlated = CorrelatedEvents(causations=[])
    try:
        r2 = await _build_correlate_crew(correlator).kickoff_async(inputs={
            "chosen_query": chosen_query,
            "deltas_json":  deltas_json,
        })
        result = r2.tasks_output[0].pydantic
        if result is None:
            result = _repair_correlated(Exception(r2.tasks_output[0].raw or ""), bundle.deltas)
        correlated = result
    except Exception as exc:
        log.warning("a8_causation.correlate_failed_using_empty", error=str(exc)[:200])
        correlated = _repair_correlated(exc, bundle.deltas)

    # ── 8c: Pure Python evidence validation ──────────────────────────────
    causations = validate_all(correlated.causations)

    total_drivers = sum(len(c.drivers) for c in causations)
    log.info("a8_causation.done",
             deltas=len(bundle.deltas),
             causations=len(causations),
             validated_drivers=total_drivers)

    return A8Output(causations=causations)


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


def _repair_bundle(exc: Exception, fallback: list) -> DeltaBundle:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return DeltaBundle.model_validate(data if isinstance(data, dict) else {"deltas": data})
        except Exception:
            pass
    return DeltaBundle(deltas=fallback)


def _repair_correlated(exc: Exception, deltas) -> CorrelatedEvents:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return CorrelatedEvents.model_validate(data if isinstance(data, dict) else {"causations": data})
        except Exception:
            pass
    # Fallback: empty-driver causations for each delta
    fallback = [
        CausationDraft(
            metric=d.metric,
            prior=d.prior,
            current=d.current,
            delta_pct=d.delta_pct,
            candidate_drivers=[],
        )
        for d in deltas
    ]
    return CorrelatedEvents(causations=fallback)

"""CrewAI crew orchestration for Agent 6 - Consolidator.

Architecture (3 isolated single-task crews, no tools):
  Phase 1 — claim_normaliser (Haiku):   merge + normalise claims → NormalisedClaims
  Phase 2 — theme_clusterer (Haiku):    group into themes → ThemeBundle
  Phase 3 — narrative_builder (Sonnet): write bottom-up narrative → ConsolidatedNarrative
"""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process, Task

from research.core.types import (
    IntentKind, NumericClaim, Observation,
    Theme, ConsolidatedReport,
)

from .agents import build_agents
from .schemas import NormalisedClaims, ThemeBundle, ConsolidatedNarrative, A6Output
from .normaliser import normalise_and_dedupe
from .compose_two_pass import compose_two_pass
from .validators import (
    assert_bottom_up_structure,
    assert_footnote_integrity,
    assert_theme_coverage,
)

log = structlog.get_logger(__name__)


# ── Phase builders ────────────────────────────────────────────────────────────

def _build_normalise_crew(normaliser) -> Crew:
    task = Task(
        description=(
            "Merge all numeric claims from Agents 3/4/5. Normalise units to canonical form. "
            "Remove exact duplicates (same metric+value+unit). Keep near-duplicates for A7.\n\n"
            "All claims:\n{all_claims_json}"
        ),
        expected_output="JSON matching NormalisedClaims: {claims: [NumericClaim, ...]}.",
        agent=normaliser,
        output_pydantic=NormalisedClaims,
    )
    return Crew(agents=[normaliser], tasks=[task], process=Process.sequential, verbose=False, memory=False)


def _build_cluster_crew(clusterer) -> Crew:
    task = Task(
        description=(
            "Group the normalised claims and scratchpad observations into 3-8 analyst themes. "
            "Every theme must have at least 1 claim. "
            "aim for themes: Supply Chain, Raw Materials, Market Dynamics, Regulatory, Technology.\n\n"
            "Normalised claims:\n{normalised_claims_json}\n\n"
            "Scratchpad observations:\n{observations_json}"
        ),
        expected_output="JSON matching ThemeBundle: {themes: [3-8 Theme objects]}.",
        agent=clusterer,
        output_pydantic=ThemeBundle,
    )
    return Crew(agents=[clusterer], tasks=[task], process=Process.sequential, verbose=False, memory=False)


def _build_narrate_crew(builder) -> Crew:
    task = Task(
        description=(
            "Write an 800-1500 word bottom-up analyst narrative. "
            "One ## section per theme, Executive Summary LAST. Cite with [N] footnotes.\n\n"
            "chosen_query={chosen_query}, intent={intent}\n\n"
            "Themes and claims:\n{themes_json}"
        ),
        expected_output=(
            "JSON matching ConsolidatedNarrative: "
            "{narrative: '800-1500 word text with [N] refs', footnotes: [Footnote, ...]}."
        ),
        agent=builder,
        output_pydantic=ConsolidatedNarrative,
    )
    return Crew(agents=[builder], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_a6(
    *,
    chosen_query: str,
    intent: IntentKind,
    topic_claims: list[NumericClaim],
    market_claims: list[NumericClaim],
    news_claims: list[NumericClaim],
    topic_narrative: str,
    market_narrative: str,
    news_narrative: str,
    scratchpad_notes: list[Observation],
    topic_profile=None,                   # research.core.topic_profile.TopicProfile | None
    dimensional_clusters: list[dict] | None = None,
) -> A6Output:
    """Run Agent 6 - Consolidator.

    Architecture (Phase 4a):
      Phase 1 - claim_normaliser (Haiku):  merge + normalise -> NormalisedClaims
      Phase 2 - theme_clusterer (Haiku):   group into themes -> ThemeBundle
      Phase 3 - compose_two_pass (DIRECT LLM calls, no CrewAI):
        - Pass 3a (opus tier): produce ReportOutline
        - Pass 3b (sonnet tier): fill prose against outline + evidence

    `topic_profile` and `dimensional_clusters` are new in Phase 4a and steer
    the two-pass compose so the brief looks domain-appropriate and weaves
    multi-source consensus values into the narrative.
    """
    if dimensional_clusters is None:
        dimensional_clusters = []

    # Deterministic pre-normalisation before LLM sees data
    all_claims_raw = topic_claims + market_claims + news_claims
    pre_normed = normalise_and_dedupe(all_claims_raw)
    all_claims_json = json.dumps([c.model_dump() for c in pre_normed], default=str)
    observations_json = json.dumps([o.model_dump() for o in scratchpad_notes], default=str)

    normaliser, clusterer, builder = build_agents()

    # ── Phase 1: normalise ────────────────────────────────────────────────────
    normed = NormalisedClaims(claims=pre_normed)  # safe fallback = Python pre-normed
    try:
        r1 = await _build_normalise_crew(normaliser).kickoff_async(
            inputs={"all_claims_json": all_claims_json}
        )
        result = r1.tasks_output[0].pydantic
        if result is None:
            result = _repair_normed(Exception(r1.tasks_output[0].raw or ""), pre_normed)
        normed = result
    except Exception as exc:
        log.warning("a6_consolidator.normalise_failed_trying_repair", error=str(exc)[:200])
        normed = _repair_normed(exc, pre_normed)

    log.info("a6_consolidator.normalise_done", claims=len(normed.claims))
    normed_json = json.dumps([c.model_dump() for c in normed.claims], default=str)

    # ── Phase 2: cluster themes ───────────────────────────────────────────────
    bundle = ThemeBundle(themes=[])
    try:
        r2 = await _build_cluster_crew(clusterer).kickoff_async(inputs={
            "normalised_claims_json": normed_json,
            "observations_json":      observations_json,
        })
        result = r2.tasks_output[0].pydantic
        if result is None:
            result = _repair_bundle(Exception(r2.tasks_output[0].raw or ""), normed.claims)
        bundle = result
    except Exception as exc:
        log.warning("a6_consolidator.cluster_failed_trying_repair", error=str(exc)[:200])
        bundle = _repair_bundle(exc, normed.claims)

    # Drop empty-claim themes before the narrative sees them.
    # Prompt says every theme must have >= 1 claim; LLM sometimes emits placeholders
    # (e.g. "Supply Chain" with 0 supporting claims). Those pollute the narrative.
    before_filter = len(bundle.themes)
    bundle.themes = [t for t in bundle.themes if t.claims]
    dropped_empty = before_filter - len(bundle.themes)
    if dropped_empty:
        log.info("a6_consolidator.dropped_empty_themes", dropped=dropped_empty)

    log.info("a6_consolidator.cluster_done", themes=len(bundle.themes))
    themes_json = json.dumps(
        [{"name": t.name, "summary": t.summary,
          "claims": [c.model_dump() for c in t.claims],
          "observations": [o.model_dump() for o in t.observations]}
         for t in bundle.themes],
        default=str
    )

    # ── Phase 3: TWO-PASS COMPOSE (direct LLM calls, no CrewAI) ─────────────
    # Replaces the old single-shot narrative builder. Pass 1 produces a
    # structured ReportOutline (sections + frameworks + causal chains + case
    # studies + contrarian + key_stats); Pass 2 fills the prose. The L3-grade
    # structural sophistication lives entirely in this step.
    consolidated = await compose_two_pass(
        chosen_query=chosen_query,
        topic_profile=topic_profile,
        claims=normed.claims,
        themes=bundle.themes,
        dimensional_clusters=dimensional_clusters,
    )

    # ── Post-compose deterministic validation (best-effort, non-blocking) ──
    try:
        assert_theme_coverage(bundle.themes, total_claims=len(normed.claims))
    except AssertionError as exc:
        log.warning("a6_consolidator.theme_coverage_failed", error=str(exc))

    try:
        assert_bottom_up_structure(consolidated.narrative)
    except AssertionError as exc:
        log.warning("a6_consolidator.bottom_up_check_failed", error=str(exc))

    try:
        assert_footnote_integrity(consolidated.narrative, consolidated.footnotes)
    except AssertionError as exc:
        log.warning("a6_consolidator.footnote_integrity_failed", error=str(exc))

    log.info(
        "a6_consolidator.done",
        claims=len(consolidated.claims),
        themes=len(consolidated.themes),
        footnotes=len(consolidated.footnotes),
        narrative_words=len(consolidated.narrative.split()),
        outline_sections=(len(consolidated.outline.sections) if consolidated.outline else 0),
        outline_frameworks=(sum(1 for s in (consolidated.outline.sections if consolidated.outline else []) if s.framework_table)),
        outline_causal_rows=(sum(len(s.causal_chain_rows) for s in (consolidated.outline.sections if consolidated.outline else []))),
        outline_case_studies=(sum(len(s.case_studies) for s in (consolidated.outline.sections if consolidated.outline else []))),
        outline_contrarian=(len(consolidated.outline.contrarian_claims) if consolidated.outline else 0),
        outline_key_stats=(len(consolidated.outline.key_stats) if consolidated.outline else 0),
    )

    return A6Output(consolidated=consolidated)


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


def _repair_normed(exc: Exception, fallback: list[NumericClaim]) -> NormalisedClaims:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return NormalisedClaims.model_validate(data if isinstance(data, dict) else {"claims": data})
        except Exception:
            pass
    return NormalisedClaims(claims=fallback)


def _repair_bundle(exc: Exception, claims: list[NumericClaim]) -> ThemeBundle:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return ThemeBundle.model_validate(data if isinstance(data, dict) else {"themes": data})
        except Exception:
            pass
    # Fallback: one theme per 3 claims
    if not claims:
        return ThemeBundle(themes=[])
    themes = []
    chunk_size = max(1, len(claims) // 3)
    for i in range(0, len(claims), chunk_size):
        chunk = claims[i:i + chunk_size]
        themes.append(Theme(
            name=f"Research Finding {len(themes)+1}",
            summary=f"{len(chunk)} verified data points.",
            claims=chunk,
            observations=[],
        ))
    return ThemeBundle(themes=themes[:8])


def _repair_narrative(exc: Exception, bundle: ThemeBundle, chosen_query: str) -> ConsolidatedNarrative:
    data = _try_repair(_extract_raw(exc))
    if data is not None:
        try:
            return ConsolidatedNarrative.model_validate(data if isinstance(data, dict) else {})
        except Exception:
            pass
    # Fallback: deterministic narrative from themes
    lines = []
    for t in bundle.themes:
        lines.append(f"## {t.name}")
        lines.append(t.summary)
        for c in t.claims[:3]:
            lines.append(f"- {c.metric}: {c.value} {c.unit}.")
        lines.append("")
    lines.append("## Executive Summary")
    lines.append(
        f"Research on {chosen_query} identified {sum(len(t.claims) for t in bundle.themes)} "
        f"verified data points across {len(bundle.themes)} analytical themes."
    )
    return ConsolidatedNarrative(narrative="\n".join(lines), footnotes=[])

"""LangGraph nodes for the research system."""

import asyncio
import os
from typing import Any, Awaitable, Callable, Dict, TypeVar

import structlog
from langchain_core.runnables import RunnableConfig

from research.crews.a1_query_refiner.crew import run_a1
from research.crews.a2_question_generator.crew import run_a2
from research.crews.a3_topic_researcher.crew import run_a3
from research.crews.a4_market_context.crew import run_a4
from research.crews.a5_news_events.crew import run_a5
from research.crews.a6_consolidator.crew import run_a6
from research.crews.a7_validator.crew import run_a7
from research.crews.a8_causation.crew import run_a8
from research.tools.ask_user import ask_user
from research.core.state import RunState
from research.core.topic_profile import (
    TopicProfile, generate_topic_profile, render_profile_for_log,
)
from research.core.types import IntentKind


_log = structlog.get_logger(__name__)


# ── Per-node wall-time guards ──────────────────────────────────────────────
#
# Every CrewAI node wraps its `run_aN` coroutine in `asyncio.wait_for` so a
# stuck LLM call / unbounded tool-loop / network hang cannot keep the graph
# blocked indefinitely. On TimeoutError the node logs the timeout, returns
# its empty/fallback shape, and the graph proceeds to the next node — its
# checkpoint still gets written so downstream nodes have a clean starting
# state and the user can resume with --resume if the partial run is salvage-
# able.
#
# Defaults are intentionally generous (the worst-case full pipeline is still
# ~25 minutes) but bounded. Override per-node via env var
# `RESEARCH_TIMEOUT_<NODE>=<seconds>`, e.g. RESEARCH_TIMEOUT_A5=120.

_DEFAULT_NODE_TIMEOUT_S: dict[str, float] = {
    "a0":   60.0,
    "a1":  180.0,
    "a2":  240.0,
    "a3":  600.0,    # Phase 4b-1: recursive investigation (~24 search+scrape pairs)
    "a4":  300.0,
    "a5":  240.0,    # was the source of the hang; cap firmly
    "a6":  360.0,    # two-pass compose (outline + prose + possible expand)
    "a6_5": 30.0,    # pure-Python; should never come close
    "a7":  240.0,
    "a8":  240.0,
    "a8_5": 90.0,    # one Haiku call; should complete fast
}


def _node_timeout(node_key: str) -> float:
    env_key = f"RESEARCH_TIMEOUT_{node_key.upper()}"
    raw = os.environ.get(env_key)
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_NODE_TIMEOUT_S.get(node_key, 240.0)


_T = TypeVar("_T")


async def _bounded(
    factory: Callable[[], Awaitable[_T]],
    *,
    node: str,
) -> _T | None:
    """Run an async coroutine with the node's wall-time cap.

    `factory` is a zero-arg callable that returns the coroutine to await
    (we take a factory rather than a coroutine because cancelling and
    retrying needs a fresh coroutine each time, and we only need one shot
    here so this is mostly future-proofing).

    On timeout: logs `<node>.timeout`, returns None. Callers should treat
    None as 'use empty fallback for this node's RunState slice'.
    """
    timeout_s = _node_timeout(node)
    try:
        return await asyncio.wait_for(factory(), timeout=timeout_s)
    except asyncio.TimeoutError:
        _log.warning(
            f"{node}.timeout",
            timeout_s=timeout_s,
            reason=("per-node wall-time guard fired; node returning empty "
                    "fallback so the graph can continue"),
        )
        return None


async def a0_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 0 - Topic Profile Generator (NEW; runs once at the very start).

    One LLM call (gpt-4o-mini) that turns the raw user query into a structured
    TopicProfile (topic_domain, expected_metric_kinds, key_dimensions,
    positive/negative_signals). Every downstream crew reads this profile from
    RunState and uses it as parameterised context — that's how the same code
    handles market / clinical / policy / social-science topics without any
    per-domain hardcoded vocabulary.

    On failure, falls back to an empty profile (empty lists + topic_domain=
    'unknown') so downstream crews still run in a permissive (legacy) mode.
    """
    profile, cost = generate_topic_profile(state["original_query"])
    _log.info(
        "a0_topic_profile.done",
        domain=profile.topic_domain,
        is_market_research=profile.is_market_research(),
        n_metric_kinds=len(profile.expected_metric_kinds),
        n_dimensions=len(profile.key_dimensions),
        cost_usd=round(cost, 5),
    )
    # Print the profile to stderr so users running the CLI see what the run is
    # optimising for (useful when something looks wrong downstream).
    for line in render_profile_for_log(profile).splitlines():
        _log.info("a0_topic_profile.line", text=line)
    return {
        "topic_profile": profile.model_dump(),
        "cost_usd": float(state.get("cost_usd", 0.0)) + cost,
    }


def _profile_from_state(state: RunState) -> TopicProfile | None:
    """Rehydrate the TopicProfile from the dict stored on RunState. Returns
    None if a0 hasn't run (defensive — pipeline should always run a0 first)."""
    raw = state.get("topic_profile")
    if not raw:
        return None
    try:
        return TopicProfile(**raw)
    except Exception:
        return None


async def a1_node(state: RunState, *, config: RunnableConfig) -> Dict[str, Any]:
    """Agent 1 - Query Refiner node.

    Takes the user's raw query, converts it into four sharp analyst-grade variants,
    scores them, shows the user a ranked multiple-choice, and writes the chosen
    query + intent back to RunState.

    On per-node timeout: falls back to the original query as `chosen_query`
    and IntentKind.GENERAL so a2/a3 can still run.
    """
    a1_result = await _bounded(
        lambda: run_a1(state["original_query"]),
        node="a1",
    )
    if a1_result is None:
        return {
            "intent": IntentKind.GENERAL,
            "query_variants": [],
            "chosen_query": state["original_query"],
        }

    conf = config.get("configurable") or {}
    if conf.get("auto_pick") is not None:
        idx = int(conf["auto_pick"]) - 1
        if 0 <= idx < len(a1_result.variants_sorted):
            chosen = a1_result.variants_sorted[idx].variant.text
        else:
            raise ValueError(f"auto_pick {idx + 1} out of range (1-{len(a1_result.variants_sorted)})")
    else:
        chosen = ask_user.ask_sync(
            question="Which refined query should we research?",
            options=[sv.variant.text for sv in a1_result.variants_sorted],
            hints=[f"{sv.composite:.1f} · {sv.reason}" for sv in a1_result.variants_sorted],
        )

    return {
        "intent": a1_result.intent,
        "query_variants": a1_result.variants_sorted,
        "chosen_query": chosen,
    }


async def a2_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 2 - Question Generator node.

    Fully autonomous (no user interaction). Reads chosen_query + intent from
    RunState, decomposes into 8-15 ranked atomic sub-questions, and writes
    them back to state["sub_questions"].

    Passes the TopicProfile to a2 so the market-research category checklist
    is skipped for clinical / policy / social-science topics.
    """
    a2_result = await _bounded(
        lambda: run_a2(
            chosen_query=state["chosen_query"],
            intent=state["intent"],
            original_query=state["original_query"],
            topic_profile=_profile_from_state(state),
        ),
        node="a2",
    )
    if a2_result is None:
        return {"sub_questions": []}
    return {"sub_questions": a2_result.questions}


async def a3_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 3 - Topic Researcher node (runs in parallel with A4, A5).

    Fetches sources, extracts numeric claims, writes analyst narrative, and
    pushes high-signal observations to the shared scratchpad. Receives the
    TopicProfile so search planning, claim extraction, and narrative writing
    are all anchored to the topic's actual domain (market / clinical /
    policy / social-science / etc.) rather than defaulting to market-research
    framing.

    Reducer-safe: topic_claims and scratchpad_notes use operator.add.
    """
    a3_result = await _bounded(
        lambda: run_a3(
            chosen_query=state["chosen_query"],
            intent=state["intent"],
            sub_questions=state["sub_questions"],
            topic_profile=_profile_from_state(state),
        ),
        node="a3",
    )
    if a3_result is None:
        return {"topic_claims": [], "topic_narrative": "", "scratchpad_notes": []}
    return {
        "topic_claims":     a3_result.claims,
        "topic_narrative":  a3_result.narrative,
        "scratchpad_notes": a3_result.scratchpad_writes,
    }


async def a4_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 4 - Market Context Researcher node (runs in parallel with A3, A5).

    Maps the value chain, quantifies parent-market pass-through, and writes
    supply-chain observations to scratchpad for Agent 5c to consume.
    Reducer-safe: market_claims and scratchpad_notes use operator.add.

    DOMAIN-CONDITIONAL: this crew only runs for market-research topics. The
    'parent market hierarchy + value chain + pass-through impact' framing is
    inherently a market-research artefact — it makes no sense for clinical
    efficacy studies, policy questions, or social-science research. For
    non-market topics we skip the entire crew and return empty results so the
    downstream consolidator doesn't see fabricated 'market context'.
    """
    profile = _profile_from_state(state)
    if profile is not None and not profile.is_market_research():
        _log.info(
            "a4_market_context.skipped_non_market_domain",
            topic_domain=profile.topic_domain,
            reason=("a4 maps parent-market hierarchy + value chain, which is "
                    "market-research-specific. Non-market topics get an empty "
                    "market_context bucket; topic-relevant context comes from "
                    "a3 and a5 instead."),
        )
        return {
            "market_claims":    [],
            "market_narrative": "",
            "scratchpad_notes": [],
        }

    a4_result = await _bounded(
        lambda: run_a4(
            chosen_query=state["chosen_query"],
            intent=state["intent"],
            sub_questions=state["sub_questions"],
        ),
        node="a4",
    )
    if a4_result is None:
        return {"market_claims": [], "market_narrative": "", "scratchpad_notes": []}
    return {
        "market_claims":     a4_result.claims,
        "market_narrative":  a4_result.narrative,
        "scratchpad_notes":  a4_result.scratchpad_writes,
    }


async def a5_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 5 - News & Events Researcher node (runs in parallel with A3, A4).

    5a and 5b run concurrently inside the crew; 5c runs after both. Each
    sub-phase receives the TopicProfile so the event hunter, regulatory
    tracker, and disruption scanner pick domain-appropriate categories
    (market: M&A / earnings; clinical: trial readouts / drug approvals;
    policy: legislation / agency rulings; social-science: studies / surveys).
    For non-market topics, 5c does NOT require a 'market_context' scratchpad
    section to exist (since a4 is skipped for those topics).

    Reducer-safe: news_claims and scratchpad_notes use operator.add.
    """
    a5_result = await _bounded(
        lambda: run_a5(
            chosen_query=state["chosen_query"],
            intent=state["intent"],
            sub_questions=state["sub_questions"],
            topic_profile=_profile_from_state(state),
        ),
        node="a5",
    )
    if a5_result is None:
        return {"news_claims": [], "news_narrative": "", "scratchpad_notes": []}
    return {
        "news_claims":       a5_result.claims,
        "news_narrative":    a5_result.narrative,
        "scratchpad_notes":  a5_result.scratchpad_writes,
    }


_MAX_CLAIMS_PER_BUCKET = 20  # cap each bucket so A6 context stays under ~60 total claims

async def a6_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 6 - Consolidator node (join point after A3/A4/A5).

    No tool calls. Normalises units, clusters themes, writes bottom-up narrative.
    Claims are capped per bucket before passing to prevent context explosion.
    """
    a6_result = await _bounded(
        lambda: run_a6(
            chosen_query=state["chosen_query"],
            intent=state["intent"],
            topic_claims=state["topic_claims"][:_MAX_CLAIMS_PER_BUCKET],
            market_claims=state["market_claims"][:_MAX_CLAIMS_PER_BUCKET],
            news_claims=state["news_claims"][:_MAX_CLAIMS_PER_BUCKET],
            topic_narrative=state["topic_narrative"],
            market_narrative=state["market_narrative"],
            news_narrative=state["news_narrative"],
            scratchpad_notes=state["scratchpad_notes"][:15],
            topic_profile=_profile_from_state(state),
            dimensional_clusters=state.get("dimensional_clusters") or [],
        ),
        node="a6",
    )
    if a6_result is None:
        return {"consolidated": None}
    return {"consolidated": a6_result.consolidated}


async def a6_5_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 6.5 - Dimensional Clusterer (NEW).

    After a6_consolidator finishes producing qualitative themes, this node
    runs dimensional clustering across ALL accumulated NumericClaims (topic,
    market, news) to surface QUANTITATIVE consensus: claims that measure the
    same dimension cluster together, complete with mean / spread / source
    count / consensus_level. This complements a6's theme grouping which is
    qualitative.

    Pure-Python: no LLM calls, no embeddings, runs in milliseconds.

    Reads:
      state.topic_claims, state.market_claims, state.news_claims
    Writes:
      state.dimensional_clusters: list[ClusteredEstimate.model_dump()]
    """
    from research.clustering import cluster_numeric_claims

    all_claims = (
        list(state.get("topic_claims") or [])
        + list(state.get("market_claims") or [])
        + list(state.get("news_claims") or [])
    )

    if not all_claims:
        _log.info("a6_5_clusterer.no_claims")
        return {"dimensional_clusters": []}

    estimates = cluster_numeric_claims(
        all_claims,
        on_progress=lambda msg: _log.info("a6_5_clusterer.progress", text=msg),
    )

    multi_src = sum(1 for e in estimates if e.n_unique_sources >= 2)
    _log.info(
        "a6_5_clusterer.done",
        n_claims=len(all_claims),
        n_clusters=len(estimates),
        multi_source=multi_src,
        time_series=sum(1 for e in estimates if e.trend_slope_pct_per_year is not None),
    )

    # Serialise to dicts for RunState (TypedDict friendliness)
    return {
        "dimensional_clusters": [e.model_dump(mode="json") for e in estimates],
    }


async def a7_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 7 - Validator node (sequential after A6).

    Authority ranking is deterministic code; LLMs only provide semantic grouping
    and human-readable rejection reasons. Code overrides any LLM deviation.
    """
    if state.get("consolidated") is None:
        return {"validated_claims": [], "conflicts": []}
    a7_result = await _bounded(
        lambda: run_a7(consolidated=state["consolidated"]),
        node="a7",
    )
    if a7_result is None:
        return {"validated_claims": [], "conflicts": []}
    return {
        "validated_claims": a7_result.validated_claims,
        "conflicts":        a7_result.conflicts,
    }


async def a8_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 8 - Causation / Reasoning node (final analytical node before END).

    8a Haiku: delta detection. 8b Sonnet+tools: event correlation.
    8c pure Python: ≥2-citation rule enforcement (zero LLM risk).
    """
    a8_result = await _bounded(
        lambda: run_a8(
            validated_claims=state.get("validated_claims", []),
            news_narrative=state.get("news_narrative", ""),
            scratchpad_notes=state.get("scratchpad_notes", []),
            chosen_query=state.get("chosen_query", ""),
        ),
        node="a8",
    )
    if a8_result is None:
        return {"causations": []}


async def a8_5_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 8.5 - Verifier (NEW; runs after a8, before END).

    Fact-checks the composed brief against validated_claims +
    dimensional_clusters. Single Haiku call (~$0.001 at gpt-4o-mini debug
    pin). Writes `verification` (a VerificationResult dict) to RunState so
    the renderer can surface the grounding score.

    Non-destructive: scores the brief, doesn't edit it. The renderer warns
    when grounding_score < 0.7.
    """
    from research.crews.a8_5_verifier.verify import verify_brief

    consolidated = state.get("consolidated")
    narrative = ""
    if consolidated is not None:
        narrative = (
            consolidated.narrative if hasattr(consolidated, "narrative")
            else (consolidated.get("narrative", "") if isinstance(consolidated, dict) else "")
        )

    if not narrative.strip():
        _log.info("a8_5_verifier.no_narrative_skipping")
        return {"verification": None}

    result = await _bounded(
        lambda: verify_brief(
            narrative=narrative,
            validated_claims=state.get("validated_claims") or [],
            dimensional_clusters=state.get("dimensional_clusters") or [],
        ),
        node="a8_5",
    )
    if result is None:
        return {"verification": None}

    _log.info(
        "a8_5_verifier.done",
        grounding_score=result.grounding_score,
        total=result.total_claims,
        verified=result.verified_claims,
        fabricated=len(result.fabricated),
        uncertain=len(result.uncertain),
    )
    return {"verification": result.model_dump(mode="json")}
    return {"causations": a8_result.causations}

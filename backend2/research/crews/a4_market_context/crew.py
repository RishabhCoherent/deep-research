"""CrewAI crew orchestration for Agent 4 - Market Context Researcher.

Architecture (3-phase isolated crews, same pattern as A3):
  Phase 1 — identify (Haiku): classify market hierarchy → ParentMarketResult
  Phase 2 — map (Sonnet):     value chain + scratchpad writes → ValueChainMap
  Phase 3 — analyse (Sonnet): pass-through impacts + narrative → ImpactAnalysis
"""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process, Task

from research.core.types import IntentKind, SubQuestion
from research.tools.research_search import reset_node_counter, get_node_call_count, research_search
from research.tools.hybrid_scraper import hybrid_scrape

from .agents import build_agents
from .schemas import ParentMarketResult, ValueChainMap, ImpactAnalysis, A4Output
from .validators import assert_impact_evidence, assert_claim_citations, assert_narrative_word_count

log = structlog.get_logger(__name__)


# ── Phase 1: identify ─────────────────────────────────────────────────────────

def _build_identify_crew(identifier) -> Crew:
    task = Task(
        description=(
            "Identify the parent and grandparent market for the child market in the chosen query. "
            "intent={intent}, chosen_query={chosen_query}\n\n"
            "sub_questions:\n{sub_questions_json}"
        ),
        expected_output="JSON matching ParentMarketResult (child, parent, grandparent, justification, citations).",
        agent=identifier,
        output_pydantic=ParentMarketResult,
    )
    return Crew(agents=[identifier], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Phase 2: map ──────────────────────────────────────────────────────────────

def _build_map_crew(mapper) -> Crew:
    task = Task(
        description=(
            "Map the full value chain (upstream, midstream, downstream, substitutes). "
            "Write key nodes to scratchpad section='market_context'. "
            "chosen_query={chosen_query}\n\n"
            "parent_market:\n{parent_market_json}"
        ),
        expected_output="JSON matching ValueChainMap (upstream, midstream, downstream, substitutes, scratchpad_writes).",
        agent=mapper,
        output_pydantic=ValueChainMap,
    )
    return Crew(agents=[mapper], tasks=[task], process=Process.sequential, verbose=False, memory=False)


# ── Phase 3: analyse ──────────────────────────────────────────────────────────

def _build_analyse_crew(analyst, context_text: str = "") -> Crew:
    context_section = (
        f"\n\nmarket_context_passages:\n{context_text}" if context_text else ""
    )
    task = Task(
        description=(
            "Quantify how parent-market forces pass through to the child market. "
            "Extract NumericClaims with verbatim raw_excerpts. Write a 400-800 word narrative. "
            "chosen_query={chosen_query}\n\n"
            "parent_market:\n{parent_market_json}\n\n"
            "value_chain:\n{value_chain_json}\n\n"
            "sub_questions:\n{sub_questions_json}"
            + context_section
        ),
        expected_output="JSON matching ImpactAnalysis (impacts with evidence, claims, 400-800 word narrative).",
        agent=analyst,
        output_pydantic=ImpactAnalysis,
    )
    return Crew(agents=[analyst], tasks=[task], process=Process.sequential, verbose=False, memory=False)


_WH_PREFIXES = (
    "what will be the ", "what is the ", "what are the ",
    "how will ", "how does ", "how is ", "how much ",
    "which ", "when ", "why ",
)
_TOPIC_FILLERS = (
    "projected size and segmentation of ",
    "projected size of ", "projected growth of ",
    "size and segmentation of ", "size of ", "growth of ",
    "outlook for ",
)


def _topic_noun_phrase(query: str) -> str:
    """Reduce a refined analyst question back to the bare market noun phrase so
    it can be embedded in tight search queries without dragging 20+ extra words.

    e.g. "What will be the projected size and segmentation of the EV charging
          infrastructure market in Europe by 2025?"
      -> "EV charging infrastructure market in Europe 2025"
    """
    q = (query or "").strip().rstrip("?").rstrip(".").strip()
    lower = q.lower()
    for prefix in _WH_PREFIXES:
        if lower.startswith(prefix):
            q = q[len(prefix):]
            break
    q_lower = q.lower()
    for filler in _TOPIC_FILLERS:
        if q_lower.startswith(filler):
            q = q[len(filler):]
            break
    # Strip articles + "by YYYY" markers to make the phrase keyword-dense
    q = q.strip()
    for art in ("the ", "a ", "an "):
        if q.lower().startswith(art):
            q = q[len(art):]
            break
    q = q.replace(" by 20", " 20")
    return q.strip()


async def _prefetch_chain_context(chain, chosen_query: str) -> str:
    """Search + scrape top result for each chain node to give Phase 3 real data.

    Queries are built as `<node-name> <topic-noun-phrase> market data` — the
    old shape pasted the full chosen_query and wasted budget on verbose queries.
    """
    topic_np = _topic_noun_phrase(chosen_query)
    node_names = [n.name for n in chain.upstream[:3]] + [n.name for n in chain.midstream[:2]]
    passages: list[str] = []

    for name in node_names:
        if len(passages) >= 6:
            break
        query = f"{name} {topic_np} market share revenue"
        try:
            raw = research_search.invoke({"query": query, "max_results": 3})
            results = json.loads(raw).get("results", [])
        except Exception:
            continue

        for r in results[:2]:
            url = (r.get("url") or "").strip()
            if not url:
                continue
            try:
                scraped = await hybrid_scrape(url, timeout=12.0)
                text = scraped["content"] if scraped["success"] else r.get("snippet", "")
            except Exception:
                text = r.get("snippet", "")
            if text:
                passages.append(f"[{name}] {text[:1_500]}")
                break   # one good result per node is sufficient

    return "\n---\n".join(passages)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_a4(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
) -> A4Output:
    """Run Agent 4 - Market Context Researcher (3 isolated phases)."""
    reset_node_counter()

    top_k = sub_questions[:8]
    sub_questions_json = json.dumps([q.model_dump() for q in top_k], default=str)

    identifier, mapper, analyst = build_agents()

    # ── Phase 1: identify ────────────────────────────────────────────────────
    parent = ParentMarketResult(
        child=chosen_query[:200], parent="", grandparent="", justification="", citations=[]
    )
    try:
        r1 = await _build_identify_crew(identifier).kickoff_async(inputs={
            "chosen_query":       chosen_query,
            "intent":             intent.value,
            "sub_questions_json": sub_questions_json,
        })
        parent = r1.tasks_output[0].pydantic
        if parent is None:
            parent = _repair_parent(Exception(r1.tasks_output[0].raw or ""), chosen_query)
    except Exception as exc:
        log.warning("a4_market_context.identify_failed_trying_repair", error=str(exc)[:200])
        parent = _repair_parent(exc, chosen_query)

    log.info("a4_market_context.identify_done", child=parent.child, parent=parent.parent)
    parent_json = parent.model_dump_json()

    # ── Phase 2: map ─────────────────────────────────────────────────────────
    chain = ValueChainMap(upstream=[], midstream=[], downstream=[], substitutes=[], scratchpad_writes=[])
    try:
        r2 = await _build_map_crew(mapper).kickoff_async(inputs={
            "chosen_query":       chosen_query,
            "parent_market_json": parent_json,
        })
        chain = r2.tasks_output[0].pydantic
        if chain is None:
            chain = _repair_chain(Exception(r2.tasks_output[0].raw or ""))
    except Exception as exc:
        log.warning("a4_market_context.map_failed_trying_repair", error=str(exc)[:200])
        chain = _repair_chain(exc)

    log.info("a4_market_context.map_done",
             upstream=len(chain.upstream), midstream=len(chain.midstream),
             scratchpad_writes=len(chain.scratchpad_writes))
    chain_json = chain.model_dump_json()

    # ── Phase 3: analyse ──────────────────────────────────────────────────────
    # Pre-fetch real-world data for chain nodes so the analyst has grounded evidence
    context_text = await _prefetch_chain_context(chain, chosen_query)
    log.info("a4_market_context.context_fetched", passages=context_text.count("---") + 1 if context_text else 0)

    analysis = ImpactAnalysis(impacts=[], claims=[], narrative="")
    try:
        r3 = await _build_analyse_crew(analyst, context_text=context_text).kickoff_async(inputs={
            "chosen_query":       chosen_query,
            "parent_market_json": parent_json,
            "value_chain_json":   chain_json,
            "sub_questions_json": sub_questions_json,
        })
        analysis = r3.tasks_output[0].pydantic
        if analysis is None:
            analysis = _repair_analysis(Exception(r3.tasks_output[0].raw or ""))
    except Exception as exc:
        log.warning("a4_market_context.analyse_failed_trying_repair", error=str(exc)[:200])
        analysis = _repair_analysis(exc)

    # ── Post-LLM deterministic validation ─────────────────────────────────────
    valid_impacts = assert_impact_evidence(analysis.impacts)

    # A4 claim extraction is INTENTIONALLY DROPPED.
    # Rationale: pass-through magnitude claims ("10% lithium drop -> 3.7% cell price")
    # are rare in reality. gpt-4o-mini hallucinates them under pressure and the claims
    # it *does* produce are usually duplicates of A3's market-size numbers (observed in
    # run 863abd8c: 2 A4 claims, both dupes of A3). The narrative and scratchpad
    # value-chain observations are A4's real contribution — they feed A5c and A6.
    # If we ever need real pass-through claims, re-enable via A4 prompt + validators
    # or surface them from analysis.impacts instead.
    valid_claims: list = []

    dropped_impacts = len(analysis.impacts) - len(valid_impacts)
    if dropped_impacts:
        log.warning("a4_market_context.dropped_impacts", dropped_impacts=dropped_impacts)
    if analysis.claims:
        log.info("a4_market_context.discarded_llm_claims",
                 n=len(analysis.claims),
                 note="A4 claim extraction is disabled; narrative + scratchpad are kept")

    try:
        assert_narrative_word_count(analysis.narrative)
    except AssertionError as exc:
        log.warning("a4_market_context.narrative_word_count_failed", error=str(exc))

    log.info("a4_market_context.done",
             claims=len(valid_claims),
             impacts=len(valid_impacts),
             tavily_calls=get_node_call_count(),
             narrative_words=len(analysis.narrative.split()))

    return A4Output(
        claims=valid_claims,
        narrative=analysis.narrative,
        scratchpad_writes=chain.scratchpad_writes,
    )


# ── Repair helpers ─────────────────────────────────────────────────────────────

def _extract_raw(exc: Exception) -> str:
    """Pull the actual partial-JSON string out of a Pydantic ValidationError."""
    from pydantic import ValidationError as PydanticVE
    if isinstance(exc, PydanticVE):
        for err in exc.errors():
            val = err.get("input")
            if isinstance(val, str) and "{" in val:
                return val
    return str(exc)


def _try_repair(raw: str) -> dict | None:
    import json_repair
    try:
        start = raw.find("{")
        if start != -1:
            return json.loads(json_repair.repair_json(raw[start:]))
    except Exception:
        pass
    return None


def _repair_parent(exc: Exception, chosen_query: str) -> ParentMarketResult:
    data = _try_repair(_extract_raw(exc))
    if isinstance(data, dict):
        try:
            return ParentMarketResult.model_validate(data)
        except Exception:
            pass
    return ParentMarketResult(
        child=chosen_query[:200],
        parent="Advanced Battery Market",
        grandparent="Energy Storage & Clean Technology",
        justification="Fallback: LLM output could not be parsed.",
        citations=[],
    )


def _repair_chain(exc: Exception) -> ValueChainMap:
    data = _try_repair(_extract_raw(exc))
    if isinstance(data, dict):
        try:
            return ValueChainMap.model_validate(data)
        except Exception:
            pass
    return ValueChainMap(upstream=[], midstream=[], downstream=[], substitutes=[], scratchpad_writes=[])


def _repair_analysis(exc: Exception) -> ImpactAnalysis:
    data = _try_repair(_extract_raw(exc))
    if isinstance(data, dict):
        try:
            return ImpactAnalysis.model_validate(data)
        except Exception:
            pass
    return ImpactAnalysis(impacts=[], claims=[], narrative="")

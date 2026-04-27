"""Per-agent test harness for the A1-A8 research pipeline.

Runs one agent at a time, persists state to backend2/state/pipeline_state.json,
and loads it automatically for the next agent. On failure, fix the bug and re-run
just that agent — no need to restart from A1.

Usage
-----
    # Start fresh — creates initial state
    python scripts/test_agent.py a1 --query "Solid-state battery supply chain in Asia 2025"

    # Each subsequent agent — reads previous state automatically
    python scripts/test_agent.py a2
    python scripts/test_agent.py a3
    python scripts/test_agent.py a4
    python scripts/test_agent.py a5
    python scripts/test_agent.py a6
    python scripts/test_agent.py a7
    python scripts/test_agent.py a8

    # Override chosen_query for A1 (auto-picks variant #1 by default)
    python scripts/test_agent.py a1 --query "..." --pick 2

    # Reset checkpoint and start over
    python scripts/test_agent.py a1 --query "..." --reset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ── path setup ─────────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_STATE_DIR = _BACKEND_ROOT / "state"
_STATE_FILE = _STATE_DIR / "pipeline_state.json"

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import io
import os
# Force UTF-8 stdout/stderr on Windows to avoid cp1252 encoding crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from dotenv import load_dotenv
load_dotenv(_BACKEND_ROOT / ".env")


# ── helpers ─────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str),
                           encoding="utf-8")


def _patch_crew_tokens():
    from crewai import Crew
    from crewai.types.usage_metrics import UsageMetrics
    total = UsageMetrics()
    _orig = Crew.kickoff_async

    async def _wrapped(self, inputs=None):
        out = await _orig(self, inputs)
        total.add_usage_metrics(out.token_usage)
        return out

    Crew.kickoff_async = _wrapped
    return total


def _cost_estimate(tokens) -> str:
    inn, out = tokens.prompt_tokens, tokens.completion_tokens
    lo = (inn * 1.0 + out * 5.0) / 1_000_000
    hi = (inn * 3.0 + out * 15.0) / 1_000_000
    return f"${lo:.4f}-${hi:.4f} (haiku<->sonnet bounds)"


def _print_section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _require_keys(state: dict, *keys: str, agent: str) -> None:
    missing = [k for k in keys if k not in state or state[k] is None]
    if missing:
        print(f"[ERROR] State missing required keys for {agent}: {missing}")
        print("  Run the previous agent(s) first.")
        sys.exit(1)


# ── per-agent runners ────────────────────────────────────────────────────────

async def run_a1(state: dict, query: str | None, pick: int) -> dict:
    from research.crews.a1_query_refiner.crew import run_a1 as _run

    raw_query = query or state.get("original_query")
    if not raw_query:
        print("[ERROR] --query is required for a1")
        sys.exit(1)

    print(f"  Query : {raw_query}")
    result = await _run(raw_query)

    idx = pick - 1
    if not (0 <= idx < len(result.variants_sorted)):
        print(f"[WARN] --pick {pick} out of range, defaulting to 1")
        idx = 0
    chosen = result.variants_sorted[idx].variant.text

    _print_section("A1 RESULTS")
    print(f"  Intent       : {result.intent}")
    print(f"  Chosen query : {chosen}")
    print(f"\n  All variants (scored):")
    for i, sv in enumerate(result.variants_sorted, 1):
        marker = " <-- chosen" if i - 1 == idx else ""
        print(f"    {i}. [{sv.composite:.1f}] {sv.variant.text}{marker}")

    return {
        "original_query":  raw_query,
        "intent":          result.intent.value,
        "query_variants":  [sv.model_dump(mode="json") for sv in result.variants_sorted],
        "chosen_query":    chosen,
    }


async def run_a2(state: dict) -> dict:
    _require_keys(state, "chosen_query", "intent", "original_query", agent="A2")
    from research.crews.a2_question_generator.crew import run_a2 as _run
    from research.core.types import IntentKind

    result = await _run(
        chosen_query=state["chosen_query"],
        intent=IntentKind(state["intent"]),
        original_query=state["original_query"],
    )

    _print_section("A2 RESULTS")
    print(f"  Sub-questions generated: {len(result.questions)}")
    for i, q in enumerate(result.questions, 1):
        print(f"    {i:>2}. [{q.composite:.1f}] [{q.category}] {q.text}")

    return {"sub_questions": [q.model_dump(mode="json") for q in result.questions]}


async def run_a3(state: dict) -> dict:
    _require_keys(state, "chosen_query", "intent", "sub_questions", agent="A3")
    from research.crews.a3_topic_researcher.crew import run_a3 as _run
    from research.core.types import IntentKind, SubQuestion

    sub_qs = [SubQuestion.model_validate(q) for q in state["sub_questions"]]
    result = await _run(
        chosen_query=state["chosen_query"],
        intent=IntentKind(state["intent"]),
        sub_questions=sub_qs,
    )

    _print_section("A3 RESULTS")
    print(f"  Topic claims     : {len(result.claims)}")
    print(f"  Scratchpad writes: {len(result.scratchpad_writes)}")
    print(f"  Narrative words  : {len(result.narrative.split())}")
    for i, c in enumerate(result.claims[:5], 1):
        print(f"    {i}. {c.metric}: {c.value} {c.unit}")
    if len(result.claims) > 5:
        print(f"    ... and {len(result.claims)-5} more")

    existing_scratchpad = state.get("scratchpad_notes", [])
    return {
        "topic_claims":     [c.model_dump(mode="json") for c in result.claims],
        "topic_narrative":  result.narrative,
        "scratchpad_notes": existing_scratchpad + [o.model_dump(mode="json") for o in result.scratchpad_writes],
    }


async def run_a4(state: dict) -> dict:
    _require_keys(state, "chosen_query", "intent", "sub_questions", agent="A4")
    from research.crews.a4_market_context.crew import run_a4 as _run
    from research.core.types import IntentKind, SubQuestion

    sub_qs = [SubQuestion.model_validate(q) for q in state["sub_questions"]]
    result = await _run(
        chosen_query=state["chosen_query"],
        intent=IntentKind(state["intent"]),
        sub_questions=sub_qs,
    )

    _print_section("A4 RESULTS")
    print(f"  Market claims    : {len(result.claims)}")
    print(f"  Scratchpad writes: {len(result.scratchpad_writes)}")
    print(f"  Narrative words  : {len(result.narrative.split())}")
    for i, c in enumerate(result.claims[:5], 1):
        print(f"    {i}. {c.metric}: {c.value} {c.unit}")
    if len(result.claims) > 5:
        print(f"    ... and {len(result.claims)-5} more")

    existing_scratchpad = state.get("scratchpad_notes", [])
    return {
        "market_claims":    [c.model_dump(mode="json") for c in result.claims],
        "market_narrative": result.narrative,
        "scratchpad_notes": existing_scratchpad + [o.model_dump(mode="json") for o in result.scratchpad_writes],
    }


async def run_a5(state: dict) -> dict:
    _require_keys(state, "chosen_query", "intent", "sub_questions", agent="A5")
    from research.crews.a5_news_events.crew import run_a5 as _run
    from research.core.types import IntentKind, SubQuestion

    sub_qs = [SubQuestion.model_validate(q) for q in state["sub_questions"]]
    result = await _run(
        chosen_query=state["chosen_query"],
        intent=IntentKind(state["intent"]),
        sub_questions=sub_qs,
    )

    _print_section("A5 RESULTS")
    print(f"  News claims      : {len(result.claims)}")
    print(f"  Scratchpad writes: {len(result.scratchpad_writes)}")
    print(f"  Narrative words  : {len(result.narrative.split())}")
    for i, c in enumerate(result.claims[:5], 1):
        print(f"    {i}. {c.metric}: {c.value} {c.unit}")
    if len(result.claims) > 5:
        print(f"    ... and {len(result.claims)-5} more")

    existing_scratchpad = state.get("scratchpad_notes", [])
    return {
        "news_claims":      [c.model_dump(mode="json") for c in result.claims],
        "news_narrative":   result.narrative,
        "scratchpad_notes": existing_scratchpad + [o.model_dump(mode="json") for o in result.scratchpad_writes],
    }


async def run_a6(state: dict) -> dict:
    _require_keys(state, "chosen_query", "intent",
                  "topic_claims", "market_claims", "news_claims", agent="A6")
    from research.crews.a6_consolidator.crew import run_a6 as _run
    from research.core.types import IntentKind, NumericClaim, Observation

    _MAX = 20
    topic_claims  = [NumericClaim.model_validate(c) for c in state.get("topic_claims", [])[:_MAX]]
    market_claims = [NumericClaim.model_validate(c) for c in state.get("market_claims", [])[:_MAX]]
    news_claims   = [NumericClaim.model_validate(c) for c in state.get("news_claims", [])[:_MAX]]
    scratchpad    = [Observation.model_validate(o)  for o in state.get("scratchpad_notes", [])[:15]]

    result = await _run(
        chosen_query=state["chosen_query"],
        intent=IntentKind(state["intent"]),
        topic_claims=topic_claims,
        market_claims=market_claims,
        news_claims=news_claims,
        topic_narrative=state.get("topic_narrative", ""),
        market_narrative=state.get("market_narrative", ""),
        news_narrative=state.get("news_narrative", ""),
        scratchpad_notes=scratchpad,
    )

    _print_section("A6 RESULTS")
    cr = result.consolidated
    print(f"  Normalised claims: {len(cr.claims)}")
    print(f"  Themes           : {len(cr.themes)}")
    print(f"  Footnotes        : {len(cr.footnotes)}")
    print(f"  Narrative words  : {len(cr.narrative.split())}")
    for t in cr.themes:
        print(f"    • {t.name}: {len(t.claims)} claims")

    return {"consolidated": cr.model_dump(mode="json")}


async def run_a7(state: dict) -> dict:
    _require_keys(state, "consolidated", agent="A7")
    from research.crews.a7_validator.crew import run_a7 as _run
    from research.core.types import ConsolidatedReport

    consolidated = ConsolidatedReport.model_validate(state["consolidated"])
    result = await _run(consolidated=consolidated)

    _print_section("A7 RESULTS")
    print(f"  Validated claims : {len(result.validated_claims)}")
    print(f"  Conflicts found  : {len(result.conflicts)}")
    for i, c in enumerate(result.validated_claims[:5], 1):
        print(f"    {i}. {c.metric}: {c.value} {c.unit}")
    if len(result.validated_claims) > 5:
        print(f"    ... and {len(result.validated_claims)-5} more")

    return {
        "validated_claims": [c.model_dump(mode="json") for c in result.validated_claims],
        "conflicts":        [_json_safe(cf)           for cf in result.conflicts],
    }


async def run_a8(state: dict) -> dict:
    _require_keys(state, "validated_claims", "chosen_query", agent="A8")
    from research.crews.a8_causation.crew import run_a8 as _run
    from research.core.types import NumericClaim, Observation

    validated = [NumericClaim.model_validate(c) for c in state.get("validated_claims", [])]
    scratchpad = [Observation.model_validate(o) for o in state.get("scratchpad_notes", [])]

    result = await _run(
        validated_claims=validated,
        news_narrative=state.get("news_narrative", ""),
        scratchpad_notes=scratchpad,
        chosen_query=state["chosen_query"],
    )

    _print_section("A8 RESULTS")
    print(f"  Causations found : {len(result.causations)}")
    for i, c in enumerate(result.causations, 1):
        print(f"    {i}. {c.metric} | Δ{c.delta_pct:+.1f}% | {len(c.drivers)} driver(s) | confidence={c.confidence}")

    return {"causations": [c.model_dump(mode="json") for c in result.causations]}


def _json_safe(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    return obj


# ── dispatch ─────────────────────────────────────────────────────────────────

_RUNNERS = {
    "a1": run_a1,
    "a2": run_a2,
    "a3": run_a3,
    "a4": run_a4,
    "a5": run_a5,
    "a6": run_a6,
    "a7": run_a7,
    "a8": run_a8,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single research pipeline agent")
    parser.add_argument("agent", choices=list(_RUNNERS), help="Agent to run (a1-a8)")
    parser.add_argument("--query", default=None, help="Raw research query (required for a1)")
    parser.add_argument("--pick",  type=int, default=1, help="A1 variant to pick (1-4, default=1)")
    parser.add_argument("--reset", action="store_true", help="Delete checkpoint before running")
    args = parser.parse_args()

    if args.reset and _STATE_FILE.exists():
        _STATE_FILE.unlink()
        print(f"[reset] Deleted {_STATE_FILE}")

    tokens = _patch_crew_tokens()
    state  = _load_state()

    print(f"\n[{args.agent.upper()}] Starting — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
    if state:
        keys = [k for k in state if state[k] is not None and state[k] != [] and state[k] != {}]
        print(f"  Loaded state keys: {keys}")

    t0  = time.perf_counter()
    err = None
    patch = {}

    try:
        runner = _RUNNERS[args.agent]
        if args.agent == "a1":
            patch = await runner(state, args.query, args.pick)
        else:
            patch = await runner(state)
    except Exception as exc:
        err = traceback.format_exc()
        print(f"\n[ERROR] {exc}")
        print(err)

    elapsed = time.perf_counter() - t0

    if patch:
        state.update(patch)
        _save_state(state)
        print(f"\n  State saved → {_STATE_FILE}")

    print(f"\n  Elapsed : {elapsed:.1f}s")
    print(f"  Tokens  : {tokens.total_tokens} (prompt={tokens.prompt_tokens}, completion={tokens.completion_tokens})")
    print(f"  Cost est: {_cost_estimate(tokens)}")

    if err:
        print(f"\n[FAILED] Fix the error above then re-run: python scripts/test_agent.py {args.agent}")
        return 1

    next_agent = {"a1":"a2","a2":"a3","a3":"a4","a4":"a5","a5":"a6","a6":"a7","a7":"a8"}.get(args.agent)
    if next_agent:
        print(f"\n  Next → python scripts/test_agent.py {next_agent}")
    else:
        print(f"\n  All agents complete. Full pipeline state in: {_STATE_FILE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

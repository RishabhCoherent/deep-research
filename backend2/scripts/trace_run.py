"""Full-pipeline trace run.

Runs the A1 -> A8 graph end-to-end on a given topic, with SmartCrawler search
(no Tavily spend) and captures EVERYTHING that happens so we can audit which
agents, tools, and fields are actually useful.

Writes to: backend2/out/trace_<run_id>/
    SUMMARY.md          - human-readable per-layer analysis
    final_brief.md      - the research brief (what the user would see)
    final_state.json    - full RunState dump
    node_updates.jsonl  - per-node state patch (one line per node transition)
    node_snapshots.jsonl- full state snapshot after each node
    llm_calls.jsonl     - every LLM call in/out (prompts, completions, timing, usage)
    tool_calls.jsonl    - every search / scrape call with args + result summary
    run_meta.json       - totals (elapsed, llm calls, tokens, tool calls, etc.)

Usage:
    python scripts/trace_run.py "EV charging infrastructure in Europe 2025"
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 everywhere to avoid Windows cp1252 charmap crashes on
# unicode characters in prompts / logs (e.g. '≥', '—', '•').
import os
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Defensive: disable Tavily entirely so a bug can never charge credit
os.environ["TAVILY_API_KEY"] = ""
os.environ["TAVILY_API_KEY_2"] = ""
os.environ["TAVILY_API_KEY_3"] = ""

from langchain_core.callbacks import BaseCallbackHandler


# ── JSON serialization helper ───────────────────────────────────────────────

def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return _to_jsonable(obj.model_dump())
        except Exception:
            pass
    # Pydantic v1
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return _to_jsonable(obj.dict())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return _to_jsonable(vars(obj))
        except Exception:
            pass
    return str(obj)


# ── LLM callback ────────────────────────────────────────────────────────────

class LLMTraceHandler(BaseCallbackHandler):
    """Logs every chat-model call with prompts + completions + token usage."""

    def __init__(self, out_path: Path, counters: dict):
        self.out_path = out_path
        self.counters = counters
        self._f = open(out_path, "a", encoding="utf-8")
        self._starts: dict[str, float] = {}
        self._payloads: dict[str, dict] = {}

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass

    def _write(self, event: dict) -> None:
        self._f.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")
        self._f.flush()

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._starts[str(run_id)] = time.time()
        model = None
        if isinstance(serialized, dict):
            model = (
                serialized.get("kwargs", {}).get("model")
                or serialized.get("kwargs", {}).get("model_name")
                or serialized.get("name")
            )
        flat = []
        for msg_list in messages:
            for m in msg_list:
                flat.append({
                    "role": getattr(m, "type", None) or m.__class__.__name__,
                    "content": (getattr(m, "content", "") or "")[:6000],  # cap
                })
        self._payloads[str(run_id)] = {"model": model, "messages_in": flat}

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        rid = str(run_id)
        start = self._starts.pop(rid, None)
        payload = self._payloads.pop(rid, {})
        gens: list[str] = []
        try:
            for gen_list in response.generations:
                for g in gen_list:
                    gens.append((getattr(g, "text", "") or "")[:8000])
        except Exception:
            pass
        usage = None
        try:
            usage = (response.llm_output or {}).get("token_usage")
        except Exception:
            pass
        if usage:
            self.counters["prompt_tokens"] = self.counters.get("prompt_tokens", 0) + int(usage.get("prompt_tokens", 0))
            self.counters["completion_tokens"] = self.counters.get("completion_tokens", 0) + int(usage.get("completion_tokens", 0))
        self.counters["llm_calls"] = self.counters.get("llm_calls", 0) + 1
        self._write({
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": rid,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "elapsed_s": round(time.time() - (start or time.time()), 3),
            "model": payload.get("model"),
            "messages_in": payload.get("messages_in", []),
            "completion": gens,
            "usage": usage,
        })

    def on_llm_error(self, error, *, run_id, **kwargs):
        rid = str(run_id)
        self._starts.pop(rid, None)
        self._payloads.pop(rid, None)
        self.counters["llm_errors"] = self.counters.get("llm_errors", 0) + 1
        self._write({
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": rid,
            "error": str(error),
        })


# ── Tool-call tracer ────────────────────────────────────────────────────────

def install_tool_tracers(tool_path: Path, counters: dict):
    """Monkey-patch search + scrape entry points to log every call."""
    f = open(tool_path, "a", encoding="utf-8")

    def log(event: dict):
        f.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")
        f.flush()

    import research.tools.smartcrawler_search as sc
    _orig_sc = sc.search_with_smartcrawler

    def traced_sc(query, *, max_results: int = 5, news_only: bool = False, **kw):
        t = time.time()
        try:
            out = _orig_sc(query, max_results=max_results, news_only=news_only, **kw)
            err = None
        except Exception as e:
            out = []
            err = str(e)
        counters["sc_calls"] = counters.get("sc_calls", 0) + 1
        urls = [r.get("url") for r in (out or [])][:10]
        full_lens = [len(r.get("full_text") or "") for r in (out or [])]
        log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": "search_with_smartcrawler",
            "query": query,
            "news_only": news_only,
            "n_results": len(out or []),
            "elapsed_s": round(time.time() - t, 2),
            "urls": urls,
            "full_text_lens": full_lens,
            "error": err,
        })
        return out

    sc.search_with_smartcrawler = traced_sc
    # research_search and web_search import this name at module level
    import research.tools.research_search as rs
    rs.search_with_smartcrawler = traced_sc
    import research.tools.web_search as ws
    ws.search_with_smartcrawler = traced_sc

    # Hybrid scraper (used by e.g. a3 fetcher outside smartcrawler path)
    try:
        import research.tools.hybrid_scraper as hs
        if hasattr(hs, "hybrid_scrape"):
            _orig_hs = hs.hybrid_scrape

            async def traced_hs(url: str, *a, **kw):
                t = time.time()
                try:
                    out = await _orig_hs(url, *a, **kw)
                    err = None
                except Exception as e:
                    out = {"success": False, "content": "", "method": "error"}
                    err = str(e)
                counters["scrape_calls"] = counters.get("scrape_calls", 0) + 1
                log({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "tool": "hybrid_scrape",
                    "url": url,
                    "elapsed_s": round(time.time() - t, 2),
                    "success": (out or {}).get("success"),
                    "method": (out or {}).get("method"),
                    "content_len": len((out or {}).get("content") or ""),
                    "error": err,
                })
                return out

            hs.hybrid_scrape = traced_hs
    except Exception:
        pass

    # Tavily pool — force disable + log attempts
    try:
        from research.tools import tavily_pool as tp
        tp.tavily_pool.available = False
        _orig_search = tp.tavily_pool.search

        def blocked_search(*a, **kw):
            counters["tavily_attempts_blocked"] = counters.get("tavily_attempts_blocked", 0) + 1
            log({
                "ts": datetime.now(timezone.utc).isoformat(),
                "tool": "tavily_pool.search",
                "status": "BLOCKED (test-harness override)",
                "query": kw.get("query") or (a[0] if a else None),
            })
            raise RuntimeError("Tavily disabled by trace harness")

        tp.tavily_pool.search = blocked_search
    except Exception:
        pass

    return f


# ── Patch ChatOpenAI + CrewAI BaseLLM to capture every LLM call ─────────────

def install_llm_callback(handler: BaseCallbackHandler, counters: dict, llm_log_path: Path):
    """Inject callbacks into both paths LLM calls travel through:
    1. LangChain ChatOpenAI (used directly by some crew code paths)
    2. CrewAI BaseLLM.call (used by CrewAI agents — bypasses LangChain entirely)
    """
    # 1. LangChain
    from langchain_openai import ChatOpenAI
    _orig_init = ChatOpenAI.__init__

    def patched_init(self, *args, **kwargs):
        cbs = kwargs.get("callbacks") or []
        if isinstance(cbs, list):
            cbs = list(cbs) + [handler]
        kwargs["callbacks"] = cbs
        _orig_init(self, *args, **kwargs)

    ChatOpenAI.__init__ = patched_init

    # 2. CrewAI native LLM — patch every concrete class that overrides `call`.
    from crewai.llms.base_llm import BaseLLM
    # Force import of provider subclasses so they appear in __subclasses__.
    try:
        import crewai.llms.providers.openai.completion  # noqa: F401
        import crewai.llms.providers.anthropic.completion  # noqa: F401
    except Exception:
        pass

    log_f = open(llm_log_path, "a", encoding="utf-8")

    def log(event: dict):
        log_f.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")
        log_f.flush()

    def _normalize_messages(messages):
        msgs_in = []
        if isinstance(messages, str):
            msgs_in = [{"role": "user", "content": messages[:6000]}]
        elif isinstance(messages, list):
            for m in messages:
                if isinstance(m, dict):
                    msgs_in.append({"role": m.get("role", "?"),
                                    "content": str(m.get("content", ""))[:6000]})
                else:
                    msgs_in.append({"role": getattr(m, "type", type(m).__name__),
                                    "content": str(getattr(m, "content", ""))[:6000]})
        return msgs_in

    def _make_patched(orig_call):
        def patched_call(self, messages, *args, **kwargs):
            t = time.time()
            msgs_in = _normalize_messages(messages)
            try:
                out = orig_call(self, messages, *args, **kwargs)
                err = None
            except Exception as e:
                counters["llm_errors"] = counters.get("llm_errors", 0) + 1
                log({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "source": "crewai",
                    "class": type(self).__name__,
                    "model": getattr(self, "model", None),
                    "provider": getattr(self, "provider", None),
                    "elapsed_s": round(time.time() - t, 3),
                    "messages_in": msgs_in,
                    "error": str(e),
                })
                raise
            # Token usage — CrewAI tracks cumulative per-instance in self._token_usage (dict).
            # Take delta since last call on this instance.
            usage_delta = {}
            try:
                cur = getattr(self, "_token_usage", None) or {}
                last = getattr(self, "_trace_last_usage", None) or {}
                pt = int(cur.get("prompt_tokens", 0)) - int(last.get("prompt_tokens", 0))
                ct = int(cur.get("completion_tokens", 0)) - int(last.get("completion_tokens", 0))
                if pt >= 0 and ct >= 0:
                    usage_delta = {"prompt_tokens": pt, "completion_tokens": ct}
                self._trace_last_usage = dict(cur)
            except Exception:
                pass
            counters["llm_calls"] = counters.get("llm_calls", 0) + 1
            if usage_delta:
                counters["prompt_tokens"] = counters.get("prompt_tokens", 0) + max(0, usage_delta.get("prompt_tokens", 0))
                counters["completion_tokens"] = counters.get("completion_tokens", 0) + max(0, usage_delta.get("completion_tokens", 0))
            log({
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "crewai",
                "class": type(self).__name__,
                "model": getattr(self, "model", None),
                "provider": getattr(self, "provider", None),
                "elapsed_s": round(time.time() - t, 3),
                "messages_in": msgs_in,
                "completion": (out if isinstance(out, str) else str(out))[:8000],
                "usage_delta": usage_delta,
            })
            return out
        return patched_call

    # Walk the BaseLLM tree and patch any class that defines its OWN `call`
    def _all_subclasses(cls):
        seen, out, stack = set(), [], [cls]
        while stack:
            c = stack.pop()
            for sub in c.__subclasses__():
                if sub in seen:
                    continue
                seen.add(sub)
                out.append(sub)
                stack.append(sub)
        return out

    patched_classes = []
    for cls in [BaseLLM] + _all_subclasses(BaseLLM):
        if "call" in cls.__dict__:
            cls.call = _make_patched(cls.__dict__["call"])
            patched_classes.append(cls.__name__)
    print(f"[trace] patched LLM classes: {patched_classes}")
    return log_f


# ── Main run ────────────────────────────────────────────────────────────────

async def run_trace(topic: str):
    from research.core.state import create_initial_state
    from research.graph.build import build_graph
    from research.report.markdown_renderer import render_to_file, render_markdown

    run_id = str(uuid.uuid4())
    short = run_id[:8]
    root = Path(__file__).resolve().parent.parent  # backend2/
    trace_dir = root / "out" / f"trace_{short}"
    trace_dir.mkdir(parents=True, exist_ok=True)

    counters: dict = {
        "llm_calls": 0, "llm_errors": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "sc_calls": 0, "scrape_calls": 0, "tavily_attempts_blocked": 0,
    }

    # Handlers
    llm_handler = LLMTraceHandler(trace_dir / "llm_calls.jsonl", counters)
    tool_fh = install_tool_tracers(trace_dir / "tool_calls.jsonl", counters)
    crewai_fh = install_llm_callback(llm_handler, counters, trace_dir / "llm_calls.jsonl")

    # Record run metadata up front
    meta = {
        "run_id": run_id,
        "topic": topic,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model_provider": "openai",
        "model": "gpt-4o-mini (all tiers)",
    }

    print(f"[trace] run_id={short}  topic={topic!r}")
    print(f"[trace] output dir: {trace_dir}")

    initial_state = create_initial_state(run_id, topic)
    graph = build_graph()
    config = {
        "configurable": {"thread_id": run_id, "auto_pick": 1},  # auto-pick first variant
        "recursion_limit": 50,
    }

    node_updates_f = open(trace_dir / "node_updates.jsonl", "w", encoding="utf-8")
    snapshots_f = open(trace_dir / "node_snapshots.jsonl", "w", encoding="utf-8")

    t_start = time.time()
    last_state: dict = dict(initial_state)
    node_seq: list[dict] = []

    try:
        async for mode, chunk in graph.astream(
            initial_state, config=config, stream_mode=["updates", "values"]
        ):
            if mode == "updates":
                for node_name, patch in (chunk or {}).items():
                    entry = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "elapsed_s": round(time.time() - t_start, 2),
                        "node": node_name,
                        "keys": sorted(list((patch or {}).keys())),
                        "patch": _to_jsonable(patch),
                    }
                    node_updates_f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
                    node_updates_f.flush()
                    node_seq.append({
                        "node": node_name,
                        "keys": entry["keys"],
                        "elapsed_s": entry["elapsed_s"],
                    })
                    print(f"[trace] +{entry['elapsed_s']:>6.1f}s  node={node_name:<18} keys={entry['keys']}")
            elif mode == "values":
                last_state = chunk or last_state
                snap = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "elapsed_s": round(time.time() - t_start, 2),
                    "keys_nonempty": [k for k, v in (chunk or {}).items() if v not in (None, [], "", 0)],
                    "state": _to_jsonable(chunk),
                }
                snapshots_f.write(json.dumps(snap, default=str, ensure_ascii=False) + "\n")
                snapshots_f.flush()
    except Exception as e:
        print(f"[trace] ERROR during graph execution: {e}")
        import traceback
        traceback.print_exc()
        meta["error"] = str(e)
        meta["traceback"] = traceback.format_exc()
    finally:
        node_updates_f.close()
        snapshots_f.close()
        total_elapsed = round(time.time() - t_start, 2)

    # Persist final state + brief
    final_state = last_state
    (trace_dir / "final_state.json").write_text(
        json.dumps(_to_jsonable(final_state), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        render_to_file(final_state, str(trace_dir / "final_brief.md"))
    except Exception as e:
        (trace_dir / "final_brief.md").write_text(
            f"# Render failed\n\n{e}\n", encoding="utf-8"
        )

    # Cost estimate (gpt-4o-mini: $0.15/M in, $0.60/M out)
    cost = (counters["prompt_tokens"] / 1_000_000 * 0.15
            + counters["completion_tokens"] / 1_000_000 * 0.60)
    meta.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": total_elapsed,
        "counters": counters,
        "estimated_cost_usd": round(cost, 4),
        "node_sequence": node_seq,
    })
    (trace_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Build SUMMARY.md
    write_summary(trace_dir, final_state, meta, counters, node_seq)

    # Cleanup
    llm_handler.close()
    tool_fh.close()
    try:
        crewai_fh.close()
    except Exception:
        pass

    print(f"\n[trace] done in {total_elapsed:.1f}s   cost=${cost:.4f}")
    print(f"[trace] LLM calls: {counters['llm_calls']}  "
          f"tokens in/out: {counters['prompt_tokens']}/{counters['completion_tokens']}")
    print(f"[trace] search calls: {counters['sc_calls']}  "
          f"scrape calls: {counters['scrape_calls']}  "
          f"tavily blocked: {counters['tavily_attempts_blocked']}")
    print(f"[trace] full trace: {trace_dir}")


def write_summary(trace_dir: Path, final: dict, meta: dict, counters: dict, node_seq: list):
    def _count(x):
        try:
            return len(x)
        except Exception:
            return 0 if x is None else 1

    consolidated = final.get("consolidated")
    themes = []
    if consolidated:
        try:
            themes = consolidated.themes if hasattr(consolidated, "themes") else consolidated.get("themes", [])
        except Exception:
            themes = []

    sq = final.get("sub_questions") or []
    scratch = final.get("scratchpad_notes") or []
    topic_claims = final.get("topic_claims") or []
    market_claims = final.get("market_claims") or []
    news_claims = final.get("news_claims") or []
    validated = final.get("validated_claims") or []
    conflicts = final.get("conflicts") or []
    causations = final.get("causations") or []

    # Which scratchpad entries were actually written, and by whom?
    scratch_by_writer: dict[str, int] = {}
    for s in scratch:
        w = getattr(s, "written_by", None) or (s.get("written_by") if isinstance(s, dict) else None) or "?"
        scratch_by_writer[w] = scratch_by_writer.get(w, 0) + 1

    lines = [
        f"# Trace Summary — run {meta['run_id'][:8]}",
        "",
        f"**Topic:** {meta.get('topic')}",
        f"**Started:** {meta.get('started_at')}",
        f"**Finished:** {meta.get('finished_at')}",
        f"**Elapsed:** {meta.get('elapsed_s')} s",
        f"**Model:** {meta.get('model')}",
        f"**Estimated cost:** ${meta.get('estimated_cost_usd'):.4f}",
        "",
        "## Totals",
        "",
        f"- **LLM calls:** {counters['llm_calls']}  (errors: {counters.get('llm_errors',0)})",
        f"- **Tokens:** {counters['prompt_tokens']:,} in / {counters['completion_tokens']:,} out",
        f"- **SmartCrawler calls:** {counters['sc_calls']}",
        f"- **Hybrid scrape calls:** {counters['scrape_calls']}",
        f"- **Tavily calls blocked:** {counters['tavily_attempts_blocked']}",
        "",
        "## Pipeline output",
        "",
        f"- intent: `{final.get('intent')}`",
        f"- chosen_query: `{final.get('chosen_query','')[:120]}`",
        f"- query_variants: {_count(final.get('query_variants'))}",
        f"- sub_questions: {_count(sq)}",
        f"- scratchpad_notes: {_count(scratch)}  — by writer: {scratch_by_writer}",
        f"- topic_claims: {_count(topic_claims)}",
        f"- market_claims: {_count(market_claims)}",
        f"- news_claims: {_count(news_claims)}",
        f"- consolidated themes: {_count(themes)}",
        f"- validated_claims: {_count(validated)}",
        f"- conflicts: {_count(conflicts)}",
        f"- causations: {_count(causations)}",
        "",
        "## Node sequence (from LangGraph stream)",
        "",
    ]
    for n in node_seq:
        lines.append(f"- `{n['node']}` @ +{n['elapsed_s']}s  keys={n['keys']}")

    lines += [
        "",
        "## Files in this trace dir",
        "",
        "- `SUMMARY.md` — this file",
        "- `final_brief.md` — the research brief the pipeline produced",
        "- `final_state.json` — complete RunState dump",
        "- `node_updates.jsonl` — per-node state patch emitted during streaming",
        "- `node_snapshots.jsonl` — full state after each node",
        "- `llm_calls.jsonl` — every LLM prompt + completion + token usage",
        "- `tool_calls.jsonl` — every search + scrape call with results",
        "- `run_meta.json` — totals and node sequence",
        "",
        "## Usefulness audit cheatsheet",
        "",
        "Open `llm_calls.jsonl` and check for each LLM call:",
        "- Is the system prompt clearly scoped? Any dead instructions?",
        "- Is the completion empty, truncated, or garbage? (→ waste)",
        "- Does a downstream node actually *read* the field this call produced?",
        "",
        "Open `tool_calls.jsonl` and check:",
        "- Any query returning 0 results? (→ wasted call)",
        "- `full_text_lens` very short? (→ page was Cloudflared / JS-gated)",
        "- Duplicate queries? (→ cache wasn't hit; investigate)",
        "",
        "Cross-reference `final_state.json`:",
        "- Fields that are `[]`, `\"\"`, or `null` after the run = agent produced nothing useful there.",
        "- `scratchpad_notes` written but never referenced by downstream narratives = waste.",
    ]
    (trace_dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]).strip() or "EV charging infrastructure in Europe 2025"
    asyncio.run(run_trace(topic))

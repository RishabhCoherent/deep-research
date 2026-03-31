# Deep Research — Claude Code Project Guide

## What This Project Does
A multi-layer research agent that produces publication-ready market research reports. Users enter a topic, the system autonomously searches the web, collects facts, verifies them, and writes a structured report. Layer 2 uses a structured **analyst agent** with mandatory hypothesis-driven reasoning (think → research → reflect) and a full audit trail.

## Architecture

### 3-Layer Pipeline
```
Layer 0: BASELINE   — Single LLM prompt, no tools
Layer 1: ENHANCED   — Web search + synthesis (LangGraph agent)
Layer 2: ANALYST    — LangGraph analyst agent with structured reasoning
```
L0 and L1 run in **parallel** via `asyncio.gather()`. L2 runs after L1 completes (receives L1's output as prior context).

Layer 2 (Analyst) internally runs 5 sequential phases:
```
Phase 1 (DECOMPOSE) → Phase 2 (INVESTIGATE) → Phase 3 (ANALYZE) → Phase 4 (QUALITY GATE) → Phase 5 (COMPOSE)
   AnalysisFramework    ResearchBoard          AnalysisResult       QualityScore            Final Report
```

The investigation phase enforces a **mandatory reasoning loop** per sub-question:
```
THINK (form hypothesis) → RESEARCH (search + scrape) → REFLECT (evaluate against hypothesis) → RECORD
```

### Stack
- **Backend**: Python 3.11+ / FastAPI / LangChain / LangGraph / OpenAI LLMs
- **Frontend**: Next.js 16 / React 19 / TypeScript / Tailwind v4 / shadcn/ui
- **Search**: SearXNG (Docker, port 8888) primary, Tavily optional, DuckDuckGo fallback
- **State**: Zustand (client), in-memory job store (server)
- **Progress**: SSE streaming from FastAPI → Next.js

### Key Entry Points
| File | Purpose |
|------|---------|
| `backend/api.py` | FastAPI endpoints + uvicorn entry point (`python api.py`) |
| `backend/research_manager.py` | Thread-based job management, serializes results to frontend |
| `backend/research_agent/pipeline.py` | Orchestrates L0+L1 parallel → L2 analyst |
| `backend/research_agent/__init__.py` | Public API: `run_all_layers()` |
| `backend/research_agent/analyst/run.py` | Analyst agent orchestrator (5 phases) |
| `backend/research_agent/analyst/graph.py` | LangGraph definition (think→research→reflect loop) |
| `frontend/` | Next.js app (App Router) |

### research_agent/ Structure
```
research_agent/
    __init__.py          # Public API: run_all_layers()
    pipeline.py          # Orchestrator — L0+L1 parallel, then L2 analyst
    models.py            # Pipeline data classes (Source, ResearchResult, ComparisonReport, etc.)
    evaluator.py         # Comparative scoring (currently disabled)
    prompts.py           # Prompts for baseline, enhanced, evaluation
    utils.py             # Helpers: get_content, extract_json, strip_preamble, infer_publisher
    cost.py              # Token/cost tracking with per-model pricing
    cli.py               # print_report, save_report

    layers/              # L0 and L1 strategies
        baseline.py      # Layer 0: single LLM prompt
        enhanced.py      # Layer 1: LangGraph agent with web search

    analyst/             # Layer 2: structured analyst agent
        __init__.py      # Lazy import of run_analyst
        run.py           # Orchestrator: decompose → investigate → analyze → quality → compose
        graph.py         # LangGraph: mandatory think → research → reflect → record loop
        models.py        # Analyst data classes (ResearchBoard, SubQuestion, AnalystEvidence, ResearchTrace, etc.)
        prompts.py       # All analyst prompts + banned research firm list
        quality.py       # Deterministic quality scoring (5 dimensions)
        tools.py         # Hybrid scraper (Trafilatura → aiohttp+BS4 fallback)
        phases/
            decompose.py # Phase 1: topic → AnalysisFramework (10-15 typed sub-questions)
            investigate.py # Phase 2: runs LangGraph per sub-question with quality gate loop
            analyze.py   # Phase 3: cross-reference findings, form judgments, resolve contradictions
            compose.py   # Phase 5: two-pass report writing (outline → prose → auto-expand)
```

### Core Data Types

**Pipeline types** (in `research_agent/models.py`):
| Type | Description |
|------|-------------|
| `Source` | URL, title, snippet, tier (1=gold, 2=reliable, 3=unknown) |
| `ResearchResult` | Per-layer output (content, sources, metadata, trace) |
| `ComparisonReport` | All layers + evaluations + summary |

**Analyst types** (in `research_agent/analyst/models.py`):
| Type | Description |
|------|-------------|
| `AnalysisFramework` | Core question, sub-questions with types/strategies/priorities |
| `SubQuestion` | Typed question with status, hypothesis, answer, confidence |
| `ResearchBoard` | Central state: framework + evidence + contradictions + judgments + budget |
| `AnalystEvidence` | Single finding with source URL, tier, confidence, evidence type |
| `Contradiction` | Conflict between sources with resolution tracking |
| `AnalystJudgment` | Analyst opinion with conviction level and reasoning |
| `ResearchTrace` | Full audit trail of every reasoning step (for demos) |
| `TraceStep` | Single step: phase, sq_id, title, content dict, elapsed_s |
| `AnalysisResult` | Key findings, judgments, causal chains, narrative thread |
| `QualityScore` | 5-dimension quality assessment (coverage, evidence strength, etc.) |

### Tools (used by analyst agent during investigation)
| Tool | File | Returns |
|------|------|---------|
| `search()` | `backend/tools/search.py` | `list[dict]` — title, url, snippet (SearXNG → Tavily → DDG fallback) |
| `hybrid_scrape()` | `backend/research_agent/analyst/tools.py` | `dict` — success, content, method (Trafilatura → aiohttp+BS4) |
| `get_source_tier()` | `backend/tools/source_classifier.py` | `int` (1=gold, 2=reliable, 3=unknown) |
| `is_banned_source()` | `backend/tools/citation.py` | `bool` — filters 70+ competitor research firms |

### LLM Model Tiers (in `backend/config.py`)
```
set_model_tier("standard" | "premium" | "budget" | "reasoning")
```
| Tier | Planner | Writer | Analyst |
|------|---------|--------|---------|
| standard | gpt-4o | gpt-4o | gpt-4o |
| premium | gpt-4.1 | gpt-4.1 | gpt-4.1 |
| budget | gpt-4o-mini | gpt-4o-mini | gpt-4o-mini |
| reasoning | gpt-5.2 | gpt-5.2 | gpt-5.2 |

The analyst agent uses: `standard` for decompose/compose-outline, `premium` for investigate/compose-report, `reasoning` for analyze.

### Research Trace (Audit Trail)
Every analyst run produces a `ResearchTrace` capturing each reasoning step. Saved as:
- `result.trace` — `ResearchTrace` object on `ResearchResult`
- `result.metadata["trace"]` — dict version, serialized to frontend

The trace is rendered in the frontend via the **Research Trace** popup on the results page (`components/AnalystTrace.tsx`).

Trace phases captured:
| Phase | What's Recorded |
|-------|----------------|
| `decompose` | Core question, assumptions, all sub-questions with types/strategies |
| `think` | Hypothesis, what would change mind, planned search queries |
| `search` | Query, results with titles/URLs/snippets/tiers |
| `scrape` | URL, success/fail, method, content length, preview |
| `reflect` | Findings (confirm/contradict), contradictions, answer, confidence |
| `analyze` | Key findings, judgments with conviction, causal chains |
| `quality` | 5-dimension scores, pass/fail, feedback |
| `compose` | Word count, sections |

### Frontend Structure
```
frontend/
    app/
        research/
            page.tsx              # Input form (Step 1)
            progress/page.tsx     # Real-time SSE progress (Step 2)
            results/page.tsx      # Final results with popups (Step 3)
            history/page.tsx      # Past research list
            history/[id]/page.tsx # Archived research detail
    components/
        AnalystTrace.tsx      # Research trace timeline (hypothesis/search/reflect journey)
        ScrollPipeline.tsx    # Claim transformation pipeline (L0→L1 overview)
        ComparatorContent.tsx # Side-by-side layer comparison
        LayerPopupContent.tsx # Per-layer metrics + markdown report
        ResultsPopup.tsx      # Full-screen modal container (Framer Motion)
        MarkdownReport.tsx    # Markdown renderer with callouts and styling
        ScoreChart.tsx        # Radar/spider chart for evaluation scores
    lib/
        types.ts              # All TypeScript interfaces (including AnalystTrace types)
        store.ts              # Zustand state management
        api.ts                # Backend API calls + SSE URLs
        extract-agent-steps.ts # Extract workflow data from layer metadata
    hooks/
        useResearch.ts        # SSE streaming handler + auto-redirect
```

## Critical Implementation Details

### LLM Response Handling
LLM `response.content` can be a `str` OR a `list[dict]` depending on the model. **Always** use `get_content(response)` from `research_agent/utils.py` — never call `response.content.strip()` directly.

### scrape_url() / hybrid_scrape() Returns a Dict, Not a String
`hybrid_scrape()` returns `dict` with `{"success", "content", "method"}`. The older `scrape_url()` returns `Optional[dict]` with `{"url", "title", "content", "extraction_date"}`. Extract text via `result.get("content", "")`. Never call `.strip()` on the result directly.

### Fact.value Type Safety
LLM-extracted JSON may return numbers for `value` fields. Always coerce to `str()` when creating `Fact` objects: `value=str(item.get("value", ""))`.

### LLM JSON Parsing
LLMs return unpredictable JSON shapes. When extracting lists from LLM JSON output, always guard with `isinstance(x, list)` before iterating. Use `extract_json()` from `research_agent/utils.py` for robust parsing.

### SubQuestion.is_answered vs is_resolved
- `is_answered` — strict: only `status == "answered"` (used for coverage scoring)
- `is_resolved` — loose: `status in ("answered", "gap")` (used for "are we done?" checks)
- `needs_research` — `status in ("pending", "researching", "conflicted")`

### Quality Gate Behavior
- Zero evidence → hard fail (0%, never passes)
- All gaps with no real answers → gap_acknowledgment penalized by 70%
- Pass threshold: 0.65 first iteration, 0.55 on retries
- On fail: adds 15 tool calls to budget, re-runs investigation with remediation queries

### Frontend Conventions
- Tailwind v4: CSS-based config, NOT `tailwind.config.ts`. Custom classes go in plain CSS.
- shadcn/ui: `new-york` style, `@/` path aliases, `components.json` config
- No inline citations — bibliography at end of reports only
- Layer names in frontend: `L1 Baseline`, `L2 Enhanced`, `L3 CMI Expert`
- Analyst trace detection: `layers[2].metadata.method === "analyst_agent"`
- ScrollPipeline skips expert steps when analyst format detected (backward compatible)

## Development

### Starting the System
```bash
# 1. Start SearXNG (required for search)
docker-compose up -d

# 2. Start backend (from backend/ directory)
cd backend && python api.py    # uvicorn on port 8000

# 3. Start frontend (separate terminal)
cd frontend && npm run dev     # Next.js on port 3000
```

### Environment
- Windows 10, Python 3.11+, Node 20+
- `.env` file at project root (never commit)
- Required: `OPENAI_API_KEY`
- Optional: `SEARXNG_URL` (default http://localhost:8888), `TAVILY_API_KEY` / `TAV_API_KEYS`
- Docker Desktop for SearXNG container

### Testing a Research Run
```bash
# Via API
curl -X POST http://127.0.0.1:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "your topic here"}'

# Via test script (runs analyst agent directly, saves trace)
python test_analyst.py
```
Monitor progress via SSE: `GET /api/research/{job_id}/progress`

### Running the Analyst Agent Directly
```python
import asyncio
from research_agent.analyst import run_analyst

result = await run_analyst(
    topic="Your research topic",
    brief="Optional context and focus areas",
    progress_callback=lambda layer, phase, msg: print(f"[{phase}] {msg}"),
)

# result.content — markdown report
# result.trace — ResearchTrace with full audit trail
# result.trace.to_markdown() — human-readable trace
# result.metadata["trace"] — dict version
```

### Common Pitfalls
1. **Stale Python processes on Windows**: Port 8000 may be held by zombie processes. Use `netstat -ano | grep :8000` to find and `taskkill /F /PID <pid>` to kill.
2. **`__pycache__` serving old code**: After changing phase files, kill ALL python processes and delete `__pycache__` dirs before restarting. Uvicorn's reloader doesn't help when research runs in a separate thread.
3. **Uvicorn reload vs threads**: The research pipeline runs in a background thread that imports modules once. File changes aren't picked up until the server fully restarts.
4. **Evaluation currently disabled**: `pipeline.py` skips the evaluation/comparison phase to reduce cost. Re-enable by uncommenting lines 113-115.
5. **Banned sources**: 70+ competitor research firms (MarketsandMarkets, Gartner, etc.) are filtered from search results and never cited. List in `tools/citation.py` and `analyst/prompts.py`.

## Code Style
- Python: standard library imports first, then third-party, then local
- No inline citations in generated reports
- Competitor data filtered via `is_banned_source()` — used for research but never cited
- Cost tracking via `track()` from `research_agent/cost.py` for every LLM call
- Brand colors: navy=#006B77, cyan=#00BCD4, steel=#5A7D8C

## Cost Estimates (per research run, standard tier)
| Phase | Model | Approx Cost |
|-------|-------|-------------|
| L0 Baseline | gpt-4o | ~$0.02 |
| L1 Enhanced | gpt-4o + gpt-4o-mini | ~$0.05-0.10 |
| L2 Analyst | gpt-4o + gpt-4.1 + gpt-5.2 | ~$0.40-0.60 |
| **Total** | | **~$0.50-0.75** |

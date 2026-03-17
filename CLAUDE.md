# Deep Research — Claude Code Project Guide

## What This Project Does
A multi-layer research agent that produces publication-ready market research reports. Users enter a topic, the system autonomously searches the web, collects facts, verifies them, and writes a structured report.

## Architecture

### 3-Layer Parallel Pipeline
```
Layer 0: BASELINE   — Single LLM prompt, no tools
Layer 1: ENHANCED   — Web search + synthesis (ReAct agent)
Layer 2: EXPERT     — Full 4-phase pipeline (Understand → Research → Analyze → Write)
```
All 3 layers run concurrently via `asyncio.gather()`. Layer 2 internally runs 4 sequential phases:
```
Phase 1 (UNDERSTAND) → Phase 2 (RESEARCH) → Phase 3 (ANALYZE) → Phase 4 (WRITE)
   ResearchPlan          KnowledgeBase        Verified KB          Final Report
```

### Stack
- **Backend**: Python 3.11+ / FastAPI / LangChain / OpenAI LLMs
- **Frontend**: Next.js 16 / React 19 / TypeScript / Tailwind v4 / shadcn/ui
- **Search**: SearXNG (Docker, port 8888) primary, DuckDuckGo fallback, Tavily optional
- **State**: Zustand (client), in-memory job store (server)
- **Progress**: SSE streaming from FastAPI → Next.js

### Key Entry Points
| File | Purpose |
|------|---------|
| `start.py` | Start backend (uvicorn on port 8000) |
| `backend/api.py` | FastAPI endpoints (`/api/research`, `/api/health`, etc.) |
| `backend/research_manager.py` | Thread-based job management, runs pipeline in background |
| `research_agent/pipeline.py` | Orchestrates 3 layers in parallel, then evaluates |
| `research_agent/__init__.py` | Public API: `run_all_layers()` |
| `research_agent/cli.py` | Console output: `print_report()`, `save_report()` |
| `frontend/` | Next.js app (App Router) |

### research_agent/ Structure
```
research_agent/
    __init__.py          # Public API: run_all_layers()
    pipeline.py          # Orchestrator — runs 3 layers in parallel
    models.py            # ALL data classes (Source, Fact, KnowledgeBase, etc.)
    react_engine.py      # ReAct loop + tool factory
    evaluator.py         # Comparative scoring
    prompts.py           # ALL prompts (baseline, enhanced, evaluation, phases)
    utils.py             # Helpers: get_content, extract_json, strip_preamble, infer_publisher
    cost.py              # Token/cost tracking
    cli.py               # print_report, save_report

    layers/              # 3 parallel research strategies
        baseline.py      # Layer 0: single LLM prompt
        enhanced.py      # Layer 1: ReAct agent with web search
        expert.py        # Layer 2: full 4-phase pipeline

    phases/              # 4 sequential steps inside Layer 2
        understand.py    # Phase 1: topic → ResearchPlan
        research.py      # Phase 2: plan → KnowledgeBase
        analyze.py       # Phase 3: plan + kb → verified kb + insights
        write.py         # Phase 4: plan + kb + insights → report
```

### Core Data Types (all in `research_agent/models.py`)
| Type | Description |
|------|-------------|
| `ResearchPlan` | Sections, questions, search queries |
| `KnowledgeBase` | Accumulated `Fact` objects |
| `Fact` | Single claim with source, tier, confidence |
| `ResearchResult` | Per-layer output (content, sources, metadata) |
| `ComparisonReport` | All layers + evaluations + summary |
| `EvalResult` | Draft evaluation scores |
| `AgentContext` | ReAct agent state (sources, iterations, kb) |

### Tools (used by Phase 2)
| Tool | File | Returns |
|------|------|---------|
| `search()` | `tools/search.py` | `list[dict]` with title, url, snippet |
| `scrape_url()` | `tools/scraper.py` | `Optional[dict]` with url, title, **content**, extraction_date |
| `get_source_tier()` | `tools/source_classifier.py` | `int` (1=gold, 2=reliable, 3=unknown) |

## Critical Implementation Details

### LLM Response Handling
LLM `response.content` can be a `str` OR a `list[dict]` depending on the model. **Always** use `get_content(response)` from `research_agent/utils.py` — never call `response.content.strip()` directly.

### scrape_url() Returns a Dict, Not a String
`scrape_url()` returns `Optional[dict]` with `{"url", "title", "content", "extraction_date"}`. Extract text via `result.get("content", "")`. Never call `.strip()` on the result directly.

### Fact.value Type Safety
LLM-extracted JSON may return numbers for `value` fields. Always coerce to `str()` when creating `Fact` objects: `value=str(item.get("value", ""))`.

### LLM JSON Parsing
LLMs return unpredictable JSON shapes. When extracting lists from LLM JSON output, always guard with `isinstance(x, list)` before iterating. Use `extract_json()` from `research_agent/utils.py` for robust parsing.

### Frontend Conventions
- Tailwind v4: CSS-based config, NOT `tailwind.config.ts`. Custom classes go in plain CSS.
- shadcn/ui: `new-york` style, `@/` path aliases, `components.json` config
- No inline citations — bibliography at end of reports only
- Layer names in frontend: Research Plan (L0), Data Collection (L1), Verification (L2), Final Report (L3)

## Development

### Starting the System
```bash
# 1. Start SearXNG (required for search)
docker-compose up -d

# 2. Start backend
python start.py          # uvicorn on port 8000

# 3. Start frontend
cd frontend && npm run dev  # Next.js on port 3000
```

### Environment
- Windows 10, Python 3.11+, Node 20+
- `.env` file at project root (never commit)
- Docker Desktop for SearXNG container

### Testing a Research Run
```bash
curl -X POST http://127.0.0.1:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "your topic here", "max_layer": 3}'
```
Monitor progress via SSE: `GET /api/research/{job_id}/progress`

### Common Pitfalls
1. **Stale Python processes on Windows**: Port 8000 may be held by zombie processes. Use `netstat -ano | grep :8000` to find and `taskkill /F /PID <pid>` to kill.
2. **`__pycache__` serving old code**: After changing phase files, kill ALL python processes and delete `__pycache__` dirs before restarting. Uvicorn's reloader doesn't help when research runs in a separate thread.
3. **Uvicorn reload vs threads**: The research pipeline runs in a background thread that imports modules once. File changes aren't picked up until the server fully restarts.

## Code Style
- Python: standard library imports first, then third-party, then local
- No inline citations in generated reports
- Competitor data tagged `_is_competitor=True`, used for research but never cited
- Cost tracking via `track()` from `research_agent/cost.py` for every LLM call
- Brand colors: navy=#006B77, cyan=#00BCD4, steel=#5A7D8C

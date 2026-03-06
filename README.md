# Coherent Market Insights — AI Research & Reports

Unified platform for AI-powered market research and report generation. Combines a **multi-layer research agent** (progressive web research, analysis, and expert review) with an **automated report generator** that produces professional `.docx` reports from structured data.

**Two core features:**

1. **Research Agent** — Enter any topic, run 4 progressive layers of AI research (baseline → web research → framework analysis → expert contrarian review), compare quality across layers, and view cost breakdowns.
2. **Report Generator** — Upload PPTX (Table of Contents) + XLSX (Market Estimates), extract structured data, generate ~80-page `.docx` reports with charts, tables, bibliography, and LLM-written analysis.

---

## Features

### Research Agent
- **Multi-layer research pipeline** — 4 progressive layers: L0 (baseline LLM), L1 (web search + synthesis), L2 (cross-reference + frameworks), L3 (assumption challenging + contrarian views)
- **Quality evaluation** — Automated scoring on factual density, source diversity, specificity, framework usage, insight depth, and contrarian views
- **Cost tracking** — Per-component token usage (input, output, reasoning) with cost breakdowns
- **Model tier selection** — Standard, premium, budget, or reasoning model configurations
- **Real-time progress** — SSE-streamed layer-by-layer progress with vertical timeline UI

### Report Generator
- **Discovery-based parsers** — TOC extracted from PPTX via XML margin-left hierarchy; ME data from XLSX via year-pattern header detection. No hardcoded row/column assumptions.
- **AI content generation** — GPT-4o writes section-specific prose (overview, insights, segment analysis, competitive profiles) guided by section-specific prompt templates.
- **Web research pipeline** — SearXNG (self-hosted metasearch) primary, DuckDuckGo fallback. Up to 3 research iterations per subsection with LLM-based source classification.
- **Citation management** — Tracks all sources, validates against banned list (45+ competing research firms), competitor data used for research context but never cited. Bibliography at end of report.
- **Charts & tables** — 5 chart types (combo forecast, doughnut share, stacked 100%, horizontal bars, line YoY) and 4 table types (forecast, snapshot, growth, share) via matplotlib + python-docx.
- **PPTX-style layout** — Slide-per-page Word sections with recurring header/footer bars, landscape orientation, branded color scheme.

### Platform
- **Modern web UI** — Next.js + React frontend with dark purple/orange/coral theme, glass-morphism design, real-time SSE progress streaming.
- **Unified landing page** — Single hub to access both Report Generator and Research Agent.
- **FastAPI backend** — RESTful API layer bridging the frontend to both Python pipelines, with SSE for real-time progress.

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker Desktop (for SearXNG search engine)
- OpenAI API key

### 1. Clone and install Python dependencies

```bash
git clone <repo-url>
cd deep-research
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Required
OPENAI_API_KEY=sk-...

# SearXNG (auto-detected, no key needed)
SEARXNG_URL=http://localhost:8888
```

### 3. Start SearXNG (search engine)

```bash
docker compose up -d
```

This starts a local SearXNG instance that aggregates Google, Bing, DuckDuckGo, Wikipedia, and Google Scholar. If SearXNG is unavailable, the system falls back to DuckDuckGo.

### 4. Start the application

**Option A: Web UI (recommended)**

```bash
# Terminal 1: FastAPI backend
python -m uvicorn backend.api:app --reload --port 8000

# Terminal 2: Next.js frontend
cd frontend
npm install   # first time only
npm run dev
```

Open **http://localhost:3000** — choose between Research Agent or Report Generator from the landing page.

**Option B: CLI**

```bash
# Research Agent
python main.py "Global EV Battery Market" --max-layer 3

# Report Generator — Extract + Generate
python extract_inputs.py --pptx "Report.pptx" --xlsx "ME_Report.xlsx" -o inputs/data.json
python -m report.generate inputs/data.json -o outputs/report.docx

# Fast preview (charts + tables only, no LLM content):
python -m report.generate inputs/data.json --no-content -o outputs/preview.docx
```

---

## Architecture

```
┌─────────────────────┐        HTTP/SSE        ┌─────────────────────────┐
│  Next.js Frontend   │  ◄───────────────────►  │  FastAPI Backend        │
│  React 19 + TS      │    localhost:3000       │  localhost:8000         │
│  Tailwind + shadcn  │    (proxied)            │                         │
│  Purple/Orange UI   │                         │  ┌───────────────────┐  │
│                     │                         │  │ Report Generator  │  │
│  ┌───────────────┐  │                         │  │ Extractors        │  │
│  │ Landing Page  │  │                         │  │ Content Engine    │  │
│  │ ├─ Report Gen │  │                         │  │ Document Assembly │  │
│  │ └─ Research   │  │                         │  ├───────────────────┤  │
│  └───────────────┘  │                         │  │ Research Agent    │  │
└─────────────────────┘                         │  │ 4-Layer Pipeline  │  │
                                                │  │ Cost Tracking     │  │
┌─────────────────────┐                         │  └───────────────────┘  │
│  SearXNG            │  ◄── search queries ──  │                         │
│  Docker :8888       │                         └─────────────────────────┘
│  Google/Bing/DDG    │
└─────────────────────┘

┌─────────────────────┐
│  OpenAI API         │  ◄── LLM calls
│  GPT-4o / 4o-mini   │
│  + reasoning models │
└─────────────────────┘
```

### Research Agent Pipeline

```
Topic Input
    │
    ▼
┌─────────────────────────────────────────┐
│  Layer 0 — Baseline                     │
│  Single LLM prompt, no external research│
├─────────────────────────────────────────┤
│  Layer 1 — Research Agent               │
│  Web search + source gathering +        │
│  synthesis of findings                  │
├─────────────────────────────────────────┤
│  Layer 2 — Analysis Agent               │
│  Cross-reference + framework application│
│  + gap-filling from additional sources  │
├─────────────────────────────────────────┤
│  Layer 3 — Expert Agent                 │
│  Assumption challenging + contrarian    │
│  views + expert-level synthesis         │
└──────────┬──────────────────────────────┘
           │
           ▼
   Comparison Report
   (scores, content, costs per layer)
```

### Report Generator Pipeline

```
PPTX + XLSX
    │
    ▼
┌─────────────────────────────────┐
│  Extraction                     │
│  toc_extractor.py → TOC dict   │
│  me_extractor.py  → ME dict    │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Mapping (mapper.py)            │
│  TOC sections → SectionPlans   │
│  Fuzzy-match segments to ME    │
│  Classify: overview, segment,  │
│  key_insights, regional,       │
│  competitive, appendix         │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Content Generation (engine.py) │
│  For each section:              │
│  1. Extract data insights       │
│  2. Web research (SearXNG)      │
│  3. LLM writes prose            │
│  4. Sources → bibliography      │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Document Assembly              │
│  Cover page + TOC               │
│  Section builders (per type)    │
│  Charts (matplotlib, 300 DPI)   │
│  Tables (styled docx)           │
│  Slide-per-page layout          │
│  Bibliography                   │
└──────────┬──────────────────────┘
           │
           ▼
       .docx Report
```

---

## Web UI

The frontend is a unified platform with two flows accessible from a landing page:

### Landing Page (`/`)

Hub with two feature cards — Report Generator and Research Agent — plus real-time API status indicators (OpenAI, SearXNG).

### Report Generator (4-step wizard)

| Step | Page | What Happens |
|------|------|-------------|
| 1 | `/upload` | Upload PPTX + XLSX files, or load pre-extracted JSON |
| 2 | `/extract` | Preview extracted sections, configure generation settings |
| 3 | `/generate` | Real-time progress via SSE — watch research + writing happen |
| 4 | `/download` | Download the generated `.docx` report |

### Research Agent (3-step flow)

| Step | Page | What Happens |
|------|------|-------------|
| 1 | `/research` | Enter topic, select max layer depth (L0-L3), choose model tier |
| 2 | `/research/progress` | Vertical timeline with SSE-streamed layer progress + activity log |
| 3 | `/research/results` | Summary metrics, quality score chart, layer content tabs, cost breakdown |

**Tech stack:** Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Zustand, Framer Motion

The sidebar is context-aware — shows wizard settings on report pages, navigation links on research pages, and feature cards on the landing page.

---

## Report Structure

The generated `.docx` contains:

| Section | Type | Content |
|---------|------|---------|
| Cover Page | Static | Title, subtitle, table of contents |
| Market Overview | overview | Market definition, total volume/value charts, executive summary with doughnut charts + snapshot tables per dimension |
| Key Insights | key_insights | Market dynamics (drivers/restraints/opportunities), PEST analysis, Porter's analysis, pricing tables, trends, regulatory scenario |
| Segment Analysis (x5) | segment | Per-dimension: BPS stacked chart, forecast tables, per-item combo charts + narrative |
| Regional Analysis | region | Cross-region overview, per-region/country breakdown with charts + tables |
| Competitive Landscape | competitive | Company tables by geography, individual company profiles |
| Analyst Recommendations | appendix | Wheel of Fortune, analyst view, opportunity map |
| Research Methodology | appendix | Methodology, about us |
| Bibliography | — | All research sources with URLs |

---

## Project Structure

```
deep-research/
├── backend/                       # FastAPI API layer
│   ├── api.py                    #   All endpoints (extract, generate, research, health)
│   ├── job_manager.py            #   In-memory job store for generation threads
│   ├── research_manager.py       #   In-memory job store for research threads
│   └── models.py                 #   Pydantic request/response schemas
│
├── frontend/                      # Next.js web application
│   ├── app/                      #   App Router pages
│   │   ├── layout.tsx            #     Root layout (Inter font, dark theme)
│   │   ├── page.tsx              #     Landing page (hub for both features)
│   │   ├── upload/page.tsx       #     Report: Step 1 — File upload
│   │   ├── extract/page.tsx      #     Report: Step 2 — Extraction preview
│   │   ├── generate/page.tsx     #     Report: Step 3 — Generation progress
│   │   ├── download/page.tsx     #     Report: Step 4 — Download report
│   │   └── research/             #     Research Agent flow
│   │       ├── page.tsx          #       Step 1 — Topic + config
│   │       ├── progress/page.tsx #       Step 2 — Layer progress timeline
│   │       └── results/page.tsx  #       Step 3 — Results + scores + costs
│   ├── components/               #   React components
│   │   ├── ui/                   #     shadcn/ui components
│   │   ├── WizardLayout.tsx      #     Report wizard shell
│   │   ├── ResearchLayout.tsx    #     Research 3-step layout
│   │   ├── StepIndicator.tsx     #     4-step progress bar
│   │   ├── Sidebar.tsx           #     Context-aware navigation + status
│   │   ├── FileDropZone.tsx      #     Drag-and-drop upload
│   │   ├── SectionPlanList.tsx   #     Section plan tree
│   │   ├── ProgressStream.tsx    #     Real-time progress display
│   │   ├── ReportCard.tsx        #     Metric card with count-up animation
│   │   ├── LayerCard.tsx         #     Research layer result display
│   │   ├── CostBreakdown.tsx     #     Token usage + cost table
│   │   └── ScoreChart.tsx        #     Quality score comparison chart
│   ├── lib/                      #   Shared utilities
│   │   ├── api.ts                #     Backend API client (report + research)
│   │   ├── store.ts              #     Zustand stores (wizard + research)
│   │   └── types.ts              #     TypeScript interfaces
│   └── hooks/                    #   Custom React hooks
│       ├── useGeneration.ts      #     Report generation SSE hook
│       ├── useResearch.ts        #     Research progress SSE hook
│       └── useHealth.ts          #     API health polling
│
├── research_agent/                # Multi-layer research agent
│   ├── runner.py                 #   Orchestrates all layers
│   ├── cost.py                   #   Token usage + cost tracking
│   ├── evaluator.py              #   Quality scoring across layers
│   └── layers/                   #   Per-layer logic
│
├── extractors/                    # File parsers
│   ├── toc_extractor.py          #   PPTX → TOC hierarchy
│   └── me_extractor.py           #   XLSX → market estimate data
│
├── report/                        # Report generation
│   ├── generate.py               #   Main orchestrator (async)
│   ├── mapper.py                 #   TOC → SectionPlan mapping
│   ├── styles.py                 #   Document formatting + slide layout
│   ├── charts.py                 #   Chart generation (5 types)
│   ├── tables.py                 #   Table generation (4 types)
│   ├── content/                  #   LLM content engine
│   │   ├── engine.py             #     Section-by-section generation
│   │   ├── citations.py          #     Citation tracking
│   │   ├── research.py           #     Web research with source filtering
│   │   ├── data_insights.py      #     ME data → text insights
│   │   ├── writer.py             #     LLM section writing
│   │   └── prompts.py            #     Section-specific prompts
│   └── sections/                 #   Document section builders
│       ├── cover.py              #     Title page + TOC
│       ├── overview.py           #     Market Overview
│       ├── key_insights.py       #     Key Industry Insights
│       ├── segment.py            #     Segment Analysis
│       ├── regional.py           #     Regional Analysis
│       ├── competitive.py        #     Competitive Landscape
│       └── appendix.py           #     Appendix sections
│
├── tools/                         # Search & citation tools
│   ├── search.py                 #   SearXNG + DuckDuckGo search
│   ├── scraper.py                #   Web page content extraction
│   ├── citation.py               #   Source validation + ID generation
│   └── source_classifier.py      #   LLM-based competitor detection
│
├── ui/                            # Legacy Streamlit UI (kept for CLI bridge)
│   ├── generation.py             #   Thread-based async generation bridge
│   └── extraction.py             #   File extraction helpers
│
├── nodes/                         # LangGraph pipeline nodes
│   ├── planner.py                #   Plan research queries
│   ├── researcher.py             #   Execute web searches
│   ├── organizer.py              #   Structure raw data
│   ├── analyst.py                #   Analyze findings
│   ├── writer.py                 #   Write prose
│   ├── reviewer.py               #   Quality check
│   └── assembler.py              #   Combine output
│
├── prompts/                       # LLM prompt templates
│
├── searxng/                       # SearXNG configuration
│   ├── settings.yml              #   Search engine config
│   └── limiter.toml              #   Rate limiting (disabled for local)
│
├── docker-compose.yml             # SearXNG Docker setup
├── config.py                      # LLM factory, model tiers, constants
├── extract_inputs.py              # CLI: PPTX+XLSX → JSON
├── main.py                        # CLI: Research agent entry point
├── app.py                         # Legacy Streamlit entry point
├── requirements.txt               # Python dependencies
└── .env.example                   # Environment variable template
```

---

## Configuration

### LLM Models

Configured in `config.py` with selectable model tiers:

| Tier | Models | Use Case |
|------|--------|----------|
| standard | GPT-4o + GPT-4o-mini | Default, good balance |
| premium | GPT-4o for all roles | Highest quality |
| budget | GPT-4o-mini for all roles | Lowest cost |
| reasoning | o1/o3 reasoning models | Deep analysis tasks |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o |
| `SEARXNG_URL` | No | SearXNG URL (default: `http://localhost:8888`) |

### Search Engine

**SearXNG** (recommended) — self-hosted metasearch engine aggregating Google, Bing, DuckDuckGo, Wikipedia, and Google Scholar. Runs in Docker on port 8888.

```bash
# Start SearXNG
docker compose up -d

# Verify it's running
curl http://localhost:8888/healthz
```

If SearXNG is unavailable, the system automatically falls back to **DuckDuckGo** (no API key required, lower quality results).

### Citation Policy

- **Primary sources** (government, news, financial reports, company filings) are cited in the bibliography
- **Competitor research firms** (Grand View Research, MarketsandMarkets, etc.) — data is used for research context but **never cited**
- No inline citations in report body — all sources listed in the bibliography at the end

---

## API Endpoints

The FastAPI backend (`backend/api.py`) exposes:

### Report Generator

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Check OpenAI + SearXNG status |
| `POST` | `/api/extract/files` | Upload PPTX + XLSX, extract data |
| `POST` | `/api/extract/json` | Upload pre-extracted JSON |
| `POST` | `/api/extract/json-path` | Load JSON from local file path |
| `POST` | `/api/extract/paths` | Extract from local file paths |
| `POST` | `/api/generate` | Start report generation (returns job_id) |
| `GET` | `/api/generate/{id}/progress` | SSE stream of generation progress |
| `GET` | `/api/generate/{id}/download` | Download completed `.docx` report |

### Research Agent

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/research` | Start multi-layer research (returns job_id) |
| `GET` | `/api/research/{id}/progress` | SSE stream of layer progress |
| `GET` | `/api/research/{id}/result` | Get final comparison report (JSON) |

### SSE Progress Events

**Report Generation** (`/api/generate/{id}/progress`):

| Event | Meaning |
|-------|---------|
| `status` | Phase change (e.g., "Mapping TOC sections...") |
| `info` | Informational message (e.g., "Mapped 12 sections") |
| `progress` | Granular step (e.g., "Building section 3/12") |
| `warning` | Non-fatal error |
| `done` | Generation complete (includes success/failure + file size) |

**Research Agent** (`/api/research/{id}/progress`):

| Event | Meaning |
|-------|---------|
| `layer_start` | Layer begins processing (includes layer number) |
| `layer_done` | Layer completed (includes layer number) |
| `done` | All layers complete (includes success/failure) |

---

## Usage Examples

### Research Agent via web UI

```bash
docker compose up -d                                    # Start SearXNG
python -m uvicorn backend.api:app --reload --port 8000  # Start backend
cd frontend && npm run dev                              # Start frontend
# Open http://localhost:3000 → Research Agent → Enter topic → Start
```

### Full report with web UI (~15-30 min)

```bash
# Open http://localhost:3000 → Report Generator → Upload → Extract → Generate → Download
```

### Quick preview without LLM (~2 min)

```bash
python extract_inputs.py --pptx input.pptx --xlsx input.xlsx -o data.json
python -m report.generate data.json --no-content -o preview.docx
```

### Research Agent via CLI

```bash
python main.py "Global EV Battery Market" --max-layer 3 --model-tier standard
```

---

## Requirements

- **Python 3.12+** — Backend, LLM pipeline, document generation
- **Node.js 18+** — Next.js frontend
- **Docker Desktop** — SearXNG search engine (optional, falls back to DuckDuckGo)
- **OpenAI API key** — Required for content generation

### Python Dependencies

`openai`, `langchain`, `langgraph`, `fastapi`, `uvicorn`, `python-docx`, `python-pptx`, `openpyxl`, `matplotlib`, `beautifulsoup4`, `httpx`, `aiohttp`, `pydantic`, `rich`

### Frontend Dependencies

`next`, `react`, `typescript`, `tailwindcss`, `shadcn/ui`, `zustand`, `framer-motion`, `lucide-react`, `react-dropzone`, `canvas-confetti`

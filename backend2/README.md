# Multi-Agent Senior Analyst Research System

A sophisticated multi-agent system that generates analyst-grade research briefs in under 3 minutes for under $3-5 in LLM + API costs.

## Architecture

The system uses **LangGraph** as the primary orchestrator with **CrewAI** sub-agent crews inside each node, running on **Anthropic Claude** models with **Tavily** for search.

### 8-Agent Pipeline

1. **A1 - Query Refiner**: Sharpens raw query, generates variants, user selection
2. **A2 - Question Generator**: Breaks query into 8-15 atomic sub-questions  
3. **A3 - Topic Researcher**: Deep research on child topic (parallel branch)
4. **A4 - Market-Context Researcher**: Parent market, value chain, impact analysis (parallel)
5. **A5 - News & Events**: Recent events affecting markets (90-day window, parallel)
6. **A6 - Consolidator**: Bottom-up synthesis of claims -> themes -> narrative
7. **A7 - Validator**: Cross-checks numeric claims, resolves conflicts by authority
8. **A8 - Causation/Reasoning**: Explains why values changed with >=2 independent citations

## Quick Start

### Installation

```bash
# Clone and install
cd backend2
pip install -e .

# Copy environment file
cp .env.example .env
# Edit .env with your API keys
```

### Running Agent 1 (Query Refiner)

```bash
# Interactive mode
research debug-a1 "tell me about the EV battery market"

# Non-interactive mode
research debug-a1 "tell me about the EV battery market" --no-interactive --pick 1
```

## Development Status

Currently implemented:
- [x] **Agent 1 - Query Refiner** (complete)
- [ ] Agent 2 - Question Generator
- [ ] Agent 3-5 - Parallel Research Branches  
- [ ] Agent 6 - Consolidator
- [ ] Agent 7 - Validator
- [ ] Agent 8 - Causation/Reasoning

## Agent 1 Features

- **Intent Classification**: Automatically classifies queries into 6 categories
- **Query Refinement**: Generates 4 analyst-grade variants covering different angles
- **Clarity Scoring**: Scores variants on specificity, scope clarity, and answerability
- **Interactive Selection**: Rich CLI interface for user selection
- **Cost Optimization**: Target < $0.01 per run using Haiku model

## Testing

```bash
# Run unit tests
pytest tests/unit/ -v

# Run integration tests (requires API keys)
pytest tests/integration/ -v

# Run cost regression tests
pytest tests/ -m cost
```

## Project Structure

```
research/
core/          # Types, state, config, errors
api/           # LLM clients, cost tracking, caching  
tools/         # @tool functions
graph/         # LangGraph DAG
crews/         # CrewAI crews (a1_query_refiner/ implemented)
pipeline/      # orchestrator + authority
report/        # markdown renderer + json exporter
```

## Cost Engineering

- **Model Routing**: Haiku for simple tasks, Sonnet for synthesis, Opus optional
- **Prompt Caching**: 2K-token shared playbook prefix cached across sub-agents
- **Budget Guards**: Hard $3 default/$5 flag ceiling with short-circuit logic
- **Token Caps**: Per-node limits to prevent cost overruns

## License

MIT

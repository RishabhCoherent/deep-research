"""
Configuration: LLM factory, constants, sub-section definitions.
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


# ─── LLM Factory ──────────────────────────────────────────────────────────────

# Model tier — switchable at runtime via set_model_tier()
_model_tier: str = "standard"

# Available tiers and their model assignments per role
MODEL_TIERS = {
    "standard": {
        "planner":    ("gpt-4o", 0.1),
        "researcher": ("gpt-4o-mini", 0),
        "organizer":  ("gpt-4o-mini", 0),
        "analyst":    ("gpt-4o", 0.2),
        "writer":     ("gpt-4o", 0.3),
        "reviewer":   ("gpt-4o", 0),
    },
    "premium": {
        "planner":    ("gpt-4.1", 0.1),
        "researcher": ("gpt-4.1-mini", 0),
        "organizer":  ("gpt-4.1-mini", 0),
        "analyst":    ("gpt-4.1", 0.2),
        "writer":     ("gpt-4.1", 0.3),
        "reviewer":   ("gpt-4.1", 0),
    },
    "budget": {
        "planner":    ("gpt-4o-mini", 0.1),
        "researcher": ("gpt-4o-mini", 0),
        "organizer":  ("gpt-4o-mini", 0),
        "analyst":    ("gpt-4o-mini", 0.2),
        "writer":     ("gpt-4o-mini", 0.3),
        "reviewer":   ("gpt-4o-mini", 0),
    },
    "reasoning": {
        "planner":    ("gpt-5.2", 0.1),
        "researcher": ("gpt-4.1-mini", 0),
        "organizer":  ("gpt-4.1-mini", 0),
        "analyst":    ("gpt-5.2", 0.2),
        "writer":     ("gpt-5.2", 0.3),
        "reviewer":   ("gpt-5.2", 0),
    },
}


def set_model_tier(tier: str):
    """Switch the active model tier. Options: standard, premium, budget, reasoning."""
    global _model_tier
    if tier not in MODEL_TIERS:
        raise ValueError(f"Unknown tier '{tier}'. Choose from: {list(MODEL_TIERS.keys())}")
    _model_tier = tier


def get_model_tier() -> str:
    """Return the current model tier name."""
    return _model_tier


def get_llm(role: str) -> ChatOpenAI:
    """Return the appropriate LLM for each pipeline role."""
    tier = MODEL_TIERS[_model_tier]
    model_name, temperature = tier[role]
    return ChatOpenAI(model=model_name, temperature=temperature)


# ─── Sub-section Definitions (canonical order) ────────────────────────────────


SUBSECTIONS = [
    {"id": "market_dynamics",       "name": "Market Dynamics"},
    {"id": "pest_analysis",         "name": "PEST Analysis"},
    {"id": "porters_five_forces",   "name": "Porter's Five Forces Analysis"},
    {"id": "tech_advancements",     "name": "Technological Advancements"},
    {"id": "mergers_acquisitions",  "name": "Merger, Acquisition and Collaboration Scenario"},
    {"id": "product_approvals",     "name": "Recent Product Approvals/Launches"},
    {"id": "key_developments",      "name": "Key Developments"},
    {"id": "market_trends",         "name": "Market Trends"},
    {"id": "cost_of_therapy",       "name": "Cost of Therapy/Product"},
    {"id": "patient_journey",       "name": "Patient Journey / Treatment Algorithm"},
    {"id": "treatment_options",     "name": "Treatment Options Analysis"},
]

SUBSECTION_ORDER = [s["id"] for s in SUBSECTIONS]


# ─── Research Constants ───────────────────────────────────────────────────────


RESEARCH_MAX_ITERATIONS = 3
SEARCH_RESULTS_PER_QUERY = 8
MIN_CITATIONS_PER_SUBSECTION = 4
MAX_REWRITE_ATTEMPTS = 1


# ─── API Keys Check ──────────────────────────────────────────────────────────


def has_tavily() -> bool:
    return bool(os.getenv("TAV_API_KEYS") or os.getenv("TAVILY_API_KEY") or os.getenv("TAV_API_KEY"))


def has_searxng() -> bool:
    """Check if SearXNG is reachable."""
    try:
        import httpx
        url = os.getenv("SEARXNG_URL", "http://localhost:8888")
        resp = httpx.get(f"{url}/healthz", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def has_openai() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))

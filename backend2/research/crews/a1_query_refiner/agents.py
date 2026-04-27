"""CrewAI agents for Agent 1 - Query Refiner."""

from crewai import Agent
from research.api.model_router import haiku
from pathlib import Path


_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK = (_PROMPTS / "_playbook.md").read_text()


def _sp(name: str, raw: str) -> str:
    """Substitute {PLAYBOOK} in prompt templates."""
    return raw.replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the three sub-agents for Agent 1."""
    
    intent_classifier = Agent(
        role="Research Intent Classifier",
        goal="Classify the raw analyst query into exactly one IntentKind.",
        backstory="20 years categorising research briefs for tier-1 analyst teams.",
        llm=haiku(),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_sp("1a", (_PROMPTS / "1a_intent_classifier.md").read_text()),
    )
    
    variant_generator = Agent(
        role="Query Variant Generator",
        goal="Write four sharply different refined queries, one per analyst angle.",
        backstory="Senior research lead rewriting fuzzy briefs into scope-tight ones.",
        llm=haiku(),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_sp("1b", (_PROMPTS / "1b_variant_generator.md").read_text()),
    )
    
    clarity_scorer = Agent(
        role="Clarity Scorer",
        goal="Score each variant on specificity, scope, and answerability.",
        backstory="Editorial reviewer for a tier-1 research shop.",
        llm=haiku(),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_sp("1c", (_PROMPTS / "1c_clarity_scorer.md").read_text()),
    )
    
    return intent_classifier, variant_generator, clarity_scorer

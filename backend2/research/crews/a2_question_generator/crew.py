"""CrewAI crew orchestration for Agent 2 - Question Generator."""

from pydantic import ValidationError
from crewai import Crew, Process
from research.core.types import IntentKind, SubQuestion, QuestionCategory
from research.core.errors import CrewFailure
from .agents import build_agents
from .tasks import build_tasks
from .schemas import A2Output, PrioritizedQuestions
from .validators import assert_checklist_coverage, missing_categories
from .dedupe import deduplicate


_FALLBACK_TEMPLATES: dict[QuestionCategory, str] = {
    QuestionCategory.SIZE:         "What is the current global market size and projected growth trajectory for {query}?",
    QuestionCategory.SEGMENTATION: "How is the {query} market segmented by product type, application, or end-user?",
    QuestionCategory.DRIVERS:     "What are the top 3 demand drivers accelerating growth in {query}?",
    QuestionCategory.CONSTRAINTS:  "What are the key risks, supply constraints, or regulatory barriers facing {query}?",
    QuestionCategory.COMPETITIVE:  "Who are the leading players and what is their competitive positioning in {query}?",
    QuestionCategory.GEOGRAPHY:   "How does the {query} market vary across major geographic regions?",
    QuestionCategory.OUTLOOK:      "What is the 3-5 year demand outlook and scenario forecast for {query}?",
    QuestionCategory.REGULATORY: "What are the primary regulations and policy developments impacting {query}?",
    QuestionCategory.VALUE_CHAIN: "What are the critical supply chain and value chain dynamics for {query}?",
    QuestionCategory.MACRO:        "What recent macro-economic or industry events are affecting {query}?",
    QuestionCategory.SUBSTITUTION: "What substitute technologies or alternatives threaten {query}?",
    QuestionCategory.TECHNOLOGY:   "What is the current technology readiness level and innovation pipeline for {query}?",
}


_WH_PREFIXES = (
    "what will be the ", "what is the ", "what are the ",
    "how will ", "how does ", "how is ", "how much ",
    "which ", "when ", "why ",
)


def _as_topic_phrase(query: str) -> str:
    """Reduce a refined analyst question back to the bare topic phrase so it can be
    embedded in fallback templates without causing double-question-mark grammar bugs.

    e.g. "What will be the projected size and segmentation of the EV charging infrastructure
          market in Europe by 2025?"
      -> "the EV charging infrastructure market in Europe by 2025"
    """
    q = (query or "").strip().rstrip("?").rstrip(".").strip()
    lower = q.lower()
    for prefix in _WH_PREFIXES:
        if lower.startswith(prefix):
            q = q[len(prefix):]
            break
    # Strip leading "projected X of / size of / growth of / etc." filler so the
    # phrase becomes the subject noun phrase itself.
    for filler in (
        "projected size and segmentation of ",
        "projected size of ",
        "projected growth of ",
        "size and segmentation of ",
        "size of ",
        "growth of ",
        "outlook for ",
    ):
        if q.lower().startswith(filler):
            q = q[len(filler):]
            break
    return q.strip()


def _fallback_questions(chosen_query: str, original_query: str,
                        missing: list[QuestionCategory]) -> list[SubQuestion]:
    """Generate generic fallback SubQuestions for missing coverage categories.

    Uses the raw topic phrase (derived from original_query) so templates like
    "...affecting {query}?" yield a single trailing '?' and read naturally.
    """
    topic_phrase = _as_topic_phrase(original_query) or _as_topic_phrase(chosen_query) or original_query
    fallbacks: list[SubQuestion] = []
    for cat in missing:
        template = _FALLBACK_TEMPLATES.get(cat, "What is the current status and outlook for {query}?")
        text = template.format(query=topic_phrase)
        fallbacks.append(SubQuestion(
            text=text,
            category=cat,
            source="fallback",
            info_value=7.0,
            answerability=7.0,
            composite=7.0,
            reason=f"Programmatically injected to ensure checklist coverage for {cat.value}.",
        ))
    return fallbacks

_STRICT_ATOMIC_SUFFIX = (
    " [Output rules: each sub-question must be one sentence with exactly one '?'; "
    "never join two questions with 'and what', 'and how', 'and why', or similar.]"
)


def build_a2_crew():
    """Build the CrewAI crew for Agent 2."""
    dec, gap, pri = build_agents()
    t_decompose, t_gap, t_prioritize = build_tasks(dec, gap, pri)

    return Crew(
        agents=[dec, gap, pri],
        tasks=[t_decompose, t_gap, t_prioritize],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


async def run_a2(
    *,
    chosen_query: str,
    intent: IntentKind,
    original_query: str,
    topic_profile=None,   # research.core.topic_profile.TopicProfile | None
) -> A2Output:
    """Run the Agent 2 crew. Fully autonomous — no user interaction.

    `topic_profile` (optional) gates the strict market-research category
    checklist: when the profile says the topic isn't market research
    (clinical / policy / social-science / engineering), the SIZE/
    SEGMENTATION/GEOGRAPHY/OUTLOOK fallback injection is skipped and the
    LLM-generated questions are trusted as-is.

    Returns A2Output containing 8-15 ranked sub-questions ready for Agents 3/4/5.
    """
    inputs = {
        "chosen_query":   chosen_query,
        "intent":         intent.value,
        "original_query": original_query,
    }
    try:
        result = await build_a2_crew().kickoff_async(inputs=inputs)
    except ValidationError:
        result = await build_a2_crew().kickoff_async(
            inputs={
                **inputs,
                "chosen_query": chosen_query + _STRICT_ATOMIC_SUFFIX,
            }
        )

    prioritized: PrioritizedQuestions = result.tasks_output[2].pydantic

    if prioritized is None:
        raise CrewFailure("Agent 2 prioritizer returned no parseable output.")

    # Node-level coverage check: inject deterministic fallbacks for missing
    # categories — but ONLY for market-research topics (per topic_profile).
    # Non-market topics get an empty `missing` list so no market-shaped
    # fallback questions get appended to a clinical / policy / social-science
    # research run.
    missing = missing_categories(intent, prioritized.questions, topic_profile=topic_profile)
    if missing:
        fallback_qs = _fallback_questions(chosen_query, original_query, missing)
        combined = list(prioritized.questions) + fallback_qs
        combined.sort(key=lambda q: q.composite, reverse=True)
        if len(combined) > 15:
            combined = combined[:15]
        return A2Output(questions=combined)

    return A2Output(questions=prioritized.questions)

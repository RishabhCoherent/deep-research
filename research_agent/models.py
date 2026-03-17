"""
All data classes for the research agent pipeline.

Section 1: Pipeline types — Source, ResearchResult, LayerEvaluation, ComparisonReport
Section 2: Knowledge types — ResearchQuestion, ResearchPlan, Fact, KnowledgeBase
Section 3: Agent types — EvalResult, AgentIteration, AgentContext
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Section 1: Pipeline types ────────────────────────────────────────────────


@dataclass
class Source:
    """A research source with metadata."""
    url: str
    title: str
    snippet: str
    scraped_content: str = ""
    publisher: str = ""
    date: str = ""
    credibility: str = "unknown"  # high, medium, low, unknown
    tier: int = 3  # 1=gold-standard, 2=reliable, 3=unknown/unverified


@dataclass
class ResearchResult:
    """Output of a single layer's research on a topic."""
    layer: int
    topic: str
    content: str
    sources: list[Source] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    word_count: int = 0

    def __post_init__(self):
        self.word_count = len(self.content.split())


@dataclass
class LayerEvaluation:
    """Quality evaluation metrics for a single layer's output."""
    layer: int
    factual_density: float = 0.0      # claims per 100 words
    source_diversity: int = 0          # unique source count
    specificity_score: float = 0.0     # % of claims with numbers/data
    framework_usage: list[str] = field(default_factory=list)
    insight_depth: str = ""            # shallow / moderate / deep / expert
    contrarian_views: int = 0          # count of assumption challenges
    word_count: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class LayerComparison:
    """Structured comparison between two adjacent layers."""
    from_layer: int                    # e.g., 0
    to_layer: int                      # e.g., 1
    improvements: list[str] = field(default_factory=list)  # 4-5 specific points
    score_delta: float = 0.0           # overall score improvement
    key_evidence: str = ""             # most striking example from content
    overall_verdict: str = ""          # one-sentence quality jump summary


@dataclass
class ComparisonReport:
    """Side-by-side comparison across all layers."""
    topic: str
    results: list[ResearchResult] = field(default_factory=list)
    evaluations: list[LayerEvaluation] = field(default_factory=list)
    summary: str = ""
    layer_comparisons: list[LayerComparison] = field(default_factory=list)


# ── Section 2: Knowledge types ───────────────────────────────────────────────


@dataclass
class ResearchQuestion:
    """A specific data need for the report."""
    id: str                          # e.g. "q1_market_size"
    section: str                     # which report section this feeds
    question: str                    # "What is the global EV battery market size in 2025?"
    data_type: str                   # "market_size", "growth_rate", "player_list", etc.
    priority: int = 1                # 1=critical, 2=important, 3=nice-to-have
    search_queries: list[str] = field(default_factory=list)
    status: str = "pending"          # pending → researched → answered → gap


@dataclass
class ResearchPlan:
    """Structured decomposition of a research topic."""
    topic: str
    report_type: str                 # "Porter's Five Forces", "PEST", "Market Overview", etc.
    sections: list[str]              # ordered section headings
    questions: list[ResearchQuestion] = field(default_factory=list)

    @property
    def critical_questions(self) -> list[ResearchQuestion]:
        return [q for q in self.questions if q.priority == 1]

    @property
    def pending_questions(self) -> list[ResearchQuestion]:
        return [q for q in self.questions if q.status in ("pending", "gap")]

    @property
    def answered_questions(self) -> list[ResearchQuestion]:
        return [q for q in self.questions if q.status == "answered"]


@dataclass
class Fact:
    """A single piece of verified information extracted from a source."""
    id: str
    question_id: str                 # links back to ResearchQuestion
    section: str                     # which report section this belongs to
    claim: str                       # "The global EV battery market was valued at $92.5B in 2025"
    value: str = ""                  # extracted key value: "$92.5B", "20%", "Apple"
    data_type: str = ""              # "market_size", "growth_rate", "market_share", etc.
    source_url: str = ""
    source_title: str = ""
    source_tier: int = 3             # 1=gold, 2=reliable, 3=unknown
    confidence: str = "medium"       # "high", "medium", "low"
    raw_snippet: str = ""            # original text from source


@dataclass
class KnowledgeBase:
    """Accumulated research knowledge — the central artifact."""
    facts: list[Fact] = field(default_factory=list)
    urls_seen: set[str] = field(default_factory=set)

    # ── Query methods ─────────────────────────────────────────────

    def facts_for_question(self, question_id: str) -> list[Fact]:
        return [f for f in self.facts if f.question_id == question_id]

    def facts_for_section(self, section: str) -> list[Fact]:
        section_lower = section.lower()
        return [f for f in self.facts if f.section.lower() == section_lower]

    def high_confidence_facts(self) -> list[Fact]:
        return [f for f in self.facts if f.confidence == "high"]

    @property
    def coverage(self) -> dict[str, int]:
        """question_id → number of facts supporting it."""
        counts: dict[str, int] = {}
        for f in self.facts:
            counts[f.question_id] = counts.get(f.question_id, 0) + 1
        return counts

    def coverage_score(self, plan: ResearchPlan) -> float:
        """Fraction of questions with at least 1 fact (0.0 - 1.0)."""
        if not plan.questions:
            return 0.0
        covered = sum(1 for q in plan.questions if self.coverage.get(q.id, 0) > 0)
        return covered / len(plan.questions)

    def add_fact(self, fact: Fact):
        self.facts.append(fact)

    # ── Serialisation for LLM context ─────────────────────────────

    def format_for_section(self, section: str, max_facts: int = 20) -> str:
        """Format facts for a specific section as LLM-readable context."""
        section_facts = self.facts_for_section(section)[:max_facts]
        if not section_facts:
            return f"No data collected for section: {section}"
        lines = []
        for f in section_facts:
            tier_label = {1: "T1", 2: "T2", 3: "T3"}.get(f.source_tier, "T?")
            lines.append(
                f"- [{tier_label}] {f.claim}"
                f"{f' (Source: {f.source_title})' if f.source_title else ''}"
            )
        return "\n".join(lines)

    def format_all(self, plan: ResearchPlan) -> str:
        """Format entire knowledge base grouped by section."""
        parts = []
        for section in plan.sections:
            facts_text = self.format_for_section(section)
            parts.append(f"## {section}\n{facts_text}")
        return "\n\n".join(parts)


# ── Section 3: Agent types ────────────────────────────────────────────────────


@dataclass
class EvalResult:
    """Self-evaluation output from the reviewer."""
    overall_score: float  # 0.0 - 10.0
    dimension_scores: dict = field(default_factory=dict)
    weaknesses: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)

    @property
    def pass_threshold(self) -> bool:
        return self._threshold_met

    def check_threshold(self, threshold: float) -> bool:
        self._threshold_met = self.overall_score >= threshold
        return self._threshold_met


@dataclass
class AgentIteration:
    """Record of one iteration for metadata/debugging."""
    iteration: int
    eval_score: float
    weaknesses: list[str]
    queries_run: list[str]
    new_sources_count: int
    stop_reason: str = ""  # "threshold", "plateau", or "" (still running)


@dataclass
class AgentContext:
    """Shared state passed to tools via closures."""
    sources: list[Source] = field(default_factory=list)
    urls_seen: set[str] = field(default_factory=set)
    tool_calls_log: list[dict] = field(default_factory=list)
    tool_call_count: int = 0
    max_tool_calls: int = 20
    prior_content: str = ""
    existing_sources: list[Source] = field(default_factory=list)

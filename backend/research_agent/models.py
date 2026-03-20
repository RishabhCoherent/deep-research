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
class ClaimPair:
    """A matched claim from two layers showing quality transformation."""
    category: str                      # e.g., "Market Size", "Competitive Landscape"
    baseline: str                      # exact quote from lower layer
    improved: str                      # exact quote from higher layer
    tags: list[str] = field(default_factory=list)  # e.g., ["+Data Point", "+Named Source"]
    source: str = ""                   # source attribution in improved claim


@dataclass
class TransformationStep:
    """One specific improvement made to a claim at a given layer."""
    action: str                        # "search" | "scrape" | "verify" | "cross_reference"
    query: str = ""                    # The actual search query that found this data
    source_title: str = ""             # Source that provided the data point
    source_url: str = ""
    data_point_added: str = ""         # The SPECIFIC number/fact/insight added (e.g. "$92.5B")
    why_it_matters: str = ""           # WHY this data point transforms the claim


@dataclass
class ClaimLayerSnapshot:
    """The exact state of a claim at one layer."""
    layer: int
    claim_text: str                    # Exact quote from this layer's report
    data_points: list[str] = field(default_factory=list)   # e.g. ["$92.5B", "15.2%"]
    sources_cited: list[str] = field(default_factory=list)  # Sources backing this version
    quality_tags: list[str] = field(default_factory=list)   # e.g. ["+Data Point", "+Named Source"]
    transformation_steps: list[TransformationStep] = field(default_factory=list)


@dataclass
class ClaimJourney:
    """Tracks ONE claim across ALL 3 layers — the full transformation story."""
    category: str                      # e.g. "Market Size", "Growth Drivers"
    topic_sentence: str                # 1-line summary of what this claim is about
    snapshots: list[ClaimLayerSnapshot] = field(default_factory=list)  # L0, L1, L2 versions
    overall_narrative: str = ""        # 2-3 sentence story of the full transformation
    selection_reason: str = ""         # Why THIS claim was chosen as the showcase


@dataclass
class LayerComparison:
    """Structured comparison between two adjacent layers."""
    from_layer: int                    # e.g., 0
    to_layer: int                      # e.g., 1
    improvements: list[str] = field(default_factory=list)  # 4-5 specific points
    score_delta: float = 0.0           # overall score improvement
    key_evidence: str = ""             # most striking example from content
    overall_verdict: str = ""          # one-sentence quality jump summary
    claim_pairs: list[ClaimPair] = field(default_factory=list)  # before/after evidence


@dataclass
class ComparisonReport:
    """Side-by-side comparison across all layers."""
    topic: str
    results: list[ResearchResult] = field(default_factory=list)
    evaluations: list[LayerEvaluation] = field(default_factory=list)
    summary: str = ""
    layer_comparisons: list[LayerComparison] = field(default_factory=list)
    claim_journey: Optional[ClaimJourney] = None
    # LLM-generated report-level metrics (0-100)
    hallucination_reduction: Optional[float] = None
    outcome_efficiency: Optional[float] = None
    relevancy: Optional[float] = None


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
    verified: bool = False           # True if fact was confirmed via cross-reference


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
            verified_tag = " ✓" if f.verified else ""
            line = f"- [{tier_label}]{verified_tag} {f.claim}"
            if f.source_url:
                line += f" (Source: {f.source_title}, {f.source_url})"
            elif f.source_title:
                line += f" (Source: {f.source_title})"
            if f.raw_snippet and f.raw_snippet != f.claim and len(f.raw_snippet) > 20:
                line += f' | Evidence: "{f.raw_snippet[:200]}"'
            lines.append(line)
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


# ── Section 4: Expert Pipeline types ─────────────────────────────────────────


@dataclass
class Claim:
    """A single factual claim extracted from a report, graded for evidence quality."""
    id: str                          # e.g. "s1_c01" (section 1, claim 1)
    section: str                     # Section heading
    text: str                        # The claim text from the report
    evidence_quality: str            # "strong" | "weak" | "unsupported" | "stale"
    data_type: str                   # "market_size" | "competitive" | "regulatory" | "trend" | "general"
    needs_research: bool             # True unless already "strong"
    reasoning: str = ""              # Why this claim needs research


@dataclass
class SectionAnnotation:
    """Annotated section from claim extraction phase."""
    section: str
    thesis: str                      # Central argument of this section
    claims: list[Claim] = field(default_factory=list)
    overall_quality: str = "thin"    # "thin" | "adequate" | "strong"
    missing_angles: list[str] = field(default_factory=list)


@dataclass
class ClaimMap:
    """Structured claim map of an entire report, produced by Phase 1 (Dissect)."""
    sections: list[SectionAnnotation] = field(default_factory=list)

    @property
    def total_claims(self) -> int:
        return sum(len(s.claims) for s in self.sections)

    @property
    def claims_needing_research(self) -> int:
        return sum(1 for c in self.all_claims() if c.needs_research)

    def all_claims(self) -> list[Claim]:
        return [c for s in self.sections for c in s.claims]

    def weak_claims(self) -> list[Claim]:
        return [c for c in self.all_claims() if c.evidence_quality in ("weak", "unsupported", "stale")]

    def claims_for_section(self, section: str) -> list[Claim]:
        section_lower = section.lower()
        for s in self.sections:
            if s.section.lower() == section_lower:
                return s.claims
        return []


@dataclass
class ResearchTask:
    """A targeted research task for a specific claim."""
    claim_id: str                    # Links back to Claim.id
    section: str
    rationale: str                   # WHY we're searching for this
    queries: list[str] = field(default_factory=list)   # 1-2 targeted search queries
    expected_evidence: str = ""      # "statistic" | "company_example" | "regulatory_detail" | "trend_data"
    priority: int = 2                # 1=critical, 2=important, 3=nice-to-have
    target_sources: list[str] = field(default_factory=list)  # e.g. ["SEC.gov", "Reuters"]


@dataclass
class ExpertResearchPlan:
    """Research plan mapping claims to targeted queries, produced by Phase 2 (Plan)."""
    tasks: list[ResearchTask] = field(default_factory=list)

    @property
    def total_queries(self) -> int:
        return sum(len(t.queries) for t in self.tasks)

    def tasks_for_section(self, section: str) -> list[ResearchTask]:
        section_lower = section.lower()
        return [t for t in self.tasks if t.section.lower() == section_lower]

    def priority_tasks(self, max_priority: int = 2) -> list[ResearchTask]:
        return [t for t in self.tasks if t.priority <= max_priority]

    def sections_covered(self) -> list[str]:
        seen = []
        for t in self.tasks:
            if t.section not in seen:
                seen.append(t.section)
        return seen


@dataclass
class Evidence:
    """A piece of evidence found during investigation, mapped to a specific claim."""
    claim_id: str                    # Which claim this supports
    fact: str                        # The factual finding
    source_url: str = ""
    source_title: str = ""
    source_tier: int = 3             # 1/2/3
    raw_snippet: str = ""            # Exact text from source
    evidence_type: str = "confirms"  # "confirms" | "contradicts" | "extends" | "quantifies"
    confidence: str = "medium"       # "high" | "medium" | "low"


@dataclass
class EvidenceLedger:
    """Evidence ledger tracking all findings mapped to claims, produced by Phase 3."""
    entries: list[Evidence] = field(default_factory=list)

    def add(self, evidence: Evidence):
        self.entries.append(evidence)

    def coverage_score(self, claim_map: ClaimMap) -> float:
        """Fraction of researchable claims with at least 1 evidence entry."""
        researchable = [c for c in claim_map.all_claims() if c.needs_research]
        if not researchable:
            return 1.0
        covered_ids = {e.claim_id for e in self.entries}
        covered = sum(1 for c in researchable if c.id in covered_ids)
        return covered / len(researchable)

    def uncovered_claims(self, claim_map: ClaimMap) -> list[Claim]:
        """Claims that still have no evidence after research."""
        covered_ids = {e.claim_id for e in self.entries}
        return [c for c in claim_map.all_claims() if c.needs_research and c.id not in covered_ids]

    def evidence_for_claim(self, claim_id: str) -> list[Evidence]:
        return [e for e in self.entries if e.claim_id == claim_id]

    def evidence_for_section(self, section: str) -> list[Evidence]:
        section_lower = section.lower()
        return [e for e in self.entries if e.claim_id.startswith("s") and
                any(e.claim_id == c.id for c in self._section_claims(section_lower))]

    def _section_claims(self, section_lower: str) -> list:
        return []  # populated via claim_map at runtime

    def format_for_section(self, section: str, claim_map: ClaimMap) -> str:
        """Format evidence for a section as LLM-readable context.

        T3 (unknown/unverified) sources are relabelled so the compose LLM
        never sees "T3".  Instead they appear as:
          - [UNVERIFIED] if no recognisable source title
          - Promoted to [T2] if the source title looks like a real publication
        This prevents the final report from showing "[T3]" citations.
        """
        claims = claim_map.claims_for_section(section)
        if not claims:
            return f"No claims extracted for section: {section}"
        lines = []
        for c in claims:
            evidence = self.evidence_for_claim(c.id)
            if evidence:
                for e in evidence:
                    tier_label = {1: "T1", 2: "T2"}.get(e.source_tier, "")
                    if not tier_label:
                        # T3/unknown — promote if it has a recognisable title
                        if e.source_title and len(e.source_title) > 3:
                            tier_label = "T2"
                        else:
                            tier_label = "UNVERIFIED"
                    line = f"- [{tier_label}] [{e.evidence_type}] {e.fact}"
                    if e.source_title:
                        line += f" (Source: {e.source_title})"
                    lines.append(line)
            else:
                lines.append(f"- [NO EVIDENCE] {c.text}")
        return "\n".join(lines)

    def format_all(self, claim_map: ClaimMap) -> str:
        """Format entire evidence ledger grouped by section."""
        parts = []
        for sa in claim_map.sections:
            evidence_text = self.format_for_section(sa.section, claim_map)
            parts.append(f"## {sa.section}\n{evidence_text}")
        return "\n\n".join(parts)


@dataclass
class CrossLink:
    """A connection between claims in different sections."""
    from_section: str
    to_section: str
    from_claim_id: str
    to_claim_id: str
    relationship: str                # "causes" | "explains" | "contradicts" | "reinforces"
    narrative: str = ""              # Human-readable explanation


@dataclass
class SynthesisResult:
    """Output of Phase 4 (Synthesize): cross-references, insights, and gaps."""
    cross_links: list[CrossLink] = field(default_factory=list)
    resolved_contradictions: list[dict] = field(default_factory=list)
    gap_report: list[str] = field(default_factory=list)          # Claim IDs still unsupported
    insights: list[str] = field(default_factory=list)            # 5-7 deep analytical insights
    contrarian_risks: list[str] = field(default_factory=list)    # Ways consensus could be wrong

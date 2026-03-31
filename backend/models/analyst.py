"""
Data structures for the Analyst Agent.

The analyst thinks in sub-questions, evidence, contradictions, and judgments —
not flat claim lists. These structures mirror how a real consultant organizes
their research board.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


# ── Sub-Question: A specific thing the analyst needs to answer ────────────────

@dataclass
class SubQuestion:
    """A typed research question with its own strategy."""
    id: str                                     # "sq_01"
    question: str                               # "What is the current market size?"
    answer_type: str = "general"                # numeric | comparison | causal | trend | opinion | list
    research_strategy: str = "data_hunt"        # data_hunt | triangulate | expert_scan | regulatory_lookup | company_deep_dive
    priority: int = 2                           # 1=blocking, 2=important, 3=enrichment
    depends_on: list[str] = field(default_factory=list)  # IDs of prerequisite sub-questions
    status: str = "pending"                     # pending | researching | answered | gap | conflicted
    search_queries: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    answer: str = ""                            # The analyst's answer
    confidence: float = 0.0                     # 0.0 - 1.0
    reasoning: str = ""                         # WHY the analyst believes this answer
    hypothesis: str = ""                        # What the analyst expected before researching

    @property
    def is_answered(self) -> bool:
        return self.status == "answered"

    @property
    def is_resolved(self) -> bool:
        """True if this question is done (answered OR acknowledged gap)."""
        return self.status in ("answered", "gap")

    @property
    def needs_research(self) -> bool:
        return self.status in ("pending", "researching", "conflicted")


# ── Analysis Framework: The structured problem decomposition ──────────────────

@dataclass
class AnalysisFramework:
    """The analyst's structured decomposition of the research problem."""
    core_question: str = ""                      # What the user is really asking
    assumptions: list[str] = field(default_factory=list)   # What must be true
    sub_questions: list[SubQuestion] = field(default_factory=list)
    scope_in: list[str] = field(default_factory=list)      # Explicitly in scope
    scope_out: list[str] = field(default_factory=list)     # Explicitly out of scope
    report_sections: list[str] = field(default_factory=list)  # Final section headings

    # Analytical approach — designed during decompose, guides research and compose.
    # Free-form dict: the LLM decides what keys to use based on the topic.
    # May contain dimensions, proposed_tables, segmentation_hypothesis, evaluation_criteria, etc.
    analytical_approach: dict = field(default_factory=dict)
    contrarian_hypotheses: list[str] = field(default_factory=list)  # Bold claims to test

    def pending_questions(self, priority: Optional[int] = None) -> list[SubQuestion]:
        """Sub-questions that still need research, optionally filtered by priority."""
        qs = [sq for sq in self.sub_questions if sq.needs_research]
        if priority is not None:
            qs = [sq for sq in qs if sq.priority == priority]
        return sorted(qs, key=lambda sq: sq.priority)

    def answered_questions(self) -> list[SubQuestion]:
        return [sq for sq in self.sub_questions if sq.is_answered]

    @property
    def coverage(self) -> float:
        """Fraction of sub-questions that have been answered."""
        if not self.sub_questions:
            return 0.0
        return len(self.answered_questions()) / len(self.sub_questions)


# ── Evidence: A single piece of data found during research ────────────────────

@dataclass
class AnalystEvidence:
    """A piece of evidence the analyst found and evaluated."""
    id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    sub_question_id: str = ""                   # Which sub-question this supports
    fact: str = ""                              # The actual data/claim found
    source_url: str = ""
    source_title: str = ""
    source_tier: int = 3                        # 1=gold, 2=reliable, 3=unknown
    evidence_type: str = "confirmed"            # confirmed | inferred | estimated | disputed
    confidence: float = 0.5                     # 0.0 - 1.0
    date_of_data: str = ""                      # When the data is from (e.g., "2025")
    scrape_method: str = ""                     # Which scraper succeeded


# ── Contradiction: When sources disagree ──────────────────────────────────────

@dataclass
class Contradiction:
    """A conflict between two pieces of evidence."""
    id: str = field(default_factory=lambda: f"ct_{uuid.uuid4().hex[:8]}")
    evidence_a_id: str = ""
    evidence_b_id: str = ""
    sub_question_id: str = ""
    description: str = ""                       # "Source A says $92B, Source B says $85B"
    resolution: str = ""                        # How the analyst resolved it
    resolved: bool = False
    preferred_evidence_id: str = ""
    reasoning: str = ""                         # WHY one was preferred


# ── Causal Link: Connections between findings ─────────────────────────────────

@dataclass
class CausalLink:
    """A causal connection the analyst identified."""
    from_sq_id: str = ""
    to_sq_id: str = ""
    mechanism: str = ""                         # "Rising input costs → margin pressure"
    confidence: float = 0.5
    supporting_evidence_ids: list[str] = field(default_factory=list)


# ── Analyst Judgment: An opinion with reasoning ───────────────────────────────

@dataclass
class AnalystJudgment:
    """An opinion the analyst formed with supporting evidence."""
    claim: str = ""                             # "India will be the #1 investment market"
    conviction: str = "medium"                  # high | medium | low
    supporting_evidence: list[str] = field(default_factory=list)  # evidence IDs
    counter_evidence: list[str] = field(default_factory=list)
    reasoning: str = ""                         # WHY the analyst believes this
    section: str = ""                           # Which report section this belongs to


# ── Hypothesis: What the analyst expected ─────────────────────────────────────

@dataclass
class Hypothesis:
    """A working hypothesis recorded before researching."""
    sub_question_id: str = ""
    hypothesis: str = ""
    reasoning: str = ""                         # Why the analyst expects this
    confirmed: Optional[bool] = None            # None=not yet tested, True/False after research


# ── Research Tree: Recursive deep-research data model ────────────────────────

@dataclass
class ResearchNode:
    """A single node in the recursive research tree.

    Root nodes (depth=0) map 1-to-1 with SubQuestions.
    Child nodes (depth 1-2) are spawned when a parent finds vague, contradictory,
    or incomplete evidence and needs to dig deeper.
    """
    id: str = field(default_factory=lambda: f"rn_{uuid.uuid4().hex[:8]}")
    parent_id: Optional[str] = None           # None for root nodes
    depth: int = 0                            # 0=root, 1=drill-down, 2=deep verification
    query: str = ""                           # The question this node is investigating
    why_created: str = "root"                 # root | vague_finding | contradiction | thin_data | surprising_data | missing_entity
    trigger_finding: str = ""                 # The specific finding that caused this node to be spawned
    sq_id: Optional[str] = None              # Sub-question this node belongs to

    # Research content
    hypothesis: str = ""
    search_queries: list[str] = field(default_factory=list)
    answer: str = ""
    confidence: float = 0.0

    # Status lifecycle
    status: str = "pending"                   # pending | exploring | complete | dead-end

    # Relationships
    children_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status in ("complete", "dead-end")

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


@dataclass
class ResearchTree:
    """Holds all ResearchNodes and their parent-child relationships."""
    nodes: dict = field(default_factory=dict)           # node_id -> ResearchNode
    sq_to_root: dict = field(default_factory=dict)      # sq_id -> root node_id

    def add_node(self, node: ResearchNode) -> None:
        self.nodes[node.id] = node
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node.id not in parent.children_ids:
                parent.children_ids.append(node.id)

    def get_node(self, node_id: str) -> Optional[ResearchNode]:
        return self.nodes.get(node_id)

    def get_children(self, node_id: str) -> list:
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [self.nodes[cid] for cid in node.children_ids if cid in self.nodes]

    def get_root_for_sq(self, sq_id: str) -> Optional[ResearchNode]:
        root_id = self.sq_to_root.get(sq_id)
        return self.nodes.get(root_id) if root_id else None

    @property
    def total_nodes(self) -> int:
        return len(self.nodes)

    @property
    def max_depth_reached(self) -> int:
        if not self.nodes:
            return 0
        return max(n.depth for n in self.nodes.values())

    @property
    def active_nodes(self) -> list:
        return [n for n in self.nodes.values() if n.status == "exploring"]

    @property
    def completed_nodes(self) -> list:
        return [n for n in self.nodes.values() if n.is_complete]

    def to_dict(self) -> dict:
        return {
            "total_nodes": self.total_nodes,
            "max_depth": self.max_depth_reached,
            "sq_to_root": self.sq_to_root,
            "nodes": {
                nid: {
                    "id": n.id,
                    "parent_id": n.parent_id,
                    "depth": n.depth,
                    "query": n.query,
                    "why_created": n.why_created,
                    "trigger_finding": n.trigger_finding,
                    "status": n.status,
                    "answer": n.answer[:300] if n.answer else "",
                    "confidence": n.confidence,
                    "children_ids": n.children_ids,
                    "evidence_ids": n.evidence_ids,
                    "sq_id": n.sq_id,
                    "hypothesis": n.hypothesis[:200] if n.hypothesis else "",
                }
                for nid, n in self.nodes.items()
            },
        }


# ── Research Board: The central state artifact ────────────────────────────────

@dataclass
class ResearchBoard:
    """Everything the analyst knows and thinks. This is the brain."""
    framework: AnalysisFramework = field(default_factory=AnalysisFramework)
    evidence: list[AnalystEvidence] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    causal_links: list[CausalLink] = field(default_factory=list)
    judgments: list[AnalystJudgment] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    research_tree: ResearchTree = field(default_factory=ResearchTree)

    # Budget tracking
    tool_calls_used: int = 0
    tool_calls_budget: int = 60
    searches_done: int = 0
    scrapes_done: int = 0
    scrapes_failed: int = 0

    # Quality tracking
    quality_scores: dict = field(default_factory=dict)
    iteration_count: int = 0
    max_iterations: int = 2

    # ── Evidence helpers ──────────────────────────────────────────────────

    def evidence_for(self, sq_id: str) -> list[AnalystEvidence]:
        """All evidence entries for a given sub-question."""
        return [e for e in self.evidence if e.sub_question_id == sq_id]

    def evidence_by_id(self, ev_id: str) -> Optional[AnalystEvidence]:
        for e in self.evidence:
            if e.id == ev_id:
                return e
        return None

    def unresolved_contradictions(self) -> list[Contradiction]:
        return [c for c in self.contradictions if not c.resolved]

    # ── Coverage & quality ────────────────────────────────────────────────

    @property
    def coverage(self) -> float:
        return self.framework.coverage

    @property
    def budget_remaining(self) -> int:
        return max(0, self.tool_calls_budget - self.tool_calls_used)

    @property
    def evidence_strength(self) -> float:
        """Average source tier quality (lower is better: T1=1, T2=2, T3=3)."""
        if not self.evidence:
            return 3.0
        return sum(e.source_tier for e in self.evidence) / len(self.evidence)

    def progress_summary(self) -> str:
        """Human-readable progress for the agent to self-assess."""
        total_sq = len(self.framework.sub_questions)
        answered = len(self.framework.answered_questions())
        pending = len(self.framework.pending_questions())
        contradictions = len(self.unresolved_contradictions())
        evidence_count = len(self.evidence)
        t1_count = sum(1 for e in self.evidence if e.source_tier == 1)
        t2_count = sum(1 for e in self.evidence if e.source_tier == 2)
        judgments = len(self.judgments)

        lines = [
            f"PROGRESS: {answered}/{total_sq} sub-questions answered ({self.coverage:.0%} coverage)",
            f"EVIDENCE: {evidence_count} findings ({t1_count} T1, {t2_count} T2)",
            f"CONTRADICTIONS: {contradictions} unresolved",
            f"JUDGMENTS: {judgments} formed",
            f"BUDGET: {self.budget_remaining}/{self.tool_calls_budget} tool calls remaining",
            f"SCRAPING: {self.scrapes_done} successful, {self.scrapes_failed} failed",
        ]

        if pending:
            lines.append(f"\nPENDING QUESTIONS (highest priority first):")
            for sq in self.framework.pending_questions()[:5]:
                lines.append(f"  [P{sq.priority}] {sq.id}: {sq.question}")

        if contradictions:
            lines.append(f"\nUNRESOLVED CONTRADICTIONS:")
            for c in self.unresolved_contradictions()[:3]:
                lines.append(f"  {c.id}: {c.description}")

        # Analytical approach context (guides what structure to fill)
        if self.framework.analytical_approach:
            lines.append(f"\nANALYTICAL APPROACH:")
            for key, value in self.framework.analytical_approach.items():
                if isinstance(value, list):
                    lines.append(f"  {key}: {', '.join(str(v) for v in value[:6])}")
                else:
                    lines.append(f"  {key}: {str(value)[:200]}")
        if self.framework.contrarian_hypotheses:
            lines.append(f"  Contrarian hypotheses to test: {'; '.join(self.framework.contrarian_hypotheses[:3])}")

        return "\n".join(lines)

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize for metadata storage."""
        return {
            "sub_questions": [
                {"id": sq.id, "question": sq.question, "status": sq.status,
                 "confidence": sq.confidence, "answer": sq.answer[:200]}
                for sq in self.framework.sub_questions
            ],
            "evidence_count": len(self.evidence),
            "evidence": [
                {"id": e.id, "fact": e.fact[:200], "source_url": e.source_url,
                 "source_title": e.source_title, "source_tier": e.source_tier,
                 "sub_question_id": e.sub_question_id}
                for e in self.evidence
            ],
            "contradictions": [
                {"id": c.id, "description": c.description, "resolved": c.resolved,
                 "resolution": c.resolution}
                for c in self.contradictions
            ],
            "judgments": [
                {"claim": j.claim, "conviction": j.conviction, "reasoning": j.reasoning[:200]}
                for j in self.judgments
            ],
            "causal_links": [
                {"from": cl.from_sq_id, "to": cl.to_sq_id, "mechanism": cl.mechanism}
                for cl in self.causal_links
            ],
            "coverage": self.coverage,
            "evidence_strength": self.evidence_strength,
            "tool_calls_used": self.tool_calls_used,
            "searches_done": self.searches_done,
            "scrapes_done": self.scrapes_done,
            "scrapes_failed": self.scrapes_failed,
            "research_tree": self.research_tree.to_dict(),
        }


# ── Research Trace: Full audit trail for demos ───────────────────────────────

@dataclass
class TraceStep:
    """A single recorded step in the analyst's reasoning journey."""
    phase: str          # decompose | think | search | scrape | reflect | analyze | quality | compose
    sq_id: str = ""     # Sub-question ID (if applicable)
    title: str = ""     # Short human-readable label
    content: dict = field(default_factory=dict)   # Phase-specific payload
    timestamp: float = field(default_factory=lambda: __import__('time').time())
    elapsed_s: float = 0.0


@dataclass
class ResearchTrace:
    """Full audit trail of the analyst's reasoning — every hypothesis, search,
    reflection, and judgment. Designed for customer demos and transparency."""
    topic: str = ""
    started_at: float = field(default_factory=lambda: __import__('time').time())
    steps: list[TraceStep] = field(default_factory=list)

    def add(self, phase: str, title: str, content: dict, sq_id: str = "", elapsed_s: float = 0.0):
        self.steps.append(TraceStep(
            phase=phase, sq_id=sq_id, title=title,
            content=content, elapsed_s=elapsed_s,
        ))

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "topic": self.topic,
            "started_at": self.started_at,
            "total_steps": len(self.steps),
            "steps": [
                {
                    "phase": s.phase,
                    "sq_id": s.sq_id,
                    "title": s.title,
                    "content": s.content,
                    "elapsed_s": s.elapsed_s,
                }
                for s in self.steps
            ],
        }

    def to_markdown(self) -> str:
        """Render as a human-readable markdown document for demos."""
        lines = [
            f"# Research Trace: {self.topic}",
            f"*How our AI analyst reasoned through this research*\n",
            "---\n",
        ]

        phase_icons = {
            "decompose": "🧩", "think": "🧠", "search": "🔍",
            "scrape": "📄", "reflect": "🪞", "analyze": "⚖️",
            "quality": "✅", "compose": "✍️",
        }

        phase_labels = {
            "decompose": "Problem Decomposition",
            "think": "Hypothesis Formation",
            "search": "Web Search",
            "scrape": "Source Extraction",
            "reflect": "Evidence Evaluation",
            "analyze": "Cross-Reference Analysis",
            "quality": "Quality Gate",
            "compose": "Report Composition",
        }

        current_sq = ""
        for step in self.steps:
            icon = phase_icons.get(step.phase, "📌")
            label = phase_labels.get(step.phase, step.phase.title())

            # New sub-question separator
            if step.sq_id and step.sq_id != current_sq:
                current_sq = step.sq_id
                lines.append(f"\n---\n")
                q_text = step.content.get("question", step.sq_id)
                priority = step.content.get("priority", "")
                p_label = f" [Priority {priority}]" if priority else ""
                lines.append(f"## 📋 Sub-Question: {q_text}{p_label}\n")

            lines.append(f"### {icon} {label}: {step.title}")
            if step.elapsed_s:
                lines.append(f"*({step.elapsed_s:.1f}s)*\n")
            else:
                lines.append("")

            c = step.content

            if step.phase == "decompose":
                if "core_question" in c:
                    lines.append(f"**Core Question:** {c['core_question']}\n")
                if "assumptions" in c:
                    lines.append("**Assumptions:**")
                    for a in c["assumptions"]:
                        lines.append(f"- {a}")
                    lines.append("")
                if "sub_questions" in c:
                    lines.append("**Research Questions:**")
                    for sq in c["sub_questions"]:
                        p = sq.get("priority", "?")
                        lines.append(f"- **[P{p}]** {sq['question']}")
                        lines.append(f"  - Type: {sq.get('answer_type', '?')} | Strategy: {sq.get('research_strategy', '?')}")
                        queries = sq.get("search_queries", [])
                        if queries:
                            lines.append(f"  - Queries: {', '.join(queries[:3])}")
                    lines.append("")

            elif step.phase == "think":
                if "hypothesis" in c:
                    lines.append(f"> **Hypothesis:** *\"{c['hypothesis']}\"*\n")
                if "would_change_mind" in c:
                    lines.append(f"> **Would change mind if:** *\"{c['would_change_mind']}\"*\n")
                if "search_queries" in c:
                    lines.append("**Planned searches:**")
                    for q in c["search_queries"]:
                        lines.append(f"- `{q}`")
                    lines.append("")

            elif step.phase == "search":
                query = c.get("query", "")
                lines.append(f"**Query:** `{query}`\n")
                results = c.get("results", [])
                if results:
                    lines.append("**Results:**")
                    for r in results:
                        tier = r.get("tier", "?")
                        lines.append(f"- **[T{tier}]** {r.get('title', '?')}")
                        lines.append(f"  - {r.get('url', '')}")
                        snippet = r.get("snippet", "")
                        if snippet:
                            lines.append(f"  - *{snippet[:150]}...*")
                    lines.append("")

            elif step.phase == "scrape":
                lines.append(f"**URL:** {c.get('url', '?')}")
                lines.append(f"**Success:** {c.get('success', '?')} | **Method:** {c.get('method', '?')}")
                chars = c.get("content_length", 0)
                if chars:
                    lines.append(f"**Extracted:** {chars:,} characters")
                    preview = c.get("content_preview", "")
                    if preview:
                        lines.append(f"\n> {preview[:300]}...\n")
                lines.append("")

            elif step.phase == "reflect":
                findings = c.get("findings", [])
                if findings:
                    lines.append("**Findings:**")
                    for f in findings:
                        conf = f.get("confidence", 0)
                        confirms = "✅ Confirms" if f.get("confirms_hypothesis") else "❌ Contradicts"
                        lines.append(f"- {confirms} hypothesis (confidence: {conf:.0%})")
                        lines.append(f"  - **{f.get('data_point', '?')}**")
                        lines.append(f"  - Source: {f.get('source_title', '?')} [T{f.get('source_tier', '?')}]")
                    lines.append("")
                contradictions = c.get("contradictions", [])
                if contradictions:
                    lines.append("**⚠️ Contradictions found:**")
                    for ct in contradictions:
                        lines.append(f"- {ct}")
                    lines.append("")
                if "answer" in c:
                    lines.append(f"**Answer:** {c['answer']}")
                    lines.append(f"**Confidence:** {c.get('confidence', 0):.0%}")
                    revised = c.get("hypothesis_revised", False)
                    if revised:
                        lines.append(f"**⚡ Hypothesis revised:** {c.get('revised_hypothesis', '')}")
                    lines.append("")

            elif step.phase == "analyze":
                if "key_findings" in c:
                    lines.append("**Key Findings:**")
                    for f in c["key_findings"]:
                        lines.append(f"- {f}")
                    lines.append("")
                if "judgments" in c:
                    lines.append("**Analyst Judgments:**")
                    for j in c["judgments"]:
                        lines.append(f"- **[{j.get('conviction', '?').upper()}]** {j.get('claim', '?')}")
                        lines.append(f"  - *{j.get('reasoning', '')[:200]}*")
                    lines.append("")
                if "causal_chains" in c:
                    lines.append("**Causal Chains:**")
                    for ch in c["causal_chains"]:
                        lines.append(f"- {ch}")
                    lines.append("")
                if "narrative_thread" in c:
                    lines.append(f"**Narrative Thread:** {c['narrative_thread']}\n")

            elif step.phase == "quality":
                lines.append(f"**Overall Score:** {c.get('overall', 0):.0%} — {'PASS ✅' if c.get('passes') else 'FAIL ❌'}\n")
                lines.append("| Dimension | Score |")
                lines.append("|-----------|-------|")
                for dim in ["coverage", "evidence_strength", "contradiction_resolution", "judgment_formation", "gap_acknowledgment"]:
                    val = c.get(dim, 0)
                    lines.append(f"| {dim.replace('_', ' ').title()} | {val:.0%} |")
                lines.append("")
                feedback = c.get("feedback", "")
                if feedback:
                    lines.append(f"**Feedback:** {feedback}\n")

            elif step.phase == "compose":
                if "outline" in c:
                    lines.append("**Report Outline:**")
                    for section in c.get("outline", []):
                        lines.append(f"- **{section.get('heading', '?')}**: {section.get('thesis', '')[:100]}")
                    lines.append("")
                if "word_count" in c:
                    lines.append(f"**Final word count:** {c['word_count']:,} words")
                if "expanded" in c:
                    lines.append(f"**Auto-expanded:** {c['expanded']}")
                lines.append("")

        # Footer
        lines.append("\n---\n")
        lines.append(f"*Total steps: {len(self.steps)} | "
                     f"Searches: {sum(1 for s in self.steps if s.phase == 'search')} | "
                     f"Scrapes: {sum(1 for s in self.steps if s.phase == 'scrape')} | "
                     f"Reflections: {sum(1 for s in self.steps if s.phase == 'reflect')}*")

        return "\n".join(lines)


# ── Analysis Result: Output of the analyze phase ─────────────────────────────

@dataclass
class AnalysisResult:
    """What the analyst concluded after cross-referencing all evidence."""
    key_findings: list[str] = field(default_factory=list)     # 5-7 headline findings
    judgments: list[AnalystJudgment] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)    # sub-question IDs with thin evidence
    gap_severity: dict = field(default_factory=dict)          # sq_id -> "critical" | "acceptable"
    overall_confidence: float = 0.0
    narrative_thread: str = ""                                # The overarching story
    causal_chains: list[str] = field(default_factory=list)    # Human-readable causal chains

    # Analytical frameworks — created by the analyze phase.
    # Free-form list: the LLM decides what frameworks to create based on evidence.
    # Each dict: {name, type, description, data}
    analytical_frameworks: list[dict] = field(default_factory=list)
    contrarian_insights: list[str] = field(default_factory=list)


# ── Quality Score: Output of the quality gate ─────────────────────────────────

@dataclass
class QualityScore:
    """Quality assessment of the research."""
    coverage: float = 0.0           # % of sub-questions answered
    evidence_strength: float = 0.0  # weighted by source tier
    contradiction_resolution: float = 0.0  # % resolved
    judgment_formation: float = 0.0  # whether opinions formed on core questions
    gap_acknowledgment: float = 0.0  # whether gaps are explicitly classified
    evidence_depth: float = 0.0     # whether answers have enough evidence for their type
    overall: float = 0.0
    passes: bool = False
    feedback: str = ""              # What needs improvement
    remediation_queries: list[str] = field(default_factory=list)  # Targeted queries for retry

"""
Layer 2 — CMI EXPERT: Section-driven deep research pipeline.

Receives L1's sources (not report) and researches the topic independently:
  Phase 1 (PLAN)         → Generate sections + research queries from topic
  Phase 2 (INVESTIGATE)  → Execute research plan, record findings per section
  Phase 3 (COMPOSE)      → Write final report from all evidence
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict

from config import get_llm, set_model_tier
from models.pipeline import (
    ResearchResult, Source, AgentContext,
    Evidence, EvidenceLedger,
    SynthesisResult,
)
from workflow import build_agent_graph, build_initial_state, make_tools, _scrub_competitor_mentions
from prompts import (
    EXPERT_TOPIC_PLAN_PROMPT, EXPERT_SECTION_INVESTIGATE_PROMPT,
    EXPERT_COMPOSE_PROMPT, get_quality_rules,
)
from utils.cost_tracker import track
from utils import get_content, extract_json, strip_preamble

logger = logging.getLogger(__name__)


# ─── Phase 1: DISSECT ────────────────────────────────────────────────────────


async def _phase_dissect(topic: str, prior_report: str, notify) -> ClaimMap:
    """Extract and grade every claim from the prior report."""
    notify("dissect", "Extracting and grading claims from prior report...")

    set_model_tier("standard")
    llm = get_llm("planner")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": EXPERT_DISSECT_PROMPT.format(prior_report=prior_report)},
    ]

    response = await llm.ainvoke(messages)
    track("L2 dissect", response)

    raw = get_content(response).strip()
    data = extract_json(raw)

    if not data or "sections" not in data:
        logger.warning("[Expert] Dissect failed to parse JSON, building fallback ClaimMap")
        return _fallback_claim_map(prior_report)

    # Parse into ClaimMap
    sections = []
    for i, s in enumerate(data.get("sections", [])):
        claims = []
        for c in s.get("claims", []):
            claims.append(Claim(
                id=str(c.get("id", f"s{i+1}_c{len(claims)+1:02d}")),
                section=str(s.get("section", f"Section {i+1}")),
                text=str(c.get("text", "")),
                evidence_quality=str(c.get("evidence_quality", "weak")),
                data_type=str(c.get("data_type", "general")),
                needs_research=bool(c.get("needs_research", True)),
                reasoning=str(c.get("reasoning", "")),
            ))
        sections.append(SectionAnnotation(
            section=str(s.get("section", f"Section {i+1}")),
            thesis=str(s.get("thesis", "")),
            claims=claims,
            overall_quality=str(s.get("overall_quality", "thin")),
            missing_angles=[str(a) for a in s.get("missing_angles", [])],
        ))

    claim_map = ClaimMap(sections=sections)
    notify("dissect", f"Extracted {claim_map.total_claims} claims, {claim_map.claims_needing_research} need research")
    return claim_map


def _fallback_claim_map(prior_report: str) -> ClaimMap:
    """Build a minimal ClaimMap from section headings when LLM parsing fails."""
    import re
    sections = []
    current_section = None
    current_claims = []
    claim_counter = 0

    for line in prior_report.split("\n"):
        heading = re.match(r'^##\s+(.+)', line)
        if heading:
            if current_section and current_claims:
                sections.append(SectionAnnotation(
                    section=current_section,
                    thesis="",
                    claims=current_claims,
                    overall_quality="thin",
                ))
            current_section = heading.group(1).strip()
            current_claims = []
        elif current_section and line.strip() and len(line.strip()) > 30:
            claim_counter += 1
            si = len(sections) + 1
            current_claims.append(Claim(
                id=f"s{si}_c{len(current_claims)+1:02d}",
                section=current_section,
                text=line.strip()[:200],
                evidence_quality="weak",
                data_type="general",
                needs_research=True,
            ))

    if current_section and current_claims:
        sections.append(SectionAnnotation(
            section=current_section,
            thesis="",
            claims=current_claims,
            overall_quality="thin",
        ))

    return ClaimMap(sections=sections)


# ─── Phase 2: PLAN ───────────────────────────────────────────────────────────


async def _phase_plan(topic: str, claim_map: ClaimMap, notify) -> ExpertResearchPlan:
    """Generate targeted research queries for each weak/unsupported claim."""
    notify("plan", "Planning targeted research queries...")

    weak_claims = claim_map.weak_claims()
    if not weak_claims:
        notify("plan", "All claims are strong — minimal research needed")
        return ExpertResearchPlan(tasks=[])

    # Cap at 25 claims to keep investigation focused
    if len(weak_claims) > 25:
        weak_claims = weak_claims[:25]
        notify("plan", f"Focusing on top 25 of {claim_map.claims_needing_research} weak claims")

    # Format claims for the prompt
    claims_json = json.dumps([
        {
            "id": c.id,
            "section": c.section,
            "text": c.text,
            "evidence_quality": c.evidence_quality,
            "data_type": c.data_type,
            "reasoning": c.reasoning,
        }
        for c in weak_claims
    ], indent=2)

    set_model_tier("standard")
    llm = get_llm("planner")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": EXPERT_PLAN_PROMPT.format(topic=topic, claims_json=claims_json)},
    ]

    response = await llm.ainvoke(messages)
    track("L2 plan", response)

    raw = get_content(response).strip()
    data = extract_json(raw)

    tasks = []
    if data and "tasks" in data:
        for t in data["tasks"]:
            tasks.append(ResearchTask(
                claim_id=str(t.get("claim_id", "")),
                section=str(t.get("section", "")),
                rationale=str(t.get("rationale", "")),
                queries=[str(q) for q in t.get("queries", [])],
                expected_evidence=str(t.get("expected_evidence", "")),
                priority=int(t.get("priority", 2)),
                target_sources=[str(s) for s in t.get("target_sources", [])],
            ))
    else:
        # Fallback: generate basic queries from claim text
        for c in weak_claims:
            tasks.append(ResearchTask(
                claim_id=c.id,
                section=c.section,
                rationale=f"Claim needs substantiation: {c.text[:100]}",
                queries=[f"{topic} {c.text[:50]} 2025 2026"],
                expected_evidence="statistic",
                priority=2,
            ))

    plan = ExpertResearchPlan(tasks=tasks)
    notify("plan", f"Generated {plan.total_queries} search queries for {len(tasks)} claims across {len(plan.sections_covered())} sections")
    return plan


# ─── Phase 3: INVESTIGATE ────────────────────────────────────────────────────


async def _phase_investigate(
    topic: str,
    plan: ExpertResearchPlan,
    claim_map: ClaimMap,
    ctx: AgentContext,
    notify,
    progress_callback=None,
    brief: str = "",
) -> EvidenceLedger:
    """Execute the research plan via LangGraph agent with evidence tracking."""
    notify("investigate", "Starting structured investigation...")

    ledger = EvidenceLedger()

    # Format research plan for the agent prompt
    plan_lines = []
    for t in plan.priority_tasks(max_priority=3):
        queries_str = ", ".join(f'"{q}"' for q in t.queries)
        plan_lines.append(
            f"CLAIM [{t.claim_id}] (Section: {t.section}, Priority: {t.priority})\n"
            f"  Need: {t.rationale}\n"
            f"  Suggested queries: {queries_str}\n"
            f"  Expected evidence: {t.expected_evidence}"
        )
    research_plan_text = "\n\n".join(plan_lines)

    # Build tools with evidence tracking
    set_model_tier("premium")
    llm = get_llm("writer")

    tools = make_tools(ctx, ledger=ledger, claim_map=claim_map)

    system_prompt = EXPERT_INVESTIGATE_PROMPT.format(research_plan=research_plan_text)

    graph = build_agent_graph(
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        max_tool_calls=70,   # Bounded — coverage gates are the real stopping condition
        min_word_count=1,    # Accept any output — this phase gathers evidence, not a report
        max_retries=0,       # Don't retry — just accept and move to next phase
        progress_callback=progress_callback,
        layer=2,
        ctx=ctx,
        ledger=ledger,
        claim_map=claim_map,
    )

    initial_state = build_initial_state(
        topic=topic,
        layer=2,
        system_prompt=system_prompt,
        prior_report=f"Investigate the claims listed in your research plan. Use record_finding after each discovery.\n\nTopic: {topic}",
        brief=brief,
        max_tool_calls=70,
        min_word_count=1,
        max_retries=0,
    )

    await graph.ainvoke(initial_state)

    coverage = ledger.coverage_score(claim_map)
    coverage_before_gap_fill = round(coverage, 2)
    gap_fill_passes_done = 0
    notify("investigate", f"Investigation complete. Coverage: {coverage:.0%} ({len(ledger.entries)} findings)")

    # Gap-fill passes if coverage is below target (up to 2 rounds)
    for gap_round in range(1, 3):
        if coverage >= 0.70:
            break
        notify("investigate", f"Coverage {coverage:.0%} below 70% — running gap-fill pass {gap_round}...")
        await _gap_fill(topic, claim_map, ledger, ctx, notify, progress_callback, brief)
        coverage = ledger.coverage_score(claim_map)
        gap_fill_passes_done = gap_round
        notify("investigate", f"After gap-fill {gap_round}: Coverage {coverage:.0%}")

    return ledger, coverage_before_gap_fill, gap_fill_passes_done


async def _gap_fill(
    topic: str,
    claim_map: ClaimMap,
    ledger: EvidenceLedger,
    ctx: AgentContext,
    notify,
    progress_callback=None,
    brief: str = "",
):
    """Second research pass focused only on uncovered claims with targeted queries."""
    uncovered = ledger.uncovered_claims(claim_map)
    if not uncovered:
        return

    # Cap gap-fill at 15 claims to keep it focused
    uncovered = uncovered[:15]

    # Generate targeted queries for uncovered claims (1 fast LLM call)
    claims_for_plan = json.dumps([
        {"id": c.id, "section": c.section, "text": c.text, "data_type": c.data_type}
        for c in uncovered
    ], indent=2)

    set_model_tier("budget")
    plan_llm = get_llm("planner")

    plan_messages = [
        {"role": "system", "content": "You output only valid JSON."},
        {"role": "user", "content": (
            f"Generate 1 targeted search query per claim to find specific evidence.\n"
            f"Topic: {topic}\n\nCLAIMS:\n{claims_for_plan}\n\n"
            "Return JSON: {\"queries\": [{\"claim_id\": \"s1_c01\", \"query\": \"specific search query 2025\"}]}"
        )},
    ]

    try:
        plan_resp = await plan_llm.ainvoke(plan_messages)
        track("L2 gap-fill plan", plan_resp)
        plan_data = extract_json(get_content(plan_resp).strip())
        query_map = {}
        if plan_data and "queries" in plan_data:
            for q in plan_data["queries"]:
                query_map[q.get("claim_id", "")] = q.get("query", "")
    except Exception:
        query_map = {}

    # Build plan text with targeted queries
    uncovered_lines = []
    for c in uncovered:
        query = query_map.get(c.id, f"{topic} {c.text[:50]} 2025")
        uncovered_lines.append(
            f"CLAIM [{c.id}] (Section: {c.section})\n"
            f"  Text: {c.text}\n"
            f"  Suggested query: \"{query}\""
        )
    gap_plan_text = "\n\n".join(uncovered_lines)

    set_model_tier("premium")
    llm = get_llm("writer")

    tools = make_tools(ctx, ledger=ledger, claim_map=claim_map)
    system_prompt = EXPERT_INVESTIGATE_PROMPT.format(research_plan=gap_plan_text)

    graph = build_agent_graph(
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        max_tool_calls=30,
        min_word_count=1,
        max_retries=0,
        progress_callback=progress_callback,
        layer=2,
        ctx=ctx,
        ledger=ledger,
        claim_map=claim_map,
    )

    initial_state = build_initial_state(
        topic=topic,
        layer=2,
        system_prompt=system_prompt,
        prior_report=f"GAP-FILL: Focus on the {len(uncovered)} uncovered claims listed in your plan.\n\nTopic: {topic}",
        brief=brief,
        max_tool_calls=15,
        min_word_count=1,
        max_retries=0,
    )

    await graph.ainvoke(initial_state)


# ─── Phase 4: SYNTHESIZE ─────────────────────────────────────────────────────


async def _phase_synthesize(
    topic: str,
    claim_map: ClaimMap,
    ledger: EvidenceLedger,
    notify,
) -> SynthesisResult:
    """Cross-reference findings, generate insights, identify gaps."""
    notify("synthesize", "Cross-referencing findings and generating insights...")

    evidence_text = ledger.format_all(claim_map)

    # Build claims summary
    claims_lines = []
    for sa in claim_map.sections:
        claims_lines.append(f"## {sa.section}")
        for c in sa.claims:
            ev_count = len(ledger.evidence_for_claim(c.id))
            status = f"({ev_count} evidence)" if ev_count > 0 else "(NO EVIDENCE)"
            claims_lines.append(f"  [{c.id}] {c.text} {status}")
    claims_summary = "\n".join(claims_lines)

    set_model_tier("reasoning")
    llm = get_llm("analyst")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": EXPERT_SYNTHESIZE_PROMPT.format(
            topic=topic,
            evidence_text=evidence_text,
            claims_summary=claims_summary,
        )},
    ]

    response = await llm.ainvoke(messages)
    track("L2 synthesize", response)

    raw = get_content(response).strip()
    data = extract_json(raw)

    if not data:
        logger.warning("[Expert] Synthesize failed to parse JSON")
        return SynthesisResult()

    # Parse cross-links
    cross_links = []
    for cl in data.get("cross_links", []):
        cross_links.append(CrossLink(
            from_section=str(cl.get("from_section", "")),
            to_section=str(cl.get("to_section", "")),
            from_claim_id=str(cl.get("from_claim_id", "")),
            to_claim_id=str(cl.get("to_claim_id", "")),
            relationship=str(cl.get("relationship", "")),
            narrative=str(cl.get("narrative", "")),
        ))

    result = SynthesisResult(
        cross_links=cross_links,
        resolved_contradictions=data.get("resolved_contradictions", []),
        gap_report=[str(g) for g in data.get("gap_report", [])],
        insights=[str(i) for i in data.get("insights", [])],
        contrarian_risks=[str(r) for r in data.get("contrarian_risks", [])],
    )

    notify("synthesize", f"Found {len(cross_links)} cross-links, {len(result.insights)} insights")
    return result


# ─── Phase 5: COMPOSE ────────────────────────────────────────────────────────


async def _phase_compose(
    topic: str,
    claim_map: ClaimMap,
    ledger: EvidenceLedger,
    synthesis: SynthesisResult,
    brief: str,
    notify,
    prior_report: str = "",
    coverage: float = 1.0,
    depth: dict | None = None,
) -> str:
    """Write the final report using all structured evidence."""
    notify("compose", "Writing final report with evidence...")

    # Build section list
    section_list = "\n".join(f"## {sa.section}" for sa in claim_map.sections)

    # Build evidence per section
    evidence_by_section = ledger.format_all(claim_map)

    # Build prior verified findings — strong claims from L1 that must be preserved
    prior_findings_lines = []
    for sa in claim_map.sections:
        strong = [c for c in sa.claims if c.evidence_quality == "strong"]
        if strong:
            prior_findings_lines.append(f"\n### {sa.section}")
            for c in strong:
                prior_findings_lines.append(f"- [{c.id}] {c.text}")
    prior_findings_text = "\n".join(prior_findings_lines) if prior_findings_lines else "None — prior report had no verified claims."

    # Build cross-links text
    cross_links_text = "\n".join(
        f"- [{cl.relationship.upper()}] {cl.from_section} → {cl.to_section}: {cl.narrative}"
        for cl in synthesis.cross_links
    ) if synthesis.cross_links else "No cross-section connections found."

    # Build insights text
    insights_text = "\n".join(f"- {i}" for i in synthesis.insights) if synthesis.insights else "No additional insights."

    # Build contrarian text
    contrarian_text = "\n".join(f"- {r}" for r in synthesis.contrarian_risks) if synthesis.contrarian_risks else "No contrarian risks identified."

    # Build gap claims text
    gap_claims = synthesis.gap_report
    if gap_claims:
        gap_lines = []
        for gid in gap_claims:
            for c in claim_map.all_claims():
                if c.id == gid:
                    gap_lines.append(f"- [{gid}] {c.text}")
                    break
        gap_claims_text = "\n".join(gap_lines) if gap_lines else "None"
    else:
        gap_claims_text = "None — all claims have supporting evidence."

    # Get topic-specific quality rules
    # Detect report type from section names (no LLM call needed)
    section_names = " ".join(sa.section.lower() for sa in claim_map.sections)
    if "swot" in section_names or ("strength" in section_names and "weakness" in section_names):
        report_type = "SWOT Analysis"
    elif "porter" in section_names or "five forces" in section_names:
        report_type = "Porter's Five Forces"
    elif "pest" in section_names or ("political" in section_names and "economic" in section_names):
        report_type = "PEST Analysis"
    elif "trend" in section_names:
        report_type = "Trend Report"
    else:
        report_type = ""
    topic_rules = get_quality_rules(report_type)

    brief_instruction = ""
    if brief:
        brief_instruction = (
            f"\n\nCLIENT BRIEF (follow these instructions carefully — they define the scope, "
            f"structure, and focus of this report):\n\n{brief}\n"
        )

    # Low-coverage warning — tell the LLM to write qualitatively for unsupported sections
    if coverage < 0.50:
        brief_instruction += (
            "\n\nLOW EVIDENCE COVERAGE WARNING: Less than 50% of claims have supporting evidence. "
            "For sections with no evidence, provide qualitative analysis based on general knowledge "
            "and the prior report findings. Clearly state when claims are analytical inference "
            "rather than sourced data. Use hedging language like 'based on industry patterns' or "
            "'available evidence suggests'. Do NOT invent statistics or fabricate data points."
        )

    set_model_tier("premium")
    llm = get_llm("writer")

    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")
    current_year = datetime.now().year

    target_words = depth["target_words"] if depth else 3000
    per_section = depth["per_section_words"] if depth else 400

    messages = [
        {"role": "system", "content": (
            f"You are a senior partner at McKinsey writing a client-ready research report. "
            f"Today's date is {current_date}. Write from a {current_year} perspective — "
            f"events from {current_year - 1} and earlier use PAST TENSE. "
            f"Your reports are known for: specific data points in every paragraph, "
            f"named companies with concrete examples, clear 'so what?' implications, "
            f"and actionable recommendations. You never hedge unnecessarily. "
            f"Write approximately {target_words} words. Every section needs data and analysis."
        )},
        {"role": "user", "content": EXPERT_COMPOSE_PROMPT.format(
            topic=topic,
            section_list=section_list,
            evidence_by_section=evidence_by_section,
            cross_links_text=cross_links_text,
            insights_text=insights_text,
            contrarian_text=contrarian_text,
            gap_claims_text=gap_claims_text,
            prior_findings_text=prior_findings_text,
            topic_rules=topic_rules,
            brief_instruction=brief_instruction,
            target_words=target_words,
            per_section_words=per_section,
        )},
    ]

    response = await llm.ainvoke(messages)
    track("L2 compose", response)

    draft = get_content(response).strip()
    draft = strip_preamble(draft)
    draft = _scrub_competitor_mentions(draft)

    word_count = len(draft.split())
    notify("compose", f"Report written: {word_count} words")

    # Quality check — if too short, rewrite with stronger demands
    expand_threshold = depth["expand_threshold"] if depth else 1500
    if word_count < expand_threshold:
        notify("compose", f"Report too short ({word_count} words, need {target_words}), requesting expansion...")
        expand_messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": (
                f"This report is only {word_count} words. It MUST be at least {target_words} words. "
                "Expand EVERY section with:\n"
                "- More specific data points from the evidence ledger\n"
                "- Named companies with concrete actions, investments, partnerships\n"
                "- Case studies: pick 2-3 real companies and describe their strategy in detail\n"
                "- Unit economics: CAC, conversion rates, logistics costs where available\n"
                "- Comparison tables with real data (not qualitative ratings)\n"
                "- 'So what?' analysis after every major finding\n"
                "Do NOT add disclaimers about evidence gaps. Write with authority. "
                "Start directly with ## headings."
            )},
        ]
        response2 = await llm.ainvoke(expand_messages)
        track("L2 compose expansion", response2)
        draft = get_content(response2).strip()
        draft = strip_preamble(draft)
        draft = _scrub_competitor_mentions(draft)
        word_count = len(draft.split())
        notify("compose", f"Expanded report: {word_count} words")

    return draft


# ─── Phase 5.25: EDITORIAL REVIEW ────────────────────────────────────────────


async def _phase_editorial_review(
    draft: str,
    claim_map: ClaimMap,
    ledger: EvidenceLedger,
    synthesis: SynthesisResult,
    notify,
) -> tuple:
    """Review draft quality and return (passes, feedback_json, unused_evidence)."""
    notify("editorial_review", "Editorial review — evaluating report quality...")

    evidence_text = ledger.format_all(claim_map)

    # Build synthesis summary
    synthesis_parts = []
    if synthesis.cross_links:
        synthesis_parts.append("Cross-links:")
        for cl in synthesis.cross_links:
            synthesis_parts.append(f"  {cl.from_section} → {cl.to_section}: {cl.relationship}")
    if synthesis.insights:
        synthesis_parts.append("\nInsights:")
        for ins in synthesis.insights:
            synthesis_parts.append(f"  - {ins}")
    synthesis_text = "\n".join(synthesis_parts) if synthesis_parts else "(none)"

    set_model_tier("reasoning")
    llm = get_llm("reviewer")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": EXPERT_EDITORIAL_REVIEW_PROMPT.format(
            draft=draft,
            evidence_text=evidence_text,
            synthesis_text=synthesis_text,
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("L2 editorial review", response)

        raw = get_content(response).strip()
        data = extract_json(raw)

        if not data or "passes" not in data:
            logger.warning("[Expert] Editorial review failed to parse, skipping")
            notify("editorial_review", "Review parse failed — skipping")
            return True, {}, []

        passes = data.get("passes", True)
        scores = data.get("scores", {})
        weaknesses = data.get("weaknesses", [])
        unused = data.get("unused_evidence", [])
        assessment = data.get("overall_assessment", "")

        score_summary = ", ".join(f"{k}: {v}" for k, v in scores.items())
        notify("editorial_review", f"Scores: {score_summary}. {'PASS' if passes else 'NEEDS REVISION'}")
        if assessment:
            logger.info(f"[Expert] Editorial assessment: {assessment}")

        return passes, data, unused

    except Exception as e:
        logger.warning(f"[Expert] Editorial review failed (non-fatal): {e}")
        notify("editorial_review", "Review failed — skipping")
        return True, {}, []


async def _phase_targeted_rewrite(
    draft: str,
    feedback: dict,
    unused_evidence: list,
    ledger: EvidenceLedger,
    claim_map: ClaimMap,
    notify,
) -> str:
    """Rewrite the draft addressing editorial feedback."""
    notify("editorial_rewrite", "Rewriting report based on editorial feedback...")

    evidence_text = ledger.format_all(claim_map)

    # Format feedback for the LLM
    feedback_lines = []
    for w in feedback.get("weaknesses", []):
        feedback_lines.append(f"- [{w.get('dimension', '')}] Section: {w.get('section', '')}")
        feedback_lines.append(f"  Issue: {w.get('issue', '')}")
        feedback_lines.append(f"  Fix: {w.get('fix', '')}")
    feedback_text = "\n".join(feedback_lines) if feedback_lines else "(no specific weaknesses)"

    unused_text = "\n".join(f"- {e}" for e in unused_evidence) if unused_evidence else "(none)"

    set_model_tier("premium")
    llm = get_llm("writer")

    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")
    current_year = datetime.now().year

    messages = [
        {"role": "system", "content": (
            f"You are a senior research analyst improving a report based on editorial feedback. "
            f"Today's date is {current_date}. Write from a {current_year} perspective. "
            f"Be direct, opinionated, and specific. Name names."
        )},
        {"role": "user", "content": EXPERT_TARGETED_REWRITE_PROMPT.format(
            draft=draft,
            feedback=feedback_text,
            unused_evidence=unused_text,
            evidence_text=evidence_text,
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("L2 editorial rewrite", response)

        rewritten = get_content(response).strip()
        rewritten = strip_preamble(rewritten)
        rewritten = _scrub_competitor_mentions(rewritten)

        word_count = len(rewritten.split())
        notify("editorial_rewrite", f"Rewrite complete: {word_count} words")

        # Sanity: rewritten version should be at least 80% of original
        if word_count >= len(draft.split()) * 0.8:
            return rewritten
        else:
            logger.warning("[Expert] Rewrite too short, keeping original")
            notify("editorial_rewrite", "Rewrite too short — keeping original")
            return draft

    except Exception as e:
        logger.warning(f"[Expert] Targeted rewrite failed (non-fatal): {e}")
        notify("editorial_rewrite", "Rewrite failed — keeping original")
        return draft


# ─── Phase 5.5: VERIFY ───────────────────────────────────────────────────────


async def _phase_verify(
    draft: str,
    claim_map: ClaimMap,
    ledger: EvidenceLedger,
    notify,
) -> str:
    """Cross-reference draft against evidence ledger, hedge or remove unsourced claims."""
    notify("verify", "Verifying factual claims against evidence ledger...")

    evidence_text = ledger.format_all(claim_map)

    set_model_tier("premium")
    llm = get_llm("reviewer")

    messages = [
        {"role": "system", "content": (
            "You are a fact-verification specialist. Your job is to ensure every claim "
            "in the report is grounded in the evidence ledger. Be precise and conservative — "
            "when in doubt, hedge the claim rather than leaving it as stated fact."
        )},
        {"role": "user", "content": EXPERT_VERIFY_PROMPT.format(
            draft=draft,
            evidence_text=evidence_text,
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("L2 verify", response)

        verified_draft = get_content(response).strip()
        verified_draft = strip_preamble(verified_draft)

        # Sanity: verified version should be at least 70% of original length
        if len(verified_draft.split()) >= len(draft.split()) * 0.7:
            removed_words = len(draft.split()) - len(verified_draft.split())
            notify("verify", f"Verification complete. {abs(removed_words)} words adjusted.")
            return verified_draft
        else:
            logger.warning("[Expert] Verified draft too short, keeping original")
            notify("verify", "Verification produced shorter output, keeping original")
            return draft
    except Exception as e:
        logger.warning(f"[Expert] Verify phase failed (non-fatal): {e}")
        notify("verify", "Verification skipped (non-fatal error)")
        return draft


# ─── Phase 6: FORMAT ─────────────────────────────────────────────────────────


async def _phase_format(draft: str, notify) -> str:
    """Reformat the composed report for maximum readability without changing content."""
    notify("format", "Formatting report for readability...")

    llm = get_llm("writer")
    messages = [
        {"role": "system", "content": "You are a document formatting specialist. Reformat for readability. Do NOT change any content."},
        {"role": "user", "content": REPORT_FORMAT_PROMPT.format(draft=draft)},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("L2 format", response)
        formatted = get_content(response).strip()
        formatted = strip_preamble(formatted)

        # Sanity check: formatted version should be at least 80% of original length
        if len(formatted.split()) >= len(draft.split()) * 0.8:
            notify("format", "Report formatted successfully")
            return formatted
        else:
            logger.warning("[Expert] Formatted report too short, keeping original")
            notify("format", "Format produced shorter output, keeping original")
            return draft
    except Exception as e:
        logger.warning(f"[Expert] Format phase failed (non-fatal): {e}")
        notify("format", "Formatting skipped (non-fatal error)")
        return draft


# ─── Main entry point ────────────────────────────────────────────────────────


async def run(
    topic: str,
    progress_callback=None,
    prior_report: str = "",
    prior_sources: list[Source] | None = None,
    brief: str = "",
) -> ResearchResult:
    """Run Layer 2: Section-driven expert research pipeline.

    New architecture: Plans from topic directly (no claim dissection).
    Uses L1's sources as a head start, not L1's report.
    """
    start = time.time()
    phase_timings = {}

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(2, status, msg)
        logger.info(f"[Expert] {status}: {msg}")

    notify("start", "Starting Expert pipeline (Plan → Investigate → Compose)...")

    # Create shared agent context
    ctx = AgentContext(max_tool_calls=80)

    # Seed with L1's sources (URLs already scraped — avoid re-scraping)
    if prior_sources:
        for s in prior_sources:
            ctx.sources.append(s)
            ctx.urls_seen.add(s.url)

    # ── Phase 1: PLAN FROM TOPIC ──────────────────────────────────────────
    t1 = time.time()
    sections = []
    all_queries = []
    try:
        set_model_tier("standard")
        llm = get_llm("planner")

        messages = [
            {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
            {"role": "user", "content": EXPERT_TOPIC_PLAN_PROMPT.format(
                topic=topic,
                brief=brief or "(no additional brief)",
            )},
        ]
        response = await llm.ainvoke(messages)
        track("L2 plan", response)

        raw = get_content(response).strip()
        data = extract_json(raw)

        if data and "sections" in data:
            for s in data["sections"]:
                section_name = str(s.get("section", ""))
                queries = s.get("queries", [])
                if isinstance(queries, list):
                    queries = [str(q) for q in queries]
                else:
                    queries = []
                sections.append({
                    "section": section_name,
                    "description": str(s.get("description", "")),
                    "queries": queries,
                    "priority": int(s.get("priority", 2)),
                })
                all_queries.extend(queries)

        notify("plan", f"Planned {len(sections)} sections with {len(all_queries)} queries")
    except Exception as e:
        logger.error(f"[Expert] Phase 1 (Plan) failed: {e}")

    # Compute dynamic depth targets
    from utils import compute_depth_targets
    depth = compute_depth_targets(
        section_count=len(sections),
        total_claims=len(all_queries),  # Use query count as complexity proxy
    )
    logger.info(f"[Expert] Depth targets: {depth}")

    phase_timings["plan"] = {
        "sections": len(sections),
        "queries_planned": len(all_queries),
        "elapsed_s": round(time.time() - t1, 1),
    }

    # ── Phase 2: INVESTIGATE ──────────────────────────────────────────────
    t2 = time.time()
    ledger = EvidenceLedger()
    try:
        # Format the plan for the agent
        plan_text_parts = []
        for s in sections:
            plan_text_parts.append(f"## {s['section']}")
            plan_text_parts.append(f"Goal: {s['description']}")
            plan_text_parts.append("Queries:")
            for q in s["queries"]:
                plan_text_parts.append(f"  - {q}")
            plan_text_parts.append("")
        plan_text = "\n".join(plan_text_parts)

        system_prompt = EXPERT_SECTION_INVESTIGATE_PROMPT.format(
            topic=topic,
            research_plan=plan_text,
        )

        set_model_tier("standard")  # gpt-4o — must reliably call record_finding(); mini fails at this
        llm = get_llm("writer")
        tools = make_tools(ctx, ledger=ledger)

        graph = build_agent_graph(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_tool_calls=80,
            min_word_count=1,
            max_retries=0,
            progress_callback=progress_callback,
            layer=2,
            ctx=ctx,
        )

        initial_state = build_initial_state(
            topic=topic,
            layer=2,
            system_prompt=system_prompt,
            prior_report=f"Research all sections in the plan. Use record_finding after each discovery.\n\nTopic: {topic}",
            brief=brief,
            max_tool_calls=80,
            min_word_count=1,
            max_retries=0,
        )

        await graph.ainvoke(initial_state)

        notify("investigate", f"Found {len(ledger.entries)} findings across "
                              f"{len({e.claim_id for e in ledger.entries})} sections")
    except Exception as e:
        logger.error(f"[Expert] Phase 2 (Investigate) failed: {e}")

    searches = [tc for tc in ctx.tool_calls_log if tc.get("tool") == "search_web"]
    scrapes = [tc for tc in ctx.tool_calls_log if tc.get("tool") == "scrape_page"]
    findings_count = len(ledger.entries)
    sections_with_evidence = len({e.claim_id for e in ledger.entries})

    phase_timings["investigate"] = {
        "searches": len(searches),
        "scrapes": len(scrapes),
        "findings": findings_count,
        "sections_covered": sections_with_evidence,
        "elapsed_s": round(time.time() - t2, 1),
    }

    # ── Phase 3: COMPOSE ──────────────────────────────────────────────────
    t3 = time.time()
    try:
        # Build query→section mapping so auto-recorded evidence can be matched
        query_to_section = {}
        for s in sections:
            for q in s.get("queries", []):
                query_to_section[q.lower()] = s["section"]

        def match_evidence_to_section(evidence, section_name):
            """Check if an evidence entry belongs to a section by name or query match."""
            cid = evidence.claim_id.lower()
            sname = section_name.lower()
            # Direct match
            if cid == sname:
                return True
            # Section name in claim_id or vice versa
            if sname in cid or cid in sname:
                return True
            # claim_id is a query — check if it maps to this section
            mapped = query_to_section.get(cid, "")
            if mapped.lower() == sname:
                return True
            # Keyword overlap: section name words appear in claim_id
            section_words = set(sname.split()) - {"and", "the", "of", "in", "for", "a", "an"}
            if len(section_words) >= 2:
                matches = sum(1 for w in section_words if w in cid)
                if matches >= 2:
                    return True
            return False

        # Build evidence text grouped by section
        used_evidence_ids = set()
        evidence_by_section_parts = []
        for s in sections:
            section_name = s["section"]
            section_evidence = [e for e in ledger.entries if match_evidence_to_section(e, section_name)]
            # Deduplicate
            unique_evidence = []
            for e in section_evidence:
                eid = (e.fact[:100], e.source_url)
                if eid not in used_evidence_ids:
                    used_evidence_ids.add(eid)
                    unique_evidence.append(e)
            evidence_by_section_parts.append(f"## {section_name}")
            if unique_evidence:
                for e in unique_evidence:
                    tier_label = {1: "T1", 2: "T2"}.get(e.source_tier, "")
                    if not tier_label:
                        tier_label = "T2" if e.source_title and len(e.source_title) > 3 else "UNVERIFIED"
                    type_label = "[INFERRED]" if e.evidence_type == "inferred" else f"[{e.evidence_type}]"
                    line = f"- [{tier_label}] {type_label} {e.fact}"
                    if e.source_title:
                        src = e.source_title
                        if e.source_url:
                            src += f" ({e.source_url})"
                        line += f"\n  Source: {src}"
                    evidence_by_section_parts.append(line)
            else:
                evidence_by_section_parts.append("- (no evidence found — write from expert knowledge)")
            evidence_by_section_parts.append("")

        # Add unmatched evidence as "Additional Research Findings"
        unmatched = [e for e in ledger.entries if (e.fact[:100], e.source_url) not in used_evidence_ids]
        if unmatched:
            evidence_by_section_parts.append("## Additional Research Findings")
            for e in unmatched[:30]:  # Cap to avoid prompt bloat
                line = f"- {e.fact}"
                if e.source_title:
                    line += f"\n  Source: {e.source_title}"
                    if e.source_url:
                        line += f" ({e.source_url})"
                evidence_by_section_parts.append(line)
            evidence_by_section_parts.append("")

        # Append deduplicated T1/T2 source list for bibliography
        seen_urls = set()
        source_list_parts = ["\n## AVAILABLE SOURCES FOR BIBLIOGRAPHY (T1 and T2 only)"]
        for src in ctx.sources:
            if src.url in seen_urls or not src.url:
                continue
            seen_urls.add(src.url)
            if src.tier <= 2:  # T1 or T2 only
                label = f"[T{src.tier}]"
                title = src.title or src.publisher or src.url
                source_list_parts.append(f"- {label} {title} — {src.url}")
        if len(source_list_parts) > 1:
            evidence_by_section_parts.extend(source_list_parts)
            evidence_by_section_parts.append("")

        evidence_by_section = "\n".join(evidence_by_section_parts)

        # Detect report type from section names
        section_names_lower = " ".join(s["section"].lower() for s in sections)
        if "swot" in section_names_lower or ("strength" in section_names_lower and "weakness" in section_names_lower):
            report_type = "SWOT Analysis"
        elif "porter" in section_names_lower or "five forces" in section_names_lower:
            report_type = "Porter's Five Forces"
        elif "pest" in section_names_lower or ("political" in section_names_lower and "economic" in section_names_lower):
            report_type = "PEST Analysis"
        else:
            report_type = ""
        topic_rules = get_quality_rules(report_type)

        brief_instruction = ""
        if brief:
            brief_instruction = (
                f"\n\nCLIENT BRIEF:\n\n{brief}\n"
            )

        target_words = depth["target_words"]
        per_section = depth["per_section_words"]

        section_list = "\n".join(f"## {s['section']}" for s in sections)

        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year

        set_model_tier("premium")
        llm = get_llm("writer")

        messages = [
            {"role": "system", "content": (
                f"You are a senior partner at McKinsey writing a client-ready research report. "
                f"Today's date is {current_date}. Write from a {current_year} perspective — "
                f"events from {current_year - 1} and earlier use PAST TENSE. "
                f"Your reports are known for: specific data points in every paragraph, "
                f"named companies with concrete examples, clear 'so what?' implications, "
                f"and actionable recommendations. You never hedge unnecessarily. "
                f"Write approximately {target_words} words. Every section needs data and analysis."
            )},
            {"role": "user", "content": EXPERT_COMPOSE_PROMPT.format(
                topic=topic,
                section_list=section_list,
                evidence_by_section=evidence_by_section,
                cross_links_text="(identify cross-section connections yourself from the evidence)",
                insights_text="(generate insights from the evidence)",
                contrarian_text="(identify contrarian risks from the evidence)",
                gap_claims_text="None",
                prior_findings_text="(use evidence above — integrate L1 findings where relevant)",
                topic_rules=topic_rules,
                brief_instruction=brief_instruction,
                target_words=target_words,
                per_section_words=per_section,
            )},
        ]

        response = await llm.ainvoke(messages)
        track("L2 compose", response)

        draft = get_content(response).strip()
        draft = strip_preamble(draft)
        draft = _scrub_competitor_mentions(draft)

        word_count = len(draft.split())
        notify("compose", f"Report written: {word_count} words")

        # Expand if too short
        expand_threshold = depth["expand_threshold"]
        if word_count < expand_threshold:
            notify("compose", f"Report too short ({word_count} words, need {target_words}), expanding...")
            expand_messages = messages + [
                {"role": "assistant", "content": draft},
                {"role": "user", "content": (
                    f"This report is only {word_count} words. It MUST be at least {target_words} words. "
                    "Expand EVERY section with:\n"
                    "- More specific data points from the evidence\n"
                    "- Named companies with concrete actions and metrics\n"
                    "- Case studies: 2-3 real companies described in detail\n"
                    "- Comparison tables with real numbers\n"
                    "- 'So what?' analysis after every major finding\n"
                    "Start directly with ## headings."
                )},
            ]
            response2 = await llm.ainvoke(expand_messages)
            track("L2 compose expansion", response2)
            draft = get_content(response2).strip()
            draft = strip_preamble(draft)
            draft = _scrub_competitor_mentions(draft)
            word_count = len(draft.split())
            notify("compose", f"Expanded report: {word_count} words")

    except Exception as e:
        import traceback
        logger.error(f"[Expert] Phase 3 (Compose) failed: {e}\n{traceback.format_exc()}")
        draft = "## Error\n\nExpert pipeline composition failed."

    phase_timings["compose"] = {
        "word_count": len(draft.split()),
        "elapsed_s": round(time.time() - t3, 1),
    }

    elapsed = time.time() - start
    sources_inherited = len(prior_sources) if prior_sources else 0
    sources_new = len(ctx.sources) - sources_inherited

    # Build frontend-compatible metadata
    iteration_history = [{
        "iteration": 0,
        "score": 0,
        "weaknesses": [],
        "queries": ctx.tool_calls_log,
        "stop_reason": "complete",
    }]

    notify("done", f"Expert pipeline complete: {len(draft.split())} words, "
                    f"{len(ctx.sources)} sources, {findings_count} findings "
                    f"in {elapsed:.1f}s")

    evidence_data = [
        {
            "claim_id": e.claim_id, "fact": e.fact,
            "source_url": e.source_url, "source_title": e.source_title,
            "evidence_type": e.evidence_type, "confidence": e.confidence,
        }
        for e in ledger.entries
    ]

    research_tasks_data = [
        {
            "claim_id": "",
            "section": s["section"],
            "rationale": s["description"],
            "queries": s["queries"],
            "expected_evidence": "",
            "priority": s["priority"],
            "target_sources": [],
        }
        for s in sections
    ]

    phase_details = [
        {
            "phase": "plan",
            "sections": len(sections),
            "questions": len(all_queries),
            "elapsed": phase_timings.get("plan", {}).get("elapsed_s", 0),
        },
        {
            "phase": "investigate",
            "facts": findings_count,
            "sources": len(ctx.sources),
            "coverage": round(sections_with_evidence / max(len(sections), 1), 2),
            "searches": len(searches),
            "scrapes": len(scrapes),
            "elapsed": phase_timings.get("investigate", {}).get("elapsed_s", 0),
        },
        {
            "phase": "compose",
            "words": len(draft.split()),
            "elapsed": phase_timings.get("compose", {}).get("elapsed_s", 0),
        },
    ]

    return ResearchResult(
        layer=2,
        topic=topic,
        content=draft,
        sources=ctx.sources,
        metadata={
            "method": "cmi_expert",
            "phases": phase_timings,
            "phase_details": phase_details,
            "evidence_ledger": evidence_data,
            "iterations": 1,
            "final_score": 0,
            "tool_calls": ctx.tool_call_count,
            "sources_found": len(ctx.sources),
            "sources_scraped": sum(1 for s in ctx.sources if s.scraped_content),
            "searches_count": len(searches),
            "scrapes_count": len(scrapes),
            "sources_inherited": sources_inherited,
            "sources_new": sources_new,
            "iteration_history": iteration_history,
            "plan_sections": [s["section"] for s in sections],
            "plan_questions": len(all_queries),
            "facts_collected": findings_count,
            "facts_verified": sum(1 for e in ledger.entries if e.confidence == "high"),
            "research_tasks": research_tasks_data,
        },
        elapsed_seconds=elapsed,
    )

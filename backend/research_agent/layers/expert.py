"""
Layer 2 — CMI EXPERT: 6-phase deep research pipeline.

Receives Layer 1's enhanced report and produces the definitive analysis via:
  Phase 1 (DISSECT)      → Extract and grade every claim
  Phase 2 (PLAN)         → Generate targeted research queries per claim
  Phase 3 (INVESTIGATE)  → Execute research plan, track evidence per claim
  Phase 4 (SYNTHESIZE)   → Cross-reference, find connections, generate insights
  Phase 5 (COMPOSE)      → Write final report with all structured evidence
  Phase 6 (FORMAT)       → Reformat for readability (tables, bullets, structure)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict

from config import get_llm, set_model_tier
from research_agent.models import (
    ResearchResult, Source, AgentContext,
    Claim, SectionAnnotation, ClaimMap,
    ResearchTask, ExpertResearchPlan,
    Evidence, EvidenceLedger,
    CrossLink, SynthesisResult,
)
from research_agent.graph import build_agent_graph, build_initial_state, make_tools, _scrub_competitor_mentions
from research_agent.prompts import (
    EXPERT_DISSECT_PROMPT, EXPERT_PLAN_PROMPT, EXPERT_INVESTIGATE_PROMPT,
    EXPERT_SYNTHESIZE_PROMPT, EXPERT_COMPOSE_PROMPT, REPORT_FORMAT_PROMPT,
    get_quality_rules,
)
from research_agent.cost import track
from research_agent.utils import get_content, extract_json, strip_preamble, generate_report_outline, parse_outline_type

logger = logging.getLogger(__name__)


# ─── Phase 1: DISSECT ────────────────────────────────────────────────────────


async def _phase_dissect(topic: str, prior_report: str, notify) -> ClaimMap:
    """Extract and grade every claim from the prior report."""
    notify("dissect", "Extracting and grading claims from prior report...")

    set_model_tier("budget")
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

    set_model_tier("budget")
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
        max_tool_calls=50,   # Bounded — coverage gates are the real stopping condition
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
        max_tool_calls=50,
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
        max_tool_calls=25,
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

    set_model_tier("premium")
    llm = get_llm("writer")

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
    report_type = ""
    try:
        set_model_tier("budget")
        outline_llm = get_llm("planner")
        outline = await generate_report_outline(topic, outline_llm, brief=brief)
        report_type = parse_outline_type(outline) if outline else ""
    except Exception:
        pass
    topic_rules = get_quality_rules(report_type)

    brief_instruction = ""
    if brief:
        brief_instruction = (
            f"\n\nCLIENT BRIEF (follow these instructions carefully — they define the scope, "
            f"structure, and focus of this report):\n\n{brief}\n"
        )

    set_model_tier("premium")
    llm = get_llm("writer")

    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")
    current_year = datetime.now().year

    messages = [
        {"role": "system", "content": (
            f"You are a senior research analyst writing a definitive report. "
            f"Today's date is {current_date}. Write from a {current_year} perspective — "
            f"events from {current_year - 1} and earlier should use PAST TENSE "
            f"(e.g. 'In {current_year - 1}, adoption reached 60%' NOT 'adoption is reaching 60%'). "
            f"Write with authority — every claim must trace to evidence. "
            f"Be direct, opinionated, and specific. Name names."
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
        )},
    ]

    response = await llm.ainvoke(messages)
    track("L2 compose", response)

    draft = get_content(response).strip()
    draft = strip_preamble(draft)
    draft = _scrub_competitor_mentions(draft)

    word_count = len(draft.split())
    notify("compose", f"Report written: {word_count} words")

    # Quality check — if too short, rewrite
    if word_count < 1500:
        notify("compose", "Report too short, requesting expansion...")
        expand_messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": (
                f"This report is only {word_count} words. It needs to be at least 2500 words. "
                "Expand EVERY section with more detail from the evidence ledger. "
                "Add more analysis, more specific data points, more 'so what?' commentary. "
                "Add a comparison table. Start directly with ## headings."
            )},
        ]
        response2 = await llm.ainvoke(expand_messages)
        track("L2 compose rewrite", response2)
        draft = get_content(response2).strip()
        draft = strip_preamble(draft)
        draft = _scrub_competitor_mentions(draft)
        word_count = len(draft.split())
        notify("compose", f"Expanded report: {word_count} words")

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
    """Run Layer 2: 5-phase expert pipeline."""
    start = time.time()
    phase_timings = {}

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(2, status, msg)
        logger.info(f"[Expert] {status}: {msg}")

    notify("start", "Starting CMI Expert pipeline (5 phases)...")

    # Create shared agent context
    ctx = AgentContext(max_tool_calls=30)

    # Seed with prior sources
    if prior_sources:
        for s in prior_sources:
            ctx.sources.append(s)
            ctx.urls_seen.add(s.url)

    # ── Phase 1: DISSECT ──────────────────────────────────────────────────
    t1 = time.time()
    try:
        claim_map = await _phase_dissect(topic, prior_report, notify)
    except Exception as e:
        logger.error(f"[Expert] Phase 1 (Dissect) failed: {e}")
        claim_map = _fallback_claim_map(prior_report)
    phase_timings["dissect"] = {
        "claims_total": claim_map.total_claims,
        "claims_weak": claim_map.claims_needing_research,
        "elapsed_s": round(time.time() - t1, 1),
    }

    # ── Phase 2: PLAN ─────────────────────────────────────────────────────
    t2 = time.time()
    try:
        research_plan = await _phase_plan(topic, claim_map, notify)
    except Exception as e:
        logger.error(f"[Expert] Phase 2 (Plan) failed: {e}")
        research_plan = ExpertResearchPlan(tasks=[])
    phase_timings["plan"] = {
        "tasks": len(research_plan.tasks),
        "queries_planned": research_plan.total_queries,
        "elapsed_s": round(time.time() - t2, 1),
    }

    # ── Phase 3: INVESTIGATE ──────────────────────────────────────────────
    t3 = time.time()
    try:
        ledger, coverage_before_gap_fill, gap_fill_passes = await _phase_investigate(
            topic, research_plan, claim_map, ctx, notify, progress_callback, brief
        )
    except Exception as e:
        logger.error(f"[Expert] Phase 3 (Investigate) failed: {e}")
        ledger = EvidenceLedger()
        coverage_before_gap_fill = 0.0
        gap_fill_passes = 0

    searches = [tc for tc in ctx.tool_calls_log if tc.get("tool") == "search_web"]
    scrapes = [tc for tc in ctx.tool_calls_log if tc.get("tool") == "scrape_page"]
    phase_timings["investigate"] = {
        "searches": len(searches),
        "scrapes": len(scrapes),
        "findings": len(ledger.entries),
        "coverage": round(ledger.coverage_score(claim_map), 2),
        "elapsed_s": round(time.time() - t3, 1),
    }

    # ── Phase 4: SYNTHESIZE ───────────────────────────────────────────────
    t4 = time.time()
    try:
        synthesis = await _phase_synthesize(topic, claim_map, ledger, notify)
    except Exception as e:
        logger.error(f"[Expert] Phase 4 (Synthesize) failed: {e}")
        synthesis = SynthesisResult()
    phase_timings["synthesize"] = {
        "cross_links": len(synthesis.cross_links),
        "insights": len(synthesis.insights),
        "gaps": len(synthesis.gap_report),
        "elapsed_s": round(time.time() - t4, 1),
    }

    # ── Phase 5: COMPOSE ──────────────────────────────────────────────────
    t5 = time.time()
    try:
        draft = await _phase_compose(topic, claim_map, ledger, synthesis, brief, notify, prior_report=prior_report)
    except Exception as e:
        logger.error(f"[Expert] Phase 5 (Compose) failed: {e}")
        draft = "## Error\n\nExpert pipeline composition failed."
    phase_timings["compose"] = {
        "word_count": len(draft.split()),
        "elapsed_s": round(time.time() - t5, 1),
    }

    # ── Phase 6: FORMAT ──────────────────────────────────────────────────
    t6 = time.time()
    try:
        draft = await _phase_format(draft, notify)
    except Exception as e:
        logger.warning(f"[Expert] Phase 6 (Format) failed (non-fatal): {e}")
    phase_timings["format"] = {
        "word_count": len(draft.split()),
        "elapsed_s": round(time.time() - t6, 1),
    }

    elapsed = time.time() - start
    sources_inherited = len(prior_sources) if prior_sources else 0
    sources_new = len(ctx.sources) - sources_inherited

    # Build iteration_history for frontend compatibility
    iteration_history = [{
        "iteration": 0,
        "score": 0,
        "weaknesses": [],
        "queries": ctx.tool_calls_log,
        "stop_reason": "complete",
    }]

    notify("done", f"Expert pipeline complete: {len(draft.split())} words, "
                    f"{len(ctx.sources)} sources, {ledger.coverage_score(claim_map):.0%} coverage "
                    f"in {elapsed:.1f}s")

    # Serialize evidence and cross-links for metadata
    evidence_data = [
        {
            "claim_id": e.claim_id, "fact": e.fact,
            "source_url": e.source_url, "source_title": e.source_title,
            "evidence_type": e.evidence_type, "confidence": e.confidence,
        }
        for e in ledger.entries
    ]
    cross_link_data = [
        {
            "from_section": cl.from_section, "to_section": cl.to_section,
            "from_claim_id": cl.from_claim_id, "to_claim_id": cl.to_claim_id,
            "relationship": cl.relationship, "narrative": cl.narrative,
        }
        for cl in synthesis.cross_links
    ]

    # Serialize claim map and research tasks for frontend Overview
    claim_map_data = [
        {
            "section": sa.section,
            "thesis": sa.thesis,
            "overall_quality": sa.overall_quality,
            "missing_angles": sa.missing_angles,
            "claims": [
                {
                    "id": c.id,
                    "text": c.text,
                    "evidence_quality": c.evidence_quality,
                    "data_type": c.data_type,
                    "needs_research": c.needs_research,
                    "reasoning": c.reasoning,
                }
                for c in sa.claims
            ],
        }
        for sa in claim_map.sections
    ]

    research_tasks_data = [
        {
            "claim_id": t.claim_id,
            "section": t.section,
            "rationale": t.rationale,
            "queries": t.queries,
            "expected_evidence": t.expected_evidence,
            "priority": t.priority,
            "target_sources": t.target_sources,
        }
        for t in research_plan.tasks
    ]

    # Build phase_details in the format the frontend CmiPipelineFlow expects
    phase_details = [
        {
            "phase": "dissect",
            "claims_total": phase_timings.get("dissect", {}).get("claims_total", 0),
            "claims_weak": phase_timings.get("dissect", {}).get("claims_weak", 0),
            "elapsed": phase_timings.get("dissect", {}).get("elapsed_s", 0),
        },
        {
            "phase": "plan",
            "sections": len(research_plan.sections_covered()),
            "questions": research_plan.total_queries,
            "elapsed": phase_timings.get("plan", {}).get("elapsed_s", 0),
        },
        {
            "phase": "investigate",
            "facts": len(ledger.entries),
            "sources": len(ctx.sources),
            "coverage": round(ledger.coverage_score(claim_map), 2),
            "searches": len(searches),
            "scrapes": len(scrapes),
            "elapsed": phase_timings.get("investigate", {}).get("elapsed_s", 0),
        },
        {
            "phase": "synthesize",
            "insights": len(synthesis.insights),
            "cross_links": len(synthesis.cross_links),
            "risks": len(synthesis.contrarian_risks),
            "gaps": len(synthesis.gap_report),
            "elapsed": phase_timings.get("synthesize", {}).get("elapsed_s", 0),
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
            "claim_coverage": round(ledger.coverage_score(claim_map), 2),
            "evidence_ledger": evidence_data,
            "cross_links": cross_link_data,
            "insights": synthesis.insights,
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
            "plan_sections": research_plan.sections_covered(),
            "plan_questions": research_plan.total_queries,
            "facts_collected": len(ledger.entries),
            "facts_verified": sum(1 for e in ledger.entries if e.confidence == "high"),
            "insights_generated": len(synthesis.insights),
            "contrarian_risks": len(synthesis.contrarian_risks),
            "review_score": 0,
            # Enriched data for Overview narrative
            "claim_map": claim_map_data,
            "research_tasks": research_tasks_data,
            "contrarian_risks_detail": synthesis.contrarian_risks,
            "resolved_contradictions": synthesis.resolved_contradictions,
            "gap_report": synthesis.gap_report,
            "coverage_before_gap_fill": coverage_before_gap_fill,
            "gap_fill_passes": gap_fill_passes,
        },
        elapsed_seconds=elapsed,
    )

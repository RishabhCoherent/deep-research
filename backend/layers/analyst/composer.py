"""
Phase 5: COMPOSE — Two-pass report writing.

Pass 1: Argument structure (reasoning model) — what each section argues
Pass 2: Full report (premium writer) — prose from structured outline + evidence
"""

import json
import logging
import re

from config import get_llm, set_model_tier
from models.analyst import AnalysisResult, ResearchBoard
from prompts.analyst import (
    COMPOSE_OUTLINE_PROMPT, COMPOSE_REPORT_PROMPT, BANNED_RESEARCH_FIRMS,
)
from utils.cost_tracker import track
from utils import get_content, extract_json, date_vars

logger = logging.getLogger(__name__)


async def compose(
    board: ResearchBoard,
    analysis: AnalysisResult,
    topic: str,
    notify=None,
    brief: str = "",
) -> str:
    """Write the final report in two passes: outline then prose."""
    if notify:
        notify("compose", "Structuring report arguments...")

    # ── Pass 1: Argument structure ────────────────────────────────────────

    sections = board.framework.report_sections
    if not sections:
        sections = ["Executive Summary", "Current State", "Key Findings",
                     "Analysis", "Implications", "Conclusion"]

    # Build evidence organized by section/sub-question
    evidence_by_section = _build_evidence_by_section(board)

    # Extract verified numeric facts for mandatory injection
    key_stats = _extract_key_stats(board)

    # Format judgments
    judgment_lines = []
    for j in analysis.judgments:
        judgment_lines.append(
            f"- [{j.conviction.upper()}] {j.claim}\n"
            f"  Reasoning: {j.reasoning}\n"
            f"  Section: {j.section}"
        )
    judgments_text = "\n".join(judgment_lines) if judgment_lines else "No judgments formed."

    # Format gaps
    gap_lines = []
    for sq_id, severity in analysis.gap_severity.items():
        for sq in board.framework.sub_questions:
            if sq.id == sq_id:
                gap_lines.append(f"- [{severity.upper()}] {sq.question}")
    gaps_text = "\n".join(gap_lines) if gap_lines else "No critical gaps."

    # Causal chains
    chains_text = "\n".join(f"- {c}" for c in analysis.causal_chains) if analysis.causal_chains else "None identified."

    # Format analytical frameworks (flexible — whatever the analyze phase produced)
    frameworks_text = _format_frameworks(analysis.analytical_frameworks)
    contrarian_text = "\n".join(f"- {c}" for c in analysis.contrarian_insights) if analysis.contrarian_insights else "None identified."

    # Build brief section for the writer (empty string = no injection)
    brief_section = (
        f"CLIENT REQUIREMENTS: {brief}\n"
        f"Ensure the report explicitly covers all named companies, metrics, and topics mentioned above."
        if brief else ""
    )

    set_model_tier("standard")
    llm_outline = get_llm("analyst")

    messages_outline = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": COMPOSE_OUTLINE_PROMPT.format(
            topic=topic,
            sections="\n".join(f"- {s}" for s in sections),
            key_findings="\n".join(f"- {f}" for f in analysis.key_findings),
            narrative_thread=analysis.narrative_thread,
            causal_chains=chains_text,
            judgments=judgments_text,
            evidence_gaps=gaps_text,
            analytical_frameworks=frameworks_text,
            contrarian_insights=contrarian_text,
        )},
    ]

    response = await llm_outline.ainvoke(messages_outline)
    track("analyst compose outline", response)
    outline_raw = get_content(response)
    outline_data = extract_json(outline_raw)

    if not outline_data or "sections" not in outline_data:
        logger.warning("[Analyst] Outline parse failed, using simple structure")
        outline_text = _simple_outline(sections, analysis)
    else:
        outline_text = _format_outline(outline_data)

    if notify:
        notify("compose", "Writing final report...")

    # ── Pass 2: Full report ───────────────────────────────────────────────

    # Calculate dynamic word targets
    num_sections = len(sections)
    target_words = max(6000, num_sections * 800)
    per_section_words = target_words // max(num_sections, 1)

    # Build banned firms summary for the prompt
    banned_firms_summary = ", ".join(BANNED_RESEARCH_FIRMS[:10]) + ", etc."

    set_model_tier("premium")
    llm_writer = get_llm("writer")

    messages_report = [
        {"role": "user", "content": COMPOSE_REPORT_PROMPT.format(
            topic=topic,
            brief_section=brief_section,
            outline=outline_text,
            evidence_by_section=evidence_by_section,
            key_stats=key_stats,
            judgments=judgments_text,
            evidence_gaps=gaps_text,
            analytical_frameworks=frameworks_text,
            contrarian_insights=contrarian_text,
            banned_firms_summary=banned_firms_summary,
            target_words=target_words,
            per_section_words=per_section_words,
            **date_vars(),
        )},
    ]

    response = await llm_writer.ainvoke(messages_report)
    track("analyst compose report", response)
    draft = get_content(response)

    # Scrub competitor mentions
    draft = _scrub_competitors(draft)

    word_count = len(draft.split())
    logger.info(f"[Analyst] Report composed: {word_count} words")

    # Auto-expand if too short (0.75 threshold — LLMs consistently underwrite)
    if word_count < target_words * 0.75:
        logger.info(f"[Analyst] Report too short ({word_count} words), expanding...")
        if notify:
            notify("compose", f"Report at {word_count} words, expanding...")

        # Truncate evidence to avoid hitting TPM limits on the expand call
        truncated_evidence = evidence_by_section[:15000] if len(evidence_by_section) > 15000 else evidence_by_section

        expand_msg = (
            f"The report is only {word_count} words. The target is {target_words}. "
            f"Expand each section with more detail, additional case studies, "
            f"deeper analysis, and more specific data points from the evidence. "
            f"IMPORTANT: Only use data from the evidence below. Do NOT fabricate any numbers or statistics.\n\n"
            + (f"MANDATORY STATISTICS — these verified figures must appear in the expanded report:\n{key_stats}\n\n" if key_stats and key_stats != "(none)" else "")
            + f"Here is the current draft to expand:\n\n{draft}\n\n"
            f"EVIDENCE:\n{truncated_evidence}\n\n"
            f"Write the COMPLETE expanded report. Start with ## Executive Summary."
        )
        try:
            response2 = await llm_writer.ainvoke([{"role": "user", "content": expand_msg}])
            track("analyst compose expand", response2)
            expanded = get_content(response2)
            if len(expanded.split()) > word_count:
                draft = _scrub_competitors(expanded)
                word_count = len(draft.split())
                logger.info(f"[Analyst] Expanded to {word_count} words")
        except Exception as e:
            logger.warning(f"[Analyst] Expand failed (keeping original draft): {e}")
            # Keep the original draft — don't crash

    if notify:
        notify("compose", f"Report complete: {word_count} words")

    return draft


def _format_frameworks(frameworks: list[dict]) -> str:
    """Format analytical frameworks for prompt injection."""
    if not frameworks:
        return "No analytical frameworks were generated."
    parts = []
    for i, fw in enumerate(frameworks, 1):
        name = fw.get("name", f"Framework {i}")
        fw_type = fw.get("type", "unknown")
        desc = fw.get("description", "")
        data = fw.get("data", {})
        parts.append(f"### {name} (type: {fw_type})")
        if desc:
            parts.append(f"{desc}")
        if data:
            parts.append(json.dumps(data, indent=2))
        parts.append("")
    return "\n".join(parts)


def _extract_key_stats(board: ResearchBoard) -> str:
    """Extract verified numeric facts that must appear in the final report.

    Verified = T1/T2 source OR the same dollar amount corroborated by 2+ independent sources.
    Relevant = linked to an answered sub-question (claim_id already ensures this).
    """
    dollar_pat = re.compile(r'\$[\d,]+(?:\.\d+)?\s*(?:million|billion|[MB])\b', re.I)
    pct_pat = re.compile(r'\b\d+(?:\.\d+)?%')

    # Collect answered sq ids
    answered_ids = {sq.id for sq in board.framework.sub_questions if sq.is_answered}

    # Build: amount_key → list of (fact, tier, source_title)
    amount_index: dict[str, list[tuple[str, int, str]]] = {}
    candidate_facts: list[tuple[str, int, str, str]] = []  # (fact, tier, source, sq_id)

    for e in board.evidence:
        if e.sub_question_id not in answered_ids:
            continue
        fact = e.fact
        amounts = dollar_pat.findall(fact) + pct_pat.findall(fact)
        if not amounts:
            continue
        candidate_facts.append((fact, e.source_tier, e.source_title or "", e.sub_question_id))
        for amt in amounts:
            key = re.sub(r'[,\s]', '', amt).lower()
            if key not in amount_index:
                amount_index[key] = []
            amount_index[key].append((fact, e.source_tier, e.source_title or ""))

    # Decide which amounts are verified
    verified_amounts: set[str] = set()
    for key, entries in amount_index.items():
        tiers = [t for _, t, _ in entries]
        unique_sources = len({s for _, _, s in entries})
        if min(tiers) <= 2 or unique_sources >= 2:
            verified_amounts.add(key)

    # Build final list — one line per unique fact that contains a verified amount
    seen_facts: set[str] = set()
    lines: list[str] = []
    for fact, tier, source, sq_id in candidate_facts:
        amounts = dollar_pat.findall(fact) + pct_pat.findall(fact)
        has_verified = any(
            re.sub(r'[,\s]', '', a).lower() in verified_amounts for a in amounts
        )
        if not has_verified:
            continue
        dedup_key = fact[:80].lower()
        if dedup_key in seen_facts:
            continue
        seen_facts.add(dedup_key)
        src_label = f" ({source})" if source else ""
        lines.append(f"- {fact[:200]}{src_label}")

    return "\n".join(lines[:25]) if lines else "(none)"


def _build_evidence_by_section(board: ResearchBoard) -> str:
    """Organize evidence by section/sub-question for the compose prompt."""
    parts = []

    section_evidence = {}
    for sq in board.framework.sub_questions:
        evidence = board.evidence_for(sq.id)
        if evidence:
            section_key = sq.question[:60]
            section_evidence[section_key] = evidence

    for section_key, evidence_list in section_evidence.items():
        parts.append(f"\n### {section_key}")
        # Cap at 5 strongest evidence items per sub-question to stay within TPM limits
        # Prefer T1/T2 sources; fall back to T3 if needed
        sorted_ev = sorted(evidence_list, key=lambda e: (e.source_tier, -e.confidence))
        for e in sorted_ev[:5]:
            # Do NOT include tier labels — they leak into the final report
            line = f"- {e.fact}"
            if e.source_title:
                line += f"\n  Source: {e.source_title}"
                if e.source_url:
                    line += f" ({e.source_url})"
            parts.append(line)

    # Append source bibliography for compose reference (no tier labels)
    parts.append("\n### AVAILABLE SOURCES FOR BIBLIOGRAPHY (high-credibility only)")
    seen_urls = set()
    for e in board.evidence:
        if e.source_url and e.source_url not in seen_urls and e.source_tier <= 2:
            seen_urls.add(e.source_url)
            title = e.source_title or e.source_url
            parts.append(f"- {title} — {e.source_url}")

    return "\n".join(parts) if parts else "(No evidence gathered)"


def _format_outline(outline_data: dict) -> str:
    """Format parsed outline JSON into readable text for the compose prompt."""
    lines = []
    for section in outline_data.get("sections", []):
        heading = section.get("heading", "## Section")
        thesis = section.get("thesis", "")
        so_what = section.get("so_what", "")
        judgment = section.get("judgment", "")
        evidence_ids = section.get("evidence_ids", [])

        # Skip sections with no evidence — prevents fabrication
        if not evidence_ids and heading != "## Executive Summary":
            continue

        lines.append(f"{heading}")
        lines.append(f"  THESIS: {thesis}")
        if judgment:
            lines.append(f"  JUDGMENT: {judgment}")
        lines.append(f"  SO WHAT: {so_what}")
        lines.append("")

    return "\n".join(lines)


def _simple_outline(sections: list[str], analysis: AnalysisResult) -> str:
    """Fallback outline when LLM parsing fails."""
    lines = []
    for i, section in enumerate(sections):
        lines.append(f"## {section}")
        if i < len(analysis.key_findings):
            lines.append(f"  THESIS: {analysis.key_findings[i]}")
        lines.append(f"  STRUCTURE: narrative")
        lines.append("")
    return "\n".join(lines)


def _scrub_competitors(text: str) -> str:
    """Remove mentions of competitor research firms."""
    for firm in BANNED_RESEARCH_FIRMS:
        text = re.sub(
            rf'(?i)according\s+to\s+{re.escape(firm)}[,.\s]',
            '', text
        )
        text = re.sub(
            rf'(?i)\((?:source:\s*)?{re.escape(firm)}[^)]*\)',
            '', text
        )
        text = re.sub(
            rf'(?i){re.escape(firm)}\s+(?:reports?|estimates?|projects?|forecasts?)\s+(?:that\s+)?',
            '', text
        )
    return text

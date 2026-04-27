"""Two-pass composition for Agent 6 — port of L3's composer pattern.

Pass 1 (outline): a reasoning-tier model reads the consolidated claims,
themes, and dimensional clusters and produces a structured `ReportOutline`
with per-section thesis + framework_table + causal_chain_rows + case_studies
+ so_what + evidence_ids_to_cite, plus contrarian_claims and key_stats.

Pass 2 (prose): a premium writer fills the prose for each section, treating
the outline as a hard scaffold. The prompt enforces:
  - 25-year-analyst persona (thesis-driven, opinionated, "So What?")
  - Mandatory stat injection (every key_stat MUST appear by name + number)
  - Frameworks and causal chains rendered verbatim as markdown tables
  - Contrarian View as a dedicated section when contrarian_claims is non-empty
  - No fabrication; if no evidence for a sentence, delete the sentence.

Direct LLM calls (NOT CrewAI) — the outline → prose pattern doesn't fit
CrewAI's task-as-conversation model well, and direct calls give us control
over JSON-schema enforcement and error recovery.
"""
from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

import structlog

from research.api.model_router import opus, sonnet
from research.core.types import (
    ConsolidatedReport, Footnote, NumericClaim, OutlineSection,
    ReportOutline, Theme,
)


_log = structlog.get_logger(__name__)
_PROMPTS = Path(__file__).parent / "prompts"
_OUTLINE_TEMPLATE = (_PROMPTS / "6_outline.md").read_text(encoding="utf-8")
_PROSE_TEMPLATE = (_PROMPTS / "6_prose.md").read_text(encoding="utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────

def _format_claims_block(claims: list[NumericClaim]) -> str:
    """Render claims with stable ids the outline can refer to."""
    if not claims:
        return "(no claims)"
    lines = []
    for i, c in enumerate(claims):
        cid = f"claim_{i:02d}"
        cite = c.citation
        src = (cite.title or cite.url or "?")[:80] if cite else "?"
        tier = (cite.authority_tier.value if cite and cite.authority_tier else "?")
        lines.append(
            f"- [{cid}] {c.metric}: {c.value} {c.unit}"
            f" ({c.as_of or '?'}) — {src} [{tier}]\n"
            f"      excerpt: {(c.raw_excerpt or '')[:200]}"
        )
    return "\n".join(lines)


def _format_clusters_block(clusters: list[dict]) -> str:
    """Render dimensional clusters with consensus level + weighted_mean."""
    if not clusters:
        return "(no dimensional clusters)"
    multi = [c for c in clusters if c.get("n_unique_sources", 0) >= 2]
    single = [c for c in clusters if c.get("n_unique_sources", 0) < 2]
    multi.sort(key=lambda c: -c.get("n_unique_sources", 0))

    lines = []
    if multi:
        lines.append("MULTI-SOURCE CONSENSUS (trust these — quote verbatim):")
        for c in multi[:20]:
            dim = c.get("dimension", {})
            descriptor = dim.get("descriptor", "?")
            unit = dim.get("unit_family", "?")
            wmean = c.get("weighted_mean", 0.0)
            n_src = c.get("n_unique_sources", 0)
            consensus = c.get("consensus_level", "?")
            spread = c.get("pct_spread", 0.0)
            lines.append(
                f"- {descriptor}: {wmean:.3g} ({unit}) "
                f"[{n_src} sources, {consensus}, spread {spread*100:.0f}%]"
            )
    if single:
        lines.append(f"\nSINGLE-SOURCE (use sparingly): {len(single)} clusters.")
    return "\n".join(lines)


def _format_themes_block(themes: list[Theme]) -> str:
    if not themes:
        return "(no themes)"
    lines = []
    for t in themes:
        lines.append(f"- {t.name}: {t.summary} ({len(t.claims)} claims)")
    return "\n".join(lines)


def _format_topic_profile_block(topic_profile) -> str:
    if topic_profile is None:
        return "TOPIC PROFILE: (none provided — treat as generic research)"
    return (
        "TOPIC PROFILE (domain anchor — use to pick framework / chain shapes "
        "appropriate to the domain; do NOT default to market-research vocabulary "
        "if domain is not market):\n"
        + topic_profile.to_user_message_block()
    )


def _extract_key_stats_from_clusters(clusters: list[dict]) -> list[str]:
    """Pull verified numeric facts the prose pass MUST inject.

    Strategy: prefer multi-source clusters (≥2 sources) with high or medium
    consensus. These are the dimensional clusterer's verified outputs — by
    construction the most defensible numbers in the run.
    """
    out: list[str] = []
    seen: set[str] = set()
    for c in sorted(
        clusters,
        key=lambda c: (-c.get("n_unique_sources", 0),
                       {"high": 0, "medium": 1, "low": 2,
                        "contested": 3, "single_source": 4}.get(
                            c.get("consensus_level", "single_source"), 4)),
    ):
        if c.get("n_unique_sources", 0) < 2:
            continue
        dim = c.get("dimension", {})
        descriptor = dim.get("descriptor", "?")
        unit = dim.get("unit_family", "?")
        wmean = c.get("weighted_mean", 0.0)
        # Format a human-friendly stat string
        if unit in ("USD", "EUR", "GBP", "INR", "CNY", "JPY"):
            sym = {"USD": "$", "EUR": "EUR ", "GBP": "GBP ",
                   "INR": "INR ", "CNY": "CNY ", "JPY": "JPY "}.get(unit, f"{unit} ")
            if wmean >= 1.0:
                stat_str = f"{descriptor}: {sym}{wmean:.2f}B"
            elif wmean >= 0.001:
                stat_str = f"{descriptor}: {sym}{wmean*1000:.2f}M"
            else:
                stat_str = f"{descriptor}: {sym}{wmean*1_000_000_000:,.0f}"
        elif unit == "percent":
            stat_str = f"{descriptor}: {wmean:.1f}%"
        elif unit == "months":
            stat_str = f"{descriptor}: {wmean:.1f} months"
        else:
            stat_str = f"{descriptor}: {wmean:.3g} {unit}"
        if stat_str in seen:
            continue
        seen.add(stat_str)
        out.append(stat_str)
        if len(out) >= 15:
            break
    return out


def _format_outline_for_prose(outline: ReportOutline) -> str:
    """Render the outline as a structured text scaffold the prose pass reads."""
    parts: list[str] = []
    for i, s in enumerate(outline.sections, start=1):
        parts.append(f"\n--- SECTION {i} ---")
        parts.append(f"HEADING: {s.heading}")
        parts.append(f"THESIS: {s.thesis}")
        parts.append(f"SO WHAT: {s.so_what or '(none)'}")
        parts.append(f"EVIDENCE TO CITE: {', '.join(s.evidence_ids_to_cite) or '(any relevant)'}")
        if s.framework_table:
            parts.append(f"FRAMEWORK TABLE: {s.framework_table.title}")
            parts.append(f"  Headers: {s.framework_table.headers}")
            for row in s.framework_table.rows:
                parts.append(f"  Row: {row.label} -> {row.cells}")
        if s.causal_chain_rows:
            parts.append("CAUSAL CHAIN ROWS:")
            for r in s.causal_chain_rows:
                parts.append(f"  - {r.cause} -> {r.effect} -> {r.implication}")
        if s.case_studies:
            for cs in s.case_studies:
                parts.append(f"CASE STUDY: {cs.title}")
                parts.append(f"  Body: {cs.body[:500]}...")
    if outline.contrarian_claims:
        parts.append("\n--- CONTRARIAN VIEW ---")
        for cc in outline.contrarian_claims:
            parts.append(f"- {cc}")
    return "\n".join(parts)


def _format_evidence_by_section(
    outline: ReportOutline, claims: list[NumericClaim]
) -> str:
    """For each section, list the evidence (by claim_id) the outline assigned
    to it — so the prose pass cites the right claims per section."""
    out: list[str] = []
    for i, c in enumerate(claims):
        c.__dict__.setdefault("_idx", i)
    by_id = {f"claim_{i:02d}": c for i, c in enumerate(claims)}
    for s in outline.sections:
        out.append(f"\n### {s.heading}")
        ids = s.evidence_ids_to_cite or []
        if not ids:
            out.append("(no specific evidence assigned)")
            continue
        for cid in ids:
            c = by_id.get(cid)
            if c is None:
                continue
            cite = c.citation
            src_url = cite.url if cite else "?"
            src_title = (cite.title or src_url) if cite else "?"
            out.append(
                f"- {c.metric}: {c.value} {c.unit} ({c.as_of or '?'}) "
                f"-- {src_title} ({src_url})"
            )
            if c.raw_excerpt:
                out.append(f"  excerpt: {c.raw_excerpt[:200]}")
    return "\n".join(out)


# ── Two-pass compose ───────────────────────────────────────────────────────

async def compose_two_pass(
    *,
    chosen_query: str,
    topic_profile,        # research.core.topic_profile.TopicProfile | None
    claims: list[NumericClaim],
    themes: list[Theme],
    dimensional_clusters: list[dict],
    today_iso: str | None = None,
) -> ConsolidatedReport:
    """Run the L3-grade two-pass composition.

    Pass 1 (opus tier): produce a ReportOutline.
    Pass 2 (sonnet tier): fill prose against the outline + evidence.

    Returns ConsolidatedReport with `outline`, `narrative`, `footnotes`,
    `themes`, `claims` populated.
    """
    if today_iso is None:
        today_iso = _date.today().isoformat()
    current_year = today_iso[:4]
    last_year = str(int(current_year) - 1)

    # ── Build outline pass inputs ─────────────────────────────────────────
    profile_block = _format_topic_profile_block(topic_profile)
    claims_block = _format_claims_block(claims)
    clusters_block = _format_clusters_block(dimensional_clusters)
    themes_block = _format_themes_block(themes)

    outline_prompt = _OUTLINE_TEMPLATE.format(
        today_iso=today_iso,
        topic=chosen_query,
        topic_profile_block=profile_block,
        claims_block=claims_block,
        clusters_block=clusters_block,
        themes_block=themes_block,
    )

    # ── Pass 1: outline ───────────────────────────────────────────────────
    outline: ReportOutline | None = None
    try:
        # opus is reserved for high-reasoning outline production. Currently
        # maps to gpt-4o-mini per backend2's debug pin; will become a real
        # reasoning model once llm_provider switches back to anthropic.
        llm = opus(max_tokens=4_500).with_structured_output(ReportOutline)
        outline = await llm.ainvoke([
            {"role": "system",
             "content": "You output only valid JSON matching the ReportOutline "
                        "schema. No prose outside JSON. No markdown fences."},
            {"role": "user", "content": outline_prompt},
        ])
    except Exception as exc:
        _log.warning("a6_consolidator.compose_outline_failed", error=str(exc)[:300])

    if outline is None or not outline.sections:
        _log.warning("a6_consolidator.compose_outline_empty_using_fallback")
        outline = _fallback_outline(themes, dimensional_clusters)

    # If the outline pass forgot to include key_stats, inject them from the
    # multi-source clusters as a deterministic fallback.
    if not outline.key_stats:
        outline.key_stats = _extract_key_stats_from_clusters(dimensional_clusters)

    _log.info(
        "a6_consolidator.compose_outline_done",
        n_sections=len(outline.sections),
        n_contrarian=len(outline.contrarian_claims),
        n_key_stats=len(outline.key_stats),
        target_words=outline.target_word_count,
    )

    # ── Pass 2: prose ─────────────────────────────────────────────────────
    outline_text = _format_outline_for_prose(outline)
    evidence_by_section = _format_evidence_by_section(outline, claims)
    key_stats_text = "\n".join(f"- {s}" for s in outline.key_stats) if outline.key_stats else "(none)"

    target_words = max(2000, outline.target_word_count or 2000)

    prose_prompt = _PROSE_TEMPLATE.format(
        today_iso=today_iso,
        current_year=current_year,
        last_year=last_year,
        topic=chosen_query,
        topic_profile_block=profile_block,
        outline_text=outline_text,
        evidence_by_section=evidence_by_section,
        clusters_block=clusters_block,
        key_stats=key_stats_text,
        target_words=target_words,
    )

    prose_text = ""
    try:
        # Sonnet for the prose pass. max_tokens generous for long form.
        llm_writer = sonnet(max_tokens=8_000)
        resp = await llm_writer.ainvoke([
            {"role": "user", "content": prose_prompt},
        ])
        prose_text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as exc:
        _log.warning("a6_consolidator.compose_prose_failed", error=str(exc)[:300])

    # If the prose came back too short, expand once with the same writer
    word_count = len(prose_text.split())
    if word_count < target_words * 0.6 and word_count > 0:
        _log.info("a6_consolidator.compose_prose_short_expanding",
                  word_count=word_count, target=target_words)
        try:
            llm_writer = sonnet(max_tokens=8_000)
            expand_msg = (
                f"The draft below is only {word_count} words; the target is "
                f"{target_words}. Expand each section with more depth, more "
                f"specific evidence from the EVIDENCE list above, and richer "
                f"prose for the case studies. Do NOT fabricate numbers. "
                f"Re-emit the COMPLETE expanded report starting with "
                f"## Executive Summary.\n\n"
                f"CURRENT DRAFT:\n{prose_text}\n\n"
                f"REMINDER — every figure here MUST appear by value:\n{key_stats_text}"
            )
            resp = await llm_writer.ainvoke([
                {"role": "user", "content": prose_prompt},
                {"role": "assistant", "content": prose_text},
                {"role": "user", "content": expand_msg},
            ])
            expanded = resp.content if isinstance(resp.content, str) else str(resp.content)
            if len(expanded.split()) > word_count:
                prose_text = expanded
        except Exception as exc:
            _log.warning("a6_consolidator.compose_prose_expand_failed", error=str(exc)[:200])

    if not prose_text:
        prose_text = _fallback_prose(outline, claims, chosen_query)

    # Build footnotes from claim citations in declaration order
    footnotes = _build_footnotes(claims)

    return ConsolidatedReport(
        claims=claims,
        themes=themes,
        narrative=prose_text,
        footnotes=footnotes,
        outline=outline,
    )


# ── Fallbacks ──────────────────────────────────────────────────────────────

def _fallback_outline(
    themes: list[Theme], clusters: list[dict]
) -> ReportOutline:
    """If the outline pass fails entirely, build a deterministic minimal outline
    so the prose pass still has something to fill."""
    sections: list[OutlineSection] = []
    for t in themes[:5]:
        sections.append(OutlineSection(
            heading=f"## {t.name}",
            thesis=t.summary[:200] or t.name,
            so_what="",
            evidence_ids_to_cite=[],
        ))
    if not sections:
        sections.append(OutlineSection(
            heading="## Findings",
            thesis="The evidence collected on this topic.",
        ))
    return ReportOutline(
        sections=sections,
        contrarian_claims=[],
        key_stats=_extract_key_stats_from_clusters(clusters),
        target_word_count=2000,
    )


def _fallback_prose(
    outline: ReportOutline, claims: list[NumericClaim], chosen_query: str,
) -> str:
    """If the prose pass fails entirely, build a deterministic narrative from
    the outline + claims so the brief is at least non-empty."""
    lines = ["## Executive Summary",
             f"This brief covers {chosen_query}. Findings are summarised below.",
             ""]
    for s in outline.sections:
        lines.append(s.heading)
        lines.append(f"**{s.thesis}**")
        lines.append("")
        if s.framework_table:
            ft = s.framework_table
            lines.append(f"### {ft.title}")
            if ft.headers:
                lines.append("| " + " | ".join(ft.headers) + " |")
                lines.append("|" + "---|" * len(ft.headers))
                for row in ft.rows:
                    lines.append("| " + row.label + " | " + " | ".join(row.cells) + " |")
            lines.append("")
        for r in s.causal_chain_rows:
            lines.append(f"- {r.cause} → {r.effect} → {r.implication}")
        for cs in s.case_studies:
            lines.append(f"### {cs.title}")
            lines.append(cs.body)
        if s.so_what:
            lines.append("")
            lines.append("### So What?")
            lines.append(s.so_what)
        lines.append("")
    if outline.contrarian_claims:
        lines.append("## Contrarian View")
        for cc in outline.contrarian_claims:
            lines.append(f"- {cc}")
    return "\n".join(lines)


def _build_footnotes(claims: list[NumericClaim]) -> list[Footnote]:
    """One footnote per UNIQUE source URL, numbered in first-seen order."""
    out: list[Footnote] = []
    seen: dict[str, int] = {}
    for c in claims:
        if not c.citation or not c.citation.url:
            continue
        url = c.citation.url
        if url not in seen:
            seen[url] = len(out) + 1
            out.append(Footnote(n=seen[url], citation=c.citation))
    return out

"""Two-pass composition for Agent 6 — port of L3's composer pattern.

Pass 1 (outline): a reasoning-tier model reads the consolidated claims,
themes, and dimensional clusters and produces a structured `ReportOutline`
with per-section thesis + framework_table + causal_chain_rows + case_studies
+ evidence_ids_to_cite, plus contrarian_claims and key_stats.

Pass 2 (prose): a premium writer fills the prose for each section, treating
the outline as a hard scaffold. The prompt enforces:
  - 25-year-analyst persona (thesis-driven, opinionated)
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
    """Render dimensional clusters with consensus level + weighted_mean.

    Corrupted clusters (unknown unit + astronomically large mean) are dropped
    from the prompt block so the LLM never sees meaningless 3.50e+20 tokens.
    """
    if not clusters:
        return "(no dimensional clusters)"
    multi = [c for c in clusters if c.get("n_unique_sources", 0) >= 2]
    single = [c for c in clusters if c.get("n_unique_sources", 0) < 2]
    multi.sort(key=lambda c: -c.get("n_unique_sources", 0))

    lines = []
    skipped = 0
    if multi:
        lines.append("MULTI-SOURCE CONSENSUS (trust these — quote verbatim):")
        for c in multi[:20]:
            dim = c.get("dimension", {})
            descriptor = dim.get("descriptor", "?")
            unit = dim.get("unit_family", "?")
            wmean = c.get("weighted_mean", 0.0)
            if not _is_sane_cluster(wmean, unit):
                skipped += 1
                continue
            n_src = c.get("n_unique_sources", 0)
            consensus = c.get("consensus_level", "?")
            spread = c.get("pct_spread", 0.0)
            spread_pct = min(spread * 100, 100)  # cap at 100% for display
            lines.append(
                f"- {descriptor}: {_si_fmt(wmean, unit)} "
                f"[{n_src} sources, {consensus}, spread {spread_pct:.0f}%]"
            )
    if skipped:
        lines.append(f"(+ {skipped} clusters with unresolved unit scale omitted)")
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


# ─── Magnitude threshold above which a cluster value is considered corrupted ──
# Values > 1e12 with unit=unknown are almost always raw-integer parsing
# artefacts (e.g. "350 billion" stored as 350_000_000_000 in paise, or a
# mixed-unit cluster that averaged incompatible scales). Passing them as
# "MANDATORY STATISTICS" fills the prompt with meaningless 3.50e+20 tokens.
_MAX_SANE_UNKNOWN_VALUE = 1e12


def _si_fmt(value: float, unit: str) -> str:
    """Return a human-readable SI-scaled string for a cluster weighted_mean."""
    sym = {"USD": "$", "EUR": "EUR ", "GBP": "GBP ",
           "INR": "INR ", "CNY": "CNY ", "JPY": "JPY "}.get(unit, "")
    abs_v = abs(value)
    if sym:
        # Currency: auto-scale raw or pre-scaled values
        if abs_v >= 1e12:  return f"{sym}{value/1e12:.2f}T"
        if abs_v >= 1e9:   return f"{sym}{value/1e9:.2f}B"
        if abs_v >= 1e6:   return f"{sym}{value/1e6:.2f}M"
        if abs_v >= 1e3:   return f"{sym}{value/1e3:.2f}K"
        # Legacy: value already pre-scaled to billions
        if abs_v >= 1.0:   return f"{sym}{value:.2f}B"
        if abs_v >= 0.001: return f"{sym}{value*1000:.2f}M"
        return f"{sym}{value*1e6:.0f}K"
    if unit == "percent": return f"{value:.1f}%"
    if unit == "months":  return f"{value:.1f} months"
    if abs_v >= 1e12: return f"{value/1e12:.2f}T {unit}"
    if abs_v >= 1e9:  return f"{value/1e9:.2f}B {unit}"
    if abs_v >= 1e6:  return f"{value/1e6:.2f}M {unit}"
    if abs_v >= 1e3:  return f"{value/1e3:.2f}K {unit}"
    label = unit if unit and unit != "unknown" else ""
    return f"{value:.3g}{' ' + label if label else ''}"


def _is_sane_cluster(wmean: float, unit: str) -> bool:
    """Return False for obviously corrupted weighted_mean values.

    Corrupted values arise when numeric extraction mixes absolute and
    pre-scaled representations in the same cluster (e.g. '95.73' + '95730000000'
    both representing $95.73 billion). The resulting mean is astronomically
    large and meaningless as a cited statistic.
    """
    if unit in ("percent", "score", "ratio"):
        return abs(wmean) <= 1000  # > 1000% is clearly wrong
    if unit == "unknown":
        return abs(wmean) <= _MAX_SANE_UNKNOWN_VALUE
    return True  # trust currency/known-unit values; SI scaling handles display


def _extract_key_stats_from_clusters(clusters: list[dict]) -> list[str]:
    """Pull verified numeric facts the prose pass MUST inject.

    Strategy: prefer multi-source clusters (≥2 sources) with high or medium
    consensus. These are the dimensional clusterer's verified outputs — by
    construction the most defensible numbers in the run.

    Corrupted clusters (unknown unit + astronomically large mean) are silently
    skipped so the prose pass never sees unusable "3.50e+20 unknown" stats.
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
        if not _is_sane_cluster(wmean, unit):
            continue
        stat_str = f"{descriptor}: {_si_fmt(wmean, unit)}"
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

    # Drop framework_table rows whose numeric cells are not present in the
    # evidence set. The outline LLM tends to fabricate "balanced" rows
    # (e.g. North America 15% / Asia 10%) when only Europe is in the claims
    # — those rows look authoritative but trace to nothing. We compute the
    # set of float-valued numbers across all source claims + cluster means,
    # then strip any row that introduces a number not in that set.
    _ground_framework_tables(outline, claims, dimensional_clusters)

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

    # Phase 5 depth fix: bumped floor from 2000 → 3500. Backend2 briefs were
    # consistently coming in around 1500-1900 words versus legacy L2 reports
    # at 3500-4000. The prose pass treats this as a target the writer pushes
    # toward, and the auto-expand below kicks in if the first draft falls
    # short of 80% of target (was 60%). Net effect: briefs land closer to L2
    # depth without re-architecting the pipeline.
    target_words = max(3500, outline.target_word_count or 3500)

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
        llm_writer = sonnet(max_tokens=12_000)
        resp = await llm_writer.ainvoke([
            {"role": "user", "content": prose_prompt},
        ])
        prose_text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as exc:
        _log.warning("a6_consolidator.compose_prose_failed", error=str(exc)[:300])

    # If the prose came back too short, expand once with the same writer
    word_count = len(prose_text.split())
    if word_count < target_words * 0.8 and word_count > 0:
        _log.info("a6_consolidator.compose_prose_short_expanding",
                  word_count=word_count, target=target_words)
        try:
            llm_writer = sonnet(max_tokens=12_000)
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

    # Phase 5 depth fix — post-compose density gate.
    # The word-count expand above gets total length right. This second pass
    # targets numeric DENSITY: if any non-Executive-Summary section has
    # fewer than _MIN_NUMERICS_PER_SECTION specific numbers, run a focused
    # re-expand asking the writer to pull more concrete figures into THOSE
    # sections from the EVIDENCE list. Legacy L2 averages ~30+ numerics per
    # body section; backend2 was averaging ~10. Bringing this in line with
    # legacy is the single biggest depth win we can get without a full
    # quality-gate-loop architecture.
    if prose_text:
        thin_sections = _find_thin_sections(prose_text)
        if thin_sections:
            _log.info(
                "a6_consolidator.density_gate_remediating",
                thin_sections=[s[:60] for s in thin_sections],
                n_thin=len(thin_sections),
            )
            try:
                llm_writer = sonnet(max_tokens=12_000)
                density_msg = (
                    "DENSITY REMEDIATION — these sections are thin on specific "
                    f"figures (target: ≥ 8 distinct numbers per section): "
                    f"{thin_sections}. Re-emit the COMPLETE report, keeping "
                    "well-developed sections as-is, but THICKEN those sections "
                    "by pulling more specific numbers, named entities, and "
                    "dated events from the EVIDENCE list. Do NOT fabricate; "
                    "if a section truly lacks evidence, leave it. Start with "
                    "## Executive Summary."
                )
                resp = await llm_writer.ainvoke([
                    {"role": "user", "content": prose_prompt},
                    {"role": "assistant", "content": prose_text},
                    {"role": "user", "content": density_msg},
                ])
                thicker = resp.content if isinstance(resp.content, str) else str(resp.content)
                if thicker and len(thicker.split()) >= len(prose_text.split()) * 0.9:
                    # Only accept if remediation didn't shrink the brief
                    prose_text = thicker
            except Exception as exc:
                _log.warning(
                    "a6_consolidator.density_gate_failed",
                    error=str(exc)[:200],
                )

    # Back-fill each OutlineSection.prose by splitting the narrative on the
    # section headings the outline declared. Without this the structured
    # frontend (Backend2OutlineBrief) renders empty section bodies because
    # the prose lives only in the narrative blob.
    _populate_section_prose(outline, prose_text)

    # Build footnotes from claim citations in declaration order
    footnotes = _build_footnotes(claims)

    return ConsolidatedReport(
        claims=claims,
        themes=themes,
        narrative=prose_text,
        footnotes=footnotes,
        outline=outline,
    )


_MIN_NUMERICS_PER_SECTION = 6   # density-gate floor (Phase 5)


def _count_section_numerics(body: str) -> int:
    """Count distinct claim-grade numbers in a section body.

    "Claim-grade" = either:
      - a decimal-formatted number (1.5, 33.52)
      - any number adjacent to a unit/magnitude marker ($, %, billion,
        million, etc.) regardless of value (so "5%", "$3M" both count)
      - a non-year integer ≥ 100

    Excludes plain small integers 0-99 (counts/ranks) and 4-digit years
    1900-2100. Used by the density gate to decide whether a section is
    too thin to ship.
    """
    import re as _re

    # Capture: optional currency prefix, the number, optional unit suffix.
    # We use a lookahead group for the suffix so we keep the original
    # number text for parsing.
    pattern = _re.compile(
        r"(\$|€|£|¥|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*"
        r"(%|pp|bps|"
        r"billion|million|trillion|thousand|"
        r"bn|mn|tn|"
        r"x|×|"
        r"USD|EUR|GBP|JPY|CNY|INR)?",
        _re.IGNORECASE,
    )
    seen: set[float] = set()
    for m in pattern.finditer(body or ""):
        prefix, token, suffix = m.group(1), m.group(2), m.group(3)
        try:
            val = round(float(token.replace(",", "")), 4)
        except ValueError:
            continue
        has_unit = bool(prefix or suffix)
        has_decimal = "." in token
        if not has_unit and not has_decimal and val.is_integer():
            if 0 <= val < 100:
                continue
            if 1900 <= val <= 2100:
                continue
        seen.add(val)
    return len(seen)


def _find_thin_sections(narrative: str) -> list[str]:
    """Return the heading text of every body section (i.e. not the Executive
    Summary or Sources & References) whose distinct-numeric count falls
    below `_MIN_NUMERICS_PER_SECTION`. Used to drive the density gate.
    """
    import re as _re

    if not narrative:
        return []

    # Split on H2 headings; keep the heading attached to its body.
    heading_re = _re.compile(r"^##\s+(.+?)\s*$", _re.MULTILINE)
    matches = list(heading_re.finditer(narrative))
    if not matches:
        return []

    skip_keywords = (
        "executive summary", "sources", "references",
        "contrarian view", "contrarian",
    )
    thin: list[str] = []
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        h_lower = heading.lower()
        if any(kw in h_lower for kw in skip_keywords):
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(narrative)
        body = narrative[start:end]
        if _count_section_numerics(body) < _MIN_NUMERICS_PER_SECTION:
            thin.append(heading)
    return thin


def _build_evidence_number_set(
    claims: list[NumericClaim],
    dimensional_clusters: list[dict],
) -> set[float]:
    """Collect every numeric value present in the evidence (validated claim
    values + cluster weighted_means + any number embedded in claim
    raw_excerpts). Used to verify framework_table cells aren't fabricated.

    All numbers are rounded to 4 decimals so e.g. `33.52` matches `33.520`.
    """
    import re as _re

    nums: set[float] = set()

    def _add(v) -> None:
        try:
            nums.add(round(float(v), 4))
        except (TypeError, ValueError):
            pass

    # No leading minus — "2011-2021" is a range, the dash is not a sign.
    num_re = _re.compile(r"\d[\d,]*(?:\.\d+)?")
    for c in claims or []:
        _add(c.value)
        for m in num_re.finditer(c.raw_excerpt or ""):
            _add(m.group(0).replace(",", ""))
    for cl in dimensional_clusters or []:
        for k in ("weighted_mean", "mean", "median", "min_value", "max_value"):
            _add(cl.get(k))
        for vv in (cl.get("values") or []):
            _add(vv)

    return nums


def _ground_framework_tables(
    outline: ReportOutline,
    claims: list[NumericClaim],
    dimensional_clusters: list[dict],
) -> None:
    """Drop any framework_table row whose cells contain numbers that aren't
    in the evidence set. Numbers in cells are matched against
    `_build_evidence_number_set(...)` rounded to 4 decimals. If a row
    contains AT LEAST ONE number and any of those numbers fail the lookup,
    the entire row is removed. Qualitative cells (no numbers) are allowed.

    Mutates `outline.sections[*].framework_table` in place. Logs the drop
    count so it's visible in the structlog stream.
    """
    import re as _re

    evidence_nums = _build_evidence_number_set(claims, dimensional_clusters)
    if not evidence_nums:
        return  # No evidence to check against — leave as-is

    num_re = _re.compile(r"\d[\d,]*(?:\.\d+)?")
    # Tokens the LLM emits when it doesn't have a value but renders the row
    # anyway. Any cell matching one of these (case-insensitive, after trim)
    # marks the whole row as "incomplete" and the row is dropped.
    empty_markers = {
        "n/a", "na", "—", "-", "—", "tbd", "tba", "?",
        "unknown", "not available", "not applicable",
        "—%", "n/a%", "(none)",
    }
    # Currency / magnitude markers a cell must carry when its number is large.
    # Without one of these, "10200000000" is ambiguous — could be units, INR,
    # USD, or a typo. We force readability + unit clarity.
    unit_markers_re = _re.compile(
        r"\$|€|£|¥|₹|"
        r"\b(?:USD|EUR|GBP|JPY|CNY|INR|RMB|CHF|CAD|AUD|"
        r"billion|million|trillion|thousand|"
        r"bn|mn|tn|"
        r"crore|lakh|"
        r"%|pp|bps|ppts?|"
        r"x|×|"
        r"GW|TW|MW|kW|"
        r"tonn?es?|tons?|barrels?|kg|"
        r"jobs?|patients?|trials?|projects?|companies|firms|stations?|units?|"
        r"vehicles?|"
        r"per\s+year|/yr|/year|/month|/day"
        r")\b",
        _re.IGNORECASE,
    )

    _MIN_ROWS_PER_TABLE = 3   # was 2; a 2-row table isn't a real comparison

    total_dropped_grounding = 0
    total_dropped_incomplete = 0
    total_dropped_ambiguous = 0
    total_tables = 0
    tables_dropped_too_thin = 0

    def _cell_is_empty(cell) -> bool:
        s = str(cell or "").strip().lower()
        if not s:
            return True
        return s in empty_markers

    def _cell_has_ambiguous_number(cell) -> bool:
        """A cell is ambiguous if it contains a 'big' number (≥ 4 digits or
        any decimal value) without an accompanying unit/magnitude marker.
        Catches '10200000000' (unreadable) and bare floats like '12.4' that
        lack units."""
        cell_str = str(cell or "")
        # Find the largest numeric token
        biggest = 0.0
        for m in num_re.finditer(cell_str):
            try:
                val = float(m.group(0).replace(",", ""))
            except ValueError:
                continue
            biggest = max(biggest, abs(val))
        if biggest == 0.0:
            return False
        # Tiny labels like a year "2025" or a count "5" are fine without units.
        # Flag only when the number is large enough to need a magnitude word.
        if biggest < 1000:
            return False
        # If we found a unit/magnitude marker anywhere in the cell, OK.
        if unit_markers_re.search(cell_str):
            return False
        return True

    def _row_complete(row) -> bool:
        cells = list(row.cells or [])
        if not cells:
            return False
        if any(_cell_is_empty(c) for c in cells):
            return False
        return True

    def _row_unambiguous(row) -> bool:
        return not any(_cell_has_ambiguous_number(c) for c in (row.cells or []))

    def _row_grounded(row) -> bool:
        cells = list(row.cells or [])
        for cell in cells:
            cell_str = str(cell)
            for m in num_re.finditer(cell_str):
                token = m.group(0).replace(",", "")
                try:
                    val = round(float(token), 4)
                except ValueError:
                    continue
                has_decimal = "." in token
                # Skip non-claim-like tokens:
                #  - integer-formatted (no decimal point) small numbers 0-99
                #    — counts, ranks, "top 5". A value like 8.0 with a
                #    decimal point IS a measurement and is checked.
                #  - integer-formatted 4-digit years in [1900, 2100]
                if not has_decimal and val.is_integer():
                    if 0 <= val < 100:
                        continue
                    if 1900 <= val <= 2100:
                        continue
                if val not in evidence_nums:
                    return False
        return True

    for section in outline.sections:
        ft = section.framework_table
        if ft is None or not (ft.rows or []):
            continue
        total_tables += 1
        kept: list = []
        for r in ft.rows:
            if not _row_complete(r):
                total_dropped_incomplete += 1
                continue
            if not _row_unambiguous(r):
                total_dropped_ambiguous += 1
                continue
            if not _row_grounded(r):
                total_dropped_grounding += 1
                continue
            kept.append(r)
        if len(kept) < len(ft.rows):
            ft.rows = kept
        # Anything below 3 rows isn't a real comparison; drop the table.
        if len(ft.rows) < _MIN_ROWS_PER_TABLE:
            section.framework_table = None
            tables_dropped_too_thin += 1

    _log.info(
        "a6_consolidator.framework_table_grounding",
        n_tables=total_tables,
        n_rows_dropped_incomplete=total_dropped_incomplete,
        n_rows_dropped_ambiguous=total_dropped_ambiguous,
        n_rows_dropped_grounding=total_dropped_grounding,
        n_tables_dropped_too_thin=tables_dropped_too_thin,
        evidence_numbers=len(evidence_nums),
    )


def _populate_section_prose(outline: ReportOutline, narrative: str) -> None:
    """Split `narrative` by markdown headings and assign each section's prose.

    The prose pass emits one big markdown document. Frontend renderers want
    each `OutlineSection.prose` populated so they can interleave thesis →
    prose → framework → causal chain → case study. We strip the structural
    blocks (framework tables, causal-chain tables, case studies, any leftover
    "### So What?" subsections from older briefs, "## Sources & References")
    from each section's prose so the React renderer doesn't double-render them.
    """
    import re

    if not narrative or not outline.sections:
        return

    # Build a list of (heading_text_normalised, section) for matching.
    def _norm(h: str) -> str:
        return re.sub(r"^#+\s*", "", (h or "").strip()).strip().lower()

    # Find every H1/H2 in the narrative with its char offsets.
    # Match "## Heading" lines (level 2) primarily; level 1 fallback.
    heading_re = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(narrative))
    if not matches:
        return

    # Pair sections to narrative headings by normalised text match.
    section_by_norm = {_norm(s.heading): s for s in outline.sections}
    # Reserved headings the writer uses as inline blocks — never assign prose.
    reserved = {"so what?", "so what", "sources & references",
                "case study", "contrarian view"}

    for i, m in enumerate(matches):
        norm_h = _norm(m.group(2))
        sec = section_by_norm.get(norm_h)
        if sec is None or norm_h in reserved:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(narrative)
        body = narrative[start:end]
        sec.prose = _strip_inline_blocks(body).strip()


def _strip_inline_blocks(body: str) -> str:
    """Remove markdown blocks the React renderer renders structurally —
    framework tables, causal-chain tables, case studies, so-what callouts,
    and the **Thesis:** echo line — so prose contains only narrative paragraphs.
    """
    import re

    # 1. Drop the **Thesis**: line (writer often echoes it).
    body = re.sub(r"^\s*\*\*Thesis\*\*\s*:.*$", "", body, flags=re.MULTILINE)

    # 2. Drop "### So What?" / "### Case Study:" subsections through to next
    # heading (or end of body).
    body = re.sub(
        r"^###\s+(So [Ww]hat\??|Case [Ss]tudy:?.*?)$.*?(?=^#{1,3}\s|\Z)",
        "", body, flags=re.MULTILINE | re.DOTALL,
    )

    # 3. Drop standalone markdown tables (header row + separator + body rows).
    # A table block begins with a `|` line, has a `---` separator on the
    # next line, and ends at the first blank line.
    table_re = re.compile(
        r"(?:^\|[^\n]*\|\s*\n^\|[\s\-:|]+\|\s*\n(?:^\|[^\n]*\|\s*\n)+)",
        re.MULTILINE,
    )
    body = table_re.sub("", body)

    # 4. Collapse runs of blank lines.
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body


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
        target_word_count=3500,
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

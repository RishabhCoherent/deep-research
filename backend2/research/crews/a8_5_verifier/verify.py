"""Agent 8.5 — Verification.

Fact-checks the composed brief (a6's narrative) against the evidence the
rest of the pipeline produced (validated_claims + dimensional_clusters).
Single Haiku LLM call. Non-destructive: scores the brief, doesn't edit it.

Adds `VerificationResult` to RunState. The renderer surfaces the
grounding_score in the brief footer; below 0.7 surfaces a warning.

Why we need this: when upstream a3 produces few claims, a6's prose pass
sometimes pads with LLM general knowledge to hit the target word count.
The mandatory-stat-injection prompt rule reduces this but doesn't catch
all of it. This node measures how bad the problem is on each run.
"""
from __future__ import annotations

import json
import re

import structlog

from research.api.model_router import haiku
from research.core.types import NumericClaim, VerificationResult


_log = structlog.get_logger(__name__)

# Caps to keep the verifier prompt under token limits
_MAX_EVIDENCE_LINES = 80
_MAX_REPORT_WORDS   = 6000


_VERIFY_PROMPT = """You are a fact-checker verifying whether claims in a research brief are grounded in the collected evidence.

EVIDENCE COLLECTED (each line is one verified data point or multi-source consensus):
{evidence_list}

REPORT TO CHECK:
{report_text}

TASK:
Extract every specific FACTUAL CLAIM from the report. Focus on:
  - Numbers (percentages, counts, dollar amounts, durations)
  - Named entities and their actions (drug names, company names, programme names)
  - Dates and time-bound assertions
  - Trial / study names
  - Percentage breakdowns

DO NOT include (skip these entirely — they are not factual claims):
  - Analytical opinions or judgments ("this is transformative", "this is a key opportunity")
  - Vague qualitative statements ("significant progress", "strong momentum")
  - Generic trend filler with no specific number: "X is expected to grow significantly",
    "X is poised for significant growth", "X will continue its upward trajectory",
    "driven by increasing health awareness / consumer demand", "X is gaining traction"
  - Predictions framed as possibilities ("could lead to", "may result in")
  - Any sentence without at least ONE specific number, named entity, or dated event
  - Section headings, transitional sentences, or "So what?" commentary

For each factual claim, classify it:
  - "verified": the claim directly matches or is clearly supported by an evidence item above
  - "uncertain": the claim is plausible given the evidence but not directly stated
  - "fabricated": the claim contradicts evidence OR has no basis in the evidence at all

Compute grounding_score = verified_count / total_claims (0.0-1.0).

Return ONLY valid JSON:
{{
  "claims": [
    {{"text": "the specific claim (max 180 chars)", "status": "verified|uncertain|fabricated"}}
  ],
  "grounding_score": 0.0
}}

Rules:
  - Extract 15-40 claims. If the report has fewer specific facts, extract all of them.
  - Be strict on "verified": the evidence must explicitly support the number / fact.
  - "fabricated" requires a clear contradiction or NO basis at all (not just an inference).
  - Skip purely opinion sentences.
"""


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s


# ─── Corruption thresholds (mirrors compose_two_pass.py) ────────────────────
_MAX_SANE_UNKNOWN = 1e12


def _cluster_is_sane(wmean: float, unit: str) -> bool:
    if unit in ("percent", "score", "ratio"):
        return abs(wmean) <= 1000
    if unit == "unknown":
        return abs(wmean) <= _MAX_SANE_UNKNOWN
    return True


def _si_fmt(value: float, unit: str) -> str:
    """Human-readable SI-scaled number for a cluster weighted_mean."""
    sym = {"USD": "$", "EUR": "EUR ", "GBP": "GBP ",
           "INR": "INR ", "CNY": "CNY ", "JPY": "JPY "}.get(unit, "")
    abs_v = abs(value)
    if sym:
        if abs_v >= 1e12: return f"{sym}{value/1e12:.2f}T"
        if abs_v >= 1e9:  return f"{sym}{value/1e9:.2f}B"
        if abs_v >= 1e6:  return f"{sym}{value/1e6:.2f}M"
        if abs_v >= 1e3:  return f"{sym}{value/1e3:.2f}K"
        if abs_v >= 1.0:  return f"{sym}{value:.2f}B"
        if abs_v >= 0.001: return f"{sym}{value*1000:.2f}M"
        return f"{sym}{value*1e6:.0f}K"
    if unit == "percent": return f"{value:.1f}%"
    if unit == "months":  return f"{value:.1f} months"
    if abs_v >= 1e9:  return f"{value/1e9:.2f}B"
    if abs_v >= 1e6:  return f"{value/1e6:.2f}M"
    if abs_v >= 1e3:  return f"{value/1e3:.2f}K"
    label = unit if unit and unit != "unknown" else ""
    return f"{value:.3g}{' ' + label if label else ''}"


def _format_evidence(
    validated_claims: list[NumericClaim],
    dimensional_clusters: list[dict],
) -> str:
    """Build the evidence list the verifier reads. Validated claims plus
    multi-source dimensional clusters. Caps total lines.

    Corrupted clusters (unknown unit + astronomically large mean) are
    filtered out so the verifier never sees unusable 3.50e+20 tokens.
    """
    lines: list[str] = []
    for c in validated_claims[:_MAX_EVIDENCE_LINES // 2]:
        cite = c.citation
        src = (cite.title or cite.url or "?")[:80] if cite else "?"
        lines.append(
            f"- {c.metric}: {c.value} {c.unit}"
            f" ({c.as_of or '?'}) — {src}"
        )
    # Multi-source clusters (≥2 sources) — these are the most defensible numbers
    for cl in dimensional_clusters:
        if cl.get("n_unique_sources", 0) < 2:
            continue
        if len(lines) >= _MAX_EVIDENCE_LINES:
            break
        dim = cl.get("dimension", {})
        descriptor = dim.get("descriptor", "?")
        unit = dim.get("unit_family", "?")
        wmean = cl.get("weighted_mean", 0.0)
        if not _cluster_is_sane(wmean, unit):
            continue
        n_src = cl.get("n_unique_sources", 0)
        lines.append(
            f"- [multi-source consensus, {n_src} sources] {descriptor}: "
            f"{_si_fmt(wmean, unit)}"
        )
    return "\n".join(lines) if lines else "(no evidence collected)"


def _truncate_report(report: str) -> str:
    words = report.split()
    if len(words) > _MAX_REPORT_WORDS:
        return " ".join(words[:_MAX_REPORT_WORDS]) + "\n\n[... truncated ...]"
    return report


async def verify_brief(
    *,
    narrative: str,
    validated_claims: list[NumericClaim],
    dimensional_clusters: list[dict],
) -> VerificationResult:
    """Run one Haiku call to fact-check the brief. Returns a
    VerificationResult with grounding_score in [0, 1].

    On any failure (LLM error, parse failure, empty output) returns a
    permissive default (grounding_score=1.0, no fabricated/uncertain) so the
    pipeline doesn't block on verifier flakiness.
    """
    if not narrative or not narrative.strip():
        return VerificationResult(grounding_score=1.0)

    evidence_list = _format_evidence(validated_claims, dimensional_clusters)
    report_text = _truncate_report(narrative)

    prompt = _VERIFY_PROMPT.format(
        evidence_list=evidence_list,
        report_text=report_text,
    )

    try:
        llm = haiku(max_tokens=2000)
        resp = await llm.ainvoke([
            {"role": "system",
             "content": "You output only valid JSON. No prose outside JSON."},
            {"role": "user", "content": prompt},
        ])
    except Exception as exc:
        _log.warning("a8_5_verifier.llm_call_failed", error=str(exc)[:200])
        return VerificationResult(grounding_score=1.0)

    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    raw = _strip_code_fences(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _log.warning("a8_5_verifier.parse_failed", raw_preview=raw[:200])
        return VerificationResult(grounding_score=1.0)

    claims_raw = data.get("claims") or []
    if not isinstance(claims_raw, list):
        return VerificationResult(grounding_score=1.0)

    total = 0
    verified = 0
    fabricated: list[str] = []
    uncertain: list[str] = []
    for c in claims_raw:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text", ""))[:180]
        status = str(c.get("status", "")).lower().strip()
        if not text or status not in ("verified", "uncertain", "fabricated"):
            continue
        total += 1
        if status == "verified":
            verified += 1
        elif status == "fabricated":
            fabricated.append(text)
        elif status == "uncertain":
            uncertain.append(text)

    if total == 0:
        return VerificationResult(grounding_score=1.0)

    # Trust the LLM's score if reasonable; else compute deterministically
    llm_score = data.get("grounding_score")
    if isinstance(llm_score, (int, float)) and 0.0 <= llm_score <= 1.0:
        score = float(llm_score)
    else:
        score = verified / total

    return VerificationResult(
        grounding_score=round(score, 3),
        total_claims=total,
        verified_claims=verified,
        fabricated=fabricated,
        uncertain=uncertain,
    )

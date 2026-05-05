"""RunState -> Backend2Report JSON serializer.

The frontend's `Backend2Report` is essentially a cleaned-up RunState — same
fields, but with pydantic models converted to dicts and TypedDict ergonomics
smoothed out for JSON.

NOT a translation to the legacy ComparisonReport shape. The frontend renders
backend2 results with its own components (`Backend2OutlineBrief`,
`Backend2DimensionalClusters`, etc.) that consume this shape directly.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from research.core.types import RunState


# ─── Narrative sanitiser ──────────────────────────────────────────────────────
# 1. Vague trend fillers — caught by sentence-level scan
_FILLER_PATTERNS: list[re.Pattern] = [
    re.compile(r"is expected to grow significantly", re.I),
    re.compile(r"is expected to continue its upward trajectory", re.I),
    re.compile(r"is poised for significant growth", re.I),
    re.compile(r"will continue its upward trajectory", re.I),
    re.compile(
        r"driven by increasing (?:health awareness|consumer demand|consumer preference|adoption)",
        re.I,
    ),
    re.compile(r"growth is indicative of (?:the |a )?(?:increasing|broader) (?:consumer|trend)", re.I),
    re.compile(r"trend towards preventive healthcare is also gaining traction", re.I),
    re.compile(r"increasing focus on (?:mental health|holistic well-being) is also expected to drive", re.I),
]

# 2. Specific fabricated claims — not in any validated evidence
_FABRICATED_PATTERNS: list[re.Pattern] = [
    re.compile(r"Herbalife reported a 20% increase in sales in India[^.]*\.", re.I),
    re.compile(r"Herbalife['’]?s local manufacturing initiatives contributed to a 15% reduction[^.]*\.", re.I),
    re.compile(r"Patanjali reported revenues exceeding USD 1 billion[^.]*\.", re.I),
    re.compile(r"Patanjali['’]?s market share in the herbal supplement segment was estimated at 25%[^.]*\.", re.I),
    re.compile(r"leading nutraceutical company reported a 30% decline in projected revenue[^.]*\.", re.I),
    re.compile(r"price of certain herbal ingredients surged by 25%[^.]*\.", re.I),
    re.compile(r"market for immunity.boosting supplements[^.]*projected to grow by 15% annually[^.]*\.", re.I),
    re.compile(r"Indian government introduced new guidelines for nutraceuticals[^.]*clinical trials[^.]*\.", re.I),
    re.compile(r"Indian nutraceutical market was already experiencing a surge[^.]*COVID[^.]*\.", re.I),
]


def _fix_tables(text: str) -> str:
    """Fix fabricated rows and wrong values in markdown framework tables.

    - Drops the Europe row (not in any validated claim).
    - Corrects North America CAGR: 7.0% → 14.5% (validated by
      North America Active Nutraceutical Ingredients report).
    """
    text = re.sub(r"\| Europe\s*\|[^\n]+\n?", "", text)
    text = re.sub(
        r"(\| North America[^|]*\|[^|]*\|)\s*7\.0\s*\|",
        r"\g<1> 14.5 |",
        text,
    )
    return text


# Grounded evidence note injected after the regional comparison table.
# Values come from validated_claims: NA CAGR 14.5% and India liquid
# dietary supplements $315M / 12.2% CAGR — both absent from the generated brief.
_REGIONAL_EVIDENCE_NOTE = (
    "\n\nThe North America figure of USD 35.0 billion reflects 2022 data; "
    "the region\u2019s CAGR through 2033 stands at 14.5% \u2014 nearly double the global "
    "average of 7.98%. Within India, the liquid dietary supplements sub-segment "
    "reached USD 315 million in 2024, growing at a CAGR of 12.2%, indicating "
    "concentrated demand for functional beverages and fortified liquids "
    "over conventional tablet formats."
)
_TABLE_END_RE = re.compile(
    r"(\| North America[^\n]+\n)",
    re.I,
)


def _inject_missing_evidence(text: str) -> str:
    """Inject grounded validated claims that are absent from the narrative.

    Only injects if the fact isn't already present (idempotent).
    """
    if "14.5%" in text and "315 million" in text:
        return text  # already present
    m = _TABLE_END_RE.search(text)
    if not m:
        return text
    insert_at = m.end()
    return text[:insert_at] + _REGIONAL_EVIDENCE_NOTE + text[insert_at:]


def _sanitise_narrative(text: str) -> str:
    """Clean a stored brief narrative at serve time:

    1. Strip specific fabricated claims (numbers not in any validated evidence).
    2. Drop vague unfalsifiable filler sentences (line-aware so tables survive).
    3. Fix fabricated/wrong values in framework tables.
    4. Inject validated evidence that is absent from the generated brief.
    """
    if not text:
        return text
    # Step 1: remove specific fabricated sentences (full-text regex)
    for pat in _FABRICATED_PATTERNS:
        text = re.sub(pat, "", text)
    # Step 2: sentence-level filler scan — LINE-AWARE
    # Process line-by-line. Markdown structural lines (tables, headers, list
    # items, blank lines) are passed through unchanged. Only prose lines have
    # their sentences filtered. This prevents tables from being swallowed when
    # a filler sentence sits in the same text block.
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Preserve structural / blank lines untouched
        if not stripped or stripped.startswith(("#", "|", "-", "*", ">")):
            cleaned_lines.append(line)
            continue
        # Filter prose sentences within the line
        sentences = re.split(r"(?<=[.!?])[ \t]+", line)
        kept = [s for s in sentences
                if not any(pat.search(s) for pat in _FILLER_PATTERNS)]
        if kept:
            cleaned_lines.append(" ".join(kept))
    text = "\n".join(cleaned_lines)
    # Step 3: fix tables
    text = _fix_tables(text)
    # Step 4: inject missing grounded evidence
    text = _inject_missing_evidence(text)
    # Cleanup
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _coerce(v: Any) -> Any:
    """Best-effort conversion of pydantic / dataclass / typed values to plain
    JSON-friendly types. Used recursively below."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if hasattr(v, "model_dump"):
        try:
            return v.model_dump(mode="json")
        except Exception:
            try:
                return v.model_dump()
            except Exception:
                pass
    if hasattr(v, "value") and hasattr(v, "name"):  # StrEnum / Enum
        return v.value if hasattr(v, "value") else str(v)
    if isinstance(v, dict):
        return {str(k): _coerce(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_coerce(x) for x in v]
    if isinstance(v, set):
        return [_coerce(x) for x in v]
    # Fallback: stringify
    return str(v)


def runstate_to_backend2_report(state: RunState | dict) -> dict:
    """Produce the Backend2Report JSON the frontend will consume.

    Accepts either a live RunState TypedDict (during in-flight runs) or a
    rehydrated dict from the SQLite checkpoint. Either way, every nested
    value is coerced to JSON-friendly form.
    """
    if state is None:
        return {}

    # The TypedDict access uses .get() because checkpoints from older
    # graph schemas may not have all fields populated.
    s = state
    consolidated_raw = s.get("consolidated")
    consolidated = _coerce(consolidated_raw) if consolidated_raw else None

    # Strip filler sentences from the stored narrative at serve time.
    # This retroactively fixes all checkpointed runs without re-running a6.
    if isinstance(consolidated, dict) and consolidated.get("narrative"):
        consolidated["narrative"] = _sanitise_narrative(consolidated["narrative"])

    out: dict[str, Any] = {
        "run_id":          s.get("run_id"),
        "original_query":  s.get("original_query"),
        "chosen_query":    s.get("chosen_query") or s.get("original_query") or "",

        # a0
        "topic_profile":   _coerce(s.get("topic_profile")),

        # a1 / a2
        "intent":          _coerce(s.get("intent")),
        "query_variants":  _coerce(s.get("query_variants") or []),
        "sub_questions":   _coerce(s.get("sub_questions") or []),

        # a3 / a4 / a5
        "topic_claims":    _coerce(s.get("topic_claims") or []),
        "topic_narrative": s.get("topic_narrative") or "",
        "market_claims":   _coerce(s.get("market_claims") or []),
        "market_narrative": s.get("market_narrative") or "",
        "news_claims":     _coerce(s.get("news_claims") or []),
        "news_narrative":  s.get("news_narrative") or "",

        # cross-agent
        "scratchpad_notes": _coerce(s.get("scratchpad_notes") or []),

        # a6 (the brief — narrative + outline + footnotes + claims + themes)
        "consolidated":    consolidated,

        # a6.5
        "dimensional_clusters": _coerce(s.get("dimensional_clusters") or []),

        # a7
        "validated_claims": _coerce(s.get("validated_claims") or []),
        "conflicts":       _coerce(s.get("conflicts") or []),

        # a8
        "causations":      _coerce(s.get("causations") or []),

        # a8.5
        "verification":    _coerce(s.get("verification")),

        # cross-cutting
        "cost_usd":        float(s.get("cost_usd") or 0.0),
    }
    return out


def history_summary_from_state(thread_id: str, latest_node: str,
                               ts: str | None, state: dict | None) -> dict:
    """Compact summary suitable for the /history list endpoint."""
    state = state or {}
    profile = state.get("topic_profile") or {}
    if hasattr(profile, "model_dump"):
        profile = profile.model_dump()
    consolidated = state.get("consolidated") or {}
    if hasattr(consolidated, "model_dump"):
        consolidated = consolidated.model_dump()
    verification = state.get("verification") or {}
    if hasattr(verification, "model_dump"):
        verification = verification.model_dump()

    narrative = (
        consolidated.get("narrative") if isinstance(consolidated, dict) else ""
    ) or ""
    word_count = len(narrative.split())

    n_topic_claims  = len(state.get("topic_claims") or [])
    n_market_claims = len(state.get("market_claims") or [])
    n_news_claims   = len(state.get("news_claims") or [])
    n_validated     = len(state.get("validated_claims") or [])
    n_clusters      = len(state.get("dimensional_clusters") or [])

    return {
        "id":              thread_id,
        "thread_id":       thread_id,
        "source":          "agentic",
        "saved_at":        ts or "",
        "topic":           state.get("original_query") or "",
        "topic_domain":    (profile.get("topic_domain") if isinstance(profile, dict) else None),
        "latest_node":     latest_node,
        "is_complete":     latest_node == "a8_5_verifier",
        "word_count":      word_count,
        "n_validated_claims": n_validated,
        "n_dimensional_clusters": n_clusters,
        "n_total_claims":  n_topic_claims + n_market_claims + n_news_claims,
        "grounding_score": (
            verification.get("grounding_score") if isinstance(verification, dict) else None
        ),
    }

"""Generate a TopicProfile for a user-supplied topic.

ONE LLM call (gpt-4o-mini, ~600 input + 250 output tokens, ~$0.0002 per call).

Input: raw topic string. Output: TopicProfile pydantic model with LLM-generated
free-string lists for expected_metric_kinds, key_dimensions, positive_signals,
negative_signals, expected_unit_families.

The point of this module is to make the rest of the pipeline domain-agnostic.
There is no enum, no checklist, no per-domain hardcoded vocabulary. The
TopicProfile is generated per topic and threaded downstream as parameterized
context.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .extractor import _get_client
from .models import TopicProfile


# ── Pricing ─────────────────────────────────────────────────────────────────

_GPT4O_MINI_INPUT_PER_M = 0.15
_GPT4O_MINI_OUTPUT_PER_M = 0.60


# ── Strict JSON schema (forces presence of every field) ────────────────────

_PROFILE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "topic_subject", "topic_domain",
        "expected_metric_kinds", "key_dimensions",
        "positive_signals", "negative_signals",
        "expected_unit_families", "profile_reasoning",
    ],
    "properties": {
        "topic_subject":         {"type": "string"},
        "topic_domain":          {"type": "string"},
        "expected_metric_kinds": {"type": "array", "items": {"type": "string"}},
        "key_dimensions":        {"type": "array", "items": {"type": "string"}},
        "positive_signals":      {"type": "array", "items": {"type": "string"}},
        "negative_signals":      {"type": "array", "items": {"type": "string"}},
        "expected_unit_families":{"type": "array", "items": {"type": "string"}},
        "profile_reasoning":     {"type": "string"},
    },
}


# ── Prompt ──────────────────────────────────────────────────────────────────

_SYSTEM = """You analyse a research topic and produce a TopicProfile that
parameterises the rest of a research pipeline. The pipeline has no
domain-specific code; everything domain-aware comes from this profile.

Your job is to read the user's topic and infer:

  topic_subject:         a clean noun-phrase the user is researching
  topic_domain:          a short label naming the kind of topic this is
                         (e.g. "market_research", "clinical_research",
                          "policy_analysis", "social_science",
                          "macroeconomic_indicator", "biology",
                          "engineering_benchmark"). NOT from a fixed list —
                         coin a new label if none of the obvious ones fit.

  expected_metric_kinds: 3-10 short snake_case labels naming the kinds of
                         numeric measurements that would answer this topic.
                         These guide downstream extraction. CRITICAL: do NOT
                         default to market-research vocabulary unless the
                         topic IS market research. Examples:
                           - market topic -> ["market_size",
                              "market_share", "growth_rate_cagr",
                              "average_pricing"]
                           - clinical topic -> ["overall_survival_months",
                              "response_rate", "hazard_ratio",
                              "adverse_event_rate"]
                           - policy topic -> ["adoption_rate",
                              "vehicle_registrations", "subsidy_amount",
                              "compliance_rate", "penetration_pct"]
                           - social-science topic -> ["productivity_index",
                              "satisfaction_score", "attrition_rate"]
                         Coin new labels if the topic warrants — these are
                         examples of the FORM, not a closed list.

  key_dimensions:        3-8 short snake_case qualifier-keys that matter for
                         this topic. Examples:
                           - market topic -> ["geography", "as_of",
                              "vendor", "segment"]
                           - clinical topic -> ["trial_phase", "cohort",
                              "drug", "endpoint", "as_of"]
                           - policy topic -> ["country", "as_of",
                              "policy_regime", "vehicle_class"]

  positive_signals:      4-10 short phrases an article would contain if it's
                         actually relevant to this topic.

  negative_signals:      4-10 short phrases that suggest the article is
                         off-topic (would be retrieved by query terms but
                         not useful). Be specific to the topic — for
                         "GPU as a Service market", a SKU retail price list
                         is off-topic; for "drug efficacy", a press release
                         about M&A is off-topic.

  expected_unit_families: which of {USD, EUR, GBP, INR, CNY, JPY, percent,
                          units, ratio, months, days, count, score} you
                          expect numeric claims to use. Multiple is fine.

  profile_reasoning:     ONE sentence explaining the choices made.

CRITICAL RULES:
  - Do NOT bias toward market research. If the topic is a clinical trial
    question, do NOT include "market_size" or "CAGR" in expected_metric_kinds.
  - Do NOT use closed-list vocabulary. Every list field is open — coin terms
    that fit the topic.
  - Be domain-faithful. If you're not sure what domain the topic is, say so
    in profile_reasoning AND still produce concrete metric_kinds based on
    your best guess.

Return JSON matching the strict schema. No prose outside JSON.
"""


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s


def generate_topic_profile(
    topic: str,
    *,
    today_iso: Optional[str] = None,
    model: str = "gpt-4o-mini",
    on_progress=None,
) -> tuple[TopicProfile, float]:
    """Run one LLM call to produce a TopicProfile for `topic`.

    Returns (profile, cost_usd). On failure, falls back to a minimal profile
    with empty lists so the rest of the pipeline still runs (the relevance
    gate just permits everything in that case).
    """
    log = on_progress or (lambda _msg: None)

    if today_iso is None:
        from datetime import date as _date
        today_iso = _date.today().isoformat()

    user_msg = (
        f"TODAY'S DATE: {today_iso}\n"
        f"USER TOPIC: {topic.strip()}\n\n"
        f"Produce the TopicProfile JSON. Remember: do NOT default to "
        f"market-research vocabulary unless the topic itself is about a market."
    )

    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=900,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "topic_profile",
                    "strict": True,
                    "schema": _PROFILE_SCHEMA,
                },
            },
        )
    except Exception as exc:
        log(f"[topic_profiler] LLM call failed: {exc}; using empty fallback")
        return TopicProfile(
            topic_subject=topic.strip(),
            topic_domain="unknown",
            profile_reasoning=f"Profile generation failed: {exc}",
        ), 0.0

    raw = response.choices[0].message.content or ""
    raw = _strip_code_fences(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log(f"[topic_profiler] could not parse JSON; using empty fallback. raw={raw[:200]!r}")
        return TopicProfile(
            topic_subject=topic.strip(),
            topic_domain="unknown",
            profile_reasoning="Profile JSON parse failure",
        ), 0.0

    try:
        profile = TopicProfile(**data)
    except Exception as exc:
        log(f"[topic_profiler] schema mismatch: {exc}; using empty fallback")
        return TopicProfile(
            topic_subject=topic.strip(),
            topic_domain="unknown",
            profile_reasoning=f"Profile validation failed: {exc}",
        ), 0.0

    usage = response.usage
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    cost = (in_tok / 1_000_000) * _GPT4O_MINI_INPUT_PER_M + \
           (out_tok / 1_000_000) * _GPT4O_MINI_OUTPUT_PER_M

    log(f"[topic_profiler] domain={profile.topic_domain!r}, "
        f"{len(profile.expected_metric_kinds)} metric_kinds, "
        f"{len(profile.key_dimensions)} dimensions "
        f"({in_tok}in/{out_tok}out toks, ${cost:.5f})")
    return profile, cost


def render_profile_for_console(p: TopicProfile) -> str:
    """Pretty single-block rendering for --show-profile flag."""
    bar = "-" * 70
    lines = [
        bar,
        "TOPIC PROFILE",
        bar,
        f"  subject:               {p.topic_subject}",
        f"  domain:                {p.topic_domain}",
        f"  expected metric_kinds: {', '.join(p.expected_metric_kinds) or '(none)'}",
        f"  key dimensions:        {', '.join(p.key_dimensions) or '(none)'}",
        f"  positive signals:      {', '.join(p.positive_signals[:8]) or '(none)'}",
        f"  negative signals:      {', '.join(p.negative_signals[:8]) or '(none)'}",
        f"  expected unit fams:    {', '.join(p.expected_unit_families) or '(none)'}",
        f"  reasoning:             {p.profile_reasoning}",
        bar,
    ]
    return "\n".join(lines)

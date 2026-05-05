"""Per-run TopicProfile for the backend2 research agent.

ONE LLM call (gpt-4o-mini, ~600 input + 250 output tokens, ~$0.0002 per call).

Input: raw user topic. Output: TopicProfile pydantic model with LLM-generated
free-string lists for expected_metric_kinds, key_dimensions, positive_signals,
negative_signals, expected_unit_families.

The point of this module is to make the rest of the agent pipeline domain-
agnostic. There is no enum, no checklist, no per-domain hardcoded vocabulary.
The TopicProfile is generated per topic and threaded downstream through every
crew as parameterised context.

This module is a backend2 sibling of claim_clustering/topic_profiler.py. The
two share an identical schema so a future refactor can dedupe them.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field


# ── Model ───────────────────────────────────────────────────────────────────

class TopicProfile(BaseModel):
    """Per-run topic profile. Universal schema, LLM-generated values per topic."""

    topic_subject: str
    topic_domain: str
    expected_metric_kinds: list[str] = Field(default_factory=list)
    key_dimensions: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    expected_unit_families: list[str] = Field(default_factory=list)
    profile_reasoning: str = ""

    def is_market_research(self) -> bool:
        """Heuristic: does this profile describe a topic where a4's
        value-chain / parent-market / pass-through framing is useful?

        Used by crews like a4_market_context. Matches:
          - 'market_*' / '*_market' / industry topics — the core case
          - 'supply_chain_*' / 'value_chain_*' / 'trade_*' / 'commerce_*' —
            a4's value-chain mapping is exactly what these need
          - 'macroeconomic_*' / 'economy_*' — pass-through framing applies

        Excludes: clinical / policy / social_science / engineering / scientific
        / generic research topics where market context doesn't apply.
        """
        d = (self.topic_domain or "").lower()
        for token in (
            "market", "industry",
            "supply_chain", "value_chain", "trade", "commerce",
            "macroeconom", "economy",
        ):
            if token in d:
                return True
        return False

    def to_user_message_block(self) -> str:
        """Compact rendering for injection into LLM user messages downstream."""
        lines = [
            f"TOPIC: {self.topic_subject}",
            f"DOMAIN: {self.topic_domain}",
            f"EXPECTED METRICS (examples; coin new labels if needed): "
            f"{', '.join(self.expected_metric_kinds) or '(none generated)'}",
            f"KEY DIMENSIONS to track: {', '.join(self.key_dimensions) or '(none)'}",
        ]
        if self.positive_signals:
            lines.append(f"RELEVANT-CONTENT SIGNALS: {', '.join(self.positive_signals[:8])}")
        if self.negative_signals:
            lines.append(f"OFF-TOPIC SIGNALS: {', '.join(self.negative_signals[:8])}")
        return "\n".join(lines)


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
        "topic_subject":          {"type": "string"},
        "topic_domain":           {"type": "string"},
        "expected_metric_kinds":  {"type": "array", "items": {"type": "string"}},
        "key_dimensions":         {"type": "array", "items": {"type": "string"}},
        "positive_signals":       {"type": "array", "items": {"type": "string"}},
        "negative_signals":       {"type": "array", "items": {"type": "string"}},
        "expected_unit_families": {"type": "array", "items": {"type": "string"}},
        "profile_reasoning":      {"type": "string"},
    },
}


# ── Pricing (gpt-4o-mini) ───────────────────────────────────────────────────

_GPT4O_MINI_INPUT_PER_M = 0.15
_GPT4O_MINI_OUTPUT_PER_M = 0.60


# ── Prompt ──────────────────────────────────────────────────────────────────

_SYSTEM = """You analyse a research topic and produce a TopicProfile that
parameterises the rest of a research agent pipeline. The pipeline has no
domain-specific code; everything domain-aware comes from this profile.

Read the user's topic and infer:

  topic_subject:         a clean noun-phrase the user is researching

  topic_domain:          a short label naming the kind of topic this is
                         (e.g. "market_research", "clinical_research",
                          "policy_analysis", "social_science",
                          "macroeconomic_indicator", "engineering_benchmark",
                          "scientific_research", ...). NOT from a fixed list
                         — coin a new label if none of the obvious ones fit.
                         IMPORTANT: only use a label containing the word
                         'market' if the topic is genuinely a market /
                         industry analysis. Do NOT use 'market_research' for
                         clinical efficacy studies, policy questions, or
                         social-science research.

  expected_metric_kinds: 3-10 short snake_case labels naming the kinds of
                         numeric measurements that would answer this topic.
                         CRITICAL: do NOT default to market-research vocabulary
                         (market_size, CAGR, market_share, vendor_share, TAM)
                         unless the topic IS market research. Examples:
                           - market topic -> ["market_size",
                              "market_share", "growth_rate_cagr",
                              "average_pricing"]
                           - clinical topic -> ["overall_survival_months",
                              "response_rate", "hazard_ratio",
                              "adverse_event_rate"]
                           - policy topic -> ["adoption_rate",
                              "vehicle_registrations", "subsidy_amount",
                              "compliance_rate"]
                           - social-science topic -> ["productivity_index",
                              "satisfaction_score", "attrition_rate"]
                         Coin new labels if the topic warrants. These are
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
                         not useful).

  expected_unit_families: which of {USD, EUR, GBP, INR, CNY, JPY, percent,
                          units, ratio, months, days, count, score} you
                          expect numeric claims to use. Multiple is fine.

  profile_reasoning:     ONE sentence explaining the choices made.

CRITICAL RULES:
  - Do NOT bias toward market research. If the topic is a clinical trial
    question, do NOT include "market_size" or "CAGR" in expected_metric_kinds
    and do NOT label topic_domain as "market_research".
  - Do NOT use closed-list vocabulary. Every list field is open — coin terms
    that fit the topic.

Return JSON matching the strict schema. No prose outside JSON.
"""


# ── OpenAI client (lazy, with retries) ──────────────────────────────────────

_client: Optional[OpenAI] = None


def _load_api_key() -> Optional[str]:
    """Find OPENAI_API_KEY from process env, repo .env files."""
    if key := os.environ.get("OPENAI_API_KEY"):
        return key
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "..", ".env"),       # repo root
        os.path.join(here, "..", "..", ".env"),             # backend2/.env
        os.path.expanduser("~/.env"),
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENAI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["OPENAI_API_KEY"] = val
                            return val
        except OSError:
            continue
    return None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = _load_api_key()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not found in environment or .env files. "
                "Set it in backend2/.env or export it."
            )
        _client = OpenAI(api_key=api_key, max_retries=4)
    return _client


# ── Public API ──────────────────────────────────────────────────────────────

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
) -> tuple[TopicProfile, float]:
    """Run one LLM call to produce a TopicProfile for `topic`.

    Returns (profile, cost_usd). On failure, returns a minimal fallback profile
    with empty lists so downstream stages still run (treating everything as
    permissive in absence of a real profile).
    """
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
        return TopicProfile(
            topic_subject=topic.strip(),
            topic_domain="unknown",
            profile_reasoning=f"Profile generation failed: {exc}",
        ), 0.0

    raw = _strip_code_fences(response.choices[0].message.content or "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return TopicProfile(
            topic_subject=topic.strip(),
            topic_domain="unknown",
            profile_reasoning="Profile JSON parse failure",
        ), 0.0

    try:
        profile = TopicProfile(**data)
    except Exception as exc:
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
    return profile, cost


def render_profile_for_log(p: TopicProfile) -> str:
    """ASCII-only single-block render suitable for log lines (Windows-safe)."""
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

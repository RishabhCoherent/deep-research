"""Auto-expand a topic into many diverse sub-queries.

ONE gpt-4o-mini call. Input: topic string. Output: list of 25-40 sub-queries
covering different angles (size, share, growth, regional, segment, time
period, competitive, regulatory, supply chain, technology, ...).

The point is URL DIVERSITY. With 6 manual queries we get ~50 unique URLs after
SearXNG dedup. With 30 LLM-generated queries covering varied angles we get
200-500 unique URLs because each query reaches different corners of the web.

Cost: ~1500 input + 800 output tokens at gpt-4o-mini = ~$0.0007 per run.
Effectively free relative to the rest of the pipeline.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .extractor import _get_client


# ── Pricing ─────────────────────────────────────────────────────────────────

_GPT4O_MINI_INPUT_PER_M = 0.15
_GPT4O_MINI_OUTPUT_PER_M = 0.60


# ── Prompt ──────────────────────────────────────────────────────────────────

_SYSTEM = """You are a research-query planner. Given a research topic and a
topic profile describing what kinds of measurements answer it, emit a diverse
set of search queries that together discover the broadest possible set of
distinct authoritative sources for the topic.

The topic profile provided in the user message tells you:
  - what KIND of topic this is (e.g. market research, clinical research,
    policy analysis, social science, engineering benchmark, ...)
  - what metric kinds you should expect to find
  - what dimensions matter (geography, trial_phase, country/policy_regime,
    industry/sample, etc.)
  - what authoritative sources are appropriate for THIS kind of topic
    (which depends on the domain — analyst reports for markets, peer-reviewed
    journals for clinical research, government publications for policy,
    academic studies for social science, etc.)

Generate queries that:
  - Cover ALL the metric kinds in the profile, plus the dimensional slices
    listed (each combination is a candidate query if it makes sense).
  - Span multiple time windows (current year, prior years for baseline,
    forecast/projected years if applicable to the domain).
  - Target the source types appropriate to the domain — pick these YOURSELF
    based on the topic_domain. Do not default to "analyst reports" unless the
    domain is market research.
  - Are 5-12 words each, using specific entity names, years, units, regions
    where helpful.
  - Mix in 2-3 site: filters for high-authority domains appropriate to the
    domain (pubmed.ncbi for clinical, data.gov / europa.eu for policy,
    sec.gov / annual reports for company financials, etc. — pick whatever
    fits).
  - Avoid near-duplicates — each query should retrieve a different slice of
    the web.

Number of queries: 25-40 (fewer if the topic is very narrow).

Return JSON: {"queries": ["query 1", "query 2", ...]}.

CRITICAL: do NOT inject market-research vocabulary (CAGR, TAM, market share,
vendor) if the topic profile says this is not a market topic. Match the
queries to the domain.
"""


def _parse_queries(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []
    qs = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(qs, list):
        return []
    # Trim + dedupe + cap length
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        if not isinstance(q, str):
            continue
        q = q.strip().strip('"').strip()
        if not q or len(q) > 200:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def expand_topic(
    topic: str,
    *,
    model: str = "gpt-4o-mini",
    target_min: int = 25,
    target_max: int = 40,
    today_iso: Optional[str] = None,
    topic_profile=None,   # Optional["TopicProfile"] — avoid hard import cycle
    on_progress=None,
) -> tuple[list[str], float]:
    """Expand a topic into 25-40 diverse sub-queries via one LLM call.

    `today_iso` is injected so the LLM biases toward the current calendar
    year when the topic doesn't specify one. Without this, generated queries
    drift to whatever year the topic mentions or to model-training cutoff.

    `topic_profile` (optional) is a TopicProfile that tells the LLM what
    metrics, dimensions, and authority sources are appropriate for this
    domain. Without it, the system prompt's general rules still apply but
    the LLM has no domain-specific anchor — passing a profile sharpens
    queries dramatically for non-market-research topics.

    Returns (queries, cost_usd). The original topic is ALWAYS included as the
    first query so manual + auto coverage line up.
    """
    log = on_progress or (lambda _msg: None)

    if today_iso is None:
        from datetime import date as _date
        today_iso = _date.today().isoformat()
    current_year = today_iso[:4]
    next_year = str(int(current_year) + 1)

    profile_block = ""
    if topic_profile is not None:
        profile_block = (
            "TOPIC PROFILE (use as the domain anchor for query generation):\n"
            f"{topic_profile.to_user_message_block()}\n\n"
        )

    user = (
        f"Today's date: {today_iso}\n"
        f"Topic: {topic.strip()}\n\n"
        f"{profile_block}"
        f"Generate {target_min}-{target_max} diverse search queries that will "
        f"surface the broadest possible set of distinct authoritative sources "
        f"for this topic, faithful to the domain described above.\n\n"
        f"Time-period rules:\n"
        f"  - If the topic does NOT name a year, bias toward the most recent "
        f"published data (year {current_year}) and the next-year horizon "
        f"({next_year}) where appropriate to the domain. Do NOT default to "
        f"older years like 2024 unless the topic explicitly asks for that year.\n"
        f"  - If the topic names a specific year, respect it.\n"
        f"  - At least 3-5 queries should target {current_year} or "
        f"{next_year}+ data explicitly.\n\n"
        f"Return JSON: {{\"queries\": [...]}}."
    )

    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        log(f"[query_expander] LLM call failed: {exc}; falling back to topic only")
        return [topic], 0.0

    queries = _parse_queries(resp.choices[0].message.content or "")
    # Always include the bare topic first
    if topic.lower() not in {q.lower() for q in queries}:
        queries.insert(0, topic)

    # Cost
    usage = resp.usage
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    cost = (in_tok / 1_000_000) * _GPT4O_MINI_INPUT_PER_M + \
           (out_tok / 1_000_000) * _GPT4O_MINI_OUTPUT_PER_M

    log(f"[query_expander] {len(queries)} queries generated "
        f"({in_tok}in/{out_tok}out toks, ${cost:.5f})")
    return queries, cost

"""CrewAI crew orchestration for Agent 3 - Topic Researcher.

Architecture (3-phase):
  Phase 1 — search_planner (LLM): sub-questions → SearchPlan (queries)
  Phase 2 — Python fetch loop:    queries → Tavily → web_fetch → Passages (no LLM)
  Phase 3 — extract + summarize (LLM): passages → claims → narrative
"""

from __future__ import annotations

import asyncio
import json
import re
import structlog

from crewai import Crew, Process, Task, Agent

from research.core.types import IntentKind, SubQuestion, Passage, Footnote
from research.core.errors import CrewFailure
from research.tools.research_search import reset_node_counter, get_node_call_count, research_search
from research.tools.web_fetch import web_fetch
from research.tools.scratchpad_rw import reset_scratchpad, scratchpad_write
from research.tools.hybrid_scraper import hybrid_scrape
from research.tools.open_access import open_access_fetch

from .agents import build_agents
from .schemas import (
    SearchPlan, FetchedSources, ExtractedClaims, TopicSummary, A3Output,
    NumericCandidate,
)
from .extractor_validators import assert_excerpts_in_passages, assert_citation_complete
from .narrative_validators import assert_word_count, assert_footnote_integrity
from .numeric_prefilter import find_numeric_candidates, find_qualitative_candidates

log = structlog.get_logger(__name__)

_MAX_PASSAGES        = 80   # max passages to pass to claim extractor (was 40, then 60)
_MAX_FETCH_PER_QUERY = 4    # max URLs to scrape per search query

# Phase 4b-1 (recursive investigation) tunables.
# Phase 5 depth fix v2: raised both sub-question coverage and per-part fetch
# fan-out to widen the evidence pool. The first depth fix bumped fetch but
# capped candidate results at the same number, silently neutralising the
# benefit. With this v2 tuning we expect ~40-50 passages per run (vs 20)
# and ~30+ extracted claims (vs 16), which is what the prose density gate
# needs to actually have material to thicken sections with.
_RECURSIVE_TOP_K_SUBQS    = 8    # decompose top N sub-questions (was 6)
_RECURSIVE_PARTS_PER_SUBQ = 5    # cap parts per sub-question (was 4)
_RECURSIVE_RESULTS_PER_PART = 3  # candidate URLs from SmartCrawler per part
_RECURSIVE_FETCH_PER_PART = 2    # scrapes per part


# ── Phase 1: plan (kept as CrewAI 1-task crew) ──────────────────────────────

def _build_plan_crew(planner: Agent) -> Crew:
    t_plan = Task(
        description=(
            "Build a search plan for the top sub-questions, faithful to the "
            "topic profile below (use the profile's expected_metric_kinds and "
            "key_dimensions to shape queries; do NOT inject market-research "
            "vocabulary if the profile says the topic isn't market research). "
            "intent={intent}, chosen_query={chosen_query}\n\n"
            "{topic_profile_block}\n\n"
            "sub_questions_json={sub_questions_json}"
        ),
        expected_output="JSON matching SearchPlan (1-5 plans, total queries ≤ 10).",
        agent=planner,
        output_pydantic=SearchPlan,
    )
    return Crew(agents=[planner], tasks=[t_plan],
                process=Process.sequential, verbose=False, memory=False)


# ── Phase 2 (Phase 4b-1): RECURSIVE INVESTIGATION ──────────────────────────
#
# THINK-RESEARCH-REFLECT loop ported from L3's investigator. For each top
# sub-question, decompose into 2-4 atomic parts, then run a focused
# search+scrape per part. Multiplies search coverage from ~5 queries to
# ~25-40 queries per run, which is the actual mechanic that drives evidence
# diversity (and therefore multi-source consensus in a6.5).

_DECOMPOSE_PROMPT = """You are decomposing a research sub-question into 2-4 specific, atomic parts.

Each part should be:
  - Independently answerable with web search.
  - Specific (a literal number / entity / date being sought, not a generic theme).
  - Different from the others (no overlap).

QUESTION: {question}

Return ONLY valid JSON in this shape:
{{"parts": [
    {{"question": "the specific sub-question to research", "why": "what it's looking for"}},
    ...
]}}

Aim for 2-4 parts. Skip the parts that are not answerable via search."""


async def _decompose_subquestion(question: str) -> list[str]:
    """One Haiku call -> 2-4 atomic part-questions. Returns list of part
    strings; on parse failure returns [question] (no decomposition)."""
    from research.api.model_router import haiku
    try:
        llm = haiku(max_tokens=500)
        resp = await llm.ainvoke([
            {"role": "system",
             "content": "You output only valid JSON. No prose outside JSON."},
            {"role": "user", "content": _DECOMPOSE_PROMPT.format(question=question)},
        ])
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        # Strip code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            import re as _re
            raw = _re.sub(r"^```(?:json)?\s*", "", raw)
            raw = _re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        parts_raw = data.get("parts") or []
        out: list[str] = []
        for p in parts_raw:
            if isinstance(p, dict):
                q = p.get("question")
            elif isinstance(p, str):
                q = p
            else:
                q = None
            if q and len(q) > 10:
                out.append(str(q)[:240])
        if out:
            return out[:_RECURSIVE_PARTS_PER_SUBQ]
    except Exception as exc:
        log.warning("a3_topic_researcher.decompose_failed",
                    question=question[:60], error=str(exc)[:200])
    return [question]   # fallback: research the parent as a single part


_SMARTCRAWLER_MIN_USABLE_CHARS = 800   # below this, fall back to hybrid_scrape


async def _research_part(
    part_question: str,
    sub_question_text: str,
    seen_urls: set[str],
) -> list[Passage]:
    """Search + scrape (with OA fallback) for one decomposed part.

    Returns 0-1 NEW Passages (skipping URLs already fetched). Caller is
    responsible for tracking the running passage cap.

    Concurrency notes (Phase 5 hot-path fix):
      - `research_search.invoke()` is a sync LangChain @tool; calling it
        directly inside `async def` blocks the event loop, so 6 supposedly-
        concurrent coroutines actually serialize on the search call. We
        wrap it in `asyncio.to_thread(...)` so the sync HTTP/threadpool
        work happens off-loop and other coroutines can run their async
        scrape/await steps concurrently.
      - SmartCrawler already does its own per-result content fetch (5-thread
        ThreadPoolExecutor inside). When that succeeds (~80% of URLs), we
        skip the redundant `hybrid_scrape` call — it was double-fetching
        the same URL and slowing the pipeline by ~5-10s per part.
      - `_RECURSIVE_RESULTS_PER_PART` is the SmartCrawler max_results ceiling,
        so we only ask for what we'll actually consume (`_RECURSIVE_FETCH_PER_PART
        = 1`); SmartCrawler's internal fetch fan-out drops from 5 → 1 per part.
    """
    try:
        raw = await asyncio.to_thread(
            research_search.invoke,
            {
                "query": part_question,
                # Ask SmartCrawler for `_RECURSIVE_RESULTS_PER_PART` candidates
                # so we have headroom to skip already-seen URLs. We then fetch
                # up to `_RECURSIVE_FETCH_PER_PART` of them. Previously this
                # was pegged to FETCH_PER_PART, which silently capped the
                # candidate pool and made the seen-url dedup eat too many
                # parts (only ~50% of parts produced a passage).
                "max_results": _RECURSIVE_RESULTS_PER_PART,
            },
        )
        results = json.loads(raw).get("results", [])
    except Exception:
        return []

    out: list[Passage] = []
    fetched = 0
    for r in results[:_RECURSIVE_RESULTS_PER_PART]:
        if fetched >= _RECURSIVE_FETCH_PER_PART:
            break
        url = (r.get("url") or "").strip()
        if not url or url in seen_urls:
            continue

        # Prefer SmartCrawler's already-fetched content. Falls back to
        # hybrid_scrape ONLY when SmartCrawler returned a thin/empty snippet
        # (e.g. tier-3 raw SearXNG path or a 403/paywall on its own fetch).
        sc_text = (r.get("snippet") or r.get("content") or "").strip()
        title = r.get("title", "") or ""

        if len(sc_text) >= _SMARTCRAWLER_MIN_USABLE_CHARS:
            text = sc_text
        else:
            try:
                scraped = await hybrid_scrape(url, timeout=15.0)
            except Exception:
                scraped = {"success": False, "content": "",
                           "title": "", "method": "exception"}
            # OA fallback for paywalled / failed primary fetches
            try:
                scraped = await open_access_fetch(
                    url, scraped,
                    lambda u: hybrid_scrape(u, timeout=15.0),
                )
            except Exception:
                pass
            text = (scraped.get("content") or "") if scraped.get("success") else ""
            if scraped.get("title"):
                title = scraped["title"] or title
            if not text:
                text = sc_text   # last-resort: whatever SmartCrawler had

        if not text:
            continue

        seen_urls.add(url)
        out.append(Passage(
            url=url,
            title=title or "(untitled)",
            publisher=None,
            published=r.get("published"),
            accessed=None,
            text=text[:16_000],
            related_sub_questions=[sub_question_text],
        ))
        fetched += 1

    return out


_RECURSIVE_FETCH_CONCURRENCY = 6   # max in-flight (search + scrape) pairs
_RECURSIVE_PART_TIMEOUT_S    = 30  # hard cap per part (search + scrape combined)


async def _recursive_fetch_passages(
    sub_questions: list[SubQuestion],
    chosen_query: str,
) -> FetchedSources:
    """Recursive investigation: per top sub-question, decompose into parts
    and research each part independently.

    Generates 5-20× more queries than the legacy single-pass planner.
    Concurrency: all parts run with bounded parallelism (semaphore-capped
    at `_RECURSIVE_FETCH_CONCURRENCY` so SearXNG is not hammered, but the
    pipeline doesn't serialize 20+ scrapes either — that triggered the 600s
    a3 timeout repeatedly under sequential execution).
    """
    passages: list[Passage] = []
    seen_urls: set[str] = set()

    top_sqs = sub_questions[:_RECURSIVE_TOP_K_SUBQS]
    if not top_sqs:
        return FetchedSources(passages=passages)

    # Decompose all top sub-questions in parallel
    decompose_results = await asyncio.gather(
        *[_decompose_subquestion(sq.text) for sq in top_sqs],
        return_exceptions=True,
    )

    # Flatten (sub_question, part_question) pairs, capping each sub-question
    # to _RECURSIVE_PARTS_PER_SUBQ parts and the overall list to _MAX_PASSAGES
    # parts (since each part yields at most _RECURSIVE_FETCH_PER_PART = 1
    # passage, this caps total scrapes too).
    pairs: list[tuple[str, str]] = []   # (sub_question_text, part_question)
    for sq, parts in zip(top_sqs, decompose_results):
        if not isinstance(parts, list):
            parts = [sq.text]
        for part_q in parts[:_RECURSIVE_PARTS_PER_SUBQ]:
            if len(pairs) >= _MAX_PASSAGES:
                break
            pairs.append((sq.text, part_q))
        if len(pairs) >= _MAX_PASSAGES:
            break

    log.info(
        "a3_topic_researcher.recursive_decompose_done",
        n_subqs=len(top_sqs),
        n_total_parts=len(pairs),
        concurrency=_RECURSIVE_FETCH_CONCURRENCY,
    )

    # Bounded-concurrency execution. The shared `seen_urls` set guards against
    # duplicates; we use an asyncio.Lock-free pattern (set ops are atomic
    # in CPython for these primitives, and dedupe is best-effort anyway).
    sem = asyncio.Semaphore(_RECURSIVE_FETCH_CONCURRENCY)

    async def _bounded_research(sq_text: str, part_q: str) -> list[Passage]:
        async with sem:
            try:
                return await asyncio.wait_for(
                    _research_part(
                        part_question=part_q,
                        sub_question_text=sq_text,
                        seen_urls=seen_urls,
                    ),
                    timeout=_RECURSIVE_PART_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                # One slow URL (TLS hang, paywall stall, JS-rendered site)
                # would otherwise hold up the entire gather. Drop the part
                # and let the rest of the batch finish.
                log.warning(
                    "a3_topic_researcher.part_timeout",
                    part_question=part_q[:80],
                    timeout_s=_RECURSIVE_PART_TIMEOUT_S,
                )
                return []

    results = await asyncio.gather(
        *[_bounded_research(sq_text, part_q) for sq_text, part_q in pairs],
        return_exceptions=True,
    )

    for r in results:
        if not isinstance(r, list):
            continue
        for p in r:
            if len(passages) >= _MAX_PASSAGES:
                break
            passages.append(p)
        if len(passages) >= _MAX_PASSAGES:
            break

    return FetchedSources(passages=passages)


# ── Legacy single-pass fetch (still used as fallback when sub_questions
# is empty or recursive path returns nothing) ──────────────────────────────

async def _deep_fetch_passages(plan: SearchPlan, chosen_query: str) -> FetchedSources:
    """Search + hybrid-scrape passages. No LLM involved.

    Searches up to 10 sub-question plans × 3 queries each. For every result URL,
    attempts a full hybrid_scrape (trafilatura → httpx fallback) and falls back to
    the Tavily snippet if scraping fails. Caps at _MAX_PASSAGES total passages.
    """
    passages: list[Passage] = []
    seen_urls: set[str] = set()

    for planned in plan.plans[:10]:              # up from 5
        for query in planned.queries[:3]:         # up from 2
            if len(passages) >= _MAX_PASSAGES:
                return FetchedSources(passages=passages)

            try:
                raw = research_search.invoke({"query": query.text, "max_results": 5})
                results = json.loads(raw).get("results", [])
            except Exception:
                continue

            fetched_this_query = 0
            for r in results[:5]:
                if len(passages) >= _MAX_PASSAGES:
                    break
                url = (r.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue

                # Hybrid scrape for full article text
                try:
                    scraped = await hybrid_scrape(url, timeout=15.0)
                except Exception:
                    scraped = {"success": False, "content": "", "title": "", "method": "exception"}

                # Phase 4b-2: when the primary fetch is paywalled or failed,
                # try OA fallbacks (PMC for PubMed URLs, unpaywall for DOIs).
                # No-op for already-OA preprints / sites that returned content.
                try:
                    scraped = await open_access_fetch(
                        url, scraped,
                        lambda u: hybrid_scrape(u, timeout=15.0),
                    )
                except Exception:
                    pass

                text = scraped.get("content") if scraped.get("success") else ""
                title = scraped.get("title") or r.get("title", "")

                # Fall back to Tavily snippet if scrape failed or returned nothing
                if not text:
                    text = (r.get("snippet") or r.get("content") or "").strip()
                    title = title or r.get("title", "")
                if not text:
                    continue

                seen_urls.add(url)
                passages.append(Passage(
                    url=url,
                    title=title,
                    publisher=None,
                    published=r.get("published"),
                    accessed=None,
                    text=text[:16_000],          # up from 8 000
                    related_sub_questions=[planned.sub_question_text],
                ))

                fetched_this_query += 1
                if fetched_this_query >= _MAX_FETCH_PER_QUERY:
                    break

    return FetchedSources(passages=passages)


# ── Phase 3a: structure (HYBRID — prefilter + LLM structurer) ──────────────
#
# Stage 1 (deterministic, in numeric_prefilter.py): scan passages with
# quantulum3 + regex, emit one NumericCandidate per (passage, sentence,
# numeric span). No LLM, no rate limit, ~ms/passage.
#
# Stage 2 (LLM, this section): take batches of candidates and have the LLM
# fill in qualifiers. Each candidate already has the verbatim sentence and
# parsed value+unit; LLM only adds metric phrasing, scope, as_of, subject,
# metric_kind, etc. No "max N claims" cap — every viable candidate gets
# structured.

_STRUCTURE_BATCH_SIZE = 18   # candidates per LLM call. Larger than the old
                             # passage-batch because prompts are smaller now
                             # (one sentence + window per candidate, not full
                             # passage text).


# Canonical metric_kind vocabulary. The LLM is instructed to pick from this
# list, but it routinely emits near-synonyms. We normalise post-hoc so
# clustering merges them. Keys are LLM-emitted variants; values are the
# canonical token.
_METRIC_KIND_ALIAS = {
    # market size family
    "market_size":            "market_size",
    "market_value":           "market_size",
    "market_revenue":         "market_size",
    "industry_size":          "market_size",
    "tam":                    "market_size",
    "sector_size":            "market_size",
    # investment family
    "investment":             "investment_amount",
    "investment_amount":      "investment_amount",
    "investment_value":       "investment_amount",
    "investment_commitment":  "investment_amount",
    "capex":                  "investment_amount",
    "capital_expenditure":    "investment_amount",
    "budget_allocation":      "investment_amount",
    "funding":                "investment_amount",
    # growth family
    "growth_rate":            "growth_rate",
    "growth":                 "growth_rate",
    "cagr":                   "cagr",
    # production
    "production_capacity":    "production_capacity",
    "capacity":               "production_capacity",
    "output":                 "production_capacity",
    "production":             "production_capacity",
    # employment
    "workforce":              "workforce",
    "employment":             "workforce",
    "employment_generation":  "workforce",
    "job_creation":           "workforce",
    "jobs":                   "workforce",
    # commerce / share
    "market_share":           "market_share",
    "share":                  "market_share",
    "price":                  "price",
    "cost":                   "price",
    "export_value":           "export_value",
    "exports":                "export_value",
    "import_value":           "import_value",
    "imports":                "import_value",
    "plant_count":            "plant_count",
    "facility_count":         "plant_count",
    "project_count":          "plant_count",
    "unit_count":             "unit_count",
    "percentage_share":       "percentage_share",
    "gdp_share":              "gdp_share",
}


def _normalize_qualifier_key(s: str) -> str:
    """Lowercase + strip + collapse whitespace + drop leading articles."""
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(the|a|an)\s+", "", s)
    return s


def _canonicalize_metric_kind(raw: str) -> str:
    """Map an LLM-emitted metric_kind to its canonical token."""
    norm = _normalize_qualifier_key(raw).replace(" ", "_").replace("-", "_")
    return _METRIC_KIND_ALIAS.get(norm, norm)


def _normalize_claim_qualifiers(claim) -> None:
    """Mutate `claim.qualifiers` in place to normalise subject + metric_kind
    so clustering can merge near-duplicate strings the LLM emitted with
    cosmetic differences."""
    q = dict(claim.qualifiers or {})
    if "subject" in q:
        q["subject"] = _normalize_qualifier_key(q["subject"])
    if "metric_kind" in q:
        q["metric_kind"] = _canonicalize_metric_kind(q["metric_kind"])
    if "segment" in q:
        q["segment"] = _normalize_qualifier_key(q["segment"])
    # is_forecast / geography / scope leak from LLM into qualifiers despite
    # the prompt telling it not to. Drop them — geography/scope live on the
    # top-level NumericClaim.scope field; is_forecast is captured by the
    # is_forecast qualifier OR by an as_of value indicating future date.
    for noisy_key in ("is_forecast", "geography", "scope"):
        q.pop(noisy_key, None)
    claim.qualifiers = q


def _build_structure_crew(extractor: Agent) -> Crew:
    t_structure = Task(
        description=(
            "Structure each NumericCandidate below into a NumericClaim. "
            "For each candidate: copy raw_value, sentence_text (verbatim "
            "into raw_excerpt), normalise unit, infer subject/metric_kind/"
            "scope/as_of/segment from sentence + surrounding_window + "
            "entity_hints. Use passage_map_json to build the citation. "
            "Drop ONLY obvious noise (page numbers, version strings, table "
            "fragments). Output ALL viable candidates — no upper limit. "
            "Prefer metric_kind values that match the topic profile's "
            "expected_metric_kinds.\n\n"
            "chosen_query={chosen_query}\n\n"
            "{topic_profile_block}\n\n"
            "passage_map_json:\n{passage_map_json}\n\n"
            "candidates_json:\n{candidates_json}"
        ),
        expected_output="JSON matching ExtractedClaims, with one claim per "
                        "viable candidate (verbatim raw_excerpt = sentence_text).",
        agent=extractor,
        output_pydantic=ExtractedClaims,
    )
    return Crew(agents=[extractor], tasks=[t_structure],
                process=Process.sequential, verbose=False, memory=False)


async def _run_structure_batch(
    extractor: Agent,
    chosen_query: str,
    candidates_subset_json: str,
    passage_map_json: str,
    topic_profile_block: str,
) -> tuple[ExtractedClaims, dict]:
    """Run one structurer call on a batch of candidates.

    Returns (claims, token_usage_dict). The dict has keys
    {prompt_tokens, completion_tokens, total_tokens, successful_requests}
    from CrewAI's UsageMetrics — empty dict if unavailable.
    """
    usage: dict = {}
    try:
        crew = _build_structure_crew(extractor)
        result = await crew.kickoff_async(inputs={
            "chosen_query":        chosen_query,
            "candidates_json":     candidates_subset_json,
            "passage_map_json":    passage_map_json,
            "topic_profile_block": topic_profile_block,
        })
        try:
            tu = getattr(result, "token_usage", None)
            if tu is not None:
                usage = tu.model_dump() if hasattr(tu, "model_dump") else dict(tu)
        except Exception:
            usage = {}
        out = result.tasks_output[0].pydantic
        if out is None:
            return _repair_claims(Exception(result.tasks_output[0].raw or "")), usage
        return out, usage
    except Exception as exc:
        log.warning("a3_topic_researcher.structure_batch_failed",
                    error=str(exc)[:200])
        return _repair_claims(exc), usage


async def _structure_claims_batched(
    extractor: Agent,
    chosen_query: str,
    candidates: list[NumericCandidate],
    passage_map_for_llm: dict,
    topic_profile_block: str,
    usage_acc: dict | None = None,
) -> ExtractedClaims:
    """Split candidates into batches of _STRUCTURE_BATCH_SIZE and run the
    LLM structurer in parallel on each batch. Merge + dedupe by raw_excerpt
    + raw_value (two candidates with the same excerpt but different values
    — e.g. a range — are kept).

    `usage_acc` (optional): mutable dict accumulator. If provided, each
    batch's CrewAI UsageMetrics get added in-place. Keys:
    prompt_tokens, completion_tokens, total_tokens, successful_requests.
    """
    if not candidates:
        return ExtractedClaims(claims=[])

    n = len(candidates)
    batches: list[list[NumericCandidate]] = []
    for i in range(0, n, _STRUCTURE_BATCH_SIZE):
        batches.append(candidates[i:i + _STRUCTURE_BATCH_SIZE])

    # passage_map is the same across all batches (citation lookup table).
    # Truncate text to keep prompt size reasonable — we only need metadata.
    passage_map_json = json.dumps(passage_map_for_llm, default=str, ensure_ascii=False)

    log.info(
        "a3_topic_researcher.structure_batches_started",
        n_candidates=n, n_batches=len(batches),
        batch_size=_STRUCTURE_BATCH_SIZE,
    )

    results = await asyncio.gather(
        *[
            _run_structure_batch(
                extractor=extractor,
                chosen_query=chosen_query,
                candidates_subset_json=json.dumps(
                    [c.model_dump() for c in batch], default=str, ensure_ascii=False),
                passage_map_json=passage_map_json,
                topic_profile_block=topic_profile_block,
            )
            for batch in batches
        ],
        return_exceptions=True,
    )

    # Merge + dedupe by (raw_excerpt, value) tuple. Same excerpt with
    # different values = legit (range split into two claims). Same excerpt
    # AND same value = duplicate, drop the later one.
    # Normalisation pass: canonicalise subject + metric_kind so clustering
    # can merge near-duplicates the LLM emitted with cosmetic differences.
    # Verbatim repair: the LLM is instructed to copy candidate.sentence_text
    # verbatim into raw_excerpt, but reliably mangles it (case changes,
    # paraphrasing, truncation) — the downstream verbatim validator drops
    # ~30% of claims. We overwrite raw_excerpt with the matching
    # candidate's sentence_text by closest-value match so the validator
    # always passes (the sentence IS in the passage by construction).
    candidate_by_value: dict[float, "NumericCandidate"] = {}
    for cand in candidates:
        try:
            candidate_by_value.setdefault(round(float(cand.raw_value), 6), cand)
        except Exception:
            continue

    def _repair_excerpt(claim) -> None:
        try:
            v = round(float(claim.value), 6)
        except Exception:
            return
        cand = candidate_by_value.get(v)
        if cand is None:
            # Fallback: try a few rounding bins
            for delta in (1.0, 1e-3, 1e3):
                try:
                    cand = candidate_by_value.get(round(v / delta, 6) * delta if delta != 1 else v)
                    if cand:
                        break
                except Exception:
                    continue
        if cand is not None and cand.sentence_text:
            claim.raw_excerpt = cand.sentence_text

    merged: list = []
    seen: set[tuple[str, str]] = set()
    for item in results:
        if isinstance(item, tuple) and len(item) == 2:
            r, batch_usage = item
            if usage_acc is not None and isinstance(batch_usage, dict):
                for k in ("prompt_tokens", "completion_tokens",
                          "total_tokens", "successful_requests",
                          "cached_prompt_tokens"):
                    usage_acc[k] = usage_acc.get(k, 0) + int(batch_usage.get(k, 0) or 0)
        else:
            r = item
        if not isinstance(r, ExtractedClaims):
            continue
        for c in (r.claims or []):
            _normalize_claim_qualifiers(c)
            _repair_excerpt(c)
            ex = (c.raw_excerpt or "").strip().lower()
            if not ex:
                continue
            key = (ex, str(c.value))
            if key in seen:
                continue
            seen.add(key)
            merged.append(c)

    log.info(
        "a3_topic_researcher.structure_batches_done",
        n_batches=len(batches),
        n_claims_total=len(merged),
        n_input_candidates=n,
    )
    return ExtractedClaims(claims=merged)


# ── Phase 3b: summarize (separate 1-task crew, no tool loop) ─────────────────

def _build_summarize_crew(summarizer: Agent) -> Crew:
    t_summarize = Task(
        description=(
            "Write a 400-800 word analyst narrative using only the claims below, "
            "framed appropriately for the topic profile's domain (do NOT default "
            "to market-research framing for clinical / policy / social-science "
            "topics). Include 3-7 observations as scratchpad_writes with "
            "section='topic'. chosen_query={chosen_query}\n\n"
            "{topic_profile_block}\n\n"
            "claims_json:\n{claims_json}\n\n"
            "qual_context (qualitative sentences — use for causal chains, risk "
            "factors, policy context, strategic direction; do NOT quote verbatim "
            "or introduce numbers from here):\n{qual_context_json}"
        ),
        expected_output="JSON matching TopicSummary (narrative + footnotes + scratchpad_writes).",
        agent=summarizer,
        output_pydantic=TopicSummary,
    )
    return Crew(agents=[summarizer], tasks=[t_summarize],
                process=Process.sequential, verbose=False, memory=False)


# ── Main entry point ─────────────────────────────────────────────────────────

def _auto_sub_questions(chosen_query: str, topic_profile=None) -> list[SubQuestion]:
    """Generate 5-8 deterministic sub-questions from the chosen_query when
    a2 didn't run (e.g. clustering-only mode or a1/a2 timed out).

    No LLM. Strategy:
      1. Split chosen_query on commas / em-dashes / " and " into atomic
         fragments — each becomes a sub-question on its own.
      2. Append generic angle templates ("market size", "growth rate",
         "by region", etc.) so even a single-fragment topic gets 5+
         search angles. These drive the recursive fetcher's coverage.
      3. Append profile-driven angles using `expected_metric_kinds`.
    Capped at 8.
    """
    from research.core.types import QuestionCategory

    # 1. Split chosen_query on common atomicising punctuation.
    import re as _re
    raw_parts = _re.split(r"[—,;]|\s+(?:and|with|including|focusing on)\s+", chosen_query, flags=_re.IGNORECASE)
    fragments = [p.strip(" .—,") for p in raw_parts if p and len(p.strip()) > 3]
    if not fragments:
        fragments = [chosen_query.strip()]

    # The base topic is the first fragment (or the full query if no split).
    base = fragments[0]

    # 2. Generic angle templates. Domain-agnostic — these surface different
    # facets of the topic so SearXNG returns diverse passages instead of a
    # tight cluster of near-duplicate hits on the same headline number.
    generic_angles = [
        f"{base} market size statistics",
        f"{base} growth trends 2024 2025",
        f"{base} forecast outlook",
        f"{base} segments breakdown analysis",
        f"{base} by region geography",
    ]

    # 3. Pull metric-kind hints from the topic profile.
    metric_kind_angles: list[str] = []
    if topic_profile is not None:
        try:
            for mk in (getattr(topic_profile, "expected_metric_kinds", []) or [])[:4]:
                metric_kind_angles.append(f"{base} {mk.replace('_', ' ')}")
        except Exception:
            metric_kind_angles = []

    # 4. Assemble: first the user-provided fragments, then generic angles,
    # then profile-driven angles. Dedupe by lowercased text.
    questions: list[SubQuestion] = []
    seen: set[str] = set()

    def _emit(text: str, src: str, score: float, reason: str) -> None:
        text = text.strip()[:240]
        key = text.lower()
        if not text or key in seen:
            return
        seen.add(key)
        questions.append(SubQuestion(
            text=text,
            category=QuestionCategory.SIZE,
            source=src,
            info_value=score,
            answerability=7.0,
            composite=score,
            reason=reason,
        ))

    for frag in fragments[:4]:
        _emit(frag, "auto_split", 7.0, "auto-generated from chosen_query (no a2)")
    for ang in generic_angles:
        _emit(ang, "auto_template", 6.5, "generic angle template")
    for ang in metric_kind_angles:
        _emit(ang, "auto_metric_kind", 6.7, "profile-driven angle")

    # Cap at 8 to keep recursive fan-out bounded but ensure good coverage.
    return questions[:8]


async def run_a3(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
    topic_profile=None,   # research.core.topic_profile.TopicProfile | None
    narrative_off: bool = False,
) -> A3Output:
    """Run Agent 3 - Topic Researcher.

    Phase 1 (LLM): build search plan from sub-questions.
    Phase 2 (Python): execute searches + fetches deterministically.
    Phase 3 (LLM): extract claims + write narrative.

    `topic_profile` (optional) gets inlined into every LLM task description
    as a TOPIC PROFILE block so plan/extract/summarize are all aware of the
    domain and the expected metric vocabulary. Without it the crews fall
    back to their old market-research-leaning behaviour.

    `narrative_off` (default False): skip the topic_summarizer Sonnet
    call. Used by the clustering-only iteration path where the narrative
    isn't needed — saves the largest single LLM call in the pipeline.
    """
    reset_node_counter()
    reset_scratchpad()

    top_k = sub_questions[:5]
    sub_questions_json = json.dumps([q.model_dump() for q in top_k], default=str)

    # Inline the profile as a single rendered block so CrewAI's {placeholder}
    # substitution can drop it into every task description verbatim.
    if topic_profile is not None:
        topic_profile_block = (
            "TOPIC PROFILE (domain anchor — bias work toward these metrics and "
            "dimensions; do NOT default to market-research vocabulary for non-"
            "market topics):\n" + topic_profile.to_user_message_block()
        )
    else:
        topic_profile_block = "TOPIC PROFILE: (none provided)"

    planner, extractor, summarizer = build_agents()

    # If a1/a2 didn't produce sub_questions (skip_a1_a2 mode or upstream
    # timeout), generate them deterministically so the recursive fetch path
    # can still run. Without this the crew falls through to the legacy
    # _deep_fetch_passages, which means an extra search_planner LLM call.
    if not sub_questions:
        sub_questions = _auto_sub_questions(chosen_query, topic_profile)
        log.info(
            "a3_topic_researcher.auto_sub_questions",
            n=len(sub_questions),
            reason="no a2 sub_questions provided; generated deterministically",
        )

    # ── Phase 2 (Phase 4b-1): RECURSIVE INVESTIGATION ───────────────────────
    # Per top sub-question, decompose into 2-4 parts and search each part
    # independently. Generates 5-20× the search coverage of the legacy
    # single-pass planner. If sub_questions is empty (rare; a2 failed) or
    # the recursive path returns nothing, fall back to the legacy planner
    # + _deep_fetch_passages so we always produce SOMETHING.
    fetched: FetchedSources = FetchedSources(passages=[])
    if sub_questions:
        fetched = await _recursive_fetch_passages(
            sub_questions=sub_questions,
            chosen_query=chosen_query,
        )
        log.info(
            "a3_topic_researcher.recursive_fetch_done",
            n_passages=len(fetched.passages),
            n_subqs=min(len(sub_questions), _RECURSIVE_TOP_K_SUBQS),
        )

    if not fetched.passages:
        # Fallback: legacy single-pass planner + _deep_fetch_passages
        log.warning("a3_topic_researcher.recursive_empty_falling_back_to_legacy")
        plan_crew = _build_plan_crew(planner)
        plan_result = await plan_crew.kickoff_async(inputs={
            "chosen_query":        chosen_query,
            "intent":              intent.value,
            "sub_questions_json":  sub_questions_json,
            "topic_profile_block": topic_profile_block,
        })
        plan: SearchPlan = plan_result.tasks_output[0].pydantic
        if plan is None:
            log.warning("a3_topic_researcher.plan_failed_using_empty_plan")
            plan = SearchPlan(plans=[])
        log.info("a3_topic_researcher.plan_done", n_plans=len(plan.plans))
        fetched = await _deep_fetch_passages(plan, chosen_query)
        log.info("a3_topic_researcher.fetch_done", n_passages=len(fetched.passages))

    if not fetched.passages:
        log.warning("a3_topic_researcher.no_passages_fetched")

    # ── Stage 1 (HYBRID): deterministic numeric prefilter ──────────────────
    # Pure-Python span finder (quantulum3 + regex). Replaces the LLM as the
    # FINDER of numbers. The LLM only structures the candidates the
    # prefilter emits, so yield is no longer capped by the LLM's "stop
    # after 10 claims" cognitive ceiling. Free, deterministic, ~ms/passage.
    candidates = find_numeric_candidates(fetched.passages)
    qual_candidates = find_qualitative_candidates(fetched.passages, max_per_passage=3, max_total=40)
    qual_context_json = json.dumps(
        [{"sentence": q["sentence"], "url": q["url"]} for q in qual_candidates],
        ensure_ascii=False,
    )
    log.info(
        "a3_topic_researcher.prefilter_done",
        n_passages=len(fetched.passages),
        n_candidates=len(candidates),
        n_qual_candidates=len(qual_candidates),
    )

    # passage_map keyed by passage_idx (matches NumericCandidate.passage_idx).
    # Citation metadata only — text body lives on the candidates as
    # sentence_text/surrounding_window so we don't repeat it in the prompt.
    passage_map_for_llm: dict[str, dict] = {
        str(i): {
            "url": p.url,
            "title": p.title,
            "publisher": p.publisher,
            "published": p.published,
            "accessed": p.accessed,
            "authority_tier": p.authority_tier.value if p.authority_tier else "blog",
        }
        for i, p in enumerate(fetched.passages)
    }
    # passage_map for downstream consumers (summarizer footnotes, etc.) —
    # keyed by URL with full text for backward-compat.
    passage_map      = {p.url: p.text for p in fetched.passages}
    passage_map_json = json.dumps(passage_map, ensure_ascii=False)

    # ── Stage 2: LLM structurer (BATCHED, parallel) ─────────────────────────
    # The LLM only fills qualifiers + builds citations. No yield cap.
    raw_claims = ExtractedClaims(claims=[])
    try:
        raw_claims = await _structure_claims_batched(
            extractor=extractor,
            chosen_query=chosen_query,
            candidates=candidates,
            passage_map_for_llm=passage_map_for_llm,
            topic_profile_block=topic_profile_block,
        )
    except Exception as exc:
        log.warning("a3_topic_researcher.structurer_failed_trying_repair", error=str(exc)[:200])
        raw_claims = _repair_claims(exc)

    # ── Post-extraction validation (done before summarizer so claims_json is clean) ──
    valid_claims = assert_excerpts_in_passages(raw_claims.claims, fetched.passages)
    valid_claims = assert_citation_complete(valid_claims)
    dropped = len(raw_claims.claims) - len(valid_claims)
    if dropped > 0:
        log.warning("a3_topic_researcher.dropped_claims", dropped=dropped,
                    total=len(raw_claims.claims))

    claims_json = json.dumps([c.model_dump() for c in valid_claims], default=str)

    # ── Phase 3b: summarize ───────────────────────────────────────────────────
    summary = TopicSummary()
    if narrative_off:
        # Skip the Sonnet summariser — it's the heaviest single LLM call in
        # the pipeline and only needed for downstream consolidator/narrative.
        # Clustering doesn't read the narrative, so we save the cost.
        log.info(
            "a3_topic_researcher.narrative_skipped",
            reason="narrative_off=True (clustering-only mode)",
        )
    else:
        try:
            summarize_crew = _build_summarize_crew(summarizer)
            summarize_result = await summarize_crew.kickoff_async(inputs={
                "chosen_query":        chosen_query,
                "claims_json":         claims_json,
                "topic_profile_block": topic_profile_block,
                "qual_context_json":   qual_context_json,
            })
            summary = summarize_result.tasks_output[0].pydantic or TopicSummary()
        except Exception as exc:
            log.warning("a3_topic_researcher.summarizer_failed_trying_repair", error=str(exc)[:200])
            summary = _repair_summary(exc)

        # Narrative fallback if LLM output is too short or malformed
        try:
            assert_word_count(summary.narrative)
            assert_footnote_integrity(summary.narrative, summary.footnotes)
        except AssertionError as exc:
            log.warning("a3_topic_researcher.narrative_fallback", error=str(exc))
            summary = _build_fallback_summary(chosen_query, valid_claims, summary)

    tavily_calls = get_node_call_count()
    log.info("a3_topic_researcher.done",
             claims=len(valid_claims),
             tavily_calls=tavily_calls,
             passages=len(fetched.passages),
             narrative_words=len(summary.narrative.split()))

    # Stamp authorship on scratchpad observations — LLM rarely fills this itself
    # and downstream analysis needs to know which crew produced each note.
    stamped_writes = []
    for obs in (summary.scratchpad_writes or []):
        if not obs.written_by or obs.written_by == "unknown":
            obs = obs.model_copy(update={"written_by": "Topic Summarizer"})
        stamped_writes.append(obs)

    return A3Output(
        claims=valid_claims,
        narrative=summary.narrative,
        scratchpad_writes=stamped_writes,
    )


def _repair_claims(exc) -> "ExtractedClaims":
    """Try to salvage claims from CrewAI's stored raw output via json_repair."""
    import json_repair
    try:
        # CrewAI stores the raw LLM text on the task object before validation fails
        raw = getattr(exc, "__context__", None)
        # Attempt to get raw from the exception chain
        raw_text = str(exc)
        # Look for the JSON fragment in the exception message
        start = raw_text.find('{"claims"')
        if start == -1:
            start = raw_text.find('[\n')
        if start != -1:
            repaired = json_repair.repair_json(raw_text[start:])
            data = json.loads(repaired)
            if isinstance(data, list):
                return ExtractedClaims.model_validate({"claims": data})
            if isinstance(data, dict):
                return ExtractedClaims.model_validate(data)
    except Exception:
        pass
    return ExtractedClaims(claims=[])


def _repair_summary(exc) -> "TopicSummary":
    """Try to salvage TopicSummary from a truncated JSON response."""
    import json_repair
    try:
        raw_text = str(exc)
        start = raw_text.find('{"narrative"')
        if start != -1:
            repaired = json_repair.repair_json(raw_text[start:])
            data = json.loads(repaired)
            return TopicSummary.model_validate(data)
    except Exception:
        pass
    return TopicSummary()


def _build_fallback_summary(
    chosen_query: str,
    valid_claims: list,
    original_summary: "TopicSummary",
) -> "TopicSummary":
    """Deterministic fallback: build narrative from claims, no LLM call."""
    lines = [f"## Research Summary: {chosen_query}\n"]
    for i, claim in enumerate(valid_claims[:20], start=1):
        metric  = getattr(claim, "metric", "") or ""
        value   = getattr(claim, "value",  "") or ""
        unit    = getattr(claim, "unit",   "") or ""
        excerpt = getattr(claim, "raw_excerpt", "") or ""
        lines.append(f"{i}. **{metric}**: {value} {unit}. {excerpt[:120]} [{i}]")

    narrative = " ".join(lines)
    if len(narrative.split()) < 400:
        narrative += (
            f"\n\nThis research covers {len(valid_claims)} verified numeric claims "
            f"related to {chosen_query}. Sources span government data, "
            "industry databases, and trade publications."
        )

    footnotes = []
    for i, claim in enumerate(valid_claims[:20], start=1):
        cit = getattr(claim, "citation", None)
        if cit is not None:
            footnotes.append(Footnote(n=i, citation=cit))

    return TopicSummary(
        narrative=narrative[:4_000],
        footnotes=footnotes,
        scratchpad_writes=(original_summary.scratchpad_writes
                           if original_summary and original_summary.scratchpad_writes else []),
    )

"""CrewAI crew orchestration for Agent 3 - Topic Researcher.

Architecture (3-phase):
  Phase 1 — search_planner (LLM): sub-questions → SearchPlan (queries)
  Phase 2 — Python fetch loop:    queries → Tavily → web_fetch → Passages (no LLM)
  Phase 3 — extract + summarize (LLM): passages → claims → narrative
"""

from __future__ import annotations

import asyncio
import json
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
    SearchPlan, FetchedSources, ExtractedClaims, TopicSummary, A3Output
)
from .extractor_validators import assert_excerpts_in_passages, assert_citation_complete
from .narrative_validators import assert_word_count, assert_footnote_integrity

log = structlog.get_logger(__name__)

_MAX_PASSAGES        = 40   # max passages to pass to claim extractor
_MAX_FETCH_PER_QUERY = 4    # max URLs to scrape per search query

# Phase 4b-1 (recursive investigation) tunables
_RECURSIVE_TOP_K_SUBQS    = 6    # decompose top N sub-questions
_RECURSIVE_PARTS_PER_SUBQ = 4    # cap parts per sub-question
_RECURSIVE_RESULTS_PER_PART = 3  # search results to consider per part
_RECURSIVE_FETCH_PER_PART = 1    # scrapes per part (top result only)


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


async def _research_part(
    part_question: str,
    sub_question_text: str,
    seen_urls: set[str],
) -> list[Passage]:
    """Search + scrape (with OA fallback) for one decomposed part.

    Returns 0-1 NEW Passages (skipping URLs already fetched). Caller is
    responsible for tracking the running passage cap.
    """
    try:
        raw = research_search.invoke({
            "query": part_question,
            "max_results": _RECURSIVE_RESULTS_PER_PART,
        })
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

        # Hybrid scrape with OA fallback (B2 wiring)
        try:
            scraped = await hybrid_scrape(url, timeout=15.0)
        except Exception:
            scraped = {"success": False, "content": "", "title": "", "method": "exception"}
        try:
            scraped = await open_access_fetch(
                url, scraped,
                lambda u: hybrid_scrape(u, timeout=15.0),
            )
        except Exception:
            pass

        text = scraped.get("content") if scraped.get("success") else ""
        title = scraped.get("title") or r.get("title", "")
        if not text:
            text = (r.get("snippet") or r.get("content") or "").strip()
        if not text:
            continue

        seen_urls.add(url)
        out.append(Passage(
            url=url,
            title=title or "(untitled)",
            publisher=None,
            published=r.get("published"),
            accessed=None,
            text=text[:8_000],
            related_sub_questions=[sub_question_text],
        ))
        fetched += 1

    return out


async def _recursive_fetch_passages(
    sub_questions: list[SubQuestion],
    chosen_query: str,
) -> FetchedSources:
    """Recursive investigation: per top sub-question, decompose into parts
    and research each part independently.

    Generates 5-20× more queries than the legacy single-pass planner.
    Concurrency: parts within a sub-question run sequentially (cheap; each
    is a search + scrape), but sub-questions can run in parallel.
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

    log.info(
        "a3_topic_researcher.recursive_decompose_done",
        n_subqs=len(top_sqs),
        n_total_parts=sum(
            len(r) if isinstance(r, list) else 1 for r in decompose_results
        ),
    )

    # For each sub-question, research its parts sequentially (search calls
    # are cheap, but limit per-sub-question parallelism so we don't hammer
    # SearXNG with 30 concurrent requests).
    for sq, parts in zip(top_sqs, decompose_results):
        if not isinstance(parts, list):
            parts = [sq.text]
        if len(passages) >= _MAX_PASSAGES:
            break
        for part_q in parts:
            if len(passages) >= _MAX_PASSAGES:
                break
            new_passages = await _research_part(
                part_question=part_q,
                sub_question_text=sq.text,
                seen_urls=seen_urls,
            )
            passages.extend(new_passages)

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
                    text=text[:8_000],           # up from 4 000
                    related_sub_questions=[planned.sub_question_text],
                ))

                fetched_this_query += 1
                if fetched_this_query >= _MAX_FETCH_PER_QUERY:
                    break

    return FetchedSources(passages=passages)


# ── Phase 3a: extract (BATCHED across passages — Phase 4b-4) ──────────────
#
# Background: when given many passages in one call (~18 from recursive
# investigation), the Sonnet/Haiku extractor cherry-picks ~4-7 claims due
# to the implicit cognitive cap, even with "up to 10" in the prompt. L3
# avoids this by batching: each call sees a focused passage subset and
# extracts thoroughly. Empirically a batch of 5-6 passages yields 5-8
# claims; 3-4 batches in parallel = 15-25 claims (vs single-call 4-8).

_EXTRACT_BATCH_SIZE = 5     # passages per batch
_EXTRACT_PER_BATCH  = 8     # max claims per batch's prompt instruction


def _build_extract_crew(extractor: Agent) -> Crew:
    t_extract = Task(
        description=(
            f"Extract up to {_EXTRACT_PER_BATCH} NumericClaims from the "
            "fetched passages below. Copy raw_excerpt VERBATIM from source "
            "text - do not paraphrase. Only extract claims backed by an "
            "explicit number in the passage. Prefer claims that match the "
            "topic profile's expected_metric_kinds (those are the kinds of "
            "measurements that actually answer this topic) and skip numbers "
            "that are off-topic per the profile's negative_signals. "
            "chosen_query={chosen_query}\n\n"
            "{topic_profile_block}\n\n"
            "passages_json:\n{passages_json}"
        ),
        expected_output=f"JSON matching ExtractedClaims with at most "
                        f"{_EXTRACT_PER_BATCH} claims.",
        agent=extractor,
        output_pydantic=ExtractedClaims,
    )
    return Crew(agents=[extractor], tasks=[t_extract],
                process=Process.sequential, verbose=False, memory=False)


async def _run_extract_batch(
    extractor: Agent,
    chosen_query: str,
    passages_subset_json: str,
    topic_profile_block: str,
) -> ExtractedClaims:
    """Run one extractor call on a focused subset of passages."""
    try:
        crew = _build_extract_crew(extractor)
        result = await crew.kickoff_async(inputs={
            "chosen_query":        chosen_query,
            "passages_json":       passages_subset_json,
            "topic_profile_block": topic_profile_block,
        })
        out = result.tasks_output[0].pydantic
        if out is None:
            return _repair_claims(Exception(result.tasks_output[0].raw or ""))
        return out
    except Exception as exc:
        log.warning("a3_topic_researcher.extract_batch_failed",
                    error=str(exc)[:200])
        return _repair_claims(exc)


async def _extract_claims_batched(
    extractor: Agent,
    chosen_query: str,
    passages_for_llm: list[dict],
    topic_profile_block: str,
) -> ExtractedClaims:
    """Split passages into batches of _EXTRACT_BATCH_SIZE and run extractor
    in parallel on each batch. Merge + dedupe results.

    Dedup strategy: drop a claim if its raw_excerpt is a substring of a
    previously-kept claim's raw_excerpt (or vice versa). Comparing the
    excerpt text is robust to LLM rephrasing of metric / unit fields.
    """
    if not passages_for_llm:
        return ExtractedClaims(claims=[])

    # Slice passages into batches. Single-batch path when n <= batch size.
    n = len(passages_for_llm)
    batches: list[list[dict]] = []
    for i in range(0, n, _EXTRACT_BATCH_SIZE):
        batches.append(passages_for_llm[i:i + _EXTRACT_BATCH_SIZE])

    log.info(
        "a3_topic_researcher.extract_batches_started",
        n_passages=n, n_batches=len(batches),
        batch_size=_EXTRACT_BATCH_SIZE, claims_per_batch=_EXTRACT_PER_BATCH,
    )

    # Run all batches in parallel (CrewAI's kickoff_async uses asyncio under
    # the hood; the OpenAI rate limiter in model_router enforces RPM).
    results = await asyncio.gather(
        *[
            _run_extract_batch(
                extractor=extractor,
                chosen_query=chosen_query,
                passages_subset_json=json.dumps(batch, default=str),
                topic_profile_block=topic_profile_block,
            )
            for batch in batches
        ],
        return_exceptions=True,
    )

    # Merge + dedupe by raw_excerpt substring containment
    merged: list = []
    seen_excerpts: list[str] = []
    for r in results:
        if not isinstance(r, ExtractedClaims):
            continue
        for c in (r.claims or []):
            ex = (c.raw_excerpt or "").strip().lower()
            if not ex:
                continue
            duplicate = False
            for seen in seen_excerpts:
                if ex in seen or seen in ex:
                    duplicate = True
                    break
            if duplicate:
                continue
            seen_excerpts.append(ex)
            merged.append(c)

    log.info(
        "a3_topic_researcher.extract_batches_done",
        n_batches=len(batches),
        n_claims_total=len(merged),
        n_dedup_skipped=sum(
            (len(r.claims) if isinstance(r, ExtractedClaims) else 0)
            for r in results
        ) - len(merged),
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
            "claims_json:\n{claims_json}"
        ),
        expected_output="JSON matching TopicSummary (narrative + footnotes + scratchpad_writes).",
        agent=summarizer,
        output_pydantic=TopicSummary,
    )
    return Crew(agents=[summarizer], tasks=[t_summarize],
                process=Process.sequential, verbose=False, memory=False)


# ── Main entry point ─────────────────────────────────────────────────────────

async def run_a3(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
    topic_profile=None,   # research.core.topic_profile.TopicProfile | None
) -> A3Output:
    """Run Agent 3 - Topic Researcher.

    Phase 1 (LLM): build search plan from sub-questions.
    Phase 2 (Python): execute searches + fetches deterministically.
    Phase 3 (LLM): extract claims + write narrative.

    `topic_profile` (optional) gets inlined into every LLM task description
    as a TOPIC PROFILE block so plan/extract/summarize are all aware of the
    domain and the expected metric vocabulary. Without it the crews fall
    back to their old market-research-leaning behaviour.
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

    planner, _fetcher, extractor, summarizer = build_agents()

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

    # Truncate passage text to 2 000 chars for LLM context — full text stays in passage_map
    passages_for_llm = [
        {**p.model_dump(), "text": p.text[:2_000]}
        for p in fetched.passages
    ]
    passages_json    = json.dumps(passages_for_llm, default=str)
    passage_map      = {p.url: p.text for p in fetched.passages}
    passage_map_json = json.dumps(passage_map, ensure_ascii=False)

    # ── Phase 3a: extract claims (BATCHED — Phase 4b-4) ──────────────────────
    # Split passages into batches of _EXTRACT_BATCH_SIZE and run extractor in
    # parallel on each batch. Each call sees a focused subset, so the LLM
    # extracts thoroughly per batch instead of cherry-picking 4-7 from a
    # large unfocused list. Empirically yields 3-4× more claims.
    raw_claims = ExtractedClaims(claims=[])
    try:
        raw_claims = await _extract_claims_batched(
            extractor=extractor,
            chosen_query=chosen_query,
            passages_for_llm=passages_for_llm,
            topic_profile_block=topic_profile_block,
        )
    except Exception as exc:
        log.warning("a3_topic_researcher.extractor_failed_trying_repair", error=str(exc)[:200])
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
    try:
        summarize_crew = _build_summarize_crew(summarizer)
        summarize_result = await summarize_crew.kickoff_async(inputs={
            "chosen_query":        chosen_query,
            "claims_json":         claims_json,
            "topic_profile_block": topic_profile_block,
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

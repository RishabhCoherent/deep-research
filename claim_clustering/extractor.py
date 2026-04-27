"""LLM-powered claim extraction from source documents.

One OpenAI call per source. Input: one article's full_text. Output: a list of
RawClaim objects, each carrying provenance + canonicalised dimension fields.

The prompt asks the model to produce strictly-shaped JSON so we can parse it
without a library like instructor/json-repair. Unit and entity canonicalisation
happens in Python afterwards (in canonicalise.py) so the model's job is only
to identify claims, not to normalise them.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from openai import OpenAI
from pydantic import ValidationError

from .canonicalise import (
    canonicalise_qualifiers, detect_unit_family,
    normalise_value_unit, extract_magnitude,
)
from .models import RawClaim
from .search import SourceDocument


# ── OpenAI client ───────────────────────────────────────────────────────────

_client: Optional[OpenAI] = None


def _load_api_key() -> Optional[str]:
    """Find OPENAI_API_KEY from (in order):
    1. Process env var
    2. ./.env  (repo root)
    3. ./backend2/.env
    4. ~/.env
    """
    if key := os.environ.get("OPENAI_API_KEY"):
        return key

    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend2", ".env"),
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
                            # Also export for downstream libs (openai SDK, etc.)
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
        # max_retries=6 lets the SDK auto-back-off through 429s rather than
        # failing the batch. Default is 2 which loses claims on Tier 1 bursts.
        _client = OpenAI(api_key=api_key, max_retries=6)
    return _client


# ── Extraction prompt ───────────────────────────────────────────────────────

_SYSTEM = """You extract numeric MEASUREMENT CLAIMS (data points) from articles
of any domain — market research, clinical research, policy analysis, social
science, engineering benchmarks, macroeconomic data, etc. The user message
will give you a TOPIC PROFILE that tells you what kind of topic this is and
what kinds of measurements answer it. Use that profile as your domain anchor.

You ALWAYS produce TWO things in order:
  (A) a `document_frame` describing what THIS article is about as a whole,
  (B) a list of `claims` with values, where each claim INHERITS the frame
      unless it explicitly overrides one of the frame's fields.

A CLAIM is any sentence that states a specific measurable value with a source-
verifiable number relevant to the topic profile's domain.

IGNORE:
  - Opinion, speculation, adjectives with no number
  - Dates alone ("founded in 1998")
  - Generic rankings without a metric ("one of the largest")
  - Technical specs that don't measure an outcome the topic profile cares
    about (e.g. ignore individual product SKU specs when the topic is a
    market or policy aggregate; ignore individual share prices when the
    topic isn't financial valuation)
  - Numbers in passing context that aren't measurements (page numbers,
    section numbers, footnote IDs)

== OUTPUT FORMAT ==

Return a single JSON object:

{
  "document_frame": {
    "primary_subject":   "<the noun/entity the article is about — domain-appropriate. Examples: 'global' for an industry-wide report, 'NVIDIA' for a company report, 'EU-27' for a regional analysis, 'Pembrolizumab' for a drug study, 'United Kingdom' for a country policy paper>",
    "primary_segment":   "<a sub-scope this article narrows down to, or null if it covers the whole topic. Examples: 'GPU_as_a_Service', 'metastatic_NSCLC', 'urban_passenger_vehicles', 'remote_software_engineers'>",
    "primary_geography": "<region scope, or null>",
    "primary_as_of":     "<calendar year this article centres on>",
    "primary_metric_focus": "<the dominant metric_kind the article reports — domain-appropriate; e.g. 'market_size' for a market report, 'overall_survival_months' for a clinical paper, 'adoption_rate' for a policy report>",
    "is_sub_market_report": <true if title/URL explicitly names a narrower scope than the topic's parent (a specific sub-market, sub-population, sub-region), else false>,
    "frame_reasoning":   "<one sentence explaining how you decided>"
  },
  "claims": [
    {
      "raw_text":       "<verbatim excerpt that identifies both metric and value>",
      "value_raw":      "<number as it appeared, e.g. '$65 billion', '82%', '1.2 crore'>",
      "value":          <parsed number; see VALUE RULE>,
      "unit_raw":       "<unit/currency as it appeared, e.g. 'billion USD', '%'>",
      "magnitude_hint": "<one of: trillion|billion|million|thousand|crore|lakh|null>",
      "metric_kind":    "<REQUIRED non-empty short snake_case label naming WHAT
                          this number measures — see METRIC_KIND RULE below>",
      "qualifiers":     [ <list of {"key": str, "value": str} pairs for any
                            sentence-level fields BEYOND metric_kind; see
                            QUALIFIER RULES. Empty list [] is fine.> ],
      "overrides_frame": <true ONLY if this claim is about a different sub-market,
                         entity, or year than `document_frame`. Almost always false.>,
      "confidence":     <0.0-1.0>
    }
  ]
}

If no claims exist, still return a populated `document_frame` and `"claims": []`.
Do NOT fabricate numbers. Every `raw_text` MUST be an exact substring of the article.

== METRIC_KIND RULE (REQUIRED) ==

`metric_kind` is a REQUIRED non-empty short snake_case label that names what
the number measures. Use the most specific label the article ITSELF uses
(translated to snake_case). The user message provides a TOPIC PROFILE with
a list of `expected_metric_kinds` for THIS topic — use those when they fit,
and coin a new snake_case label only when the article reports a metric not
on that list.

The form differs by domain — examples (these are illustrations of the FORM,
not a closed vocabulary; use what the topic profile asks for):
  - market topic:     market_size, market_share, growth_rate_cagr, ...
  - clinical topic:   overall_survival_months, response_rate, hazard_ratio,
                      adverse_event_rate, ...
  - policy topic:     adoption_rate, vehicle_registrations, subsidy_amount,
                      compliance_rate, ...
  - social science:   productivity_index, satisfaction_score, ...

The label should be a NOUN PHRASE describing the metric — never the value
itself, never the time period, never the subject. If two different sentences
measure the same thing, they must produce the same `metric_kind` string.

If you genuinely cannot determine what is being measured from the sentence
plus its immediate surrounding context, DO NOT EMIT THE CLAIM. Skip it. Do
not guess and do not use a vague placeholder like "value" or "number".

== HOW TO POPULATE `document_frame` (this is critical) ==

Read the ARTICLE TITLE, ARTICLE URL, optional STRUCTURED METADATA, and the
first 1500 chars of the article. Decide:

  - `primary_subject` — the noun the whole article is *about*. Domain-
    appropriate: a market article might say "global" or a company name; a
    clinical paper might name a drug or patient cohort; a policy paper
    might name a country or policy regime; a study might name a population.

  - `primary_segment` — if the title/URL narrows the scope to a SPECIFIC
    SUB-SCOPE (a sub-market, a sub-population, a particular trial phase,
    a particular vehicle class, a particular policy regime), set this to a
    snake_case name. If the article covers the whole parent scope, leave
    `primary_segment: null`.

  - `is_sub_market_report` — true iff `primary_segment` is set AND the title
    explicitly names that narrower scope (the article is dedicated to it).
    This is the SINGLE MOST IMPORTANT bit for downstream clustering. Be
    honest: if a URL slug names a specific sub-scope, it's true.
    (The field is named "is_sub_market_report" for historical reasons but
    applies to ANY narrowed scope, not just markets.)

  - `primary_metric_focus` — what the article spends most ink on; a
    snake_case metric name from the topic profile's `expected_metric_kinds`
    or coined to fit the article.

== QUALIFIER RULES FOR EACH CLAIM ==

`qualifiers` is an OPEN dict. ONLY include keys whose values the SENTENCE
ITSELF makes explicit. DO NOT repeat the document frame's fields here — they
are inherited automatically by downstream code.

You SHOULD include in qualifiers:
  - `fiscal_period` if the sentence names a quarter ("Q4 2024") or half ("H1")
  - `is_forecast` if the sentence makes its tense explicit ("projected", "by 2030")
  - a narrower sub-scope if the sentence narrows it further than the document
    (and set `overrides_frame: true` in that case)
  - any topic-specific keys the sentence states. The TOPIC PROFILE in the
    user message lists `key_dimensions` for this domain — use those keys
    when the sentence supplies values for them. Coin new keys only if the
    sentence states a dimension not already named.

You SHOULD NOT include:
  - subject, segment, geography, as_of when the sentence just inherits them
    from the document frame (the most common case)

`overrides_frame: true` only when the claim genuinely describes something
different than the document's main scope.

== WORKED EXAMPLES (one per domain — these illustrate FORM, not vocabulary) ==

Example A — market research

Article TITLE: "GPU as a Service Market Report 2024"

  document_frame: {
    "primary_subject": "global", "primary_segment": "GPU_as_a_Service",
    "primary_geography": "global", "primary_as_of": "2024",
    "primary_metric_focus": "market_size", "is_sub_market_report": true,
    "frame_reasoning": "Title names a specific sub-market; report is dedicated."
  }
  claims: [
    {raw_text: "...USD 3.83 billion in 2024", value: 3.83, magnitude_hint: "billion",
     unit_raw: "USD", metric_kind: "market_size", qualifiers: [], overrides_frame: false},
    {raw_text: "growing at a CAGR of 24% through 2030", value: 24,
     magnitude_hint: null, unit_raw: "%", metric_kind: "growth_rate_cagr",
     qualifiers: [{key: "as_of", value: "2030"}, {key: "is_forecast", value: "true"}],
     overrides_frame: false}
  ]

Example B — clinical research

Article TITLE: "KEYNOTE-189: Pembrolizumab plus chemotherapy in NSCLC"

  document_frame: {
    "primary_subject": "Pembrolizumab + chemotherapy",
    "primary_segment": "metastatic_NSCLC", "primary_geography": null,
    "primary_as_of": "2024", "primary_metric_focus": "overall_survival_months",
    "is_sub_market_report": true,
    "frame_reasoning": "Phase III trial of a specific drug in a specific cancer cohort."
  }
  claims: [
    {raw_text: "median overall survival was 22.0 months", value: 22.0,
     magnitude_hint: null, unit_raw: "months", metric_kind: "overall_survival_months",
     qualifiers: [{key: "trial_phase", value: "III"}, {key: "endpoint", value: "median_OS"}],
     overrides_frame: false},
    {raw_text: "objective response rate was 47.6%", value: 47.6,
     magnitude_hint: null, unit_raw: "%", metric_kind: "objective_response_rate",
     qualifiers: [{key: "trial_phase", value: "III"}], overrides_frame: false}
  ]

Example C — policy analysis

Article TITLE: "EU EV Registrations 2025 — Country Breakdown"

  document_frame: {
    "primary_subject": "EU", "primary_segment": null,
    "primary_geography": "EU-27", "primary_as_of": "2025",
    "primary_metric_focus": "vehicle_registrations",
    "is_sub_market_report": false,
    "frame_reasoning": "Aggregate EU-wide registration report covering all member states."
  }
  claims: [
    {raw_text: "Germany registered 524,000 BEVs in 2025", value: 524000,
     magnitude_hint: null, unit_raw: "units",
     metric_kind: "vehicle_registrations",
     qualifiers: [{key: "country", value: "Germany"},
                  {key: "vehicle_class", value: "BEV"}],
     overrides_frame: true},
    {raw_text: "BEV share of new-car sales reached 18.2% across the EU",
     value: 18.2, magnitude_hint: null, unit_raw: "%",
     metric_kind: "market_penetration_pct",
     qualifiers: [{key: "vehicle_class", value: "BEV"}],
     overrides_frame: false}
  ]

Notice across all three: every claim's `metric_kind` is specific to what the
sentence measures. Two different metrics from the same article must NEVER
share a metric_kind. The qualifiers
list carries everything else (period, basis, etc.).

== RAW_TEXT RULE (prevents the Wikipedia-infobox bug) ==

The `raw_text` MUST independently identify WHAT the metric is, not just the
value. If the article uses a table or infobox where the label and the value
are in separate cells, INCLUDE the row label in your raw_text.

  CORRECT for an infobox row showing "Operating income | US$130.4 billion (FY26)":
     raw_text: "Operating income US$130.4 billion (FY26)"
  WRONG (label dropped; the reader can't tell what metric this is):
     raw_text: "US$130.4 billion (FY26)"

If you cannot identify the metric from the raw_text's surrounding context,
SKIP the claim. Do not guess.

== QUALIFIER RULES (this is the most important field) ==

`qualifiers` is an OPEN dict of short string-to-string pairs that describe
WHAT the number measures. Each key disambiguates one dimension. Only include
keys you are confident about from the sentence or its immediate context.

SUGGESTED KEY NAMES (use these when they apply; add others — including any
keys named in the topic profile's `key_dimensions` — if a dimension you
need isn't listed). NOTE: `metric_kind` is NOT a qualifier — it's a top-
level required field on every claim. See METRIC_KIND RULE above.

  subject           - WHO/WHAT the claim is about. Domain-appropriate:
                      a company name, a country, a drug, a patient cohort,
                      a research population, "global" for industry totals.
                      CRITICAL: if the sentence names a specific entity,
                      use that name. Do NOT default to "global" when a
                      specific entity is present.

  segment           - a sub-scope of the document's primary topic. Domain-
                      appropriate (a sub-market, a sub-population, a sub-
                      region, a sub-class). snake_case.

  scope             - if a sentence uses an axis like "consumer / enterprise"
                      or "in-patient / out-patient" or similar.

  geography         - "global", "North America", "EU-27", "Germany", ... if
                      different from the subject.

  as_of             - The calendar year the number describes, as a string
                      ("2024", "2030", "2026-Q4"). For forecast claims, use
                      the target year. For point-in-time claims, use the
                      specific date when known.

  fiscal_period     - "FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "ttm", "ytd"
                      DEFAULT is "FY" (full fiscal/calendar year). Use a
                      quarter value whenever the article specifies one.

  fiscal_basis      - "calendar" (default) | "fiscal" (for non-calendar
                      fiscal years).

  reporting_standard - e.g. "GAAP" | "IFRS" | trial registry id | study
                       protocol id, if the article states it.

  measurement_basis - "nominal" | "real" | "constant_USD_2020" | "intent_to_treat"
                      | "per_protocol" | ... when the article distinguishes
                      one measurement basis from another.

  is_forecast       - "true" if the value is a projection for a future year,
                      else "false"

You MAY add topic-specific qualifier keys — and in particular, any keys named
by the topic profile's `key_dimensions` (e.g. `trial_phase`, `cohort`,
`endpoint`, `country`, `policy_regime`, `vehicle_class`, `industry`,
`role_type`, ...). Keep keys lowercase_with_underscores, values short.

== VALUE RULE ==

The `value` must be the COMPACT HUMAN-WRITTEN NUMBER, not the expanded form.
Always provide `magnitude_hint` when a suffix like "billion" or "trillion"
appears, and let `value` hold just the small leading number.

  CORRECT for "$110.6 billion":
     { "value": 110.6, "magnitude_hint": "billion", "unit_raw": "USD" }
  WRONG (double-scaled, will be rejected):
     { "value": 110600000000, "magnitude_hint": "billion" }

  CORRECT for "1.2 crore vehicles":
     { "value": 1.2, "magnitude_hint": "crore", "unit_raw": "units" }
  CORRECT for "32%":
     { "value": 32, "magnitude_hint": null, "unit_raw": "percent" }
"""


def _parse_json_output(raw: str) -> tuple[dict, list[dict]]:
    """Extract (document_frame, list_of_claims) from the LLM response text.

    Strict structured outputs guarantee the shape, but we still defensively
    parse to handle older responses or fallback paths.

    Per-claim `qualifiers` may arrive as either:
      - a list of {"key": str, "value": str} pairs (strict-schema shape), or
      - a flat dict {key: value} (legacy / json_object shape)
    We normalise both to a flat dict here so downstream code is unchanged.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}, []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return {}, []
    if not isinstance(data, dict):
        return {}, []
    frame = data.get("document_frame") or {}
    if not isinstance(frame, dict):
        frame = {}
    claims = data.get("claims") or []
    if not isinstance(claims, list):
        claims = []

    # Normalise per-claim qualifiers from list-of-pairs -> dict
    for c in claims:
        if not isinstance(c, dict):
            continue
        q = c.get("qualifiers")
        if isinstance(q, list):
            d: dict[str, str] = {}
            for pair in q:
                if not isinstance(pair, dict):
                    continue
                k = str(pair.get("key") or "").strip()
                v = str(pair.get("value") or "").strip()
                if k and v:
                    d[k] = v
            c["qualifiers"] = d
        elif not isinstance(q, dict):
            c["qualifiers"] = {}
    return frame, claims


# Strict JSON schema for OpenAI structured outputs. Forces every claim to
# include a non-null `metric_kind` field at the top level. Python-side validation
# additionally rejects empty `metric_kind` strings (strict mode does not support
# minLength).
_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_frame", "claims"],
    "properties": {
        "document_frame": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "primary_subject", "primary_segment", "primary_geography",
                "primary_as_of", "primary_metric_focus",
                "is_sub_market_report", "frame_reasoning",
            ],
            "properties": {
                "primary_subject":      {"type": ["string", "null"]},
                "primary_segment":      {"type": ["string", "null"]},
                "primary_geography":    {"type": ["string", "null"]},
                "primary_as_of":        {"type": ["string", "null"]},
                "primary_metric_focus": {"type": ["string", "null"]},
                "is_sub_market_report": {"type": "boolean"},
                "frame_reasoning":      {"type": "string"},
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "raw_text", "value_raw", "value", "unit_raw",
                    "magnitude_hint", "metric_kind", "qualifiers",
                    "overrides_frame", "confidence",
                ],
                "properties": {
                    "raw_text":        {"type": "string"},
                    "value_raw":       {"type": "string"},
                    "value":           {"type": "number"},
                    "unit_raw":        {"type": "string"},
                    "magnitude_hint":  {"type": ["string", "null"]},
                    "metric_kind":     {"type": "string"},
                    "qualifiers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["key", "value"],
                            "properties": {
                                "key":   {"type": "string"},
                                "value": {"type": "string"},
                            },
                        },
                    },
                    "overrides_frame": {"type": "boolean"},
                    "confidence":      {"type": "number"},
                },
            },
        },
    },
}


def _frame_to_qualifiers(frame: dict) -> dict[str, str]:
    """Convert the document_frame's `primary_*` fields into qualifier-key form
    that can be inherited by individual claims."""
    out: dict[str, str] = {}
    if not isinstance(frame, dict):
        return out
    mapping = {
        "primary_subject":   "subject",
        "primary_segment":   "segment",
        "primary_geography": "geography",
        "primary_as_of":     "as_of",
    }
    for src_key, dst_key in mapping.items():
        v = frame.get(src_key)
        if v is None or v == "":
            continue
        s = str(v).strip()
        if s and s.lower() not in ("null", "none"):
            out[dst_key] = s
    # primary_metric_focus is NOT inherited blindly — many articles report
    # multiple metrics (revenue, share, growth) and frame's metric_focus
    # describes the dominant one only. Let claim-level qualifiers fill it.
    return out


# Removed: _METRIC_NOUN_RE and _raw_text_identifies_metric.
#
# These were a Python safety net that whitelisted market-research metric
# nouns (revenue|share|shipment|...) in raw_text to catch the
# Wikipedia-infobox bug where the LLM kept only a number and dropped the
# row label. They have been removed because:
#   1. The metric_kind required field (enforced via strict json_schema +
#      Python non-empty validation in _build_raw_claim) already prevents
#      label-less claims from being emitted.
#   2. The keyword list was domain-specific (market-research nouns), so it
#      silently rejected valid pharma / clinical / policy claims that
#      didn't happen to use those words.
#   3. The new topic-profile-driven relevance gate in relevance.py handles
#      "is this claim on-topic" via embedding cosine, which is
#      domain-agnostic.
# Net effect: no claim is dropped here purely on raw_text wording.


def _build_raw_claim(record: dict, source: SourceDocument,
                     frame_qualifiers: dict[str, str] | None = None) -> Optional[RawClaim]:
    """Turn an LLM-emitted dict into a validated RawClaim, inheriting any
    missing qualifier keys from the document frame.

    `frame_qualifiers` comes from `_frame_to_qualifiers(document_frame)`.
    Inheritance rule: for each key in frame_qualifiers, if the claim's own
    `qualifiers` dict doesn't already have that key AND the claim is not
    flagged with `overrides_frame=true`, copy the frame's value in.

    DROPS the claim if `metric_kind` (top-level required field) is missing or
    empty. The new schema makes metric_kind mandatory; we enforce non-empty
    here because strict-mode JSON schema cannot enforce minLength.
    """
    try:
        # REQUIRED: metric_kind at top level. Drop the claim if missing/empty.
        metric_kind = str(record.get("metric_kind") or "").strip()
        if not metric_kind or metric_kind.lower() in ("value", "number", "unknown", "n/a"):
            return None

        value_raw = str(record.get("value_raw") or "")
        unit_raw = str(record.get("unit_raw") or "")
        magnitude_hint = record.get("magnitude_hint")

        # Parse value
        try:
            value = float(record.get("value", 0))
        except (TypeError, ValueError):
            return None

        canon_value, unit_family = normalise_value_unit(
            value=value,
            unit_raw=unit_raw,
            value_raw=value_raw,
            magnitude_hint=magnitude_hint,
        )
        if unit_family == "unknown":
            return None
        if canon_value == 0.0 and value != 0.0:
            return None

        # Canonicalise the LLM-emitted qualifiers (sentence-level only).
        # metric_kind is fed in from the top-level field, NOT pulled from
        # qualifiers — even if the LLM put it in both places, the top-level
        # one wins.
        raw_qualifiers = dict(record.get("qualifiers") or {})
        raw_qualifiers["metric_kind"] = metric_kind
        qualifiers = canonicalise_qualifiers(raw_qualifiers)
        overrides_frame = bool(record.get("overrides_frame", False))

        # Inherit frame qualifiers for any keys the claim DIDN'T set itself,
        # unless the claim explicitly overrides the frame.
        if frame_qualifiers and not overrides_frame:
            for k, v in frame_qualifiers.items():
                if k not in qualifiers or not qualifiers[k]:
                    qualifiers[k] = v
        # Even when overrides_frame=true, still fill in any keys the claim
        # didn't set AND aren't the explicit override target. Heuristic: if
        # the claim names `segment`, the override is on segment — inherit
        # subject/geography/as_of from frame anyway (rare edge case).
        elif frame_qualifiers and overrides_frame:
            for k, v in frame_qualifiers.items():
                if k not in qualifiers and k not in ("segment",):
                    # When override flag is set, don't auto-inherit segment
                    qualifiers.setdefault(k, v)

        # If subject is STILL missing after frame inheritance, mark unknown
        # rather than silently bucketing as "global" (per audit fix).
        if not qualifiers.get("subject"):
            qualifiers["subject"] = "unknown"

        raw_text = str(record.get("raw_text") or "")[:600].strip()
        if not raw_text:
            return None

        return RawClaim(
            source_url=source.url,
            source_domain=source.domain,
            source_title=source.title,
            source_tier=source.tier,  # type: ignore[arg-type]
            published_at=source.published,

            raw_text=raw_text,

            value_raw=value_raw,
            value=canon_value,
            unit_raw=unit_raw,
            unit_family=unit_family,  # type: ignore[arg-type]
            unit_magnitude_hint=magnitude_hint,

            qualifiers=qualifiers,
            rank="normal",

            extractor_confidence=float(record.get("confidence", 0.7)),
        )
    except (ValidationError, ValueError, TypeError):
        return None


# ── Public API ──────────────────────────────────────────────────────────────

def _format_structured_metadata(md: dict) -> str:
    """Render schema.org/og: dict as a compact line for the user message."""
    if not md:
        return ""
    bits = []
    for k in ("name", "headline", "about", "description", "keywords",
              "datePublished", "og:title", "og:description"):
        v = md.get(k)
        if v:
            v_short = str(v)[:200]
            bits.append(f"  {k}: {v_short}")
    return "\n".join(bits)


def _extract_cache_key(source: SourceDocument, *, model: str, max_text_chars: int,
                       topic_profile_subject: str) -> str:
    """Build a deterministic SHA-256 cache key for one extract call.

    The cache key includes the URL + content hash + model + char-cap + topic
    subject. Two runs of the same topic on the same page = same key = cached
    result. Different topic = different key (so a clinical-topic extract
    doesn't get reused for a market-topic run on the same page).
    """
    import hashlib
    text = (source.full_text or "")[:max_text_chars]
    h = hashlib.sha256()
    h.update((source.url or "").encode("utf-8"))
    h.update(b"|")
    h.update(text.encode("utf-8"))
    h.update(b"|")
    h.update(model.encode("utf-8"))
    h.update(f"|{max_text_chars}|".encode("utf-8"))
    h.update(topic_profile_subject.encode("utf-8"))
    return h.hexdigest()


_EXTRACT_CACHE_DIR = Path.home() / ".research" / "cache" / "extract"
_EXTRACT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_extract_cache(key: str) -> Optional[list[dict]]:
    p = _EXTRACT_CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_extract_cache(key: str, frame: dict, records: list[dict]) -> None:
    p = _EXTRACT_CACHE_DIR / f"{key}.json"
    try:
        p.write_text(
            json.dumps({"frame": frame, "records": records},
                       ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError:
        pass


def extract_from_source(
    source: SourceDocument,
    *,
    model: str = "gpt-4o-mini",
    max_text_chars: int = 6_000,
    today_iso: Optional[str] = None,
    topic_profile=None,   # Optional[TopicProfile]; avoids hard import cycle
    use_cache: bool = True,
) -> list[RawClaim]:
    """Extract all claims from one source. Returns [] on any failure.

    Produces a `document_frame` first, then claims that inherit from it.
    The user message includes today's date, the article's URL/title, optional
    schema.org structured metadata, and (when supplied) a TopicProfile block
    describing the user's research domain — `expected_metric_kinds` and
    `key_dimensions` from that profile sharpen claim extraction toward the
    measurements that actually answer the topic, without baking domain
    vocabulary into the system prompt.

    `use_cache` (default True): keys are SHA-256 of (URL, content, model,
    char-cap, topic-subject). Cache lives at `~/.research/cache/extract/`.
    """
    if not source.has_content:
        return []

    text = source.full_text[:max_text_chars]

    # Cache lookup before paying for an LLM call
    profile_subject = topic_profile.topic_subject if topic_profile is not None else ""
    cache_key = _extract_cache_key(
        source, model=model, max_text_chars=max_text_chars,
        topic_profile_subject=profile_subject,
    )
    if use_cache:
        cached = _load_extract_cache(cache_key)
        if cached is not None:
            frame_q = canonicalise_qualifiers(_frame_to_qualifiers(cached.get("frame") or {}))
            cached_claims: list[RawClaim] = []
            for rec in (cached.get("records") or []):
                claim = _build_raw_claim(rec, source, frame_qualifiers=frame_q)
                if claim is not None and claim.raw_text:
                    cached_claims.append(claim)
            return cached_claims
    if today_iso is None:
        from datetime import date as _date
        today_iso = _date.today().isoformat()

    md = getattr(source, "structured_metadata", None) or {}
    md_section = ""
    if md:
        md_section = (
            "STRUCTURED METADATA from the page's schema.org / OpenGraph markup\n"
            "(high-confidence — use as ground-truth signal for document_frame):\n"
            f"{_format_structured_metadata(md)}\n\n"
        )

    profile_section = ""
    if topic_profile is not None:
        profile_section = (
            "TOPIC PROFILE (use as the domain anchor — examples of the form,\n"
            "not a closed vocabulary; coin new metric_kind/qualifier labels\n"
            "if the article reports things not on the lists below):\n"
            f"{topic_profile.to_user_message_block()}\n\n"
        )

    user_msg = (
        f"TODAY'S DATE: {today_iso}\n"
        f"{profile_section}"
        f"ARTICLE URL: {source.url}\n"
        f"ARTICLE TITLE: {source.title}\n\n"
        f"{md_section}"
        f"ARTICLE TEXT:\n{text}\n\n"
        f"Return the JSON now. Remember: produce `document_frame` FIRST, "
        f"then claims that inherit from it."
    )

    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=2800,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "claim_extraction",
                    "strict": True,
                    "schema": _EXTRACTION_SCHEMA,
                },
            },
        )
    except Exception as exc:
        print(f"[extractor] OpenAI call failed for {source.url}: {exc}")
        return []

    raw = response.choices[0].message.content or ""
    frame, records = _parse_json_output(raw)
    frame_qualifiers = canonicalise_qualifiers(_frame_to_qualifiers(frame))

    # Cache the parsed LLM output (frame + records) keyed by URL+content+...
    # so future runs on the same page skip the LLM call entirely.
    if use_cache:
        try:
            _save_extract_cache(cache_key, frame, records)
        except Exception:
            pass

    claims: list[RawClaim] = []
    for rec in records:
        claim = _build_raw_claim(rec, source, frame_qualifiers=frame_qualifiers)
        if claim is not None and claim.raw_text:
            claims.append(claim)
    return claims


def extract_from_sources(
    sources: list[SourceDocument],
    *,
    model: str = "gpt-4o-mini",
    max_workers: int = 16,
    today_iso: Optional[str] = None,
    topic_profile=None,
    use_cache: bool = True,
) -> list[RawClaim]:
    """Parallel extraction across sources. Each source is one LLM call.

    `topic_profile` (optional) is passed verbatim to every per-source call so
    the LLM extracts metric_kinds appropriate to the user's domain.

    `use_cache` (default True): each call's parsed JSON output is cached on
    disk keyed by SHA-256 of (URL + content + model + char-cap + topic-
    subject). Repeat runs on the same topic + same URL cost $0.

    `max_workers=16` keeps peak request rate around 240 RPM at gpt-4o-mini,
    well under OpenAI Tier 1's 500 RPM limit. Lower it if you start seeing
    429 errors on a constrained tier.
    """
    all_claims: list[RawClaim] = []
    if not sources:
        return all_claims

    if today_iso is None:
        from datetime import date as _date
        today_iso = _date.today().isoformat()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                extract_from_source, s,
                model=model, today_iso=today_iso, topic_profile=topic_profile,
                use_cache=use_cache,
            ): s
            for s in sources
        }
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                claims = fut.result()
            except Exception as exc:
                print(f"[extractor] worker failed for {src.url}: {exc}")
                continue
            if claims:
                print(f"[extractor] {src.domain:<30} -> {len(claims)} claims")
                all_claims.extend(claims)
    return all_claims

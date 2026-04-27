"""Topic-relevance gate for sources AND claims.

Two stages:

  1. score_source_relevance() — runs BEFORE extract. Embeds each source's
     title + snippet + first 500 chars, drops low-relevance sources from
     extraction entirely. Saves ~80% of the extract cost on irrelevant
     sources (extract is the most expensive stage).

  2. score_claim_relevance() — runs AFTER extract+describe. Catches stray
     off-topic claims that slipped through a relevant source (e.g., a market
     article briefly citing weather data). Belt-and-suspenders.

Cost: source stage embeds ~30 sources ~ 1k tokens; claim stage embeds ~100
claims ~ 3k tokens. Combined ~$0.00010 per run.
"""
from __future__ import annotations

import math
from typing import Optional

from .extractor import _get_client
from .models import RawClaim, TopicProfile
from .search import SourceDocument


_EMBED_MODEL = "text-embedding-3-small"
_PRICE_PER_M = 0.02
_BATCH_SIZE = 512


def _profile_signature_text(profile: TopicProfile) -> str:
    """Build the embedding 'signature' text for a topic profile.

    Concatenates the topic_subject, expected_metric_kinds, key_dimensions, and
    positive_signals into one string. The embedding of this string is what
    each claim's descriptor is compared against.
    """
    parts: list[str] = [profile.topic_subject]
    if profile.expected_metric_kinds:
        parts.append("metrics: " + ", ".join(profile.expected_metric_kinds))
    if profile.key_dimensions:
        parts.append("dimensions: " + ", ".join(profile.key_dimensions))
    if profile.positive_signals:
        parts.append("relevant content: " + ", ".join(profile.positive_signals[:8]))
    return ". ".join(parts)


def _claim_signature_text(claim: RawClaim) -> str:
    """Build the embedding text for one claim. Uses descriptor first (canonical
    short summary) plus the metric_kind qualifier; falls back to raw_text.
    """
    bits: list[str] = []
    if claim.descriptor:
        bits.append(claim.descriptor)
    mk = (claim.qualifiers or {}).get("metric_kind")
    if mk and mk not in (claim.descriptor or ""):
        bits.append(f"metric: {mk.replace('_', ' ')}")
    if not bits:
        bits.append((claim.raw_text or "")[:200])
    return " — ".join(bits)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def score_claim_relevance(
    claims: list[RawClaim],
    profile: TopicProfile,
    *,
    threshold: float = 0.30,
    model: str = _EMBED_MODEL,
    on_progress=None,
) -> tuple[list[RawClaim], float]:
    """Embed the topic profile + every claim's descriptor; score each claim.

    Sets `claim.topic_relevance` (cosine in [0, 1]) and `claim.is_topic_relevant`
    (cosine >= threshold) on every claim in-place. Returns (claims, cost_usd).

    The fallback path (LLM call failure or empty profile) sets
    is_topic_relevant=True on all claims so nothing is dropped silently.
    """
    log = on_progress or (lambda _msg: None)
    if not claims:
        return claims, 0.0

    profile_text = _profile_signature_text(profile)
    if not profile_text.strip() or profile_text.strip() == profile.topic_subject.strip():
        log("[relevance] profile too thin to score against; passing all claims")
        for c in claims:
            c.topic_relevance = None
            c.is_topic_relevant = True
        return claims, 0.0

    client = _get_client()

    # Embed the profile once
    try:
        prof_resp = client.embeddings.create(model=model, input=[profile_text])
    except Exception as exc:
        log(f"[relevance] profile embed failed: {exc}; passing all claims")
        for c in claims:
            c.topic_relevance = None
            c.is_topic_relevant = True
        return claims, 0.0

    profile_embedding = list(prof_resp.data[0].embedding)
    total_tokens = int(getattr(prof_resp.usage, "total_tokens", 0) or 0)

    # Embed each claim's signature in batches
    texts = [_claim_signature_text(c) for c in claims]
    embeddings: list[list[float]] = [[] for _ in claims]
    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start:batch_start + _BATCH_SIZE]
        try:
            resp = client.embeddings.create(model=model, input=batch)
        except Exception as exc:
            log(f"[relevance] claim embed batch at {batch_start} failed: {exc}")
            continue
        for k, datum in enumerate(resp.data):
            embeddings[batch_start + k] = list(datum.embedding)
        total_tokens += int(getattr(resp.usage, "total_tokens", 0) or 0)

    n_relevant = 0
    n_off_topic = 0
    for c, emb in zip(claims, embeddings):
        if not emb:
            c.topic_relevance = None
            c.is_topic_relevant = True
            continue
        sim = _cosine(emb, profile_embedding)
        c.topic_relevance = round(sim, 4)
        c.is_topic_relevant = sim >= threshold
        if c.is_topic_relevant:
            n_relevant += 1
        else:
            n_off_topic += 1

    cost = (total_tokens / 1_000_000) * _PRICE_PER_M
    log(f"[relevance] {n_relevant} on-topic / {n_off_topic} off-topic "
        f"(threshold={threshold}, {total_tokens:,} toks, ${cost:.5f})")
    return claims, cost


def _source_signature_text(s: SourceDocument) -> str:
    """Build the embedding text for one source. Kept short — title + snippet
    + the first 500 chars of full_text + any structured-metadata `about` /
    `description`. The intent is a cheap doc-level filter, not deep semantic
    analysis."""
    parts: list[str] = []
    if s.title:
        parts.append(s.title)
    snippet = (s.snippet or "").strip()
    if snippet:
        parts.append(snippet[:300])
    md = getattr(s, "structured_metadata", None) or {}
    for k in ("about", "description", "headline"):
        v = md.get(k)
        if v:
            parts.append(str(v)[:300])
    if s.full_text:
        parts.append(s.full_text[:500])
    return " — ".join(parts)


def score_source_relevance(
    sources: list[SourceDocument],
    profile: TopicProfile,
    *,
    threshold: float = 0.30,
    model: str = _EMBED_MODEL,
    on_progress=None,
) -> tuple[list[SourceDocument], list[SourceDocument], float]:
    """Pre-extract source-level relevance gate.

    Embeds the topic profile once, embeds each source's title+snippet+first-
    500-chars+schema.org metadata, and partitions sources into kept (cosine
    >= threshold) and dropped (< threshold).

    Cosine and is_topic_relevant are stamped onto each SourceDocument in-place
    so the audit log can report which sources got dropped and why.

    Returns (kept, dropped, cost_usd). On any failure (LLM error, empty
    profile) returns (sources, [], 0.0) — i.e. permissive fallback.
    """
    log = on_progress or (lambda _msg: None)
    if not sources:
        return [], [], 0.0

    profile_text = _profile_signature_text(profile)
    if not profile_text.strip() or profile_text.strip() == profile.topic_subject.strip():
        log("[relevance/source] profile too thin to score against; passing all sources")
        return sources, [], 0.0

    client = _get_client()
    try:
        prof_resp = client.embeddings.create(model=model, input=[profile_text])
    except Exception as exc:
        log(f"[relevance/source] profile embed failed: {exc}; passing all sources")
        return sources, [], 0.0

    profile_embedding = list(prof_resp.data[0].embedding)
    total_tokens = int(getattr(prof_resp.usage, "total_tokens", 0) or 0)

    texts = [_source_signature_text(s) for s in sources]
    embeddings: list[list[float]] = [[] for _ in sources]
    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start:batch_start + _BATCH_SIZE]
        try:
            resp = client.embeddings.create(model=model, input=batch)
        except Exception as exc:
            log(f"[relevance/source] embed batch at {batch_start} failed: {exc}; passing batch")
            continue
        for k, datum in enumerate(resp.data):
            embeddings[batch_start + k] = list(datum.embedding)
        total_tokens += int(getattr(resp.usage, "total_tokens", 0) or 0)

    kept: list[SourceDocument] = []
    dropped: list[SourceDocument] = []
    for s, emb in zip(sources, embeddings):
        if not emb:
            # Failed embedding — pass-through to be safe
            kept.append(s)
            continue
        sim = _cosine(emb, profile_embedding)
        # Stamp onto the document for downstream auditing. We attach via
        # setattr so SourceDocument's pydantic model doesn't need new fields.
        try:
            object.__setattr__(s, "topic_relevance", round(sim, 4))
            object.__setattr__(s, "is_topic_relevant", sim >= threshold)
        except Exception:
            pass
        if sim >= threshold:
            kept.append(s)
        else:
            dropped.append(s)

    cost = (total_tokens / 1_000_000) * _PRICE_PER_M
    log(f"[relevance/source] kept {len(kept)} / dropped {len(dropped)} "
        f"(threshold={threshold}, {total_tokens:,} toks, ${cost:.5f})")
    return kept, dropped, cost

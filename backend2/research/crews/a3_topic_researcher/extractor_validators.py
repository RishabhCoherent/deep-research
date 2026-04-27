"""Post-LLM validators for claim extraction (deterministic, no LLM)."""

from __future__ import annotations

import re

from research.core.types import NumericClaim, Passage


def _norm(s: str) -> str:
    """Normalise whitespace and lowercase for substring matching."""
    return re.sub(r"\s+", " ", s).strip().lower()


# Phase 4b-3: fuzzy threshold tuning.
#
# Approach: three tiers —
#   1. Exact substring (fast path; catches verbatim copy-paste).
#   2. Numeric claim path (excerpt has numbers): every numeric value in the
#      excerpt MUST appear in the passage (strong anti-hallucination signal),
#      AND content-overlap >= _FUZZY_NUMERIC_OVERLAP. Permissive on overlap
#      because the number-match check is already doing the heavy grounding.
#   3. Qualitative claim path (no numbers in excerpt): require strong content
#      overlap (>= _FUZZY_QUAL_OVERLAP) since numbers can't anchor the claim.
#
# Why two thresholds: the recursive investigator (Phase 4b-1) produces
# focused PART-passages (short single-fact snippets). Sonnet/Haiku then
# writes longer `raw_excerpt`s than the focused passage actually contains,
# adding LLM context (study design, patient population). The strict 0.70
# threshold dropped 4 of 7 valid numeric claims on the first Phase 4b run.
# Lowering the numeric path to 0.40 keeps those without making qualitative
# claims pass as long as their key entity tokens still appear.
_FUZZY_NUMERIC_OVERLAP = 0.40
_FUZZY_QUAL_OVERLAP    = 0.70
_FUZZY_MIN_LENGTH      = 30   # below this, fuzzy is too noisy

# Stopwords stripped before computing content-word overlap. Kept short and
# domain-neutral; the overlap calculation just needs the substantive nouns
# / verbs / adjectives to match.
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "for",
    "to", "is", "was", "were", "are", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "by", "with", "from", "as", "than", "that",
    "this", "these", "those", "it", "its", "their", "they", "them",
    "approximately", "about", "around", "roughly", "nearly", "almost",
    "over", "under", "more", "less", "during", "while", "when", "then",
}


def _content_tokens(s: str) -> set[str]:
    """Tokens from `s`, lowercased, alphanumeric-only, stopwords removed."""
    return {t for t in re.findall(r"\w+", s.lower()) if t not in _STOP_WORDS}


def _numeric_values(s: str) -> set[float]:
    """Extract pure numeric values as floats. Handles `22`, `22.0`, `22%`,
    `1,200`, `$1.5`, `13.6 months`, etc. Returns the set of distinct values.

    Why floats not strings: the LLM commonly rounds (`22.0` -> `22`) or strips
    units (`22.0%` -> `22.0` / `22`). A raw string-token comparison would
    reject these as different. Float equality (with rounding to 4 decimals)
    treats all of them as the same number.
    """
    out: set[float] = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", s):
        try:
            n = float(m.group(0).replace(",", ""))
            out.add(round(n, 4))
        except ValueError:
            continue
    return out


def _fuzzy_in_passage(excerpt: str, passage_text: str,
                      *, numeric_overlap: float = _FUZZY_NUMERIC_OVERLAP,
                      qual_overlap: float = _FUZZY_QUAL_OVERLAP) -> bool:
    """Three-tier 'is this excerpt grounded in this passage' check.

    Tier 1 (fast): normalised substring match — catches verbatim copies.

    Tier 2 (numeric claim, excerpt contains numbers):
        a) Every numeric VALUE in the excerpt must appear in the passage
           (float comparison so `22.0` matches `22`). Strong
           anti-hallucination guard: an LLM that fabricates "22.0 months"
           against a passage saying "13.6 months" gets rejected here.
        b) Content-overlap >= numeric_overlap (default 0.40 — permissive,
           because the number guard does the heavy lifting). This catches
           the case where excerpt and passage share at least the named
           entity (drug, cohort, study) even if the LLM padded with
           explanatory context not in the passage.

    Tier 3 (qualitative claim, no numbers in excerpt):
        Content-overlap >= qual_overlap (default 0.70 — strict, because
        without numbers we have no other anchor against hallucination).

    For very short excerpts (< _FUZZY_MIN_LENGTH chars) we skip the fuzzy
    path — short excerpts must match by substring or be rejected.
    """
    n_excerpt = _norm(excerpt)
    n_passage = _norm(passage_text)
    if not n_excerpt:
        return False
    # Tier 1: substring (fast path)
    if n_excerpt in n_passage:
        return True
    if len(n_excerpt) < _FUZZY_MIN_LENGTH:
        return False

    # Tier 2/3: compute numeric values + content tokens once
    e_nums = _numeric_values(n_excerpt)
    e_content = _content_tokens(n_excerpt)
    if not e_content:
        return False
    p_content = _content_tokens(n_passage)
    overlap = len(e_content & p_content) / len(e_content)

    if e_nums:
        # Numeric claim path — strict on numbers, permissive on overlap
        p_nums = _numeric_values(n_passage)
        if not e_nums.issubset(p_nums):
            return False
        return overlap >= numeric_overlap
    # Qualitative claim path — strict on overlap (numbers can't anchor)
    return overlap >= qual_overlap


def assert_excerpts_in_passages(
    claims: list[NumericClaim],
    passages: list[Passage],
    *,
    numeric_overlap: float = _FUZZY_NUMERIC_OVERLAP,
    qual_overlap: float = _FUZZY_QUAL_OVERLAP,
) -> list[NumericClaim]:
    """Keep only claims whose raw_excerpt is grounded in its source passage.

    Uses three-tier match (see `_fuzzy_in_passage`):
      - exact substring;
      - numeric path (numbers must match + 0.40 overlap);
      - qualitative path (0.70 overlap).
    Reject claims whose URL has no passage.

    Silently drops violators; caller should log the drop count.
    """
    by_url: dict[str, str] = {p.url: _norm(p.text) for p in passages}
    valid: list[NumericClaim] = []
    for claim in claims:
        passage_text = by_url.get(claim.citation.url)
        if passage_text is None:
            continue
        if _fuzzy_in_passage(claim.raw_excerpt, passage_text,
                             numeric_overlap=numeric_overlap,
                             qual_overlap=qual_overlap):
            valid.append(claim)
    return valid


def assert_citation_complete(claims: list[NumericClaim]) -> list[NumericClaim]:
    """Drop claims missing a citation URL."""
    return [c for c in claims if c.citation and c.citation.url]

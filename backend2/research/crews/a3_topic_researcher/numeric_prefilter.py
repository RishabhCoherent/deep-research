"""Stage 1 of hybrid claim extraction: deterministic numeric span finder.

Pure Python — no LLM, no rate limit, no cost. Runs in ~ms per passage.

Design
------
For each fetched passage:
  1. Sentence-split (regex; handles common abbreviations).
  2. For each sentence, find every numeric span via two parallel finders:
       - quantulum3 (structured: value + unit + surface form)
       - regex fallback (catches what quantulum3 misses — Indian-style
         "crore"/"lakh", informal "$10B", "5K USD", etc.)
     Dedupe overlapping spans within a sentence (prefer quantulum3 when both
     hit the same position).
  3. Filter noise: drop sentences shorter than _MIN_SENTENCE_CHARS, drop
     sentences that are pure number-noise (table cells, page numbers,
     version strings).
  4. Emit one NumericCandidate per (passage, sentence, primary span). If a
     sentence has multiple distinct spans, emit one candidate per span so
     the LLM can structure each value separately (range "$10-12B" → two
     candidates; multi-fact sentence "revenue $5B, growth 12%" → two).

The LLM (Stage 2) only fills in qualifiers (subject, metric_kind, scope,
as_of, segment) for these candidates and copies the verbatim sentence
through as raw_excerpt. No yield cap — every viable candidate gets
structured.

Optional: spaCy NER hints (ORG/GPE/DATE) are added to candidates IF the
en_core_web_sm model is installed. Guarded with try/except so it's not a
hard dependency.
"""

from __future__ import annotations

import re
import structlog
from dataclasses import dataclass

from research.core.types import Passage
from .schemas import NumericCandidate

log = structlog.get_logger(__name__)


# ── Tunables ────────────────────────────────────────────────────────────────

_MIN_SENTENCE_CHARS = 30   # below this, sentence is too noisy to be a claim
_MAX_SENTENCE_CHARS = 600  # above this, almost certainly a paragraph mis-split
_MAX_CANDIDATES_PER_PASSAGE = 25   # belt-and-braces: cap so one bad passage
                                   # (parsed PDF table) can't flood the LLM


# Indian-style scale words quantulum3 misses. Multipliers in raw units (no
# currency conversion — that's downstream).
_SCALE_WORDS = {
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
    "lakh": 100_000,
    "crore": 10_000_000,
    "k": 1_000,         # ambiguous; only matched when adjacent to a number
    "m": 1_000_000,
    "mn": 1_000_000,
    "bn": 1_000_000_000,
    "tn": 1_000_000_000_000,
    "cr": 10_000_000,   # crore abbreviation
}

# Currency / unit prefixes that often precede a number ("$10B", "₹1 Lakh Cr").
_CURRENCY_SYMBOLS = "₹$€£¥"


# Regex fallback: matches a number (with optional decimal / commas / leading
# currency symbol) followed optionally by a scale word and/or unit suffix.
# We deliberately keep this loose — Stage 2's LLM filters meaningful from
# noise. Better to over-extract here than miss a claim.
#
# Number alternation prefers the comma-separated form ("76,000") and falls
# back to a plain digit run ("2030", "5.5"). The plain form last so it
# doesn't eat a longer comma-grouped number prematurely.
_NUMBER_RE = re.compile(
    rf"""
    (?P<full>
        (?:[{_CURRENCY_SYMBOLS}]\s*)?
        (?:
            \d{{1,3}}(?:[,\s]\d{{3}})+(?:\.\d+)?    # 1,200 / 76,000 / 1,234.5
          | \d+(?:\.\d+)?                            # 2030 / 5.5 / 100
        )
        (?:\s*(?:thousand|million|billion|trillion|lakh|crore|k|mn|bn|tn|cr|m)\b){{0,2}}
        (?:\s*(?:%|percent|pp|bps|USD|INR|EUR|GBP|kWh|MWh|GWh|TWh|MW|GW|TW))?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Sentence splitter that preserves abbreviations. Split on . ! ? followed by
# whitespace + capital letter, but not after common abbreviations. Newlines
# also count as sentence boundaries (handles bulleted/listed text).
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "co", "inc", "ltd",
    "corp", "vs", "etc", "e.g", "i.e", "cf", "no", "vol", "fig", "p", "pp",
    "approx", "est", "avg", "min", "max", "u.s", "u.k", "u.n",
}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Conservative — keeps short sentences in
    case they're tabular claims ('Revenue: $5B'). Caller filters by length.

    Newline policy: single newlines that occur mid-sentence (no terminal
    punctuation on the prior line) are joined back together — scraped HTML
    routinely wraps paragraphs at arbitrary widths. Only paragraph breaks
    (blank lines) and bullets are treated as hard boundaries.
    """
    text = re.sub(r"\r\n", "\n", text)
    # Bullet list markers → sentence boundary
    text = re.sub(r"^\s*[\-•·*]\s+", "\n\n", text, flags=re.MULTILINE)

    # Collapse single newlines that don't follow terminal punctuation (these
    # are wrap artifacts, not boundaries). Preserve double newlines.
    text = re.sub(r"(?<![.!?:])\n(?!\n)", " ", text)
    # Now any remaining \n is a real paragraph boundary.
    chunks = [c.strip() for c in re.split(r"\n+", text) if c.strip()]

    out: list[str] = []
    for chunk in chunks:
        # Within each chunk, split on . / ! / ? followed by whitespace + capital.
        # Don't split if preceded by an abbreviation token.
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\(\[])", chunk)
        for p in parts:
            p_stripped = p.strip()
            if not p_stripped:
                continue
            # Glue back if last token before terminator is an abbrev
            if out and _ends_with_abbrev(out[-1]):
                out[-1] = out[-1] + " " + p_stripped
            else:
                out.append(p_stripped)
    return out


def _ends_with_abbrev(s: str) -> bool:
    """True if s ends with a common abbreviation followed by '.'."""
    m = re.search(r"\b(\w+)\.\s*$", s)
    if not m:
        return False
    return m.group(1).lower() in _ABBREV


@dataclass
class _Span:
    """Internal: a numeric span found in a sentence."""
    start: int           # char offset within the sentence
    end: int
    surface: str         # the literal matched text
    value: float | None  # parsed numeric value (None if parse failed)
    unit: str            # unit surface form ("USD", "%", "GWh", "" if none)
    source: str          # "quantulum3" | "regex"


def _quantulum_spans(sentence: str) -> list[_Span]:
    """Use quantulum3 to find quantities. Returns [] if quantulum3 isn't
    installed or fails on this sentence. Drops obvious mis-parses where
    the unit contains stopwords like 'to the' (quantulum3 sometimes
    grabs the next number's words as unit tokens)."""
    try:
        from quantulum3 import parser as q_parser
    except ImportError:
        return []
    try:
        quants = q_parser.parse(sentence)
    except Exception:
        return []
    out: list[_Span] = []
    for q in quants:
        try:
            value = float(q.value) if q.value is not None else None
            unit = str(q.unit.name) if q.unit and q.unit.name != "dimensionless" else ""
            # Reject mis-parses: unit shouldn't contain function words
            if unit and re.search(r"\b(to the|of the|and|the)\b", unit):
                continue
            out.append(_Span(
                start=q.span[0],
                end=q.span[1],
                surface=q.surface,
                value=value,
                unit=unit,
                source="quantulum3",
            ))
        except Exception:
            continue
    return out


def _regex_spans(sentence: str) -> list[_Span]:
    """Fallback regex span finder. Catches Indian-style 'crore'/'lakh',
    informal '$10B', and quantulum3 misses on currency-prefix patterns."""
    out: list[_Span] = []
    for m in _NUMBER_RE.finditer(sentence):
        surface = m.group("full").strip()
        if not surface:
            continue
        value, unit = _parse_regex_value(surface)
        out.append(_Span(
            start=m.start(),
            end=m.end(),
            surface=surface,
            value=value,
            unit=unit,
            source="regex",
        ))
    return out


def _parse_regex_value(surface: str) -> tuple[float | None, str]:
    """Best-effort parse of a regex-matched number. Returns (value, unit).
    Unit is the surface-form suffix ('billion', '%', 'USD', ...); Stage 2
    LLM normalises it. Returns (None, '') if parse fails."""
    s = surface.strip()
    # Strip leading currency
    leading_currency = ""
    if s and s[0] in _CURRENCY_SYMBOLS:
        leading_currency = s[0]
        s = s[1:].strip()

    # Find the numeric prefix
    m_num = re.match(r"[\d,\s]*\d(?:\.\d+)?", s)
    if not m_num:
        return None, ""
    num_str = m_num.group(0).replace(",", "").replace(" ", "")
    try:
        value = float(num_str)
    except ValueError:
        return None, ""

    # Tail: scale word + unit
    tail = s[m_num.end():].strip().lower()
    unit_parts: list[str] = []
    if leading_currency:
        unit_parts.append(leading_currency)

    # Apply scale word multiplier(s). Allow up to 2 chained scale words to
    # handle Indian "lakh crore" (= 1e5 × 1e7 = 1e12).
    scale_re = re.compile(r"(thousand|million|billion|trillion|lakh|crore|cr|mn|bn|tn|k|m)\b", re.IGNORECASE)
    for _ in range(2):
        scale_match = scale_re.match(tail)
        if not scale_match:
            break
        scale_word = scale_match.group(1).lower()
        value *= _SCALE_WORDS.get(scale_word, 1)
        unit_parts.append(scale_word)
        tail = tail[scale_match.end():].strip()

    # Remainder is the unit (%, USD, GWh, ...)
    if tail:
        unit_parts.append(tail)

    return value, " ".join(unit_parts).strip()


def _dedupe_spans(spans: list[_Span]) -> list[_Span]:
    """Drop overlapping spans, preferring (in order):
       1. Spans that pass the usefulness filter (non-zero, non-year, etc).
          A useless span never wins over a useful overlapping one.
       2. Wider spans (more characters covered = more informative — e.g.
          "₹91,000 crore" beats "000" even though both come from the same
          source).
       3. quantulum3 over regex when widths are equal (structured units).
    """
    if not spans:
        return []
    # Annotate usefulness so we can prefer useful spans on overlap.
    annotated = [(sp, _is_useful_span(sp)) for sp in spans]
    # Sort by (start ascending, length descending). Wider spans considered
    # first at any given start position so they're seeded as the kept span.
    annotated.sort(key=lambda x: (x[0].start, -(x[0].end - x[0].start)))

    kept: list[tuple[_Span, bool]] = []
    for sp, useful in annotated:
        # Find any existing kept span this one overlaps with
        overlap_idx = None
        for i, (k, _) in enumerate(kept):
            if not (sp.end <= k.start or sp.start >= k.end):
                overlap_idx = i
                break
        if overlap_idx is None:
            kept.append((sp, useful))
            continue

        k_sp, k_useful = kept[overlap_idx]
        # Decide: replace, or skip
        new_wins = False
        if useful and not k_useful:
            new_wins = True
        elif useful == k_useful:
            sp_len = sp.end - sp.start
            k_len  = k_sp.end - k_sp.start
            if sp_len > k_len:
                new_wins = True
            elif sp_len == k_len and sp.source == "quantulum3" and k_sp.source == "regex":
                new_wins = True
        if new_wins:
            kept[overlap_idx] = (sp, useful)
        # else: keep existing
    # Filter to useful only
    return [sp for sp, useful in kept if useful]


def _is_useful_span(sp: _Span) -> bool:
    """Reject spans that are obviously useless:
       - missing parsed value
       - value is exactly 0 (table noise, page numbers, '$0' boilerplate)
       - value is implausibly large (parser glitch)
       - surface form is just a year-like 4-digit number with no unit
         (we'd capture the same year via as_of qualifier downstream — no
         need to emit "2024" as a standalone numeric claim)
    """
    if sp.value is None:
        return False
    if sp.value <= 0:
        return False
    if abs(sp.value) > 1e18:
        return False
    # Year-only spans: 4-digit number, no unit, no scale word in surface
    if not sp.unit and re.fullmatch(r"(19|20)\d{2}", sp.surface.strip()):
        return False
    return True


def _is_meaningful_sentence(sentence: str) -> bool:
    """Reject sentences that are obvious noise:
       - too short / too long
       - mostly punctuation or whitespace
       - looks like a page number / version string / table cell
    """
    s = sentence.strip()
    if len(s) < _MIN_SENTENCE_CHARS or len(s) > _MAX_SENTENCE_CHARS:
        return False
    # Need at least 4 alpha-words to be a sentence (kills "Page 5", "1.2.3", "v3.4.0")
    word_count = len(re.findall(r"[A-Za-z]{2,}", s))
    if word_count < 4:
        return False
    return True


def _surrounding_window(sentences: list[str], idx: int) -> str:
    """Return the sentence at idx with ±1 neighbour for LLM context. Bounded
    so we never blow past 800 chars."""
    lo = max(0, idx - 1)
    hi = min(len(sentences), idx + 2)
    window = " ".join(sentences[lo:hi])
    return window[:800]


# ── spaCy entity hints (optional) ──────────────────────────────────────────

_SPACY_NLP = None
_SPACY_TRIED = False


def _maybe_load_spacy():
    """Lazy-load spaCy en_core_web_sm if installed. Idempotent. Returns
    None if not available — entity hints become empty dict."""
    global _SPACY_NLP, _SPACY_TRIED
    if _SPACY_TRIED:
        return _SPACY_NLP
    _SPACY_TRIED = True
    try:
        import spacy
        _SPACY_NLP = spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        _SPACY_NLP = None
    return _SPACY_NLP


def _entity_hints(sentence: str) -> dict[str, list[str]]:
    """Return ORG/GPE/DATE entity surface forms, if spaCy is available."""
    nlp = _maybe_load_spacy()
    if nlp is None:
        return {}
    try:
        doc = nlp(sentence)
    except Exception:
        return {}
    hints: dict[str, list[str]] = {}
    for ent in doc.ents:
        if ent.label_ in {"ORG", "GPE", "DATE", "MONEY", "PERCENT"}:
            hints.setdefault(ent.label_, []).append(ent.text)
    return hints


# ── Main entry ──────────────────────────────────────────────────────────────


def find_numeric_candidates(passages: list[Passage]) -> list[NumericCandidate]:
    """Run Stage 1 on a list of passages. Pure-Python, deterministic."""
    candidates: list[NumericCandidate] = []
    n_passages_with_candidates = 0

    for p_idx, passage in enumerate(passages):
        text = passage.text or ""
        if not text:
            continue
        sentences = _split_sentences(text)
        if not sentences:
            continue

        passage_candidates = 0
        for s_idx, sentence in enumerate(sentences):
            sentence_clean = re.sub(r"\s+", " ", sentence).strip()
            if not _is_meaningful_sentence(sentence_clean):
                continue
            spans = _dedupe_spans(
                _quantulum_spans(sentence_clean) + _regex_spans(sentence_clean)
            )
            if not spans:
                continue
            window = _surrounding_window(sentences, s_idx)
            window_clean = re.sub(r"\s+", " ", window).strip()
            hints = _entity_hints(sentence_clean)
            seen_values_in_sentence: set[float] = set()
            for sp in spans:
                # Dedupe within sentence: if two spans yield the same value,
                # keep only the first.
                if sp.value in seen_values_in_sentence:
                    continue
                seen_values_in_sentence.add(sp.value)
                candidates.append(NumericCandidate(
                    passage_idx=p_idx,
                    sentence_text=sentence_clean,
                    raw_value=sp.value,
                    raw_unit=sp.unit,
                    surrounding_window=window_clean,
                    entity_hints=hints,
                ))
                passage_candidates += 1
                if passage_candidates >= _MAX_CANDIDATES_PER_PASSAGE:
                    break
            if passage_candidates >= _MAX_CANDIDATES_PER_PASSAGE:
                break
        if passage_candidates > 0:
            n_passages_with_candidates += 1

    log.info(
        "numeric_prefilter.done",
        n_passages=len(passages),
        n_passages_with_candidates=n_passages_with_candidates,
        n_candidates=len(candidates),
        spacy_loaded=_SPACY_NLP is not None,
    )
    return candidates


# ── Qualitative candidate extraction ─────────────────────────────────────────

_QUAL_SIGNALS: frozenset[str] = frozenset([
    # Causation / drivers
    "because", "due to", "driven by", "resulting in", "led to",
    "attributed to", "caused by", "fueled by", "stemming from",
    # Trends / direction
    "increasing", "declining", "growing", "rising", "falling",
    "surging", "accelerating", "contracting", "expanding", "slowing",
    # Forward-looking
    "will", "expected", "projected", "forecast", "anticipated",
    "likely", "poised", "set to", "on track",
    # Comparative
    "compared to", "versus", "outperformed", "exceeded", "surpassed",
    "ahead of", "relative to",
    # Events / institutional actions
    "launched", "announced", "deployed", "signed", "approved",
    "partnered", "acquired", "invested", "committed", "allocated",
    # Risk / opportunity
    "risk", "challenge", "barrier", "bottleneck", "constraint",
    "opportunity", "advantage", "threat", "concern", "uncertainty",
    # Policy / regulation
    "regulation", "policy", "mandate", "legislation", "framework",
    "subsidy", "tariff", "ban", "incentive", "standard",
    # Strategy
    "strategy", "initiative", "roadmap", "target", "goal",
    "priority", "program", "objective",
])


def find_qualitative_candidates(
    passages: list[Passage],
    max_per_passage: int = 3,
    max_total: int = 40,
) -> list[dict]:
    """Find high-value qualitative sentences from passages.

    Complements the numeric prefilter by capturing causal relationships,
    policy context, strategic direction, and risk factors — sentences that
    carry analytical weight but contain no dominant numeric span.

    Returns a list of dicts sorted by score:
      {sentence, url, title, score}
    """
    results: list[dict] = []

    for passage in passages:
        text = passage.text or ""
        if not text:
            continue
        sentences = _split_sentences(text)
        passage_results: list[dict] = []

        for sentence in sentences:
            sentence_clean = re.sub(r"\s+", " ", sentence).strip()
            if not _is_meaningful_sentence(sentence_clean):
                continue
            # Skip sentences where >10% of chars are digits — those are handled
            # by the numeric prefilter and would create duplicate context.
            digit_ratio = sum(c.isdigit() for c in sentence_clean) / max(len(sentence_clean), 1)
            if digit_ratio > 0.10:
                continue
            lower = sentence_clean.lower()
            hits = sum(1 for sig in _QUAL_SIGNALS if sig in lower)
            if hits == 0:
                continue
            length_bonus = min(len(sentence_clean) / 150, 1.5)
            score = hits + length_bonus
            passage_results.append({
                "sentence": sentence_clean,
                "url":      passage.url,
                "title":    passage.title or "",
                "score":    score,
            })

        passage_results.sort(key=lambda x: -x["score"])
        results.extend(passage_results[:max_per_passage])

    results.sort(key=lambda x: -x["score"])
    return results[:max_total]


# ── Standalone smoke test ──────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    sample_text = """
    The Semicon India Program (₹76,000 crore / $10B+) aims to boost local
    manufacturing. Tata Electronics announced a ₹91,000 crore (~$11 billion)
    investment in March 2024. The Indian semiconductor market is projected
    to grow at 19% CAGR, reaching $103 billion by 2030. Page 5 of 17.
    """
    p = Passage(
        url="https://example.com/test",
        title="Test",
        text=sample_text,
    )
    cands = find_numeric_candidates([p])
    print(f"Found {len(cands)} candidates:")
    for c in cands:
        print(json.dumps(c.model_dump(), indent=2, default=str))

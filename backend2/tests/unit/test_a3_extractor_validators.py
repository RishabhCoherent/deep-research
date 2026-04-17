"""Unit tests for Agent 3 extractor validators."""

import pytest
from datetime import datetime, timezone

from research.core.types import NumericClaim, Citation, Passage, AuthorityTier
from research.crews.a3_topic_researcher.extractor_validators import (
    assert_excerpts_in_passages, assert_citation_complete
)


def _citation(url="https://example.com/a"):
    return Citation(url=url, title="Test Source", authority_tier=AuthorityTier.ANALYST_FIRM)


def _passage(url="https://example.com/a", text="Battery price fell to $89/kWh in Q1 2026."):
    return Passage(
        url=url, text=text,
        accessed=datetime.now(timezone.utc).isoformat(),
        authority_tier=AuthorityTier.ANALYST_FIRM,
    )


def _claim(excerpt="Battery price fell to $89/kWh in Q1 2026.", url="https://example.com/a"):
    return NumericClaim(
        metric="EV battery cell price",
        value=89.0,
        unit="USD/kWh",
        as_of="2026-Q1",
        scope="global",
        raw_excerpt=excerpt,
        citation=_citation(url=url),
    )


class TestExcerptValidation:

    def test_exact_excerpt_kept(self):
        passages = [_passage()]
        claims = [_claim()]
        valid = assert_excerpts_in_passages(claims, passages)
        assert len(valid) == 1

    def test_paraphrased_excerpt_dropped(self):
        passages = [_passage()]
        claims = [_claim(excerpt="The price dropped to 89 dollars per kWh in early 2026.")]
        valid = assert_excerpts_in_passages(claims, passages)
        assert len(valid) == 0

    def test_case_insensitive_match(self):
        passages = [_passage(text="BATTERY PRICE FELL TO $89/KWH IN Q1 2026.")]
        claims = [_claim(excerpt="battery price fell to $89/kWh in Q1 2026.")]
        valid = assert_excerpts_in_passages(claims, passages)
        assert len(valid) == 1

    def test_whitespace_normalised_match(self):
        passages = [_passage(text="Battery  price  fell   to  $89/kWh  in Q1 2026.")]
        claims = [_claim(excerpt="Battery price fell to $89/kWh in Q1 2026.")]
        valid = assert_excerpts_in_passages(claims, passages)
        assert len(valid) == 1

    def test_wrong_url_drops_claim(self):
        passages = [_passage(url="https://example.com/a")]
        claims = [_claim(url="https://different.com/b")]
        valid = assert_excerpts_in_passages(claims, passages)
        assert len(valid) == 0

    def test_multiple_claims_partial_drop(self):
        passages = [_passage()]
        valid_c = _claim()
        bad_c = _claim(excerpt="This text does not appear in any passage.")
        valid = assert_excerpts_in_passages([valid_c, bad_c], passages)
        assert len(valid) == 1
        assert valid[0].raw_excerpt == valid_c.raw_excerpt


class TestCitationComplete:

    def test_claim_with_url_kept(self):
        claims = [_claim()]
        result = assert_citation_complete(claims)
        assert len(result) == 1

    def test_claim_without_url_dropped(self):
        c = _claim()
        c.citation.url = ""
        result = assert_citation_complete([c])
        assert len(result) == 0

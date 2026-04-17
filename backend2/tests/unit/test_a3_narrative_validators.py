"""Unit tests for Agent 3 narrative validators."""

import pytest
from research.core.types import Footnote, Citation, AuthorityTier
from research.crews.a3_topic_researcher.narrative_validators import (
    assert_word_count, assert_footnote_integrity, word_count
)


def _footnote(n: int):
    return Footnote(
        n=n,
        citation=Citation(url=f"https://example.com/{n}", authority_tier=AuthorityTier.ANALYST_FIRM)
    )


class TestWordCount:

    def test_valid_word_count(self):
        narrative = " ".join(["word"] * 500)
        assert_word_count(narrative)  # should not raise

    def test_too_short_rejected(self):
        narrative = " ".join(["word"] * 399)
        with pytest.raises(AssertionError, match="399"):
            assert_word_count(narrative)

    def test_too_long_rejected(self):
        narrative = " ".join(["word"] * 801)
        with pytest.raises(AssertionError, match="801"):
            assert_word_count(narrative)

    def test_exactly_400_ok(self):
        narrative = " ".join(["word"] * 400)
        assert_word_count(narrative)

    def test_exactly_800_ok(self):
        narrative = " ".join(["word"] * 800)
        assert_word_count(narrative)

    def test_word_count_helper(self):
        assert word_count("one two three") == 3


class TestFootnoteIntegrity:

    def test_matching_footnotes_ok(self):
        narrative = "The price fell [1] and supply dropped [2]."
        footnotes = [_footnote(1), _footnote(2)]
        assert_footnote_integrity(narrative, footnotes)  # should not raise

    def test_missing_footnote_declaration(self):
        narrative = "The price fell [1] and supply dropped [2]."
        footnotes = [_footnote(1)]  # missing [2]
        with pytest.raises(AssertionError, match="not declared"):
            assert_footnote_integrity(narrative, footnotes)

    def test_extra_footnote_not_cited(self):
        narrative = "The price fell [1]."
        footnotes = [_footnote(1), _footnote(2)]  # [2] never used
        with pytest.raises(AssertionError, match="never cited"):
            assert_footnote_integrity(narrative, footnotes)

    def test_no_footnotes_no_citations_ok(self):
        narrative = "The market is large and growing."
        footnotes = []
        assert_footnote_integrity(narrative, footnotes)  # should not raise

    def test_two_digit_footnote_ok(self):
        narrative = "Data shows growth [10] and contraction [11]."
        footnotes = [_footnote(10), _footnote(11)]
        assert_footnote_integrity(narrative, footnotes)

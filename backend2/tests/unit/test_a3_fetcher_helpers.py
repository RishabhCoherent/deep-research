"""Unit tests for Agent 3 deterministic fetcher helpers."""

import pytest
from datetime import datetime, timezone
from research.core.types import Passage, AuthorityTier
from research.crews.a3_topic_researcher.fetcher import (
    dedupe_by_url, rank_passages, authority_score, composite_score
)


def _p(url="https://example.com", tier=AuthorityTier.ANALYST_FIRM,
       text="EV battery price fell 38% in 2026."):
    return Passage(
        url=url, text=text,
        accessed=datetime.now(timezone.utc).isoformat(),
        authority_tier=tier,
    )


class TestDedupeByUrl:

    def test_unique_urls_unchanged(self):
        passages = [_p("https://a.com"), _p("https://b.com"), _p("https://c.com")]
        result = dedupe_by_url(passages)
        assert len(result) == 3

    def test_duplicate_url_removed(self):
        passages = [_p("https://a.com"), _p("https://a.com"), _p("https://b.com")]
        result = dedupe_by_url(passages)
        assert len(result) == 2

    def test_trailing_slash_deduped(self):
        passages = [_p("https://a.com/page"), _p("https://a.com/page/")]
        result = dedupe_by_url(passages)
        assert len(result) == 1

    def test_first_occurrence_kept(self):
        p1 = _p("https://a.com", tier=AuthorityTier.GOVERNMENT)
        p2 = _p("https://a.com", tier=AuthorityTier.BLOG)
        result = dedupe_by_url([p1, p2])
        assert result[0].authority_tier == AuthorityTier.GOVERNMENT


class TestAuthorityScore:

    def test_government_highest(self):
        assert authority_score(_p(tier=AuthorityTier.GOVERNMENT)) > \
               authority_score(_p(tier=AuthorityTier.ANALYST_FIRM))

    def test_blog_lowest(self):
        assert authority_score(_p(tier=AuthorityTier.BLOG)) < \
               authority_score(_p(tier=AuthorityTier.TRADE_PRESS))


class TestRankPassages:

    def test_top_n_respected(self):
        passages = [_p(f"https://example.com/{i}") for i in range(15)]
        ranked = rank_passages(passages, "EV battery", top_n=5)
        assert len(ranked) <= 5

    def test_dedupes_before_ranking(self):
        passages = [_p("https://dup.com")] * 5 + [_p("https://unique.com")]
        ranked = rank_passages(passages, "EV battery", top_n=10)
        assert len(ranked) == 2

    def test_high_authority_ranked_first(self):
        gov = _p("https://iea.org", tier=AuthorityTier.GOVERNMENT,
                 text="EV battery market 2026 analysis.")
        blog = _p("https://blog.com", tier=AuthorityTier.BLOG,
                  text="EV battery market 2026 analysis.")
        ranked = rank_passages([blog, gov], "EV battery 2026", top_n=10)
        assert ranked[0].url == "https://iea.org"

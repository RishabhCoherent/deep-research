"""Unit tests for Agent 3 schemas."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from research.core.types import (
    SearchQuery, PlannedSearch, Passage, Footnote, Citation,
    NumericClaim, Observation, AuthorityTier
)
from research.crews.a3_topic_researcher.schemas import (
    SearchPlan, FetchedSources, ExtractedClaims, TopicSummary, A3Output
)


def _passage(url="https://example.com/a", text="Battery price fell to $89/kWh in Q1 2026."):
    return Passage(
        url=url, text=text,
        accessed=datetime.now(timezone.utc).isoformat(),
        authority_tier=AuthorityTier.ANALYST_FIRM,
    )


def _plan(sq_text="What is market size?", n_queries=1):
    queries = [SearchQuery(text=f"EV battery market size 2026 USD billion") for _ in range(n_queries)]
    return PlannedSearch(sub_question_text=sq_text, queries=queries, rationale="Targets numeric size data.")


class TestSearchPlan:

    def test_valid_plan(self):
        sp = SearchPlan(plans=[_plan() for _ in range(4)])
        assert len(sp.plans) == 4

    def test_zero_plans_rejected(self):
        with pytest.raises(ValidationError, match="1-8"):
            SearchPlan(plans=[])

    def test_too_many_plans_rejected(self):
        with pytest.raises(ValidationError, match="1-8"):
            SearchPlan(plans=[_plan() for _ in range(9)])

    def test_total_queries_over_12_rejected(self):
        # 7 plans × 2 queries = 14 > 12
        plans = [_plan(n_queries=2) for _ in range(7)]
        with pytest.raises(ValidationError, match="12"):
            SearchPlan(plans=plans)

    def test_exactly_12_queries_ok(self):
        # 6 plans × 2 = 12
        plans = [_plan(f"Q{i}", n_queries=2) for i in range(6)]
        sp = SearchPlan(plans=plans)
        assert sum(len(p.queries) for p in sp.plans) == 12


class TestFetchedSources:

    def test_valid_sources(self):
        passages = [_passage(f"https://example.com/{i}") for i in range(5)]
        fs = FetchedSources(passages=passages)
        assert len(fs.passages) == 5

    def test_duplicate_url_rejected(self):
        passages = [_passage("https://example.com/dup") for _ in range(2)]
        with pytest.raises(ValidationError, match="duplicate URLs"):
            FetchedSources(passages=passages)

    def test_too_many_passages_rejected(self):
        passages = [_passage(f"https://example.com/{i}") for i in range(13)]
        with pytest.raises(ValidationError, match="too many passages"):
            FetchedSources(passages=passages)

    def test_exactly_12_passages_ok(self):
        passages = [_passage(f"https://example.com/{i}") for i in range(12)]
        fs = FetchedSources(passages=passages)
        assert len(fs.passages) == 12


class TestTopicSummary:

    def _obs(self, section="topic", key="k1", value="some value"):
        return Observation(section=section, key=key, value=value, written_by="a3")

    def test_valid_summary(self):
        ts = TopicSummary(
            narrative="Test narrative word " * 50,
            footnotes=[],
            scratchpad_writes=[self._obs()],
        )
        assert len(ts.scratchpad_writes) == 1

    def test_wrong_section_rejected(self):
        with pytest.raises(ValidationError, match="section must be 'topic'"):
            TopicSummary(
                narrative="x",
                footnotes=[],
                scratchpad_writes=[self._obs(section="market_context")],
            )

    def test_too_many_scratchpad_writes_rejected(self):
        with pytest.raises(ValidationError):
            TopicSummary(
                narrative="x",
                footnotes=[],
                scratchpad_writes=[self._obs(key=f"k{i}") for i in range(8)],
            )

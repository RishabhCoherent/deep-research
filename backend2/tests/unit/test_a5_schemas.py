"""Unit tests for Agent 5 schemas, types, and validators."""

import pytest
from datetime import date, timedelta
from pydantic import ValidationError

from research.core.types import (
    Citation, AuthorityTier, NewsEvent, RegulatoryChange,
    Disruption, NumericClaim, Observation,
)
from research.crews.a5_news_events.schemas import (
    EventBundle, RegulatoryBundle, GeopoliticalBundle, A5Output,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _citation(url="https://reuters.com/ev-news"):
    return Citation(url=url, title="EV News", authority_tier=AuthorityTier.TIER1_MEDIA)


def _event(days_ago=10, category="earnings", impact="positive", magnitude="medium"):
    return NewsEvent(
        headline="CATL reports record quarterly revenue",
        date=date.today() - timedelta(days=days_ago),
        category=category,
        summary="CATL beat analyst estimates with 38% YoY revenue growth in Q1 2026.",
        impact=impact,
        magnitude=magnitude,
        source=_citation(),
    )


def _reg_change(cost_impact="$35/kWh"):
    return RegulatoryChange(
        regulator="European Commission",
        action="Extended CBAM scope to include battery cells effective 2026-07-01.",
        effective_date=date(2026, 7, 1),
        impact_summary="Imported cells face carbon-adjusted tariffs from July 2026.",
        estimated_cost_impact=cost_impact,
        source=_citation("https://ec.europa.eu/cbam"),
    )


def _disruption(severity="elevated"):
    return Disruption(
        upstream_node="Indonesia nickel",
        event="Indonesia tightened export licensing for nickel ore in March 2026.",
        severity=severity,
        supply_chain_path="Indonesia → CATL → Tesla",
        evidence=[_citation("https://reuters.com/indonesia-nickel")],
    )


def _observation(key="indonesia_nickel_risk"):
    return Observation(
        section="news", key=key,
        value="Tightened export licensing Mar 2026",
        written_by="a5_news_events",
    )


# ── NewsEvent ──────────────────────────────────────────────────────────────

class TestNewsEvent:

    def test_valid(self):
        e = _event()
        assert e.category == "earnings"

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            NewsEvent(
                headline="X", date=date.today(),
                category="rumour",
                summary="Y", impact="positive", magnitude="low",
                source=_citation(),
            )

    def test_invalid_impact(self):
        with pytest.raises(ValidationError):
            NewsEvent(
                headline="X", date=date.today(),
                category="earnings",
                summary="Y", impact="unknown", magnitude="low",
                source=_citation(),
            )

    def test_invalid_magnitude(self):
        with pytest.raises(ValidationError):
            NewsEvent(
                headline="X", date=date.today(),
                category="earnings",
                summary="Y", impact="positive", magnitude="extreme",
                source=_citation(),
            )

    def test_headline_max_length(self):
        with pytest.raises(ValidationError):
            NewsEvent(
                headline="a" * 301, date=date.today(),
                category="other",
                summary="Y", impact="neutral", magnitude="low",
                source=_citation(),
            )


# ── RegulatoryChange ───────────────────────────────────────────────────────

class TestRegulatoryChange:

    def test_valid_with_cost(self):
        r = _reg_change()
        assert r.estimated_cost_impact == "$35/kWh"

    def test_valid_without_cost(self):
        r = _reg_change(cost_impact=None)
        assert r.estimated_cost_impact is None

    def test_action_max_length(self):
        with pytest.raises(ValidationError):
            RegulatoryChange(
                regulator="EC", action="a" * 401,
                impact_summary="X", source=_citation(),
            )


# ── Disruption ─────────────────────────────────────────────────────────────

class TestDisruption:

    def test_valid(self):
        d = _disruption()
        assert d.severity == "elevated"

    def test_invalid_severity(self):
        with pytest.raises(ValidationError):
            Disruption(
                upstream_node="X", event="Y",
                severity="catastrophic",
                supply_chain_path="A → B → C",
                evidence=[_citation()],
            )

    def test_empty_evidence_allowed_by_type(self):
        d = Disruption(
            upstream_node="X", event="Y",
            severity="watch",
            supply_chain_path="A → B",
            evidence=[],
        )
        assert d.evidence == []


# ── EventBundle ────────────────────────────────────────────────────────────

class TestEventBundle:

    def test_valid(self):
        b = EventBundle(events=[_event(), _event(days_ago=20)])
        assert len(b.events) == 2

    def test_empty_rejected(self):
        with pytest.raises(ValidationError, match="at least 1 news event"):
            EventBundle(events=[])


# ── RegulatoryBundle ───────────────────────────────────────────────────────

class TestRegulatoryBundle:

    def test_valid(self):
        b = RegulatoryBundle(changes=[_reg_change()])
        assert len(b.changes) == 1

    def test_empty_rejected(self):
        with pytest.raises(ValidationError, match="at least 1 regulatory change"):
            RegulatoryBundle(changes=[])


# ── GeopoliticalBundle ─────────────────────────────────────────────────────

class TestGeopoliticalBundle:

    def test_valid(self):
        b = GeopoliticalBundle(
            disruptions=[_disruption()],
            scratchpad_writes=[_observation()],
        )
        assert b.disruptions[0].severity == "elevated"

    def test_disruption_no_evidence_rejected(self):
        bad = Disruption(
            upstream_node="X", event="Y", severity="watch",
            supply_chain_path="A → B", evidence=[],
        )
        with pytest.raises(ValidationError, match="at least one evidence citation"):
            GeopoliticalBundle(disruptions=[bad], scratchpad_writes=[])

    def test_wrong_scratchpad_section_rejected(self):
        bad_obs = Observation(section="topic", key="k", value="v",
                              written_by="a5")
        with pytest.raises(ValidationError, match="section='news'"):
            GeopoliticalBundle(disruptions=[], scratchpad_writes=[bad_obs])

    def test_empty_disruptions_allowed(self):
        b = GeopoliticalBundle(disruptions=[], scratchpad_writes=[])
        assert b.disruptions == []


# ── Validators ────────────────────────────────────────────────────────────

class TestValidators:

    def test_filter_recent_events_drops_old(self):
        from research.crews.a5_news_events.validators import filter_recent_events
        recent = _event(days_ago=10)
        old = _event(days_ago=100)
        result = filter_recent_events([recent, old])
        assert len(result) == 1
        assert result[0].headline == recent.headline

    def test_filter_recent_events_keeps_all_within_window(self):
        from research.crews.a5_news_events.validators import filter_recent_events
        events = [_event(days_ago=i * 5) for i in range(1, 7)]  # 5, 10, ..., 30 days ago
        result = filter_recent_events(events, days=90)
        assert len(result) == 6

    def test_filter_disruptions_drops_no_evidence(self):
        from research.crews.a5_news_events.validators import filter_disruptions_with_evidence
        good = _disruption()
        bad = Disruption(
            upstream_node="X", event="Y", severity="watch",
            supply_chain_path="A → B", evidence=[],
        )
        result = filter_disruptions_with_evidence([good, bad])
        assert len(result) == 1

    def test_filter_claims_drops_missing_url(self):
        from research.crews.a5_news_events.validators import filter_claims_with_citations
        good = NumericClaim(
            metric="test", value=1.0, unit="units",
            raw_excerpt="Test excerpt.", citation=_citation(),
        )
        bad = NumericClaim(
            metric="test", value=2.0, unit="units",
            raw_excerpt="Test excerpt 2.",
            citation=Citation(url="", title="No URL"),
        )
        result = filter_claims_with_citations([good, bad])
        assert len(result) == 1

    def test_assert_narrative_word_count_pass(self):
        from research.crews.a5_news_events.validators import assert_narrative_word_count
        assert_narrative_word_count(" ".join(["word"] * 500), lo=100, hi=1200)

    def test_assert_narrative_word_count_fail_short(self):
        from research.crews.a5_news_events.validators import assert_narrative_word_count
        with pytest.raises(AssertionError):
            assert_narrative_word_count("too short", lo=400, hi=800)

    def test_assert_narrative_word_count_fail_long(self):
        from research.crews.a5_news_events.validators import assert_narrative_word_count
        with pytest.raises(AssertionError):
            assert_narrative_word_count(" ".join(["w"] * 900), lo=400, hi=800)


# ── web_search tool counter ────────────────────────────────────────────────

class TestWebSearchCounter:

    def test_reset_and_get(self):
        from research.tools.web_search import reset_news_counter, get_news_call_count
        reset_news_counter()
        assert get_news_call_count() == 0

    def test_cap_returns_error_json(self):
        import json
        from research.tools.web_search import (
            reset_news_counter, set_news_limit, web_search,
        )
        reset_news_counter()
        set_news_limit(0)
        result = json.loads(web_search.invoke({"query": "test", "days": 7}))
        assert "error" in result
        assert result["results"] == []
        set_news_limit(15)  # restore

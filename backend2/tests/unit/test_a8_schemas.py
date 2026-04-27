"""Unit tests for Agent 8 — evidence_validator, delta_detector, schemas.

Includes:
  - Standard validation cases (spec Phase A)
  - Property test: citation removal always causes driver drop
  - Adversarial test: zero causal evidence → empty drivers, not fabricated
"""

import pytest
from datetime import date

from research.core.types import (
    Citation, AuthorityTier, NumericClaim, Driver,
    Causation, Delta, CausationDraft,
)
from research.crews.a8_causation.schemas import (
    DeltaBundle, CorrelatedEvents, ValidatedCausations, A8Output,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _citation(url: str, tier=AuthorityTier.TIER1_MEDIA):
    return Citation(url=url, title="Test Source", authority_tier=tier)


def _claim(metric="Brent crude", value=78.0, unit="USD/bbl",
           as_of="2025-12-31", url="https://eia.gov"):
    return NumericClaim(
        metric=metric, value=value, unit=unit,
        as_of=as_of, raw_excerpt="Brent crude at $78.",
        citation=_citation(url, AuthorityTier.GOVERNMENT),
    )


def _driver(name="Test Driver", n_cites=2, same_domain=False) -> Driver:
    if same_domain:
        cites = [
            _citation(f"https://reuters.com/a{i}",
                      AuthorityTier.TIER1_MEDIA if i == 0 else AuthorityTier.ANALYST_FIRM)
            for i in range(n_cites)
        ]
    else:
        domains = [
            "https://reuters.com",
            "https://ft.com",
            "https://iea.org",
            "https://bloomberg.com",
        ]
        cites = [
            _citation(domains[i % len(domains)],
                      [AuthorityTier.TIER1_MEDIA, AuthorityTier.ANALYST_FIRM,
                       AuthorityTier.GOVERNMENT, AuthorityTier.TIER1_MEDIA][i % 4])
            for i in range(n_cites)
        ]
    return Driver(
        name=name,
        description="A test driver.",
        evidence=cites,
        confidence="medium",
    )


def _draft(drivers=None) -> CausationDraft:
    return CausationDraft(
        metric="Brent crude",
        prior=_claim(value=78.0, as_of="2025-12-31"),
        current=_claim(value=115.0, as_of="2026-04-10"),
        delta_pct=47.4,
        candidate_drivers=drivers or [],
    )


# ── Driver type ────────────────────────────────────────────────────────────

class TestDriverType:
    def test_valid_driver(self):
        d = _driver(n_cites=2)
        assert len(d.evidence) == 2

    def test_invalid_confidence(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Driver(name="x", description="y", evidence=[_citation("https://a.com")],
                   confidence="extreme")


# ── evidence_validator — validate_driver ──────────────────────────────────

class TestValidateDriver:

    def test_3_cites_3_domains_3_tiers_high(self):
        from research.crews.a8_causation.evidence_validator import validate_driver
        d = _driver(n_cites=3)
        result, reason = validate_driver(d)
        assert result is not None
        assert result.confidence == "high"
        assert reason == ""

    def test_2_cites_2_domains_1_tier_medium(self):
        from research.crews.a8_causation.evidence_validator import validate_driver
        cites = [
            _citation("https://reuters.com", AuthorityTier.TIER1_MEDIA),
            _citation("https://wsj.com", AuthorityTier.TIER1_MEDIA),
        ]
        d = Driver(name="OPEC+ cut", description="Cut extension",
                   evidence=cites, confidence="medium")
        result, reason = validate_driver(d)
        assert result is not None, f"Expected keep, got drop: {reason}"
        assert result.confidence == "medium"

    def test_1_citation_dropped(self):
        from research.crews.a8_causation.evidence_validator import validate_driver
        d = _driver(n_cites=1)
        result, reason = validate_driver(d)
        assert result is None
        assert "1 citation" in reason

    def test_2_cites_same_domain_dropped(self):
        from research.crews.a8_causation.evidence_validator import validate_driver
        cites = [
            _citation("https://reuters.com/a", AuthorityTier.TIER1_MEDIA),
            _citation("https://reuters.com/b", AuthorityTier.ANALYST_FIRM),
        ]
        d = Driver(name="x", description="y", evidence=cites, confidence="medium")
        result, reason = validate_driver(d)
        assert result is None
        assert "same domain" in reason.lower() or "reuters" in reason.lower()

    def test_0_citations_dropped(self):
        from research.crews.a8_causation.evidence_validator import validate_driver
        d = Driver(name="x", description="y", evidence=[], confidence="low")
        result, reason = validate_driver(d)
        assert result is None

    def test_3_cites_2_domains_1_tier_medium(self):
        """3 citations, 2 domains, 1 tier → keep, medium (≥2 domains sufficient)."""
        from research.crews.a8_causation.evidence_validator import validate_driver
        cites = [
            _citation("https://reuters.com/1", AuthorityTier.TIER1_MEDIA),
            _citation("https://reuters.com/2", AuthorityTier.TIER1_MEDIA),
            _citation("https://ft.com/1", AuthorityTier.TIER1_MEDIA),
        ]
        d = Driver(name="x", description="y", evidence=cites, confidence="medium")
        result, reason = validate_driver(d)
        # 2 unique domains (reuters.com, ft.com) → keep, medium
        assert result is not None, f"Expected keep (2 domains), got: {reason}"
        assert result.confidence == "medium"


# ── evidence_validator — validate_causation ───────────────────────────────

class TestValidateCausation:

    def test_all_drivers_valid(self):
        from research.crews.a8_causation.evidence_validator import validate_causation
        draft = _draft(drivers=[_driver("D1", 3), _driver("D2", 2)])
        causation = validate_causation(draft)
        assert len(causation.drivers) == 2

    def test_bad_driver_dropped(self):
        from research.crews.a8_causation.evidence_validator import validate_causation
        bad = _driver("blog rumour", n_cites=1)
        good = _driver("OPEC+ cut", n_cites=3)
        draft = _draft(drivers=[good, bad])
        causation = validate_causation(draft)
        assert len(causation.drivers) == 1
        assert causation.drivers[0].name == "OPEC+ cut"

    def test_all_drivers_dropped_empty_list(self):
        """Adversarial: zero good evidence → drivers=[], confidence='low'. No fabrication."""
        from research.crews.a8_causation.evidence_validator import validate_causation
        bad1 = _driver("blog rumour", n_cites=1)
        bad2 = _driver("same-domain", n_cites=2, same_domain=True)
        draft = _draft(drivers=[bad1, bad2])
        causation = validate_causation(draft)
        assert causation.drivers == []
        assert causation.confidence == "low"

    def test_no_candidate_drivers(self):
        """Adversarial: event_correlator found nothing — empty drivers is correct."""
        from research.crews.a8_causation.evidence_validator import validate_causation
        draft = _draft(drivers=[])
        causation = validate_causation(draft)
        assert causation.drivers == []
        assert causation.confidence == "low"
        assert causation.metric == "Brent crude"

    def test_high_confidence_from_3_tiers(self):
        from research.crews.a8_causation.evidence_validator import validate_causation
        d = _driver("US-Iran tensions", n_cites=3)  # 3 different domains, 3 tiers
        draft = _draft(drivers=[d])
        causation = validate_causation(draft)
        assert causation.confidence == "high"

    def test_validate_all(self):
        from research.crews.a8_causation.evidence_validator import validate_all
        drafts = [
            _draft(drivers=[_driver("Good", 2)]),
            _draft(drivers=[]),  # empty
        ]
        results = validate_all(drafts)
        assert len(results) == 2
        assert results[0].confidence in ("medium", "high")
        assert results[1].confidence == "low"


# ── Property test: removing citations always drops driver ─────────────────

class TestPropertyCitationRemoval:

    def _make_valid_driver(self) -> Driver:
        return Driver(
            name="valid",
            description="valid driver",
            evidence=[
                _citation("https://reuters.com", AuthorityTier.TIER1_MEDIA),
                _citation("https://ft.com", AuthorityTier.ANALYST_FIRM),
                _citation("https://iea.org", AuthorityTier.GOVERNMENT),
            ],
            confidence="high",
        )

    def test_remove_to_1_always_drops(self):
        """Removing citations until only 1 remains always causes a drop."""
        from research.crews.a8_causation.evidence_validator import validate_driver
        for keep in range(0, 2):  # keep 0 or 1 citation
            d = self._make_valid_driver()
            d = d.model_copy(update={"evidence": d.evidence[:keep]})
            result, reason = validate_driver(d)
            assert result is None, f"Expected drop with {keep} citations, got keep"

    def test_property_100_removals(self):
        """100 random removals to 1 citation all drop."""
        import random
        from research.crews.a8_causation.evidence_validator import validate_driver
        sources = [
            ("https://a.com", AuthorityTier.TIER1_MEDIA),
            ("https://b.com", AuthorityTier.ANALYST_FIRM),
            ("https://c.com", AuthorityTier.GOVERNMENT),
            ("https://d.com", AuthorityTier.TRADE_PRESS),
            ("https://e.com", AuthorityTier.INDUSTRY_BODY),
        ]
        random.seed(42)
        for _ in range(100):
            all_cites = [_citation(u, t) for u, t in sources]
            # Keep exactly 1 citation
            kept = [random.choice(all_cites)]
            d = Driver(name="x", description="y", evidence=kept, confidence="medium")
            result, reason = validate_driver(d)
            assert result is None, f"Should have been dropped with 1 citation"


# ── delta_detector.py ─────────────────────────────────────────────────────

class TestDeltaDetector:

    def _make_pair(self, metric="Brent crude", v1=78.0, v2=115.0,
                   d1="2025-12-31", d2="2026-04-10"):
        prior   = _claim(metric=metric, value=v1, as_of=d1)
        current = _claim(metric=metric, value=v2, as_of=d2)
        return prior, current

    def test_detects_simple_delta(self):
        from research.crews.a8_causation.delta_detector import detect_deltas
        prior, current = self._make_pair()
        deltas = detect_deltas([prior, current])
        assert len(deltas) == 1
        assert abs(deltas[0].delta_pct - 47.4) < 1.0

    def test_no_delta_single_claim(self):
        from research.crews.a8_causation.delta_detector import detect_deltas
        deltas = detect_deltas([_claim()])
        assert len(deltas) == 0

    def test_no_delta_no_dates(self):
        from research.crews.a8_causation.delta_detector import detect_deltas
        c1 = _claim(as_of=None)
        c2 = NumericClaim(metric="Brent crude", value=115.0, unit="USD/bbl",
                          as_of=None, raw_excerpt="...",
                          citation=_citation("https://b.com"))
        deltas = detect_deltas([c1, c2])
        assert len(deltas) == 0

    def test_sorted_by_abs_delta_desc(self):
        from research.crews.a8_causation.delta_detector import detect_deltas
        small_prior = _claim(metric="CATL share", value=38.0, as_of="2025-01-01",
                             url="https://catl.com")
        small_curr  = _claim(metric="CATL share", value=39.0, as_of="2026-01-01",
                             url="https://catl.com")
        big_prior   = _claim(metric="Brent crude", value=78.0, as_of="2025-12-31")
        big_curr    = _claim(metric="Brent crude", value=115.0, as_of="2026-04-10")
        deltas = detect_deltas([small_prior, small_curr, big_prior, big_curr])
        assert len(deltas) == 2
        assert abs(deltas[0].delta_pct) > abs(deltas[1].delta_pct)

    def test_negative_delta(self):
        from research.crews.a8_causation.delta_detector import detect_deltas
        prior, current = self._make_pair(v1=115.0, v2=78.0)
        deltas = detect_deltas([prior, current])
        assert deltas[0].delta_pct < 0

    def test_different_scopes_not_paired(self):
        from research.crews.a8_causation.delta_detector import detect_deltas
        c1 = NumericClaim(metric="CATL share", value=38.0, unit="%",
                          scope="global", as_of="2025-01-01",
                          raw_excerpt="...", citation=_citation("https://a.com"))
        c2 = NumericClaim(metric="CATL share", value=41.0, unit="%",
                          scope="china", as_of="2026-01-01",
                          raw_excerpt="...", citation=_citation("https://b.com"))
        deltas = detect_deltas([c1, c2])
        assert len(deltas) == 0  # different scope → not the same metric


# ── Delta and CausationDraft types ────────────────────────────────────────

class TestCoreNewTypes:

    def test_delta_fields(self):
        prior, current = _claim(as_of="2025-12-31"), _claim(value=115.0, as_of="2026-04-10")
        d = Delta(metric="Brent", prior=prior, current=current, delta_pct=47.4,
                  window_start=date(2025, 12, 31), window_end=date(2026, 4, 10))
        assert d.delta_pct == 47.4

    def test_causation_draft_fields(self):
        draft = _draft(drivers=[_driver("D1", 2)])
        assert draft.delta_pct == 47.4
        assert len(draft.candidate_drivers) == 1

    def test_causation_confidence_pattern(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Causation(metric="x", delta_pct=10.0, confidence="extreme")

    def test_causation_empty_drivers_ok(self):
        c = Causation(metric="x", delta_pct=5.0, drivers=[], confidence="low")
        assert c.drivers == []


# ── Markdown renderer ─────────────────────────────────────────────────────

class TestMarkdownRenderer:

    def _minimal_state(self) -> dict:
        return {
            "run_id": "test-001",
            "original_query": "EV battery market",
            "chosen_query": "Global EV battery cell market size 2026",
            "intent": "market_sizing",
            "query_variants": [],
            "topic_claims": [],
            "market_claims": [],
            "news_claims": [],
            "validated_claims": [_claim()],
            "conflicts": [],
            "causations": [],
            "consolidated": None,
            "scratchpad_notes": [],
            "sub_questions": [],
            "news_narrative": "",
            "topic_narrative": "",
            "market_narrative": "",
            "cost_usd": 0.0,
        }

    def test_render_produces_markdown(self):
        from research.report.markdown_renderer import render_markdown
        md = render_markdown(self._minimal_state())
        assert "# Research Brief" in md
        assert "Global EV battery cell market size 2026" in md

    def test_render_causation_section(self):
        from research.report.markdown_renderer import render_markdown
        state = self._minimal_state()
        state["causations"] = [
            Causation(
                metric="Brent crude",
                delta_pct=47.4,
                prior=_claim(value=78.0, as_of="2025-12-31"),
                current=_claim(value=115.0, as_of="2026-04-10"),
                drivers=[_driver("US-Iran tensions", 3)],
                confidence="high",
            )
        ]
        md = render_markdown(state)
        assert "Causal Analysis" in md
        assert "Brent crude" in md
        assert "US-Iran tensions" in md

    def test_render_no_causal_evidence_section(self):
        from research.report.markdown_renderer import render_markdown
        state = self._minimal_state()
        state["causations"] = [
            Causation(metric="Brent", delta_pct=10.0, drivers=[], confidence="low")
        ]
        md = render_markdown(state)
        assert "Insufficient causal evidence" in md

    def test_render_empty_state_no_crash(self):
        from research.report.markdown_renderer import render_markdown
        md = render_markdown(self._minimal_state())
        assert len(md) > 100

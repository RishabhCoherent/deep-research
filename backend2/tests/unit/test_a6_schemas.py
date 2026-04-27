"""Unit tests for Agent 6 schemas, normaliser, and validators."""

import pytest
from pydantic import ValidationError

from research.core.types import (
    Citation, AuthorityTier, NumericClaim, Observation,
    Theme, Footnote, ConsolidatedReport,
)
from research.crews.a6_consolidator.schemas import (
    NormalisedClaims, ThemeBundle, ConsolidatedNarrative, A6Output,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _citation(url="https://bnef.com/ev-report"):
    return Citation(url=url, title="BNEF EV Report",
                    authority_tier=AuthorityTier.ANALYST_FIRM)


def _claim(metric="EV battery cell price", value=89.0, unit="USD/kWh"):
    return NumericClaim(
        metric=metric, value=value, unit=unit,
        raw_excerpt="EV battery cell prices fell to $89/kWh in Q1 2026.",
        citation=_citation(),
    )


def _observation(section="topic", key="market_size"):
    return Observation(section=section, key=key,
                       value="Global EV battery market ~$120B in 2025",
                       written_by="a3_topic_researcher")


def _theme(name="Market Size & Segmentation", n_claims=2):
    return Theme(
        name=name,
        summary="Cell prices fell 38% YoY to $89/kWh.",
        claims=[_claim(metric=f"claim_{i}") for i in range(n_claims)],
        observations=[_observation()],
    )


def _footnote(n=1):
    return Footnote(n=n, citation=_citation())


# ── NormalisedClaims ───────────────────────────────────────────────────────

class TestNormalisedClaims:

    def test_valid(self):
        nc = NormalisedClaims(claims=[_claim(), _claim(metric="CAGR")])
        assert len(nc.claims) == 2

    def test_empty_rejected(self):
        with pytest.raises(ValidationError, match="at least 1 claim"):
            NormalisedClaims(claims=[])


# ── ThemeBundle ────────────────────────────────────────────────────────────

class TestThemeBundle:

    def _bundle(self, n_themes=5):
        return ThemeBundle(themes=[_theme(name=f"Theme {i}") for i in range(n_themes)])

    def test_5_themes_valid(self):
        b = self._bundle(5)
        assert len(b.themes) == 5

    def test_8_themes_valid(self):
        b = self._bundle(8)
        assert len(b.themes) == 8

    def test_4_themes_rejected(self):
        with pytest.raises(ValidationError, match="5-8 themes"):
            self._bundle(4)

    def test_9_themes_rejected(self):
        with pytest.raises(ValidationError, match="5-8 themes"):
            self._bundle(9)

    def test_theme_without_claims_rejected(self):
        empty_theme = Theme(name="Empty", summary="No claims.", claims=[], observations=[])
        with pytest.raises(ValidationError, match="at least 1 supporting claim"):
            ThemeBundle(themes=[empty_theme] + [_theme(name=f"T{i}") for i in range(4)])


# ── ConsolidatedNarrative ──────────────────────────────────────────────────

class TestConsolidatedNarrative:

    def _make(self, words=900, footnotes=None):
        narrative = "## Market Size\n\n" + " ".join(["word"] * words)
        return ConsolidatedNarrative(
            narrative=narrative,
            footnotes=footnotes or [],
        )

    def test_valid_900_words(self):
        cn = self._make(words=900)
        assert len(cn.narrative.split()) >= 900

    def test_too_short_rejected(self):
        with pytest.raises(ValidationError, match="800-1500 words"):
            self._make(words=500)

    def test_too_long_rejected(self):
        with pytest.raises(ValidationError, match="800-1500 words"):
            self._make(words=1600)

    def test_duplicate_footnote_ids_rejected(self):
        with pytest.raises(ValidationError, match="unique"):
            ConsolidatedNarrative(
                narrative="## Theme\n\n" + " ".join(["w"] * 900),
                footnotes=[_footnote(1), _footnote(1)],
            )

    def test_unique_footnote_ids_valid(self):
        cn = ConsolidatedNarrative(
            narrative="## Theme\n\n" + " ".join(["w"] * 900),
            footnotes=[_footnote(1), _footnote(2), _footnote(3)],
        )
        assert len(cn.footnotes) == 3


# ── Normaliser ────────────────────────────────────────────────────────────

class TestNormaliser:

    def test_normalise_unit_alias(self):
        from research.crews.a6_consolidator.normaliser import normalise_unit
        assert normalise_unit("usd billion") == "USD billion"
        assert normalise_unit("$ billion") == "USD billion"
        assert normalise_unit("bn usd") == "USD billion"
        assert normalise_unit("GWh") == "GWh"
        assert normalise_unit("$/kWh") == "USD/kWh"

    def test_normalise_unit_unknown_passthrough(self):
        from research.crews.a6_consolidator.normaliser import normalise_unit
        assert normalise_unit("custom_unit_xyz") == "custom_unit_xyz"

    def test_normalise_value_string_billion(self):
        from research.crews.a6_consolidator.normaliser import normalise_value_string
        val, unit = normalise_value_string("$132B")
        assert val == 132.0
        assert unit == "USD billion"

    def test_normalise_value_string_trillion(self):
        from research.crews.a6_consolidator.normaliser import normalise_value_string
        val, unit = normalise_value_string("$2.1T")
        assert val == 2.1
        assert unit == "USD trillion"

    def test_normalise_value_string_million(self):
        from research.crews.a6_consolidator.normaliser import normalise_value_string
        val, unit = normalise_value_string("$500M")
        assert val == 500.0
        assert unit == "USD million"

    def test_normalise_value_string_percent(self):
        from research.crews.a6_consolidator.normaliser import normalise_value_string
        val, unit = normalise_value_string("38%")
        assert val == 38.0
        assert unit == "%"

    def test_normalise_value_string_cagr(self):
        from research.crews.a6_consolidator.normaliser import normalise_value_string
        val, unit = normalise_value_string("18% CAGR")
        assert val == 18.0
        assert unit == "% CAGR"

    def test_normalise_value_string_unrecognised(self):
        from research.crews.a6_consolidator.normaliser import normalise_value_string
        val, unit = normalise_value_string("complicated figure")
        assert val == "complicated figure"

    def test_dedupe_exact_duplicates_removed(self):
        from research.crews.a6_consolidator.normaliser import dedupe_claims
        c1 = _claim()
        c2 = _claim()  # exact same metric/value/unit
        result = dedupe_claims([c1, c2])
        assert len(result) == 1

    def test_dedupe_keeps_different_values(self):
        from research.crews.a6_consolidator.normaliser import dedupe_claims
        c1 = _claim(value=89.0)
        c2 = _claim(value=92.0)  # different value — potential conflict, keep both
        result = dedupe_claims([c1, c2])
        assert len(result) == 2

    def test_normalise_and_dedupe_pipeline(self):
        from research.crews.a6_consolidator.normaliser import normalise_and_dedupe
        claims = [
            _claim(value=89.0, unit="USD/kWh"),
            _claim(value=89.0, unit="$/kwh"),  # alias — same after norm
            _claim(value=95.0, unit="USD/kWh"),  # different value
        ]
        result = normalise_and_dedupe(claims)
        assert len(result) == 2  # first two dedupe after unit normalisation


# ── Validators ─────────────────────────────────────────────────────────────

class TestValidators:

    def test_assert_bottom_up_heading(self):
        from research.crews.a6_consolidator.validators import assert_bottom_up_structure
        narrative = "## Market Size\n\nGlobal EV battery market..."
        assert_bottom_up_structure(narrative)  # no raise

    def test_assert_bottom_up_bold(self):
        from research.crews.a6_consolidator.validators import assert_bottom_up_structure
        narrative = "**Market Size & Segmentation**: Global market..."
        assert_bottom_up_structure(narrative)  # no raise

    def test_assert_bottom_up_fails_no_structure(self):
        from research.crews.a6_consolidator.validators import assert_bottom_up_structure
        with pytest.raises(AssertionError, match="bottom-up"):
            assert_bottom_up_structure("This is a plain paragraph with no headings.")

    def test_footnote_integrity_pass(self):
        from research.crews.a6_consolidator.validators import assert_footnote_integrity
        narrative = "Market size is $132B [1] with CAGR of 18% [2]."
        footnotes = [_footnote(1), _footnote(2)]
        assert_footnote_integrity(narrative, footnotes)  # no raise

    def test_footnote_integrity_missing_definition(self):
        from research.crews.a6_consolidator.validators import assert_footnote_integrity
        narrative = "Market size [1] and CAGR [3]."
        footnotes = [_footnote(1)]  # [3] is cited but not defined
        with pytest.raises(AssertionError, match="not in footnotes"):
            assert_footnote_integrity(narrative, footnotes)

    def test_footnote_integrity_no_citations_ok(self):
        from research.crews.a6_consolidator.validators import assert_footnote_integrity
        assert_footnote_integrity("No citations here.", [])  # no raise

    def test_assert_theme_coverage_pass(self):
        from research.crews.a6_consolidator.validators import assert_theme_coverage
        themes = [_theme(name=f"T{i}") for i in range(6)]
        assert_theme_coverage(themes)  # no raise

    def test_assert_theme_coverage_fail_too_few(self):
        from research.crews.a6_consolidator.validators import assert_theme_coverage
        with pytest.raises(AssertionError, match="≥ 5"):
            assert_theme_coverage([_theme()])

    def test_assert_theme_coverage_fail_empty_claims(self):
        from research.crews.a6_consolidator.validators import assert_theme_coverage
        empty = Theme(name="E", summary="No claims", claims=[], observations=[])
        with pytest.raises(AssertionError, match="no supporting claims"):
            assert_theme_coverage([empty] + [_theme(name=f"T{i}") for i in range(4)])

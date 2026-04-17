"""Unit tests for Agent 4 schemas."""

import pytest
from pydantic import ValidationError

from research.core.types import (
    Citation, AuthorityTier, ChainNode, SubstituteEntry,
    ImpactItem, NumericClaim, Observation
)
from research.crews.a4_market_context.schemas import (
    ParentMarketResult, ValueChainMap, ImpactAnalysis, A4Output
)


def _citation(url="https://mckinsey.com/ev-report"):
    return Citation(url=url, title="EV Market Report",
                    authority_tier=AuthorityTier.ANALYST_FIRM)


def _chain_node(stage="upstream", name="Albemarle", role="Lithium mining"):
    return ChainNode(stage=stage, name=name, role=role,
                     approx_share=18.0, geography="Chile/Australia")


def _substitute(name="Na-ion battery", maturity="early_commercial", threat="medium"):
    return SubstituteEntry(name=name, maturity=maturity, threat_level=threat,
                           rationale="Lower cost but lower energy density.")


def _impact(force="lithium spot price", direction="negative"):
    return ImpactItem(
        force=force,
        direction=direction,
        magnitude="10% ↓ lithium → ~3.7% ↓ cell price",
        mechanism="pass-through factor ≈ 0.37 per BNEF 2026",
        evidence=[_citation()],
    )


def _observation(key="value_chain_summary"):
    return Observation(section="market_context", key=key,
                       value="upstream: Albemarle, SQM; midstream: CATL, BYD",
                       written_by="a4_market_context")


def _claim():
    return NumericClaim(
        metric="lithium carbonate price",
        value=14000.0, unit="USD/tonne",
        raw_excerpt="Lithium carbonate averaged $14,000/t in Q1 2026.",
        citation=_citation(),
    )


# ── ParentMarketResult ─────────────────────────────────────────────────────

class TestParentMarketResult:

    def test_valid(self):
        r = ParentMarketResult(
            child="EV battery market",
            parent="EV powertrain market",
            grandparent="Global automotive manufacturing",
            justification="Defined by GICS sector classification.",
            citations=[_citation()],
        )
        assert r.parent == "EV powertrain market"

    def test_no_citations_rejected(self):
        with pytest.raises(ValidationError, match="at least one citation"):
            ParentMarketResult(
                child="X", parent="Y", grandparent="Z",
                justification="Some text.",
                citations=[],
            )

    def test_justification_max_length(self):
        with pytest.raises(ValidationError):
            ParentMarketResult(
                child="X", parent="Y", grandparent="Z",
                justification="a" * 501,
                citations=[_citation()],
            )


# ── ValueChainMap ──────────────────────────────────────────────────────────

class TestValueChainMap:

    def _valid_map(self, n_upstream=2, n_midstream=1):
        return ValueChainMap(
            upstream=[_chain_node(name=f"Up{i}") for i in range(n_upstream)],
            midstream=[_chain_node(stage="midstream", name="CATL", role="Cell manufacturing")
                       for _ in range(n_midstream)],
            downstream=[_chain_node(stage="downstream", name="Tesla", role="OEM")],
            substitutes=[_substitute()],
            scratchpad_writes=[_observation()],
        )

    def test_valid(self):
        m = self._valid_map()
        assert len(m.upstream) == 2

    def test_too_few_upstream_rejected(self):
        with pytest.raises(ValidationError, match="≥ 2 upstream"):
            self._valid_map(n_upstream=1)

    def test_empty_midstream_rejected(self):
        with pytest.raises(ValidationError, match="≥ 1 midstream"):
            self._valid_map(n_midstream=0)

    def test_wrong_scratchpad_section_rejected(self):
        bad_obs = Observation(section="topic", key="k", value="v",
                              written_by="a4")
        with pytest.raises(ValidationError, match="market_context"):
            ValueChainMap(
                upstream=[_chain_node(name="A"), _chain_node(name="B")],
                midstream=[_chain_node(stage="midstream", name="C", role="r")],
                downstream=[],
                substitutes=[],
                scratchpad_writes=[bad_obs],
            )

    def test_too_many_scratchpad_writes_rejected(self):
        with pytest.raises(ValidationError):
            ValueChainMap(
                upstream=[_chain_node(name="A"), _chain_node(name="B")],
                midstream=[_chain_node(stage="midstream", name="C", role="r")],
                downstream=[],
                substitutes=[],
                scratchpad_writes=[_observation(key=f"k{i}") for i in range(11)],
            )

    def test_no_scratchpad_writes_rejected(self):
        with pytest.raises(ValidationError):
            ValueChainMap(
                upstream=[_chain_node(name="A"), _chain_node(name="B")],
                midstream=[_chain_node(stage="midstream", name="C", role="r")],
                downstream=[],
                substitutes=[],
                scratchpad_writes=[],
            )


# ── ImpactAnalysis ─────────────────────────────────────────────────────────

class TestImpactAnalysis:

    def test_valid(self):
        a = ImpactAnalysis(
            impacts=[_impact()],
            claims=[_claim()],
            narrative=" ".join(["word"] * 100),
        )
        assert len(a.impacts) == 1

    def test_impact_without_evidence_rejected(self):
        bad = ImpactItem(force="test", direction="negative",
                         magnitude="5%", mechanism="unknown", evidence=[])
        with pytest.raises(ValidationError, match="at least one evidence citation"):
            ImpactAnalysis(
                impacts=[bad],
                claims=[],
                narrative=" ".join(["word"] * 100),
            )

    def test_narrative_too_short_rejected(self):
        with pytest.raises(ValidationError, match="50 words"):
            ImpactAnalysis(
                impacts=[_impact()],
                claims=[],
                narrative="too short",
            )


# ── ChainNode and SubstituteEntry ──────────────────────────────────────────

class TestCoreTypes:

    def test_chain_node_invalid_stage(self):
        with pytest.raises(ValidationError):
            ChainNode(stage="lateral", name="X", role="Y")

    def test_substitute_invalid_maturity(self):
        with pytest.raises(ValidationError):
            SubstituteEntry(name="X", maturity="beta", threat_level="low",
                            rationale="test")

    def test_substitute_invalid_threat(self):
        with pytest.raises(ValidationError):
            SubstituteEntry(name="X", maturity="mature", threat_level="critical",
                            rationale="test")

    def test_impact_item_invalid_direction(self):
        with pytest.raises(ValidationError):
            ImpactItem(force="X", direction="sideways", magnitude="5%",
                       mechanism="unknown", evidence=[_citation()])


# ── Validators ────────────────────────────────────────────────────────────

class TestValidators:

    def test_assert_impact_evidence_drops_empty(self):
        from research.crews.a4_market_context.validators import assert_impact_evidence
        good = _impact()
        bad = ImpactItem(force="X", direction="mixed", magnitude="?",
                         mechanism="?", evidence=[])
        result = assert_impact_evidence([good, bad])
        assert len(result) == 1
        assert result[0].force == good.force

    def test_assert_claim_citations_drops_no_url(self):
        from research.crews.a4_market_context.validators import assert_claim_citations
        good = _claim()
        bad = _claim()
        bad.citation.url = ""
        result = assert_claim_citations([good, bad])
        assert len(result) == 1

    def test_assert_narrative_word_count_pass(self):
        from research.crews.a4_market_context.validators import assert_narrative_word_count
        assert_narrative_word_count(" ".join(["w"] * 500))

    def test_assert_narrative_word_count_fail(self):
        from research.crews.a4_market_context.validators import assert_narrative_word_count
        with pytest.raises(AssertionError):
            assert_narrative_word_count("too short narrative")

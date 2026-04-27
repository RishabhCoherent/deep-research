"""Unit tests for Agent 7 — authority ranking, crosscheck logic, schemas, and validators."""

import pytest
from pydantic import ValidationError

from research.core.types import (
    Citation, AuthorityTier, NumericClaim, Conflict, ConflictCandidate, RangeValue,
)
from research.crews.a7_validator.schemas import (
    RankedClaims, CrossCheckResult, RecencyResult, ValidationResult, A7Output,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _citation(url="https://bnef.com", tier=AuthorityTier.ANALYST_FIRM, published=None):
    return Citation(url=url, title="BNEF", authority_tier=tier, published=published)


def _claim(metric="EV battery market size", value=132.0, unit="USD billion",
           scope=None, as_of=None, url="https://bnef.com",
           tier=AuthorityTier.ANALYST_FIRM):
    return NumericClaim(
        metric=metric, value=value, unit=unit, scope=scope,
        as_of=as_of, raw_excerpt="Market valued at $132B.",
        citation=_citation(url=url, tier=tier),
    )


# ── AuthorityTier enum ────────────────────────────────────────────────────

class TestAuthorityTier:
    def test_unknown_in_enum(self):
        assert AuthorityTier.UNKNOWN == "unknown"

    def test_all_tiers_present(self):
        tiers = {t.value for t in AuthorityTier}
        expected = {"government", "multilateral", "industry_body", "tier1_media",
                    "analyst_firm", "trade_press", "blog", "unknown"}
        assert expected.issubset(tiers)


# ── authority.py deterministic ranking ───────────────────────────────────

class TestAuthorityRanking:

    def test_government_is_highest(self):
        from research.crews.a7_validator.authority import tier_rank
        assert tier_rank(AuthorityTier.GOVERNMENT) == 0

    def test_unknown_is_lowest(self):
        from research.crews.a7_validator.authority import tier_rank
        assert tier_rank(AuthorityTier.UNKNOWN) == 7

    def test_blog_below_analyst(self):
        from research.crews.a7_validator.authority import tier_rank
        assert tier_rank(AuthorityTier.BLOG) > tier_rank(AuthorityTier.ANALYST_FIRM)

    def test_compare_authority_higher(self):
        from research.crews.a7_validator.authority import compare_authority
        assert compare_authority(AuthorityTier.GOVERNMENT, AuthorityTier.BLOG) == -1

    def test_compare_authority_equal(self):
        from research.crews.a7_validator.authority import compare_authority
        assert compare_authority(AuthorityTier.ANALYST_FIRM, AuthorityTier.ANALYST_FIRM) == 0

    def test_compare_authority_lower(self):
        from research.crews.a7_validator.authority import compare_authority
        assert compare_authority(AuthorityTier.BLOG, AuthorityTier.GOVERNMENT) == 1

    def test_pick_winner_chooses_highest_authority(self):
        from research.crews.a7_validator.authority import pick_winner
        analyst = _claim(tier=AuthorityTier.ANALYST_FIRM, url="https://bnef.com")
        blog    = _claim(tier=AuthorityTier.BLOG, url="https://blog.com")
        gov     = _claim(tier=AuthorityTier.GOVERNMENT, url="https://doe.gov")
        winner = pick_winner([analyst, blog, gov])
        assert winner.citation.authority_tier == AuthorityTier.GOVERNMENT

    def test_pick_winner_recency_tiebreak(self):
        from research.crews.a7_validator.authority import pick_winner
        old = _claim(tier=AuthorityTier.ANALYST_FIRM, as_of="2025-06-01",
                     url="https://a.com", value=125.0)
        new = _claim(tier=AuthorityTier.ANALYST_FIRM, as_of="2026-02-01",
                     url="https://b.com", value=132.0)
        winner = pick_winner([old, new])
        assert winner.value == 132.0

    def test_rank_reason_lower_tier(self):
        from research.crews.a7_validator.authority import rank_reason
        winner = _claim(tier=AuthorityTier.ANALYST_FIRM)
        loser  = _claim(tier=AuthorityTier.BLOG, url="https://blog.com")
        reason = rank_reason(winner, loser)
        assert "blog" in reason.lower()

    def test_none_tier_treated_as_unknown(self):
        from research.crews.a7_validator.authority import tier_rank
        assert tier_rank(None) == 7


# ── crosscheck.py ─────────────────────────────────────────────────────────

class TestCrosscheck:

    def test_pct_diff_basic(self):
        from research.crews.a7_validator.crosscheck import pct_diff
        assert abs(pct_diff(100.0, 105.0) - 4.878) < 0.01

    def test_pct_diff_zero_avg(self):
        from research.crews.a7_validator.crosscheck import pct_diff
        assert pct_diff(0.0, 0.0) == 0.0

    def test_should_emit_range_within_5pct(self):
        from research.crews.a7_validator.crosscheck import should_emit_range
        assert should_emit_range(125.0, 132.0) is False  # 5.6% > 5%
        assert should_emit_range(128.0, 132.0) is True   # 3.1% < 5%

    def test_group_claims_unanimous(self):
        from research.crews.a7_validator.crosscheck import group_claims
        c1 = _claim(metric="EV market size")
        c2 = _claim(metric="CATL share")
        unanimous, candidates = group_claims([c1, c2])
        assert len(unanimous) == 2
        assert len(candidates) == 0

    def test_group_claims_conflict(self):
        from research.crews.a7_validator.crosscheck import group_claims
        c1 = _claim(metric="EV market size", value=132.0, url="https://bnef.com")
        c2 = _claim(metric="EV market size", value=125.0, url="https://wsj.com")
        unanimous, candidates = group_claims([c1, c2])
        assert len(unanimous) == 0
        assert len(candidates) == 1
        assert candidates[0].max_diff_pct > 0

    def test_group_claims_scope_separates(self):
        from research.crews.a7_validator.crosscheck import group_claims
        c1 = _claim(metric="CATL share", scope="global")
        c2 = _claim(metric="CATL share", scope="china")
        unanimous, candidates = group_claims([c1, c2])
        assert len(unanimous) == 2  # different scopes → not same metric
        assert len(candidates) == 0

    def test_resolve_candidate_picks_higher_authority(self):
        from research.crews.a7_validator.crosscheck import resolve_candidate
        analyst = _claim(tier=AuthorityTier.ANALYST_FIRM, value=132.0)
        blog    = _claim(tier=AuthorityTier.BLOG, value=140.0, url="https://blog.com")
        cand = ConflictCandidate(metric="ev market", scope=None, claims=[analyst, blog])
        winner, rejected = resolve_candidate(cand)
        assert not isinstance(winner, RangeValue)
        assert winner.citation.authority_tier == AuthorityTier.ANALYST_FIRM
        assert len(rejected) == 1

    def test_resolve_candidate_emits_range_within_5pct(self):
        from research.crews.a7_validator.crosscheck import resolve_candidate
        c1 = _claim(tier=AuthorityTier.ANALYST_FIRM, value=128.0, url="https://a.com")
        c2 = _claim(tier=AuthorityTier.ANALYST_FIRM, value=132.0, url="https://b.com",
                    as_of="2026-02-01")
        cand = ConflictCandidate(metric="ev market", scope=None, claims=[c1, c2])
        winner, rejected = resolve_candidate(cand)
        assert isinstance(winner, RangeValue)
        assert winner.low < winner.high

    def test_resolve_all_no_conflicts(self):
        from research.crews.a7_validator.crosscheck import resolve_all
        c1 = _claim(metric="A")
        c2 = _claim(metric="B")
        validated, conflicts = resolve_all([c1, c2], [])
        assert len(validated) == 2
        assert len(conflicts) == 0

    def test_resolve_all_with_conflict(self):
        from research.crews.a7_validator.crosscheck import resolve_all
        analyst = _claim(tier=AuthorityTier.ANALYST_FIRM, value=132.0)
        blog    = _claim(tier=AuthorityTier.BLOG, value=90.0, url="https://b.com")
        cand = ConflictCandidate(metric="ev market", scope=None, claims=[analyst, blog])
        validated, conflicts = resolve_all([], [cand])
        assert len(validated) == 1
        assert len(conflicts) == 1
        assert conflicts[0].chosen.citation.authority_tier == AuthorityTier.ANALYST_FIRM


# ── Schemas ────────────────────────────────────────────────────────────────

class TestSchemas:

    def test_ranked_claims_valid(self):
        rc = RankedClaims(claims=[_claim()])
        assert len(rc.claims) == 1

    def test_ranked_claims_empty_rejected(self):
        with pytest.raises(ValidationError, match="at least 1"):
            RankedClaims(claims=[])

    def test_cross_check_result_valid(self):
        c1 = _claim(url="https://a.com")
        c2 = _claim(url="https://b.com")
        cand = ConflictCandidate(metric="ev", scope=None, claims=[c1, c2])
        result = CrossCheckResult(unanimous=[], conflicted=[cand])
        assert len(result.conflicted) == 1

    def test_cross_check_candidate_single_claim_rejected(self):
        cand = ConflictCandidate(metric="ev", scope=None, claims=[_claim()])
        with pytest.raises(ValidationError, match="≥ 2 claims"):
            CrossCheckResult(unanimous=[], conflicted=[cand])

    def test_validation_result_empty_rejected(self):
        with pytest.raises(ValidationError, match="at least 1"):
            ValidationResult(validated_claims=[], conflicts=[])

    def test_a7_output_valid(self):
        out = A7Output(validated_claims=[_claim()], conflicts=[])
        assert len(out.validated_claims) == 1


# ── ConflictCandidate and RangeValue core types ────────────────────────────

class TestCoreNewTypes:

    def test_conflict_candidate_fields(self):
        c1, c2 = _claim(url="https://a.com"), _claim(url="https://b.com")
        cand = ConflictCandidate(metric="test", scope="global",
                                 claims=[c1, c2], max_diff_pct=5.6)
        assert cand.max_diff_pct == 5.6
        assert cand.recency_winner_idx is None

    def test_range_value(self):
        rv = RangeValue(low=125.0, high=132.0, unit="USD billion")
        assert rv.high > rv.low

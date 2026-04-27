"""Unit tests for Agent 1 schemas."""

import pytest
from pydantic import ValidationError
from research.core.types import IntentKind, AngleKind, Variant, ScoredVariant
from research.crews.a1_query_refiner.schemas import (
    IntentClassification, VariantBundle, ScoredBundle, A1Output
)


class TestIntentClassification:
    """Test IntentClassification schema."""
    
    def test_valid_intent_classification(self):
        """Test valid intent classification."""
        data = {
            "intent": "market_sizing",
            "confidence": 0.85,
            "reasoning": "Query mentions market size and growth"
        }
        result = IntentClassification(**data)
        assert result.intent == IntentKind.MARKET_SIZING
        assert result.confidence == 0.85
        assert result.reasoning == "Query mentions market size and growth"
    
    def test_invalid_confidence_range(self):
        """Test confidence outside valid range."""
        with pytest.raises(ValidationError):
            IntentClassification(
                intent="market_sizing",
                confidence=1.5,  # Too high
                reasoning="Test"
            )
        
        with pytest.raises(ValidationError):
            IntentClassification(
                intent="market_sizing",
                confidence=-0.1,  # Too low
                reasoning="Test"
            )
    
    def test_invalid_intent_maps_to_general(self):
        """Unknown intent strings fall back to 'general' instead of crashing."""
        result = IntentClassification(
            intent="invalid_intent",
            confidence=0.8,
            reasoning="Test",
        )
        assert result.intent == IntentKind.GENERAL

    def test_supply_chain_intent_maps_to_market_sizing(self):
        """'supply_chain' — a common LLM mistake — maps to market_sizing."""
        result = IntentClassification(
            intent="supply_chain",
            confidence=0.9,
            reasoning="Test",
        )
        assert result.intent == IntentKind.MARKET_SIZING


class TestVariantBundle:
    """Test VariantBundle schema."""
    
    def test_valid_variant_bundle(self):
        """Test valid variant bundle with 4 unique angles."""
        variants = [
            Variant(text="Global EV battery market size 2024-2026", angle="size_segmentation"),
            Variant(text="Key drivers shaping EV battery market", angle="drivers_constraints"),
            Variant(text="Top EV battery manufacturers share", angle="competitive_share"),
            Variant(text="EV battery demand outlook scenarios", angle="outlook_scenarios")
        ]
        bundle = VariantBundle(variants=variants)
        assert len(bundle.variants) == 4
        angles = {v.angle for v in bundle.variants}
        assert len(angles) == 4
    
    def test_wrong_number_of_variants(self):
        """Test wrong number of variants."""
        with pytest.raises(ValidationError, match="must produce exactly 4 variants"):
            VariantBundle(variants=[
                Variant(text="Test 1", angle="size_segmentation"),
                Variant(text="Test 2", angle="drivers_constraints")
            ])
    
    def test_duplicate_angles(self):
        """Test duplicate angles."""
        with pytest.raises(ValidationError, match="all four angles must be distinct"):
            VariantBundle(variants=[
                Variant(text="Test 1", angle="size_segmentation"),
                Variant(text="Test 2", angle="size_segmentation"),
                Variant(text="Test 3", angle="drivers_constraints"),
                Variant(text="Test 4", angle="competitive_share")
            ])
    
    def test_duplicate_texts(self):
        """Test duplicate variant texts."""
        with pytest.raises(ValidationError, match="variants must be unique"):
            VariantBundle(variants=[
                Variant(text="Same text", angle="size_segmentation"),
                Variant(text="Same text", angle="drivers_constraints"),
                Variant(text="Test 3", angle="competitive_share"),
                Variant(text="Test 4", angle="outlook_scenarios")
            ])


class TestScoredBundle:
    """Test ScoredBundle schema."""
    
    def test_valid_scored_bundle(self):
        """Test valid scored bundle sorted by composite."""
        scored_variants = [
            ScoredVariant(
                variant=Variant(text="Test 1", angle="size_segmentation"),
                specificity=9.0,
                scope_clarity=8.0,
                answerability=8.5,
                composite=8.6,
                reason="Best option"
            ),
            ScoredVariant(
                variant=Variant(text="Test 2", angle="drivers_constraints"),
                specificity=7.0,
                scope_clarity=8.0,
                answerability=7.5,
                composite=7.4,
                reason="Good option"
            ),
            ScoredVariant(
                variant=Variant(text="Test 3", angle="competitive_share"),
                specificity=6.0,
                scope_clarity=7.0,
                answerability=6.5,
                composite=6.4,
                reason="Fair option"
            ),
            ScoredVariant(
                variant=Variant(text="Test 4", angle="outlook_scenarios"),
                specificity=5.0,
                scope_clarity=6.0,
                answerability=5.5,
                composite=5.4,
                reason="Poor option"
            )
        ]
        bundle = ScoredBundle(scored=scored_variants)
        assert len(bundle.scored) == 4
        # Verify sorted descending
        composites = [sv.composite for sv in bundle.scored]
        assert composites == sorted(composites, reverse=True)
    
    def test_unsorted_bundle_auto_sorts(self):
        """Unsorted input is auto-sorted descending — no crash."""
        scored_variants = [
            ScoredVariant(
                variant=Variant(text="Test 1", angle="size_segmentation"),
                specificity=5.0,
                scope_clarity=6.0,
                answerability=5.5,
                composite=5.4,
                reason="Lower score"
            ),
            ScoredVariant(
                variant=Variant(text="Test 2", angle="drivers_constraints"),
                specificity=9.0,
                scope_clarity=8.0,
                answerability=8.5,
                composite=8.6,
                reason="Higher score"
            ),
            ScoredVariant(
                variant=Variant(text="Test 3", angle="competitive_share"),
                specificity=6.0,
                scope_clarity=7.0,
                answerability=6.5,
                composite=6.4,
                reason="Middle score"
            ),
            ScoredVariant(
                variant=Variant(text="Test 4", angle="outlook_scenarios"),
                specificity=7.0,
                scope_clarity=8.0,
                answerability=7.5,
                composite=7.4,
                reason="Good score"
            )
        ]
        bundle = ScoredBundle(scored=scored_variants)
        composites = [sv.composite for sv in bundle.scored]
        assert composites == sorted(composites, reverse=True)


class TestA1Output:
    """Test A1Output schema."""
    
    def test_valid_a1_output(self):
        """Test valid A1Output."""
        scored_variant = ScoredVariant(
            variant=Variant(text="Test query", angle="size_segmentation"),
            specificity=8.0,
            scope_clarity=7.5,
            answerability=8.0,
            composite=7.85,
            reason="Good query"
        )
        output = A1Output(
            intent="market_sizing",
            variants_sorted=[scored_variant],
            chosen_query="Test query"
        )
        assert output.intent == IntentKind.MARKET_SIZING
        assert len(output.variants_sorted) == 1
        assert output.chosen_query == "Test query"
    
    def test_a1_output_without_chosen_query(self):
        """Test A1Output without chosen query (pre-user selection)."""
        scored_variant = ScoredVariant(
            variant=Variant(text="Test query", angle="size_segmentation"),
            specificity=8.0,
            scope_clarity=7.5,
            answerability=8.0,
            composite=7.85,
            reason="Good query"
        )
        output = A1Output(
            intent="market_sizing",
            variants_sorted=[scored_variant],
            chosen_query=None
        )
        assert output.chosen_query is None

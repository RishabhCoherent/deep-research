"""Unit tests for Agent 2 near-duplicate detection."""

import pytest
from research.core.types import SubQuestionDraft
from research.crews.a2_question_generator.dedupe import (
    near_duplicate_clusters, deduplicate
)


def _d(text, category="size"):
    return SubQuestionDraft(text=text, category=category, source="decomposer",
                            geography="global", time_frame="2026")


class TestNearDuplicateClusters:

    def test_identical_texts_are_duplicates(self):
        qs = [
            _d("What is the 2026 global EV battery market size in USD billion?"),
            _d("What is the 2026 global EV battery market size in USD billion?"),
            _d("What is the 2026 CAGR of the EV battery market?"),
        ]
        clusters = near_duplicate_clusters(qs, threshold=0.88)
        assert len(clusters) == 1
        assert 0 in clusters[0] and 1 in clusters[0]

    def test_distinct_questions_no_clusters(self):
        qs = [
            _d("What is the 2026 global EV battery market size?"),
            _d("Who are the top 5 EV battery manufacturers by share?"),
            _d("What regulations affect EV battery imports in the EU?"),
        ]
        clusters = near_duplicate_clusters(qs, threshold=0.88)
        assert len(clusters) == 0

    def test_near_duplicate_at_lower_threshold(self):
        qs = [
            _d("What is the EV battery market size globally in 2026?"),
            _d("What is the global EV battery market size in 2026?"),
        ]
        clusters_strict = near_duplicate_clusters(qs, threshold=0.99)
        clusters_loose = near_duplicate_clusters(qs, threshold=0.70)
        assert len(clusters_loose) >= len(clusters_strict)


class TestDeduplicate:

    def test_removes_duplicate_keeps_first(self):
        qs = [
            _d("What is the 2026 global EV battery market size in USD billion?"),
            _d("What is the 2026 global EV battery market size in USD billion?"),
            _d("What is the CAGR of EV batteries 2026-2030 globally?"),
        ]
        result = deduplicate(qs, threshold=0.88)
        assert len(result) == 2
        assert result[0].text == qs[0].text

    def test_no_duplicates_unchanged(self):
        qs = [
            _d("What is the 2026 EV battery market size?"),
            _d("Who leads in EV battery manufacturing?"),
            _d("What tariffs affect lithium imports in 2026?"),
        ]
        result = deduplicate(qs, threshold=0.88)
        assert len(result) == 3

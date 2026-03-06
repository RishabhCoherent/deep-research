"""
Shared types for the multi-layer research agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Source:
    """A research source with metadata."""
    url: str
    title: str
    snippet: str
    scraped_content: str = ""
    publisher: str = ""
    date: str = ""
    credibility: str = "unknown"  # high, medium, low, unknown
    tier: int = 3  # 1=gold-standard, 2=reliable, 3=unknown/unverified


@dataclass
class ResearchResult:
    """Output of a single layer's research on a topic."""
    layer: int
    topic: str
    content: str
    sources: list[Source] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    word_count: int = 0

    def __post_init__(self):
        self.word_count = len(self.content.split())


@dataclass
class LayerEvaluation:
    """Quality evaluation metrics for a single layer's output."""
    layer: int
    factual_density: float = 0.0      # claims per 100 words
    source_diversity: int = 0          # unique source count
    specificity_score: float = 0.0     # % of claims with numbers/data
    framework_usage: list[str] = field(default_factory=list)  # analytical frameworks used
    insight_depth: str = ""            # shallow / moderate / deep / expert
    contrarian_views: int = 0          # count of assumption challenges
    word_count: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class ComparisonReport:
    """Side-by-side comparison across all layers."""
    topic: str
    results: list[ResearchResult] = field(default_factory=list)
    evaluations: list[LayerEvaluation] = field(default_factory=list)
    summary: str = ""

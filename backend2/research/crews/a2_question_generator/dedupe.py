"""Near-duplicate detection for sub-questions (no LLM, uses rapidfuzz)."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research.core.types import SubQuestionDraft

try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


def _similarity(a: str, b: str) -> float:
    """Return token-set-ratio similarity in [0, 1]."""
    if _HAS_RAPIDFUZZ:
        return _fuzz.token_set_ratio(a, b) / 100.0
    # Fallback: basic word-overlap Jaccard when rapidfuzz not installed
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def near_duplicate_clusters(
    qs: list["SubQuestionDraft"],
    threshold: float = 0.88,
) -> list[set[int]]:
    """Return clusters of indices considered near-duplicates.

    Each cluster is a set of indices whose pairwise similarity >= threshold.
    Single-element clusters are not returned.
    """
    n = len(qs)
    visited = [False] * n
    clusters: list[set[int]] = []

    for i in range(n):
        if visited[i]:
            continue
        cluster = {i}
        for j in range(i + 1, n):
            if not visited[j] and _similarity(qs[i].text, qs[j].text) >= threshold:
                cluster.add(j)
                visited[j] = True
        if len(cluster) > 1:
            visited[i] = True
            clusters.append(cluster)

    return clusters


def deduplicate(
    qs: list["SubQuestionDraft"],
    threshold: float = 0.88,
) -> list["SubQuestionDraft"]:
    """Remove near-duplicates, keeping the first occurrence in each cluster.

    Safe to call before prioritizer — reduces LLM context size.
    """
    clusters = near_duplicate_clusters(qs, threshold)
    remove: set[int] = set()
    for cluster in clusters:
        sorted_cluster = sorted(cluster)
        remove.update(sorted_cluster[1:])  # keep lowest index (first seen)
    return [q for i, q in enumerate(qs) if i not in remove]

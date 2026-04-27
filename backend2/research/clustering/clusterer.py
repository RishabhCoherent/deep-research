"""Hash-based clusterer for the backend2 dimensional clustering library.

This is a trimmed port of claim_clustering/clusterer.py:
  - HASH path only (cosine + LLM-judge dropped — no LLM cost, no async).
  - Fuzzy merge via Jaro-Winkler on subject/segment string variation.
  - Hard-qualifier-contradiction guard prevents cross-merging of clearly
    different measurements (different metric_kind / as_of / segment).

Public entry: `cluster_claims_hash(claims) -> (proto_clusters, stats)`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import ClaimDimension, RawClaim


# ── Proto-cluster (mutable scratch) ─────────────────────────────────────────

@dataclass
class _ProtoCluster:
    dimension: ClaimDimension
    claims: list[RawClaim] = field(default_factory=list)

    def add(self, claim: RawClaim) -> None:
        self.claims.append(claim)


def _build_qualifier_summary(members: list[RawClaim]) -> dict[str, list[str]]:
    agg: dict[str, set[str]] = {}
    for c in members:
        for k, v in (c.qualifiers or {}).items():
            if not k or v is None or v == "":
                continue
            agg.setdefault(k, set()).add(str(v))
    return {k: sorted(v) for k, v in agg.items()}


# Qualifier keys that are HARD identifying dimensions: if two claims both have
# one of these keys and the values differ, they describe DIFFERENT measurements
# regardless of how similar their descriptor sentences look.
_HARD_IDENTITY_KEYS = ("subject", "metric_kind", "segment", "as_of", "fiscal_period")


def _qualifiers_hard_contradict(a_q: dict, b_q: dict) -> bool:
    if not a_q or not b_q:
        return False
    for k in _HARD_IDENTITY_KEYS:
        av = a_q.get(k)
        bv = b_q.get(k)
        if av and bv:
            if str(av).strip().lower() != str(bv).strip().lower():
                return True
    return False


# Keys that build the deterministic hash key for a claim. Order is fixed for
# reproducibility. Missing keys collapse to empty string.
_HASH_KEYS = ("subject", "metric_kind", "segment", "scope", "geography",
              "as_of", "fiscal_period", "fiscal_basis", "is_forecast")


def _qualifier_hash_key(claim: RawClaim) -> str:
    """Deterministic key built from canonicalised qualifiers. Two claims with
    the same key share the same dimension. unit_family is prefixed so cross-
    family clusters never collide.

    DEFENSIVE: if `metric_kind` is missing, return a per-claim unique key so
    the claim lands in its own singleton bucket (never silently merges with
    other unknown-metric claims).
    """
    q = claim.qualifiers or {}
    mk = str(q.get("metric_kind") or "").strip()
    if not mk:
        return f"__no_metric_kind__|{id(claim)}|{claim.source_url}"
    parts = [claim.unit_family]
    for k in _HASH_KEYS:
        v = q.get(k, "")
        parts.append(f"{k}={str(v).strip().lower()}")
    return "|".join(parts)


def _fuzzy_can_merge(c_a: RawClaim, c_b: RawClaim, threshold: float) -> bool:
    """Two claim-buckets with same metric+unit+time but differing-string
    subject/segment are merge candidates if their string similarities are
    above threshold (Jaro-Winkler from rapidfuzz)."""
    from rapidfuzz.distance import JaroWinkler

    if c_a.unit_family != c_b.unit_family:
        return False
    qa, qb = c_a.qualifiers or {}, c_b.qualifiers or {}
    for k in ("metric_kind", "as_of", "fiscal_period"):
        va, vb = qa.get(k, ""), qb.get(k, "")
        if (va or vb) and str(va).lower() != str(vb).lower():
            return False
    sims: list[float] = []
    for k in ("subject", "segment", "scope"):
        va, vb = qa.get(k, ""), qb.get(k, "")
        if va and vb and str(va).lower() != str(vb).lower():
            sims.append(JaroWinkler.normalized_similarity(
                str(va).lower().strip(), str(vb).lower().strip()))
    if not sims:
        return True
    return min(sims) >= threshold


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            out[self.find(i)].append(i)
        return out


def cluster_claims_hash(
    claims: list[RawClaim],
    *,
    fuzzy_threshold: float = 0.88,
    on_progress=None,
) -> tuple[list[_ProtoCluster], dict]:
    """Pure-Python clusterer (no LLM, no embeddings).

    Pass 1: bucket by exact qualifier hash.
    Pass 2: fuzzy-merge buckets that have same metric_kind+unit+time but
            differ slightly on subject/segment string. Union-find for
            transitive closure.

    Returns (proto_clusters, stats).
    """
    log = on_progress or (lambda _msg: None)
    stats: dict = {
        "method": "hash+fuzzy",
        "n_unit_families": 0,
        "n_exact_buckets": 0,
        "n_fuzzy_merges": 0,
        "n_pairs_evaluated": 0,
    }
    if not claims:
        return [], stats

    # Pass 1
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(claims):
        buckets[_qualifier_hash_key(c)].append(i)
    stats["n_exact_buckets"] = len(buckets)

    bucket_keys = list(buckets.keys())
    bucket_reps = [claims[buckets[k][0]] for k in bucket_keys]

    # Pass 2 — fuzzy-merge by family blocking
    by_family: dict[str, list[int]] = defaultdict(list)
    for i, rep in enumerate(bucket_reps):
        by_family[rep.unit_family].append(i)
    stats["n_unit_families"] = len(by_family)

    uf = _UnionFind(len(bucket_keys))
    for fam, idxs in by_family.items():
        for ii in range(len(idxs)):
            i_b = idxs[ii]
            for jj in range(ii + 1, len(idxs)):
                j_b = idxs[jj]
                stats["n_pairs_evaluated"] += 1
                if _qualifiers_hard_contradict(
                    bucket_reps[i_b].qualifiers or {},
                    bucket_reps[j_b].qualifiers or {},
                ):
                    continue
                if _fuzzy_can_merge(
                    bucket_reps[i_b], bucket_reps[j_b], fuzzy_threshold
                ):
                    uf.union(i_b, j_b)
                    stats["n_fuzzy_merges"] += 1

    final_clusters: list[_ProtoCluster] = []
    for group_bucket_indices in uf.groups().values():
        member_claim_indices: list[int] = []
        for b_idx in group_bucket_indices:
            member_claim_indices.extend(buckets[bucket_keys[b_idx]])
        members = [claims[i] for i in member_claim_indices]
        rep_claim = members[0]
        dim = ClaimDimension(
            descriptor=rep_claim.descriptor or "(no descriptor)",
            unit_family=rep_claim.unit_family,
            qualifier_summary=_build_qualifier_summary(members),
        )
        proto = _ProtoCluster(dimension=dim)
        for c in members:
            proto.add(c)
        final_clusters.append(proto)

    final_clusters.sort(key=lambda p: len(p.claims), reverse=True)
    log(f"[clusterer/hash] {len(claims)} claims -> {len(buckets)} exact buckets "
        f"-> {len(final_clusters)} clusters after {stats['n_fuzzy_merges']} fuzzy merges")
    return final_clusters, stats

"""Descriptor-based clusterer (v2).

Pipeline (per run):
    1. Group claims by unit_family (HARD constraint: % can't merge with $).
    2. Inside each unit_family group, build the descriptor cosine-similarity
       matrix.
    3. For each pair (i, j):
        cosine >= AUTO_MERGE      -> link them in union-find (no LLM call)
        cosine <  AUTO_SEPARATE   -> never link
        AUTO_SEPARATE <= c < AUTO_MERGE  -> ask LLM judge "same dimension?"
                                           (batched, parallelised, cached)
    4. Walk union-find -> connected components = clusters.
    5. For each cluster, pick the representative descriptor (median by
       intra-cluster cosine to all others).

Caching: judge decisions are cached by (descriptor_a, descriptor_b) order-
independent key so re-runs on overlapping data are free.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .embedder import cosine_matrix
from .extractor import _get_client
from .models import ClaimDimension, RawClaim


# ── Tunable thresholds ──────────────────────────────────────────────────────

AUTO_MERGE_THRESHOLD = 0.92      # cosine above this = same dimension, no LLM
AUTO_SEPARATE_THRESHOLD = 0.70   # cosine below this = different, no LLM
                                 # in between => LLM judge decides

# Cap LLM judge calls per run so a pathological gray-zone matrix can't blow up
MAX_JUDGE_CALLS = 200


# ── Proto-cluster (mutable scratch) ─────────────────────────────────────────

@dataclass
class _ProtoCluster:
    dimension: ClaimDimension
    claims: list[RawClaim] = field(default_factory=list)

    def add(self, claim: RawClaim) -> None:
        self.claims.append(claim)


def _build_qualifier_summary(members: list[RawClaim]) -> dict[str, list[str]]:
    """For each qualifier KEY seen across member claims, collect the sorted
    unique VALUES. Used as the cluster's metadata-aggregate view.
    """
    agg: dict[str, set[str]] = {}
    for c in members:
        for k, v in (c.qualifiers or {}).items():
            if not k or v is None or v == "":
                continue
            agg.setdefault(k, set()).add(str(v))
    return {k: sorted(v) for k, v in agg.items()}


# Qualifier keys that are HARD identifying dimensions: if two claims both have
# one of these keys and the values differ, they describe DIFFERENT measurements
# regardless of how similar their descriptor sentences look. Cosine similarity
# is allowed to say "merge" only if there is no hard contradiction on any of
# these keys. Missing-on-one-side is OK (unknown, not contradiction).
_HARD_IDENTITY_KEYS = ("subject", "metric_kind", "segment", "as_of", "fiscal_period")


def _qualifiers_hard_contradict(a_q: dict, b_q: dict) -> bool:
    """True iff two qualifier dicts disagree on at least one HARD identity key
    (both sides have the key, and the values differ after normalisation).
    """
    if not a_q or not b_q:
        return False
    for k in _HARD_IDENTITY_KEYS:
        av = a_q.get(k)
        bv = b_q.get(k)
        if av and bv:
            if str(av).strip().lower() != str(bv).strip().lower():
                return True
    return False


# ── Pure-Python clusterer (qualifier-hash + fuzzy merge, no LLM/embeddings) ──

# Keys that build the deterministic hash key for a claim. Order is fixed for
# reproducibility. Missing keys collapse to empty string.
_HASH_KEYS = ("subject", "metric_kind", "segment", "scope", "geography",
              "as_of", "fiscal_period", "fiscal_basis", "is_forecast")


def _qualifier_hash_key(claim: RawClaim) -> str:
    """Deterministic key built from canonicalised qualifiers. Two claims with
    the same key share the same dimension. unit_family is prefixed so cross-
    family clusters never collide.

    DEFENSIVE: if `metric_kind` is missing or empty (shouldn't happen now that
    the extractor enforces it, but possible if someone bypasses validation),
    return a per-claim unique key so the claim lands in its own singleton
    bucket instead of silently merging with other unknown-metric claims.
    """
    q = claim.qualifiers or {}
    mk = str(q.get("metric_kind") or "").strip()
    if not mk:
        # Force singleton bucket. id() is stable across this run, sufficient
        # for the clusterer's lifetime; we don't need cross-run determinism
        # for a defensive fallback.
        return f"__no_metric_kind__|{id(claim)}|{claim.source_url}"
    parts = [claim.unit_family]
    for k in _HASH_KEYS:
        v = q.get(k, "")
        parts.append(f"{k}={str(v).strip().lower()}")
    return "|".join(parts)


def _fuzzy_can_merge(c_a: RawClaim, c_b: RawClaim, threshold: float) -> bool:
    """Two clusters with same metric_kind+unit_family+as_of+fiscal_period BUT
    differing-string subject or segment are merge candidates if their string
    similarities are above threshold.
    Uses Jaro-Winkler from rapidfuzz (already a dependency).
    """
    from rapidfuzz.distance import JaroWinkler

    if c_a.unit_family != c_b.unit_family:
        return False
    qa, qb = c_a.qualifiers or {}, c_b.qualifiers or {}
    # Hard fields must match exactly
    for k in ("metric_kind", "as_of", "fiscal_period"):
        va, vb = qa.get(k, ""), qb.get(k, "")
        if (va or vb) and str(va).lower() != str(vb).lower():
            return False
    # Compare subject + segment as strings (where both sides have them)
    sims: list[float] = []
    for k in ("subject", "segment", "scope"):
        va, vb = qa.get(k, ""), qb.get(k, "")
        if va and vb and str(va).lower() != str(vb).lower():
            sims.append(JaroWinkler.normalized_similarity(
                str(va).lower().strip(), str(vb).lower().strip()))
    if not sims:
        return True   # no string-different fields means they should already share a hash
    return min(sims) >= threshold


def cluster_claims_hash(
    claims: list[RawClaim],
    *,
    fuzzy_threshold: float = 0.88,
    on_progress=None,
) -> tuple[list[_ProtoCluster], dict]:
    """Pure-Python clusterer.

    Pass 1: bucket by exact qualifier hash (O(N), defaultdict groupby).
    Pass 2: for each pair of buckets that COULD merge by metric+unit+time,
            run Jaro-Winkler on the differing subject/segment strings.
            Merge if all string similarities >= fuzzy_threshold.
            Union-find for transitive closure.

    Returns (proto_clusters, stats). Same shape as cluster_claims so the
    aggregator + visualiser don't care which clusterer ran.
    """
    log = on_progress or (lambda _msg: None)
    stats: dict = {
        "method": "hash+fuzzy",
        "n_unit_families": 0,
        "n_exact_buckets": 0,
        "n_fuzzy_merges": 0,
        "judge_cost_usd": 0.0,
        "n_judge_calls": 0,
        "n_pairs_evaluated": 0,
        "n_auto_merge": 0,
        "n_auto_separate": 0,
        "n_judged_llm": 0,
        "n_judged_cached": 0,
        "n_judge_same": 0,
    }
    if not claims:
        return [], stats

    # Pass 1 — group by exact qualifier hash
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(claims):
        buckets[_qualifier_hash_key(c)].append(i)
    stats["n_exact_buckets"] = len(buckets)

    # Build a representative claim per bucket for fuzzy-merge comparison
    bucket_keys = list(buckets.keys())
    bucket_reps = [claims[buckets[k][0]] for k in bucket_keys]

    # Pass 2 — fuzzy-merge buckets that should join (by family for blocking)
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
                    stats["n_auto_separate"] += 1
                    continue
                if _fuzzy_can_merge(
                    bucket_reps[i_b], bucket_reps[j_b], fuzzy_threshold
                ):
                    uf.union(i_b, j_b)
                    stats["n_fuzzy_merges"] += 1
                    stats["n_auto_merge"] += 1
                else:
                    stats["n_auto_separate"] += 1

    # Build proto-clusters from bucket-level groups
    final_clusters: list[_ProtoCluster] = []
    for group_bucket_indices in uf.groups().values():
        # Collect all claim indices across buckets in this group
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


# ── Judge cache (disk) ──────────────────────────────────────────────────────

_CACHE_DIR = Path.home() / ".research" / "cache" / "clusterer_judge"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _judge_cache_key(a: str, b: str) -> str:
    canon = "|||".join(sorted([a.strip().lower(), b.strip().lower()]))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _load_judge_cache(key: str) -> Optional[bool]:
    p = _CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    try:
        return bool(json.loads(p.read_text(encoding="utf-8"))["same"])
    except Exception:
        return None


def _save_judge_cache(key: str, same: bool, reason: str = "") -> None:
    p = _CACHE_DIR / f"{key}.json"
    try:
        p.write_text(json.dumps({"same": same, "reason": reason}), encoding="utf-8")
    except OSError:
        pass


# ── LLM judge ───────────────────────────────────────────────────────────────

_JUDGE_BATCH_SYSTEM = """You decide whether each pair of claims describes THE
SAME measurement — meaning both claims could be acceptable as estimates of
one quantity and averaged together. Each claim has a short descriptor sentence
AND a qualifier dict that carries explicit dimensions.

Two claims are the SAME measurement iff BOTH of these hold:
  (a) their descriptors describe the same quantity, AND
  (b) their qualifier sets do not CONTRADICT on any shared key.

Rule for qualifier contradiction: if both claims have the same qualifier key
(e.g. both have "metric_kind"), the canonicalised values must match. If only
one has a key, that's NOT a contradiction — missing keys are unknowns, not
disagreements.

DIFFERENT if any of these differs between the two:
  - subject (industry-total vs specific company; NVIDIA vs AMD; region X vs Y)
  - metric_kind (revenue vs operating_income vs net_income vs market_size)
  - segment (discrete GPU vs AIB vs Radeon-only vs datacenter GPU)
  - fiscal_period (Q4 vs FY)
  - as_of (2024 vs 2030)
  - geography / scope / reporting_standard when present on both

You receive JSON input and return JSON output.

Input JSON:  {"pairs": [
    {"id": 0,
     "a": {"descriptor": "...", "qualifiers": {...}},
     "b": {"descriptor": "...", "qualifiers": {...}}},
    {"id": 1, ...}, ...
]}
Output JSON: {"results": [{"id": 0, "same": true|false, "reason": "..."}, ...]}

Every input id must appear in the output JSON exactly once. `reason` should
be one short clause naming the deciding qualifier (e.g. "same subject/metric/
period", or "differ on metric_kind: revenue vs net_income"). Return ONLY the
JSON object.
"""


def _judge_batch(
    pairs: list[tuple[int, int, dict, dict]],
    *,
    model: str = "gpt-4o-mini",
) -> tuple[dict[tuple[int, int], bool], int, int]:
    """Send a batch of (i, j, claim_i_view, claim_j_view) to the LLM.

    Each claim_view is {"descriptor": str, "qualifiers": dict}.
    Returns (decisions, prompt_tokens, completion_tokens) keyed by (i, j) with i < j.
    """
    if not pairs:
        return {}, 0, 0

    payload = {"pairs": [
        {"id": k, "a": a, "b": b} for k, (_, _, a, b) in enumerate(pairs)
    ]}
    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _JUDGE_BATCH_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        print(f"[clusterer] judge batch failed: {exc}")
        return {}, 0, 0

    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    results = data.get("results", []) if isinstance(data, dict) else []

    decisions: dict[tuple[int, int], bool] = {}
    for r in results:
        try:
            k = int(r.get("id"))
            same = bool(r.get("same"))
            reason = str(r.get("reason", ""))
            i, j, a_view, b_view = pairs[k]
            ij = (min(i, j), max(i, j))
            decisions[ij] = same
            # Cache key uses the descriptor strings only — descriptor is a
            # function of the qualifiers (same qualifiers -> same descriptor),
            # so this key space is stable across runs.
            desc_a = str(a_view.get("descriptor", ""))
            desc_b = str(b_view.get("descriptor", ""))
            _save_judge_cache(_judge_cache_key(desc_a, desc_b), same, reason)
        except (TypeError, ValueError, IndexError, AttributeError):
            continue

    usage = resp.usage
    return (
        decisions,
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


# ── Cluster representative ──────────────────────────────────────────────────

def _pick_representative(indices: list[int], cosine_mat: np.ndarray) -> int:
    """Pick the cluster member whose descriptor is most central (highest avg
    similarity to other members)."""
    if len(indices) == 1:
        return indices[0]
    sub = cosine_mat[np.ix_(indices, indices)]
    avg_sim = sub.mean(axis=1)
    return indices[int(np.argmax(avg_sim))]


# ── Union-find ──────────────────────────────────────────────────────────────

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


# ── Main entry ──────────────────────────────────────────────────────────────

def cluster_claims(
    claims: list[RawClaim],
    *,
    auto_merge: float = AUTO_MERGE_THRESHOLD,
    auto_separate: float = AUTO_SEPARATE_THRESHOLD,
    judge_model: str = "gpt-4o-mini",
    judge_batch_size: int = 12,
    max_judge_calls: int = MAX_JUDGE_CALLS,
    on_progress=None,
) -> tuple[list[_ProtoCluster], dict]:
    """Cluster claims using descriptor embeddings + LLM judge for gray zone.

    Returns (proto_clusters, stats) where stats includes:
        n_pairs_evaluated, n_auto_merge, n_auto_separate, n_judged,
        n_judge_same, n_judge_calls, judge_cost_usd
    """
    log = on_progress or (lambda _msg: None)

    stats = {
        "n_unit_families": 0,
        "n_pairs_evaluated": 0,
        "n_auto_merge": 0,
        "n_auto_separate": 0,
        "n_judged_cached": 0,
        "n_judged_llm": 0,
        "n_judge_calls": 0,
        "n_judge_same": 0,
        "judge_cost_usd": 0.0,
    }
    if not claims:
        return [], stats

    # Group by unit_family - clusters never cross unit families
    by_family: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(claims):
        by_family[c.unit_family].append(i)
    stats["n_unit_families"] = len(by_family)

    final_clusters: list[_ProtoCluster] = []

    # Per-family clustering
    for family, idxs in by_family.items():
        n = len(idxs)
        if n == 0:
            continue
        family_claims = [claims[i] for i in idxs]
        embeddings = [c.descriptor_embedding for c in family_claims]
        cos_mat = cosine_matrix(embeddings)
        uf = _UnionFind(n)

        # First pass: classify pairs into auto-merge / gray / auto-separate.
        # HARD RULE (this is the whole point of qualifiers): if two claims
        # contradict on any HARD identity qualifier (subject, metric_kind,
        # segment, as_of, fiscal_period), they CANNOT merge regardless of
        # cosine similarity — cosine on descriptor strings alone is
        # token-count biased and would happily merge "NVIDIA share ..." with
        # "AMD share ..." because they share 14/15 tokens.
        gray_pairs: list[tuple[int, int]] = []
        for i in range(n):
            q_i = family_claims[i].qualifiers or {}
            for j in range(i + 1, n):
                stats["n_pairs_evaluated"] += 1
                q_j = family_claims[j].qualifiers or {}
                if _qualifiers_hard_contradict(q_i, q_j):
                    stats["n_auto_separate"] += 1
                    stats["n_qualifier_block"] = stats.get("n_qualifier_block", 0) + 1
                    continue
                c = float(cos_mat[i, j])
                if c >= auto_merge:
                    uf.union(i, j)
                    stats["n_auto_merge"] += 1
                elif c < auto_separate:
                    stats["n_auto_separate"] += 1
                else:
                    gray_pairs.append((i, j))

        # Second pass: resolve gray-zone via cache + LLM judge.
        # Judge receives BOTH descriptor and qualifiers per claim so it can
        # reason about qualifier contradictions explicitly.
        cached_decisions: dict[tuple[int, int], bool] = {}
        to_query: list[tuple[int, int, dict, dict]] = []
        for (i, j) in gray_pairs:
            ci = family_claims[i]
            cj = family_claims[j]
            a_view = {"descriptor": ci.descriptor or "",
                      "qualifiers": dict(ci.qualifiers or {})}
            b_view = {"descriptor": cj.descriptor or "",
                      "qualifiers": dict(cj.qualifiers or {})}
            key = _judge_cache_key(a_view["descriptor"], b_view["descriptor"])
            cached = _load_judge_cache(key)
            if cached is not None:
                cached_decisions[(i, j)] = cached
                stats["n_judged_cached"] += 1
                if cached:
                    uf.union(i, j)
                    stats["n_judge_same"] += 1
            else:
                to_query.append((i, j, a_view, b_view))

        # Cap LLM calls
        if len(to_query) > max_judge_calls * judge_batch_size:
            log(f"[clusterer] {len(to_query)} gray pairs > cap; truncating to {max_judge_calls * judge_batch_size}")
            to_query = to_query[:max_judge_calls * judge_batch_size]

        # Batch the remaining pairs
        batches = [
            to_query[k:k + judge_batch_size]
            for k in range(0, len(to_query), judge_batch_size)
        ]
        if batches:
            log(f"[clusterer] family={family}: {len(to_query)} gray pairs, {len(batches)} judge batches")

        from .describer import _price_for_model
        in_per_m, out_per_m = _price_for_model(judge_model)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_judge_batch, b, model=judge_model) for b in batches]
            for fut in as_completed(futures):
                try:
                    decisions, p_tok, c_tok = fut.result()
                except Exception as exc:
                    log(f"[clusterer] judge crashed: {exc}")
                    continue
                stats["n_judge_calls"] += 1
                stats["n_judged_llm"] += len(decisions)
                stats["judge_cost_usd"] += (p_tok / 1_000_000) * in_per_m + (c_tok / 1_000_000) * out_per_m
                for (i, j), same in decisions.items():
                    if same:
                        uf.union(i, j)
                        stats["n_judge_same"] += 1

        # Build proto-clusters from union-find groups
        for group_indices in uf.groups().values():
            rep_local_idx = _pick_representative(group_indices, cos_mat)
            rep_claim = family_claims[rep_local_idx]
            members = [family_claims[i] for i in group_indices]

            dim = ClaimDimension(
                descriptor=rep_claim.descriptor or "(no descriptor)",
                unit_family=family,  # type: ignore[arg-type]
                qualifier_summary=_build_qualifier_summary(members),
            )
            proto = _ProtoCluster(dimension=dim)
            for c in members:
                proto.add(c)
            final_clusters.append(proto)

    # Sort: largest clusters first
    final_clusters.sort(key=lambda p: len(p.claims), reverse=True)

    log(
        f"[clusterer] {len(claims)} claims -> {len(final_clusters)} clusters "
        f"({stats['n_auto_merge']} auto-merge, {stats['n_auto_separate']} auto-sep, "
        f"{stats['n_judged_llm']}+{stats['n_judged_cached']} judged, "
        f"${stats['judge_cost_usd']:.4f} judge cost)"
    )
    return final_clusters, stats

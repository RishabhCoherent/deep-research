# claim_clustering

Standalone module for **claim-level dimensional disambiguation + consensus estimation**
across research sources. Distinct from `clustering.py` at the repo root, which clusters
whole articles by topic.

## Goal

Given many numeric claims extracted from different sources during research:

1. Assign each claim a **canonical dimension** tuple: `(entity, metric, segment, scope, unit, as_of)`
2. Cluster claims that share the same dimension
3. For each cluster, compute consensus statistics: weighted mean, range, stddev,
   outliers, time-series trend
4. Emit `ClusteredEstimate` objects that replace single-point claims in the final report

## Why

A research report saying *"GPU market is $65B (source: Gartner)"* is fragile.
A report saying *"GPU market is $67B (range $62-70B across 4 sources; 26% YoY growth
from $53B in 2023)"* is analyst-grade.

This module exists to produce the second kind.

## Scope

- **Input:** a list of claim-like dicts with at least `metric`, `value`, `unit`,
  optional `as_of`, `citation` (url, authority_tier, published).
  Compatible with `backend2/research/core/types.py::NumericClaim`.
- **Output:** `list[ClusteredEstimate]` with full provenance + aggregate statistics.
- **Self-contained:** pulls no imports from `backend/` or `backend2/`. Can be wired in later.

## Planned structure (will fill in as we go)

```
claim_clustering/
  README.md                 - this file
  __init__.py               - package marker
  models.py                 - Pydantic: ClaimDimension, ClusteredEstimate
  extractor.py              - LLM: raw claim -> canonical dimension
  canonicalise.py           - deterministic: unit normalisation, entity aliases
  clusterer.py              - tuple match + fuzzy merge
  aggregator.py             - tier-weighted mean, outlier flag, trend slope
  cli.py                    - entry: analyse a prior trace's final_state.json
  tests/
    test_canonicalise.py
    test_clusterer.py
    test_aggregator.py
  data/
    fixtures/               - sample claim batches for testing
```

## Phases

1. **Phase 1 - standalone module.** Build models, extractor, clusterer, aggregator
   as a library. CLI that ingests a `final_state.json` trace and emits
   `clustered_estimates.json`. No pipeline integration yet.
2. **Phase 2 - pipeline integration.** Add a node between A5 and A6 in
   `backend2/research/graph/build.py` that runs this module over the merged claims.
3. **Phase 3 - downstream upgrades.** Refactor A6/A7/A8 to consume clustered
   estimates instead of raw claims; render consensus ranges and trends in the brief.

Phase 1 is validatable in isolation against existing traces; start there.

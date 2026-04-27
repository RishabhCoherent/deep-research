{PLAYBOOK}

## Your specific job
Identify metrics that appear at two different points in time and compute the change.

You will receive a JSON list of validated claims. Your job:
1. Group claims by SEMANTIC metric equivalence (e.g. "Brent crude Q4 2025" and
   "Brent crude Apr 2026" are the same metric despite different phrasing).
2. Within each group, find pairs with different as_of dates.
3. For each pair: the earlier as_of = prior, the later as_of = current.
4. Compute delta_pct = (current_value - prior_value) / |prior_value| * 100.
5. Sort output by |delta_pct| descending — biggest changes first.
6. Only include pairs where both values are numeric and prior_value ≠ 0.
7. Limit to the top 10 largest deltas (by absolute value).

Rules:
  - Skip non-numeric values (e.g. "TBD", "N/A").
  - If as_of is absent for a claim, skip that claim.
  - Do NOT invent prior/current values — only use exact claim data.
  - Return ONLY valid JSON matching DeltaBundle: {deltas: [Delta, ...]}.

Delta fields:
  - metric: canonical metric name (normalised)
  - prior: the NumericClaim with the earlier as_of date
  - current: the NumericClaim with the later as_of date
  - delta_pct: float (positive = increase)
  - window_start: prior.as_of (ISO date)
  - window_end: current.as_of (ISO date)

{PLAYBOOK}

## Your specific job
Group claims by (metric, scope) and identify conflicts.

Two claims are about the SAME metric if they measure the same concept with the same scope,
even if phrased differently. Examples:
  - "global EV battery market size" == "EV battery market value worldwide" → SAME
  - "CATL market share" (global) != "CATL market share" (China) → DIFFERENT (different scope)
  - "cell price USD/kWh" == "battery cell price per kWh" → SAME

Steps:
1. Group the ranked claims by (normalised metric name, scope).
2. For groups with exactly 1 claim: mark as unanimous.
3. For groups with ≥2 claims: compute max pairwise % diff and create a ConflictCandidate.
   - max_diff_pct = max(|a - b| / avg(|a|, |b|) * 100 for all pairs)
   - Leave recency_winner_idx as null (set by 7c).

Rules:
  - Every input claim must appear in exactly one group.
  - If two claims reference the same metric but different time periods (2024 vs 2025),
    treat them as DIFFERENT scope (add the year to scope field).
  - Return ONLY valid JSON matching CrossCheckResult:
    {unanimous: [NumericClaim, ...], conflicted: [ConflictCandidate, ...]}.

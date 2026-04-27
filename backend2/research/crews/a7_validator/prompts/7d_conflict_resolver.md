{PLAYBOOK}

## Your specific job
Make the final resolution for each conflict candidate and build the complete Conflict audit trail.

For each ConflictCandidate:
1. Pick the winner using this STRICT priority (code-enforced — you MUST follow it):
   a. Highest authority tier wins (government > multilateral > industry_body > tier1_media >
      analyst_firm > trade_press > blog > unknown).
   b. If tied on tier, the claim at recency_winner_idx wins.
   c. If the top-2 finalists are within 5% of each other AND have the same tier:
      emit a RANGE claim: value = "{low}–{high}", unit = same unit.
      The chosen claim is the range version of the higher-authority one.
2. For each rejected claim, write a clear rejection reason (<= 80 chars).
   CRITICAL: `as_of` is the year the claim's NUMBER is about (forecast target
   or measurement period). `citation.published` is when the SOURCE DOCUMENT
   was published. When writing "older source", you MUST be comparing
   `citation.published` values — NOT `as_of` years. A claim with as_of=2033
   is a 2033 forecast; it is NOT an old source.

   Good rejection reasons:
   - "lower authority tier (blog) vs analyst_firm winner"
   - "same tier, source published earlier (published 2024-11 vs 2026-02)"
   - "lower authority and older publication date"
   - "same tier, same publication date, superseded by as_of"
   - "same tier, insufficient publication-date info, kept first-listed claim"

   BAD rejection reasons (DO NOT write these):
   - "older source (2033 vs 2025)"  <- these are as_of forecast years, not pub dates
   - "2030 projection older than 2025 current"  <- same confusion
3. Collect all unanimous claims as-is into validated_claims.
4. Return the final validated_claims list (including range claims) and all Conflict objects.

CRITICAL: The winner MUST be the highest-authority claim. You cannot pick a blog source
over an analyst_firm source, regardless of the narrative context.

Rules:
  - Return ONLY valid JSON matching ValidationResult:
    {validated_claims: [NumericClaim, ...], conflicts: [Conflict, ...]}.
  - Every Conflict needs: chosen (NumericClaim) + rejected [(NumericClaim, reason)].
  - validated_claims must include ALL unanimous claims + one winner per conflicted group.

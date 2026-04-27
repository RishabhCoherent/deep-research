{PLAYBOOK}

## Your specific job
Tag every claim with its source authority tier by calling assess_source(url).

For each claim in the input list:
1. Call assess_source(url) where url = claim.citation.url
2. If the returned tier is higher authority than the claim's existing authority_tier,
   update it. Never downgrade an existing tier.
3. Return the complete list of claims with confirmed authority_tier values.

Authority hierarchy (highest to lowest):
  government > multilateral > industry_body > tier1_media > analyst_firm > trade_press > blog > unknown

Rules:
  - Call assess_source once per unique URL (deduplicate tool calls).
  - Do NOT remove any claims.
  - Do NOT change metric, value, unit, raw_excerpt, or citation fields.
  - Return ONLY valid JSON matching RankedClaims: {claims: [NumericClaim, ...]}.

{PLAYBOOK}

## Your specific job
Quantify how parent-market and value-chain forces pass through to the child market.

Workflow:
1. Call scratchpad_read("topic") to read claims already found by Agent 3 — use them as benchmarks.
2. Call scratchpad_read("market_context") to read the value chain already mapped by 4b.
3. For each major force (≤ 2 Tavily calls to find pass-through estimates):
   - Identify the force: e.g. "lithium spot price", "EU CBAM regulation", "IRA domestic content"
   - Determine direction: positive / negative / mixed impact on child market
   - Quantify magnitude: e.g. "10% ↓ lithium → ~3.7% ↓ cell price"
   - Explain mechanism: e.g. "pass-through factor ≈ 0.37 per BNEF 2026 analysis"
   - Cite evidence: ≥ 1 citation per impact item

4. Extract NumericClaims from the pass-through data (raw_excerpt verbatim).
5. Write a 400-800 word analyst narrative:
   - Open with the most quantified, surprising, or high-stakes pass-through
   - Cite inline with [N] footnotes
   - Cover 2-4 major forces
   - Close with implications for the child market over the next 12-18 months

Rules:
  - ≤ 2 Tavily calls.
  - Every ImpactItem must have ≥ 1 evidence citation.
  - raw_excerpt in every NumericClaim must be verbatim from a fetched source.
  - Return ONLY valid JSON matching ImpactAnalysis.

Chosen query: <<<{chosen_query}>>>
Parent market (JSON): {parent_market_json}
Value chain (JSON):   {value_chain_json}
Top sub-questions (JSON): {sub_questions_json}

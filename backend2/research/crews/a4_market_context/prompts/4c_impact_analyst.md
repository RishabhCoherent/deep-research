{PLAYBOOK}

## Your specific job
Write the **market-context narrative** — how parent-market and value-chain forces
shape the child market. Your deliverable is a well-grounded analyst paragraph, not
a bag of numeric claims. A3 already owns the size-and-growth numbers.

Workflow:
1. Call scratchpad_read("topic") to read claims already found by Agent 3 — use them as benchmarks.
2. Call scratchpad_read("market_context") to read the value chain already mapped by 4b.
3. Spend at most 2 web_search calls to back-fill any pass-through estimate the
   narrative will cite (e.g. commodity price link, regulatory cost impact).
4. Note 2-4 major forces acting on the market:
   - Identify each force: e.g. "lithium spot price", "EU CBAM regulation", "IRA domestic content"
   - Direction: positive / negative / mixed impact on child market
   - Mechanism: why and through which value-chain node
   - Cite evidence: >= 1 citation per ImpactItem

5. Write a 400-800 word analyst narrative:
   - Open with the most high-stakes pass-through force
   - Cite inline with [N] footnotes
   - Cover 2-4 major forces
   - Close with implications for the child market over the next 12-18 months

Query-crafting rules (CRITICAL):
  - Derive a SHORT market noun-phrase from the chosen_query.
  - Query format: `<force-or-entity> <market-noun-phrase> <metric>`.
  - NEVER paste the full chosen_query into a query.

Rules:
  - At most 2 web_search calls.
  - Every ImpactItem must have >= 1 evidence citation.
  - You MAY emit `claims` in the output, but the node intentionally DISCARDS them
    (A3 already owns numeric claims; A4's role is narrative + scratchpad).
    Put `claims: []` to avoid wasting tokens on claim JSON, OR include what you find
    — either way the node drops them. Focus your effort on narrative quality.
  - Return ONLY valid JSON matching ImpactAnalysis.

{PLAYBOOK}

## Your specific job
Map the complete value chain for the parent market with named players and approximate shares.

Workflow:
1. Call scratchpad_read("topic") to see what Agent 3 already found — avoid re-fetching sources.
2. Run up to 4 Tavily searches targeting named upstream suppliers, midstream processors,
   and downstream OEMs/integrators. Focus on:
   - "upstream suppliers <parent market> market share 2025"
   - "midstream manufacturers <parent market> top players"
   - "downstream customers <child market> leading companies"
   - "substitute technologies <child market> maturity commercial"
3. Build the ValueChainMap:
   - upstream:    raw material / component suppliers (≥ 2 entries, include approx_share where known)
   - midstream:   processors / manufacturers / assemblers
   - downstream:  OEMs, integrators, end-use buyers
   - substitutes: competing technologies (maturity + threat_level + rationale)

4. IMMEDIATELY write to scratchpad before finishing:
   - One observation per major upstream node: key="{stage}_{name}", value="role + share + geography"
   - One consolidated observation: key="value_chain_summary", value=JSON summary of all stages
   Use section="market_context", written_by="a4_market_context".
   These observations are read by Agent 5c to target geopolitical searches.

Rules:
  - ≤ 4 Tavily calls.
  - Every ChainNode must have a name, role, and stage.
  - approx_share is optional — only include when a credible source states it.
  - Return ONLY valid JSON matching ValueChainMap.

Chosen query: <<<{chosen_query}>>>
Parent market result (JSON):
{parent_market_json}

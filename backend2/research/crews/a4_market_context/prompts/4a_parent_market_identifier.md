{PLAYBOOK}

## Your specific job
Identify where the target market sits in the global market hierarchy.

Steps:
1. Call research_search with a precise query like:
   "<child market> parent market hierarchy industry classification"
   Add site: filters for oecd.org, iea.org, mckinsey.com, gartner.com, spglobal.com.
2. Call web_fetch on the most authoritative result.
3. Produce ParentMarketResult with:
   - child:       the exact market named in the chosen_query (short noun phrase)
   - parent:      the immediate parent market (one level up)
   - grandparent: the sector/macro category (one more level up)
   - justification: 2-3 sentences explaining the hierarchy using industry classification systems
                    (NAICS, SIC, GICS, or analyst convention). Cite your source inline.
   - citations:   1-3 citations from authoritative sources

Rules:
  - ≤ 2 Tavily calls total.
  - If a reputable source is not found in 2 calls, use industry-standard taxonomy reasoning
    and provide a citation to the taxonomy document itself.
  - Do NOT invent parent markets — use standard analyst convention.
  - Return ONLY valid JSON matching ParentMarketResult.

Intent: {intent}
Chosen query: <<<{chosen_query}>>>

Top sub-questions (JSON):
{sub_questions_json}

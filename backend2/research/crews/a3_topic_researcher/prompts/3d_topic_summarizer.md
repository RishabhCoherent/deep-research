{PLAYBOOK}

## Your specific job
Write a 400-800 word analyst-tone narrative answering the chosen query.
Use ONLY the validated claims provided — do not introduce any numbers from memory.

Narrative rules:
  - Open with the strongest, most specific number (market size, price, share, growth rate).
  - Cite inline with [N] (e.g. "...at $89/kWh [1], down 38% year-on-year [2]...").
  - footnotes: list every [N] with its full citation (url, title, publisher, authority_tier).
  - Footnote IDs must be 1-indexed and CONTIGUOUS (1, 2, 3… not 1, 3, 5).
  - Every [N] used in the narrative MUST appear in the footnotes list.
  - Every footnote N in the list MUST be cited in the narrative.
  - Do NOT introduce linkages between claims that aren't supported by a source.
  - Use concise, active prose. No marketing language. No hedging beyond what the data supports.
  - Target 550 words (min 400, max 800).

Scratchpad writes:
  - After the narrative, include 3-7 scratchpad_writes under section="topic".
  - Each write captures one high-signal observation that Agents 4 and 5 might use:
    key market prices, named upstream players, supply chain chokepoints, regulatory signals.
  - key: short snake_case identifier (e.g. "cell_price_2026_q1_global")
  - value: one-sentence fact with units and date (max 400 chars)
  - written_by: "a3_topic_researcher"
  - citation: attach if the observation has a specific source

Return ONLY valid JSON matching TopicSummary.

Validated claims (JSON):
{claims_json}

Passage map (JSON, url → {publisher, title, authority_tier}):
{passage_map_json}

Chosen query:
<<<{chosen_query}>>>

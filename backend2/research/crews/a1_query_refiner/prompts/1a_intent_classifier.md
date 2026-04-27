{PLAYBOOK}

## Your specific job
Read the raw analyst query below and classify it into exactly ONE IntentKind.

**Valid intent values (use ONLY these exact strings):**
- `market_sizing`  — market size, TAM, revenue, growth, CAGR, forecast, supply chain, bottlenecks
- `competitive`    — competitors, market share, rankings, OEMs, player comparison
- `trend`          — emerging patterns, adoption curves, multi-year shifts
- `regulatory`     — policy, tariffs, subsidies, standards, antitrust, compliance
- `technology`     — specific tech, chemistry, protocol, R&D, innovation pipeline
- `geographic`     — country/region comparison, cross-border dynamics
- `general`        — anything that does not fit the above market research intents

Use these tie-breakers when two intents seem plausible:
  - Mentions number/size/forecast/supply chain/bottleneck → `market_sizing`
  - Names competitors, share, ranking → `competitive`
  - Mentions policy, regulator, tariff, standard → `regulatory`
  - Geographic comparison (country vs country) → `geographic`
  - Specific technology or capability → `technology`
  - Otherwise → `general`

Return ONLY valid JSON matching IntentClassification. confidence ∈ [0,1].
Keep reasoning under 60 words.

Raw query:
<<<{raw_query}>>>

{PLAYBOOK}

## Your specific job
Read the raw analyst query below and classify it into exactly ONE IntentKind.

Use these tie-breakers when two intents seem plausible:
  - If the query mentions a number/size/forecast → market_sizing wins.
  - If it names competitors, share, ranking, or OEMs → competitive wins.
  - If it mentions a policy, regulator, tariff, standard → regulatory wins.
  - If it mentions a geographic comparison (country/region vs another) → geographic wins.
  - If it mentions a technology, chemistry, protocol, or new capability → technology wins.
  - Otherwise → trend.

Return ONLY valid JSON matching IntentClassification. confidence ∈ [0,1].
Keep reasoning under 60 words.

Raw query:
<<<{raw_query}>>>

{PLAYBOOK}

## Your specific job
From the fetched passages, extract NumericClaims.

For each claim:
  - metric:      short noun phrase ("global EV battery cell price", "LFP cell price")
  - value:       number as float (e.g. 89.0) — extract from a single stated number
  - unit:        short string ("USD/kWh", "% YoY", "GWh", "USD billion")
  - as_of:       ISO date IF stated in the passage (e.g. "2026-Q1", "2026-03"); null if absent
  - scope:       geographic scope IF stated ("global", "US", "APAC"); null if absent
  - raw_excerpt: COPY the EXACT sentence from the passage that contains the number.
                 DO NOT paraphrase. DO NOT summarise. Preserve original casing.
  - citation:    build from the passage metadata:
                 url, title, publisher, published, accessed, authority_tier

CRITICAL RULES:
  - Only extract claims where you can find the EXACT sentence in the passage text.
  - Drop any claim where the exact sentence is not present (it will be validated).
  - For a range like "$10-12B", emit TWO claims: one with value=10, one with value=12.
  - Do NOT invent numbers — only extract what is explicitly stated in the passages.
  - Prefer quantitative claims over qualitative ones.
  - Aim for 6-25 claims across all passages.

Return ONLY valid JSON matching ExtractedClaims.

Passages (JSON):
{passages_json}

Chosen query:
<<<{chosen_query}>>>

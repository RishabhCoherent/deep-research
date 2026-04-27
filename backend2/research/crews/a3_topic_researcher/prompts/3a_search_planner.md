{PLAYBOOK}

## Your specific job
For EACH sub-question provided (top 8 by composite score), produce 1-2 Tavily
search queries designed to surface high-authority passages containing NUMERIC answers.

Rules:
  - Use precise nouns, units, and time frames. Quote multi-word phrases where helpful.
  - Prefer site: filters when the answer obviously lives on a known authority domain
    (iea.org, oecd.org, sec.gov, ec.europa.eu, bnef.com, worldbank.org, etc.).
  - Set time_window_days=365 when recency matters; 730 for 2-year trends.
  - Total queries across ALL sub-questions MUST be ≤ 12.
  - Each PlannedSearch must have 1-2 queries, never 0.
  - rationale: one sentence explaining why these queries will surface numeric answers.
  - Do NOT include any queries already covered by adjacent sub-questions.
  - Return ONLY valid JSON matching SearchPlan.

Valid SearchQuery fields:
  - text: str (max 200 chars)
  - time_window_days: int | null
  - site_filter: str | null (e.g. "site:iea.org")

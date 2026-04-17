{PLAYBOOK}

## Your specific job
Find tariff changes, subsidies, standards, and antitrust actions from regulators
that affect the child market or its parent market in the last 90 days.

Workflow:
1. Run up to 4 web_search calls (topic=news, days=90). Target:
   - "{chosen_query} regulation policy 2026"
   - "{child_market} tariff subsidy incentive 2026"
   - "{child_market} antitrust standard compliance 2026"
   - "{parent_market} government policy trade 2026"
2. For each regulatory action, identify:
   - regulator: the government body or agency (e.g. "European Commission", "US DOE")
   - action: what they did (max 400 chars)
   - effective_date: when it takes/took effect (ISO format YYYY-MM-DD, or null if unknown)
   - impact_summary: what it means for the market (max 400 chars)
   - estimated_cost_impact: quantified if available (e.g. "$35/kWh", "3% margin hit", or null)

Rules:
  - ≤ 4 web_search calls.
  - Only include changes from the last 90 days or taking effect within 12 months.
  - Every change must have a source Citation.
  - Return at least 1 regulatory change.
  - Return ONLY valid JSON matching RegulatoryBundle: {changes: [RegulatoryChange, ...]}.

Intent: {intent}
Chosen query: <<<{chosen_query}>>>

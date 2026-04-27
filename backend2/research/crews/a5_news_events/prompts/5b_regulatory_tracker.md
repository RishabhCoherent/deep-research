{PLAYBOOK}

## Your specific job
Find tariff changes, subsidies, standards, and antitrust actions from regulators
that affect **the specific market named in the user's query** within the last 90 days.
You will be given the market topic at task execution time in the `chosen_query` input.

Query-crafting rules (CRITICAL — most common failure mode is losing the topic):
  - EVERY web_search query you issue MUST mention the specific market (or its obvious
    parent sector). Never issue a generic query like "tariff subsidy changes" — that
    returns unrelated wine / asylum / AI policy noise.
  - Good query shape: "<topic-keyword-or-phrase> <policy-lever> <year>".
    Example for EV charging infrastructure in Europe 2025:
      - "EV charging subsidy EU 2026"
      - "EV charging tariff import duty 2026"
      - "EV charging interoperability standard AFIR 2026"
      - "EV charging antitrust competition ruling 2026"
  - If a search returns unrelated items, reformulate — do not accept them.

Workflow:
1. Run up to 4 web_search calls (topic=news, days=90), each scoped to the market topic.
2. For each regulatory action, identify:
   - regulator: the government body or agency (e.g. "European Commission", "US DOE")
   - action: what they did (max 400 chars)
   - effective_date: when it takes/took effect (ISO format YYYY-MM-DD, or null if unknown)
   - impact_summary: what it means for the market (max 400 chars)
   - estimated_cost_impact: quantified if available (e.g. "$35/kWh", "3% margin hit", or null)

Rules:
  - ONE search = one topic-scoped query. Four searches MAX.
  - Only include changes from the last 90 days or taking effect within 12 months.
  - Every change must have a source Citation.
  - Discard any regulatory hit that doesn't explicitly reference the market sector.
  - Return ONLY valid JSON matching RegulatoryBundle: {changes: [RegulatoryChange, ...]}.
  - If no topic-relevant regulatory changes are found, return {changes: []}.

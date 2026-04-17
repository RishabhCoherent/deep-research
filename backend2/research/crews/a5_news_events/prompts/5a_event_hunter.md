{PLAYBOOK}

## Your specific job
Find significant company, product, M&A, earnings, partnership, and investment events
from the last 90 days that affect the child market or its parent market.

Workflow:
1. Run up to 6 web_search calls (topic=news, days=90). Target:
   - "{chosen_query} news 2026"
   - "top companies {child_market} earnings Q1 2026"
   - "{child_market} mergers acquisitions investment 2026"
   - "{child_market} new product launch 2026"
   - "{parent_market} major news 2026" (use parent from scratchpad if available)
2. For each significant event found, call web_fetch on the article URL for the full headline and date.
3. Classify each event into: m_and_a / earnings / product / partnership / investment / other.
4. Rate impact (positive/negative/neutral/mixed) and magnitude (low/medium/high) on the child market.

Rules:
  - ≤ 6 web_search calls.
  - Only include events from the last 90 days. Exclude older events.
  - Every event must have a source Citation with a valid URL.
  - headline max 300 chars, summary max 500 chars.
  - Return at least 3 events. If fewer are found, lower the significance threshold.
  - Return ONLY valid JSON matching EventBundle: {events: [NewsEvent, ...]}.

Intent: {intent}
Chosen query: <<<{chosen_query}>>>

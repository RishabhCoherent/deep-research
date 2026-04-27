{PLAYBOOK}

## Your specific job
Find significant company, product, M&A, earnings, partnership, and investment events
from the last 90 days that affect **the specific market named in the user's query**.
You will be given the market topic at task execution time in the `chosen_query` input.

Query-crafting rules (CRITICAL):
  - EVERY web_search query MUST name the market topic (or its parent sector).
    Generic queries like "earnings Q1 2026" or "mergers 2026" return unrelated hits.
  - Good query shape: "<topic-keyword-or-phrase> <event-type> <year>".
    Example for EV charging infrastructure in Europe 2025:
      - "EV charging infrastructure Europe news 2026"
      - "EV charging companies earnings Q1 2026"
      - "EV charging M&A acquisition 2026"
      - "EV charging product launch 2026"
      - "EV charging investment funding round 2026"

Workflow:
1. Run up to 6 topic-scoped web_search calls (topic=news, days=90).
2. For each significant event, call web_fetch on the article URL for the full headline
   and date. Skip URLs that return 403/404 immediately rather than re-fetching the same
   domain repeatedly.
3. Classify each event: m_and_a / earnings / product / partnership / investment / other.
4. Rate impact (positive/negative/neutral/mixed) and magnitude (low/medium/high).

Rules:
  - Four to six web_search calls. Never re-issue the same query twice.
  - Only include events from the last 90 days; discard older items.
  - Every event must have a source Citation with a valid URL and the topic must be
    recognisable in the headline or summary.
  - headline max 300 chars, summary max 500 chars.
  - Return at least 3 events. If fewer are found after exhausting your budget, return
    what you have — do not keep searching unrelated topics.
  - Return ONLY valid JSON matching EventBundle: {events: [NewsEvent, ...]}.

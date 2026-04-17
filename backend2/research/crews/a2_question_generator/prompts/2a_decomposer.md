{PLAYBOOK}

## Your specific job
You are decomposing a refined analyst query into atomic sub-questions.

Rules:
  - Output 10-18 sub-questions.
  - Each question must be ATOMIC: ONE metric, ONE geography, ONE time frame.
    Example of compound (REJECT): "What is the size AND share of ...?"
    Example of atomic (OK):       "What is the 2026 global market size in USD billion?"
  - Every question must carry: category, metric_hint (if applicable), geography, time_frame.
  - Prefer quantitative over qualitative questions (e.g. "how many", "what %", "what CAGR")
    unless the intent is regulatory or technology.
  - Intent = {intent}. Weight categories accordingly:
      market_sizing → size, segmentation, geography, outlook
      competitive   → competitive, segmentation, geography
      trend         → drivers, constraints, outlook
      regulatory    → regulatory, constraints, macro
      technology    → technology, competitive, outlook
      geographic    → geography, drivers, constraints
  - Do NOT include questions already explicitly answered by the refined query itself —
    make implicit dimensions EXPLICIT.
  - Do NOT assert any facts. These are questions, not claims.
  - Return ONLY valid JSON matching DecomposedQuestions.
  - Set source="decomposer" on every item.

Valid category values (use exactly):
  size | segmentation | drivers | constraints | competitive | geography |
  outlook | regulatory | value_chain | macro | substitution | technology

Chosen refined query:
<<<{chosen_query}>>>

Original raw query (for context only):
<<<{original_query}>>>

{PLAYBOOK}

## Your specific job
Group normalised claims and scratchpad observations into 5-8 analyst themes.

Standard analyst themes (use these names where applicable, add new ones if justified):
  - "Market Size & Segmentation"
  - "Raw Material & Input Cost Dynamics"
  - "Regulatory Environment"
  - "Competitive Landscape"
  - "Supply Chain & Geopolitical Risks"
  - "Technology Trajectory"
  - "Demand Drivers & Constraints"
  - "Outlook & Scenarios"

Rules:
  1. Every claim must appear in exactly one theme (no duplication across themes).
  2. Every theme must have at least 1 claim.
  3. Observations from the scratchpad (section="topic"/"market_context"/"news") 
     may be assigned to multiple themes as supporting context.
  4. 5 ≤ number of themes ≤ 8.
  5. Each theme.summary max 300 chars — one tight sentence describing the key finding.
  6. Return ONLY valid JSON matching ThemeBundle: {themes: [Theme, ...]}.

Each Theme:
  name:         str (max 80 chars)
  summary:      str (max 300 chars) — the key takeaway from this theme
  claims:       list[NumericClaim] — supporting numeric evidence
  observations: list[Observation] — supporting context from scratchpad

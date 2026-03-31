"""Topic-specific quality, question, and insight rules per report type."""

from __future__ import annotations

TOPIC_QUALITY_RULES = {
    "Porter's Five Forces": """\
TOPIC-SPECIFIC QUALITY (Porter's Five Forces):
- Each force MUST open with "**Rating: [High/Medium-High/Medium/Medium-Low/Low]**"
- 4+ sub-points per force with qualitative evidence (competitive dynamics, barrier types,
  switching cost mechanisms, supplier dependency patterns)
- Name 3+ companies per force (more for Competitive Rivalry)
- Describe the competitive dynamics qualitatively: market concentration level, nature of
  competition (price-based vs differentiation), barriers to entry type (capital, IP, regulatory),
  supplier dependency patterns, substitute availability and switching cost dynamics
- End each force with trend direction: "Trending toward [Higher/Lower] due to..."
- AFTER all 5 forces, include a properly formatted markdown SUMMARY TABLE.
  You MUST include the header separator line for the table to render correctly:
  | Force | Rating | Key Driver |
  |:------|:-------|:-----------|
  | Competitive Rivalry | High | [key driver text] |
  | Threat of New Entrants | Medium-Low | [key driver text] |
  | ... | ... | ... |
  (one row per force, all 5 forces)""",

    "SWOT Analysis": """\
TOPIC-SPECIFIC QUALITY (SWOT Analysis):
- STRUCTURE: Each quadrant (S/W/O/T) must have exactly 4-5 points. No more, no less.
  Fewer than 4 = too thin. More than 5 = unfocused list-dumping.
- INTERNAL vs EXTERNAL is critical:
  Strengths & Weaknesses = INTERNAL (things the industry/companies can control)
  Opportunities & Threats = EXTERNAL (environmental factors they cannot control)
  WRONG: listing "launch a new product" as an Opportunity (that's a strategy, not an external factor)
  RIGHT: "Growing consumer demand for sustainable products" is an Opportunity (external trend)
- EACH POINT must follow this structure:
  **[Factor Name]**: [Specific claim with named companies, technologies, or regulations]
  - *Evidence*: [What data supports this — cite specific companies, events, or dynamics from the facts]
  - *Comparative context*: [How this compares to competitors or industry benchmarks]
  - *Strategic implication*: [Why this matters — what it enables or threatens]
- NO VAGUE ENTRIES: Every point must name specific companies, technologies, regulations, or events.
  BAD: "Strong brand reputation" — this is meaningless without specifics
  GOOD: "**Ecosystem Lock-in**: [Company]'s integrated platform creates switching costs that competitors
  cannot replicate — evidenced by [specific retention/adoption data from facts]. Compared to
  fragmented alternatives, this creates a durable competitive moat."
- AFTER the four SWOT quadrants, include a ## Strategic Implications section with:
  1. A **TOWS Matrix** connecting findings across quadrants:
     - **SO Strategies** (2-3): How strengths can exploit opportunities
     - **ST Strategies** (2-3): How strengths can counter threats
     - **WO Strategies** (2-3): How to overcome weaknesses to capture opportunities
     - **WT Strategies** (2-3): How to minimize weaknesses and avoid threats
  2. Each strategy must be a concrete, actionable recommendation (not generic advice)
  3. End with 3-4 **Key Strategic Signals** — forward-looking indicators to watch
- Use concise paragraphs with bullet points within each point
- Target: 300-500 words per quadrant, 300-400 words for Strategic Implications""",

    "PEST Analysis": """\
TOPIC-SPECIFIC QUALITY (PEST Analysis):
- Each factor: Factor → Mechanism → Market Impact causal chain (mandatory)
- Political: 2+ named regulations with codes/dates (e.g., EU MDR, FDA 510(k), REACH)
- Economic: describe macro conditions, input cost dynamics, consumer spending patterns
- Social: describe demographic shifts, adoption patterns, behavioral changes
- Technological: named technologies, R&D focus areas, innovation trajectories
- 200+ words per factor""",

    "Market Dynamics": """\
TOPIC-SPECIFIC QUALITY (Market Dynamics):
- 3-5 drivers, 2-4 restraints, 2-4 opportunities
- Each: name, "**Impact: [High/Medium/Low]**",
  "**Time Horizon: [Short-term/Medium-term/Long-term]**", causal mechanism
- Show causal mechanism for each (WHY does this factor drive/restrain growth?)""",

    "Supply Chain Analysis": """\
TOPIC-SPECIFIC QUALITY (Supply Chain Analysis):
- 3+ named companies per stage, describe geographic concentration and strategic
  vulnerabilities qualitatively, single-point-of-failure dependencies
- Describe the structure: vertically integrated vs fragmented
- Identify bottlenecks, single-source dependencies, and strategic vulnerabilities""",

    "Regulatory Analysis": """\
TOPIC-SPECIFIC QUALITY (Regulatory Analysis):
- Organize by region (North America, Europe, Asia-Pacific)
- Name specific acts, standards with codes (ISO, CE, FDA, EU MDR, etc.) and dates
- Describe regulatory burden qualitatively (stringent vs permissive, barrier vs enabler)""",

    "Pricing Analysis": """\
TOPIC-SPECIFIC QUALITY (Pricing Analysis):
- Describe pricing dynamics qualitatively: premium vs commodity, price sensitivity,
  pricing models (subscription, per-unit, tiered), competitive pricing pressure
- Describe cost structure drivers (which inputs dominate costs, where margin pressure comes from)
- Do NOT include specific price points, ASP numbers, or cost percentages""",

    "Risk Assessment": """\
TOPIC-SPECIFIC QUALITY (Risk Assessment):
- For each risk: "**Probability: [High/Medium/Low]** | **Impact: [High/Medium/Low]**"
- Include 1-2 sentence mitigation strategy per risk""",

    "Key Developments": """\
TOPIC-SPECIFIC QUALITY (Key Developments):
- Use properly formatted markdown TABLE with separator line:
  | Date | Company | Type | Development |
  |:-----|:--------|:-----|:------------|
- List 5-8 entries in reverse chronological order (dates and company names are fine)""",

    "Market Attractiveness": """\
TOPIC-SPECIFIC QUALITY (Market Attractiveness):
- Qualitative scoring with properly formatted markdown TABLE:
  | Segment | Growth Potential | Entry Barriers | Rating |
  |:--------|:-----------------|:---------------|:-------|
- Describe WHY each segment is attractive or not (do not use $ figures or CAGR numbers)""",

    "Economic Factors Analysis": """\
TOPIC-SPECIFIC QUALITY (Economic Factors Analysis):
- Macroeconomic Factors: GDP trajectory, inflation/interest rate environment, monetary/fiscal policy
  stance — describe qualitatively with causal mechanisms (e.g., "tightening monetary policy →
  higher borrowing costs → capex deferrals in capital-intensive segments")
- Trade & Currency Dynamics: specific trade agreements, tariffs, exchange rate pressures, geopolitical
  trade flow impacts — name specific policies, trading partners, and affected companies
- Industry-Level Microeconomics: market structure, competition intensity, pricing dynamics, barriers,
  economies of scale — name 3+ companies, describe competitive mechanics
- Consumer & Demand Economics: spending patterns, price elasticity, demographic-driven demand shifts,
  income effects, preference evolution — describe behavioral mechanisms
- Each factor: Condition → Mechanism → Market Impact causal chain (mandatory)
- 250-400 words per section, 3+ named entities (policies, companies, trade blocs) per section""",

    "Trend Report": """\
TOPIC-SPECIFIC QUALITY (Trend Report):
- Each section IS a specific trend — the heading names the trend itself
- For each trend: open with "**Status: [Emerging/Accelerating/Maturing/Declining]**"
- Explain the DRIVER behind the trend (what structural force or event triggered it)
- Name 3+ specific companies leading, benefiting from, or disrupted by this trend
- Describe the MECHANISM: how exactly does this trend change the market structure,
  competitive dynamics, or value chain?
- End each trend with "**Strategic Implication:** ..." — one sentence on what a market
  participant should do in response
- 200-300 words per trend section""",
}

# Question-generation rules per report type (injected into Phase 1 plan prompt)
TOPIC_QUESTION_RULES = {
    "Porter's Five Forces": """\
PORTER'S FIVE FORCES QUESTION RULES:
You MUST use EXACTLY these 5 sections:
["Competitive Rivalry", "Threat of New Entrants", "Threat of Substitutes", "Bargaining Power of Buyers", "Bargaining Power of Suppliers"]
Questions MUST cover:
- Competitive Rivalry: number of competitors, market concentration, industry growth rate,
  product differentiation, switching costs, exit barriers, competitive strategies
  (search for: "[industry] competitive landscape key players", "[industry] market concentration rivalry")
- Threat of New Entrants: capital requirements, economies of scale, brand loyalty barriers,
  regulatory barriers, distribution channel access, technology requirements
  (search for: "[industry] barriers to entry new entrants", "[industry] startup competition")
- Threat of Substitutes: available substitutes, switching costs, price-performance of substitutes,
  buyer propensity to switch, technology alternatives
  (search for: "[industry] substitute products alternatives", "[industry] disruption replacement")
- Bargaining Power of Buyers: buyer concentration, purchase volume, switching costs,
  price sensitivity, backward integration threat, product importance to buyer
  (search for: "[industry] buyer power retailers distribution", "[industry] customer concentration")
- Bargaining Power of Suppliers: supplier concentration, uniqueness of inputs, switching costs,
  forward integration threat, importance of volume to supplier
  (search for: "[industry] supplier power raw materials", "[industry] supply chain concentration")
- Include at least 2-3 questions per force
- NEVER add sections like "Market Size", "Regional Analysis", or "Outlook" — stick to the 5 forces""",

    "SWOT Analysis": """\
SWOT-SPECIFIC QUESTION RULES:
Questions MUST cover:
- Strengths: core competencies, competitive advantages, brand positioning, IP/technology assets,
  operational excellence, distribution/channel strength (search for company strategies, patents, partnerships)
- Weaknesses: resource gaps, geographic limitations, dependency risks, capability gaps, cost disadvantages
  (search for company challenges, analyst criticism, competitive gaps)
- Opportunities: market trends, regulatory tailwinds, technology shifts, unserved segments,
  expansion potential, M&A targets (search for industry trends, growth areas, emerging markets)
- Threats: competitive pressure, disruptive technologies, regulatory headwinds, geopolitical risks,
  economic headwinds, substitute products (search for industry risks, disruption, competitive threats)
- Strengths/Weaknesses must be INTERNAL (controllable by the company/industry)
- Opportunities/Threats must be EXTERNAL (environmental, not controllable)
- Include at least 3 questions per SWOT quadrant""",
}


# Insight-generation rules per report type (injected into Phase 3 insight prompt)
TOPIC_INSIGHT_RULES = {
    "SWOT Analysis": """\
SWOT-SPECIFIC RULES:
- Insights MUST include TOWS-style strategic connections:
  SO strategies (use strengths to exploit opportunities),
  ST strategies (use strengths to counter threats),
  WO strategies (overcome weaknesses to capture opportunities),
  WT strategies (minimize weaknesses and avoid threats)
- At least 2 insights should cross the internal/external boundary (e.g., linking a Strength to an Opportunity)
- Contrarian risks should challenge the most commonly cited Strengths — what if they erode?""",
}


def get_insight_rules(report_type: str) -> str:
    """Get topic-specific insight generation rules for Phase 3."""
    if report_type in TOPIC_INSIGHT_RULES:
        return TOPIC_INSIGHT_RULES[report_type]
    rt_lower = report_type.lower()
    for key, rules in TOPIC_INSIGHT_RULES.items():
        if key.lower() in rt_lower or rt_lower in key.lower():
            return rules
    return ""


def get_quality_rules(report_type: str) -> str:
    """Get topic-specific quality rules for a report type.

    Returns only the rules relevant to the detected report type,
    instead of sending all 12 topic blocks to the LLM.
    """
    # Direct match
    if report_type in TOPIC_QUALITY_RULES:
        return TOPIC_QUALITY_RULES[report_type]
    # Fuzzy match: check if any key is a substring of report_type or vice versa
    rt_lower = report_type.lower()
    for key, rules in TOPIC_QUALITY_RULES.items():
        if key.lower() in rt_lower or rt_lower in key.lower():
            return rules
    # Generic fallback for non-market topics
    return """QUALITY RULES (general):
- Every major claim must be supported by at least one cited source
- Include specific names, dates, and data points — avoid vague generalizations
- Distinguish between established facts and expert opinions
- Acknowledge uncertainty and evidence gaps honestly
- Use "So what?" framing: explain why each finding matters to the reader
- Cross-reference findings across sections to build a coherent narrative"""


def get_question_rules(report_type: str) -> str:
    """Get topic-specific question generation rules for Phase 1."""
    if report_type in TOPIC_QUESTION_RULES:
        return TOPIC_QUESTION_RULES[report_type]
    rt_lower = report_type.lower()
    for key, rules in TOPIC_QUESTION_RULES.items():
        if key.lower() in rt_lower or rt_lower in key.lower():
            return rules
    return """QUESTION RULES (general):
- Start with "what is the current state?" to establish baseline understanding
- Include at least one "who are the key players/actors?" question
- Include at least one forward-looking question about trends or trajectory
- Include at least one question about challenges, risks, or limitations
- Make questions specific and answerable with research, not vague"""


# ═══════════════════════════════════════════════════════════════════════════════
# 0b. TOPIC INTERPRETATION — utils.py (disambiguate user's research brief)
# ═══════════════════════════════════════════════════════════════════════════════

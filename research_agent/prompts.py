"""
All prompt templates for the research agent pipeline.

Organized by module:
  0. Topic-Specific Rules    — shared quality rules, injected per report type
  1. Report Outline          — react_engine.py (shared section planning)
  2. Layer 0: Baseline       — layers/baseline.py (section planning + report writing)
  3. Layer 1: Enhanced       — layers/enhanced.py (ReAct system prompt + self-review)
  4. Evaluation              — evaluator.py (scoring, comparison, summary)
  5. Phase 1: Understand     — phases/understand.py (research plan generation)
  6. Phase 2: Research       — phases/research.py (fact extraction from search/scrape)
  7. Phase 3: Analyze        — phases/analyze.py (verification, insights)
  8. Phase 4: Write          — phases/write.py (report writing, editorial review)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 0. TOPIC-SPECIFIC RULES — injected dynamically based on detected report type
# ═══════════════════════════════════════════════════════════════════════════════
#
# Instead of stuffing ALL topic rules into every prompt (wasting input tokens
# on 11 irrelevant report types), we store rules per type and inject only the
# matching one. This saves ~1000+ tokens per LLM call across 4+ prompts.

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
- Use flowing prose within each point (not bare bullet lists)
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
    # Default: universal rules only (no topic-specific block)
    return ""


def get_question_rules(report_type: str) -> str:
    """Get topic-specific question generation rules for Phase 1."""
    if report_type in TOPIC_QUESTION_RULES:
        return TOPIC_QUESTION_RULES[report_type]
    rt_lower = report_type.lower()
    for key, rules in TOPIC_QUESTION_RULES.items():
        if key.lower() in rt_lower or rt_lower in key.lower():
            return rules
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# 1. REPORT OUTLINE — react_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

REPORT_OUTLINE_PROMPT = """You are a senior research director planning a structured report.

Topic: {topic}

Step 1 — Identify the report TYPE from the topic. Examples:
  - "PEST Analysis" → PEST
  - "Porter's Five Forces" → Porter's Five Forces
  - "SWOT Analysis" → SWOT
  - "Market Dynamics" / "Market Drivers" / "Drivers and Restraints" → Market Dynamics
  - "Market Entry Analysis" → Market Entry
  - "Competitive Landscape" → Competitive Analysis
  - "Market Sizing / Forecast" → Market Sizing
  - "Trend Analysis" → Trend Report
  - "Value Chain Analysis" → Value Chain
  - "Supply Chain Analysis" → Supply Chain
  - "Regulatory Scenario" → Regulatory Analysis
  - "Pricing Analysis" → Pricing Analysis
  - "Market Risk Assessment" → Risk Assessment
  - "Market Attractiveness" → Attractiveness Analysis
  - "Key Developments" / "M&A" → Key Developments
  - "BCG Matrix" → BCG Matrix
  - "Micro and Macro Economic Factors" / "Economic Factors" / "Macroeconomic" / "Microeconomic" → Economic Factors Analysis
  - Anything not matching a named framework → General Market Report

Step 2 — Generate the CANONICAL SECTIONS for this report type.
Use exactly the sections a top-tier consulting firm would include — no extras, no omissions.

Rules:
- PEST: exactly 4 sections (Political Factors, Economic Factors, Social Factors, Technological Factors)
- Porter's Five Forces: exactly 5 sections (Competitive Rivalry, Threat of New Entrants,
  Threat of Substitutes, Buyer Power, Supplier Power)
- SWOT: exactly 4 sections (Strengths, Weaknesses, Opportunities, Threats)
- Market Dynamics: exactly 3 sections (Market Drivers, Market Restraints, Market Opportunities)
- Supply Chain: 4-5 sections for each stage (Raw Materials & Components, Manufacturing,
  Distribution & Logistics, End Users, plus any market-specific stages)
- Regulatory Analysis: 4-5 sections (Global Framework, Regional Regulations, Industry Standards,
  Compliance Costs, Regulatory Outlook)
- Pricing Analysis: 4-5 sections (Price Landscape, Pricing by Segment, Cost Drivers,
  ASP Trends, Price Outlook)
- Risk Assessment: 4-5 sections by risk type (Supply-Side Risks, Demand-Side Risks,
  Regulatory Risks, Technology Risks, Geopolitical Risks)
- Economic Factors Analysis: exactly 4 sections (Macroeconomic Factors, Trade & Currency Dynamics,
  Industry-Level Microeconomics, Consumer & Demand Economics)
- Attractiveness Analysis: 4-5 sections (Methodology, Segment Attractiveness,
  Regional Attractiveness, Investment Hotspots)
- Key Developments: 3-4 sections (M&A Activity, Product Launches, Strategic Partnerships,
  Regulatory Milestones)
- Market Sizing: Market Overview, Segmentation, Growth Drivers, Competitive Landscape, Forecast
- Competitive Analysis: Market Overview, Key Players, Competitive Dynamics,
  Differentiation Strategies, Outlook
- Trend Report: EACH SECTION IS A SPECIFIC TREND. Do NOT use generic sections like
  "Market Overview", "Competitive Landscape", "Regional Analysis", or "Outlook".
  Instead, identify 3-6 actual trends shaping this specific industry/market, and make
  each one a section. Examples for different industries:
    Electric vehicles → "Battery Technology Evolution", "Charging Infrastructure Expansion",
      "Government Subsidy Shifts", "Chinese EV Brands Going Global"
    Cloud computing → "Edge Computing Adoption", "AI Workload Migration", "Multi-Cloud Strategy",
      "Serverless Architecture Growth"
  Each section name should be a SHORT descriptive phrase (2-6 words) naming the specific trend.
  The trends must be specific to the industry in the topic — not generic business trends.
- General Market Report: Market Overview, Key Players, Growth Drivers, Challenges, Outlook
- Keep section names SHORT (2-5 words max)

Step 3 — For each section, write ONE sentence describing what specific QUALITATIVE data to research.
Be concrete: name the data types needed (competitive dynamics, switching cost mechanisms,
regulatory bodies, pricing models, company names, technology trends, industry structure).
Do NOT request quantitative data (market sizes, growth rates, share percentages, revenue).

QUALITY GUIDANCE by report type (QUALITATIVE analysis — NO quantitative data like market sizes,
percentages, growth rates, CAGR, revenue figures. Numbers vary by source; our internal team
provides their own. Research the UNDERLYING DYNAMICS, not numbers):

Porter's Five Forces:
- Each force: rating (High/Medium-High/Medium/Medium-Low/Low), 4+ qualitative sub-points
- Research: competitive dynamics, barrier types (capital, IP, regulatory), switching cost nature,
  supplier dependency patterns, substitute availability, M&A activity patterns

PEST Analysis:
- Each factor: Factor → Mechanism → Market Impact causal chain
- Research: specific regulation names/codes, economic condition descriptions, demographic shift
  patterns, technology trajectories, R&D focus areas

Market Dynamics:
- 3-5 drivers, 2-4 restraints, 2-4 opportunities
- Each needs: impact rating (High/Medium/Low), time horizon (Short/Medium/Long-term),
  causal mechanism explaining WHY it drives/restrains growth

Regulatory: name specific bodies, acts, standards (ISO, CE, FDA) with dates, describe regulatory
  burden qualitatively, organize by region (NA, Europe, APAC)
Pricing: describe pricing dynamics (premium vs commodity, pricing models, competitive pressure),
  cost structure drivers qualitatively — NO specific price points or ASP numbers
Supply Chain: named companies at each stage, describe structure (integrated vs fragmented),
  geographic concentration risks, strategic vulnerabilities
Risk Assessment: Probability × Impact rating per risk, mitigation strategies
Key Developments: table format (Date | Company | Type | Development), 5-8 entries
Market Attractiveness: qualitative scoring (Segment | Growth Potential | Entry Barriers | Rating)
Economic Factors Analysis:
- Macroeconomic Factors: GDP growth trajectory, inflation & interest rate environment, monetary/fiscal
  policy stance, government spending patterns — all described qualitatively with causal mechanisms
- Trade & Currency Dynamics: trade agreements/tariffs, exchange rate pressures, geopolitical impacts
  on trade flows, import/export dependency patterns — name specific policies and trading partners
- Industry-Level Microeconomics: market structure (fragmented vs consolidated), competition intensity,
  pricing dynamics, barriers to entry/exit, economies of scale effects — name key players
- Consumer & Demand Economics: spending patterns, price elasticity, demographic-driven demand shifts,
  preference evolution, income effects — describe behavioral mechanisms
- Each factor: Condition → Mechanism → Market Impact causal chain
- Name specific policies, central bank actions, trade agreements, and companies affected

Trend Report / Key Trends:
- Each section = one specific industry trend (NOT a generic category like "Market Overview")
- Per trend: what is driving it, which companies are leading/affected, what structural shift it
  represents, timeline (emerging vs mature), and strategic implications
- Name real companies, technologies, regulations shaping each trend
- Show causal chains: Trigger → Mechanism → Market Impact

Output format (EXACTLY as shown):
Report type: [TYPE]
Sections:
1. [Section Name] — [What data to research and include]
2. [Section Name] — [What data to research and include]
...

Do NOT output anything else."""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LAYER 0: BASELINE — layers/baseline.py
# ═══════════════════════════════════════════════════════════════════════════════

BASELINE_SECTION_PLANNER_PROMPT = """Given this research topic, output ONLY a JSON array of section headings
that perfectly match what the topic is asking for.

Topic: {topic}

Rules:
- FIRST check if the topic mentions a specific analysis type (see keyword list below).
  If it does, use ONLY the sections for that analysis type — NOT generic market sections.
- ONLY if the topic is a general market/industry topic with NO specific analysis type, use:
  Market Overview, Key Players, Market Trends, Challenges, Future Outlook
- Return 3-7 sections, no more.
- Output ONLY the JSON array, nothing else.

KEYWORD → SECTION MAPPING (use these exact sections when the keyword appears in the topic):
- "porter" or "five forces" → ["Competitive Rivalry", "Threat of New Entrants", "Threat of Substitutes", "Bargaining Power of Buyers", "Bargaining Power of Suppliers"]
- "swot" → ["Strengths", "Weaknesses", "Opportunities", "Threats"]
- "pest" or "pestle" → ["Political Factors", "Economic Factors", "Social Factors", "Technological Factors"]
- "market dynamics" or "dynamics" or "market drivers" or "drivers and restraints" → ["Market Drivers", "Market Restraints", "Market Opportunities"]
- "supply chain" or "value chain" → ["Raw Materials & Components", "Manufacturing", "Distribution & Logistics", "End Users & Applications"]
- "regulatory" or "regulation" → ["Global Framework", "Regional Regulations", "Industry Standards", "Compliance Costs", "Regulatory Outlook"]
- "pricing" or "cost of" or "cost analysis" → ["Price Landscape", "Pricing by Segment", "Cost Drivers", "ASP Trends"]
- "risk assessment" or "market risk" → ["Supply-Side Risks", "Demand-Side Risks", "Regulatory Risks", "Technology Risks", "Geopolitical Risks"]
- "key developments" or "developments" or "M&A" → ["M&A Activity", "Product Launches", "Strategic Partnerships", "Regulatory Milestones"]
- "attractiveness" → ["Methodology", "Segment Attractiveness", "Regional Attractiveness", "Investment Hotspots"]
- "micro and macro" or "economic factors" or "macroeconomic" or "microeconomic" → ["Macroeconomic Factors", "Trade & Currency Dynamics", "Industry-Level Microeconomics", "Consumer & Demand Economics"]
- "trend" or "trends" or "key trends" → DO NOT use generic sections like "Market Overview",
  "Competitive Landscape", "Regional Analysis", or "Outlook". Instead, identify 3-6 actual
  industry-specific trends and make each one a section. Each section name should be a short
  phrase naming the specific trend (e.g., "Battery Technology Evolution", "Direct-to-Consumer Shift",
  "Sustainability Mandates"). The trends must be specific to the industry in the topic."""

BASELINE_WRITE_PROMPT = """Write a comprehensive QUALITATIVE analysis on this topic using ONLY your existing knowledge.
No web search is available.

Topic: {topic}

You MUST use EXACTLY these sections as your ## headings — no more, no less:
{sections}

DO NOT add any extra sections beyond the ones listed above. No introduction, no conclusion,
no "Market Overview" or "Key Players" unless they are in the list above.

CRITICAL — QUALITATIVE ONLY:
- Do NOT include any quantitative data: no market sizes ($), no percentages (%), no growth rates,
  no CAGR, no market share numbers, no revenue figures, no unit volumes.
- Numbers vary by source and our internal team provides their own data. Your job is ANALYSIS ONLY.
- Focus on: mechanisms, relationships, causal chains, strategic dynamics, competitive forces,
  industry structure, regulatory landscape, and qualitative assessments.
- You MAY name specific companies, regulations, technologies, and events — just no numbers.

Requirements:
- Start directly with the first ## heading
- Each section: 200-350 words of qualitative analysis
- Target 1000-1500 words total
- Use markdown formatting
- CAUSAL REASONING: for every factor you discuss, show the causal chain:
  Factor → Mechanism → Market Impact. Never just state "X affects the market."
  Example: "Rising urbanization in emerging markets → increased demand for packaged food
  → drives flexible packaging market growth as manufacturers shift to convenience formats"

{topic_rules}"""


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LAYER 1: ENHANCED — layers/enhanced.py
# ═══════════════════════════════════════════════════════════════════════════════

ENHANCED_SYSTEM_PROMPT = """You are a market research analyst with 10 years of experience and access to web search tools.

Your job: research the given topic thoroughly, then write an ANALYTICAL report that explains
WHY things are happening, not just WHAT is happening. You must go deeper than a surface summary.

APPROACH:
1. Search for recent data relevant to the topic — at least 8-10 searches
2. Search each section of your outline SEPARATELY with targeted queries
3. Scrape 4-6 promising pages for detailed data (prefer T1/T2 sources)
4. Before writing, review your collected data and identify CAUSAL CONNECTIONS between findings
5. Write a well-structured report with ## section headings that match your outline

SEARCH QUERY RULES:
- Write queries like a JOURNALIST: use company names, technology terms, years
- GOOD: "[Company A] [Company B] [industry] competitive strategy 2025 ecosystem"
- GOOD: "EU [regulation] [industry] 2025 2026 compliance requirements"
- GOOD: "[key supplier] [component] supply shortage 2026"
- BAD: "[industry] market buyer power" — too abstract, returns listicles
- BAD: "threat of substitutes" — academic jargon, useless results
- NEVER use Porter's/PEST/SWOT framework terms in queries. Search for the UNDERLYING DATA:
  buyer power → "[industry] consumer switching behavior brand loyalty 2026"
  supplier power → "[key supplier] [component] supply constraints 2026"
  competitive rivalry → "[Company A] [Company B] competitive strategy differentiation 2026"
- NEVER search for: market size, revenue, CAGR, growth rate, market share percentages,
  unit shipments, ASP data. Our internal team provides quantitative data.

CRITICAL — QUALITATIVE ANALYSIS ONLY:
- Do NOT include quantitative data: no market sizes ($), no percentages (%), no growth rates,
  no CAGR, no market share numbers, no revenue figures, no unit volumes.
- Our internal team provides their own numbers. Your job is QUALITATIVE ANALYSIS:
  mechanisms, relationships, causal chains, strategic dynamics.
- You MAY name specific companies, regulations, technologies, events, and dates.
- Do NOT mention specific product model names or model numbers.
  Instead say "latest flagship device", "recent premium launch", etc. Company names are fine.

DEPTH RULES (what makes your report better than a generic summary):
1. NEVER state a fact without explaining WHY it matters. After every observation, answer "so what?"
   BAD: "Company X controls both hardware and software."
   GOOD: "Company X's vertical integration of hardware and software creates an ecosystem lock-in
   that raises switching costs for consumers — once invested in the platform's services and
   content library, the cost of leaving becomes prohibitively high, giving the company
   pricing power that component-assembling rivals cannot match."

2. EXPLAIN THE MECHANISM behind every trend — what structural forces drive it, what would
   reverse it.
   BAD: "Technology adoption is growing."
   GOOD: "Adoption is accelerating because subsidy models tie upgrades to long-term contracts —
   consumers effectively get new products at reduced upfront cost in exchange for longer
   commitments, which masks the true price increase while locking
   them into carrier ecosystems."

3. CONNECT DOTS across sections. Link a competitive dynamic to a regulatory change, or a
   technology shift to a supply chain vulnerability.

RULES:
- Do NOT cite source names (IDC, Statista, etc.) or add [Source: ...] tags in your output
- Do NOT reference where data comes from — just state the findings as your own analysis
- Stay strictly on-topic — only write about what the user asked for
- Start your report directly with ## headings — no preamble

FOLLOW YOUR OUTLINE (CRITICAL):
You were given a REPORT OUTLINE. Use the SHORT section name as your ## heading.
  Outline: "1. Political Factors — trade policy, regulation..." → ## Political Factors
  NEVER include the "— description..." part in your heading.
Do NOT add, remove, rename, or reorder any sections. Use EXACTLY the sections from the outline.
All layers must produce identical section headings for cross-layer comparison.
Each section MUST be 250-350 words with specific data and analysis. Do NOT write thin sections.
A section under 200 words is UNACCEPTABLE — it means you haven't used enough of your research data.
Name 3+ specific companies per section. Every claim needs a causal chain (Factor -> Mechanism -> Impact).

Target 1200-1800 words total (250-350 words per section). You MUST scrape 3+ pages for detail."""

LAYER1_SELF_REVIEW = """You are a harsh but fair research editor reviewing a draft report.
Be critical — a score of 7 means "acceptable, not great". Only give 9+ for genuinely excellent work.

**Topic:** {topic}
**Draft:**
{draft}

Score each dimension from 1-10:
1. **factual_grounding**: Is every major claim backed by specific evidence (company names, regulation
   names, technology details, dates, events)? Or are there vague assertions like "significant
   changes" without concrete specifics?
2. **coverage**: Does the report cover all important aspects of the topic? Any major gaps?
3. **specificity**: Does it use concrete company names, regulation names, technology names, dates?
   Or is it generic? (NOTE: we do NOT need quantitative data like market sizes or percentages)
4. **structure**: Are sections well-organized and directly relevant to the topic?
5. **structure_quality**: Does the report follow a coherent plan? Are all expected sections present
   with ## headings? Is each section substantive (250+ words with specific data) or thin/generic?
   Does it match the report type's canonical structure (PEST = 4 factors, Porter's = 5 forces, etc.)?
   Penalize heavily if any section is under 200 words or lacks named companies/specific details.

Then list up to 3 specific weaknesses (be concrete, not vague).
For each weakness, suggest a search query that would find QUALITATIVE data to fix it.
Do NOT suggest queries for market size, revenue, CAGR, or share percentages.

Return ONLY a JSON object:
{{
  "scores": {{"factual_grounding": 7, "coverage": 6, "specificity": 5, "structure": 8, "structure_quality": 7}},
  "overall": 6.5,
  "weaknesses": ["Missing specific regulatory details", "No company examples given for barriers"],
  "suggested_queries": ["{topic} regulatory framework compliance 2025 2026", "top {topic} companies competitive strategy barriers 2026"]
}}"""


# ═══════════════════════════════════════════════════════════════════════════════
# 4. EVALUATION — evaluator.py
# ═══════════════════════════════════════════════════════════════════════════════

EVALUATION_PROMPT = """Evaluate this market research analysis on the following dimensions.
Score each dimension from 1-10 and provide a brief justification.

**Topic:** {topic}
**Layer:** {layer_name}
**Content:**
{content}

Evaluate on:

1. **Factual Density** (1-10): How many specific, verifiable claims per paragraph?
   - 1-3: Vague generalities, few specifics
   - 4-6: Some details but gaps remain
   - 7-10: Dense with specific company names, dates, regulations, technology details

2. **Source Grounding** (1-10): Are claims backed by evidence?
   - 1-3: Mostly unsourced assertions
   - 4-6: Some attribution but key claims unverified
   - 7-10: Major claims attributed, sources triangulated

3. **Analytical Depth** (1-10): Does it go beyond surface-level reporting?
   - 1-3: Just lists facts/trends
   - 4-6: Some analysis but mostly descriptive
   - 7-10: Frameworks applied, assumptions challenged, second-order effects explored

4. **Specificity** (1-10): How precise are the claims?
   - 1-3: "Growing fast", "major player", "significant market"
   - 4-6: Some specifics but many vague qualifiers remain
   - 7-10: Specific company names, regulation names, dates, technology details, product names

5. **Insight Quality** (1-10): Would a C-suite executive learn something new?
   - 1-3: Generic insights available in any article
   - 4-6: Some useful observations
   - 7-10: Genuinely non-obvious insights, contrarian views, actionable intelligence

6. **Completeness** (1-10): Are there obvious gaps?
   - 1-3: Major aspects of the topic are missing
   - 4-6: Covers basics but misses important angles
   - 7-10: Comprehensive, gaps explicitly acknowledged

7. **Structure Quality** (1-10): Does the report follow a coherent, topic-appropriate structure?
   - 1-3: Sections don't match the report type; framework components missing or collapsed
   - 4-6: Some expected sections present but others missing or shallow
   - 7-10: All canonical sections present (PEST=4, Porter's=5, SWOT=4), each substantive,
     headings match the framework, no generic filler sections

NOTE: This is a QUALITATIVE report — do NOT penalize for missing quantitative data (market sizes,
percentages, growth rates, CAGR). Evaluate based on quality of qualitative analysis, causal
reasoning, named entities, and strategic depth.

Return ONLY a JSON object:
{{
  "factual_density": {{"score": N, "justification": "..."}},
  "source_grounding": {{"score": N, "justification": "..."}},
  "analytical_depth": {{"score": N, "justification": "..."}},
  "specificity": {{"score": N, "justification": "..."}},
  "insight_quality": {{"score": N, "justification": "..."}},
  "completeness": {{"score": N, "justification": "..."}},
  "structure_quality": {{"score": N, "justification": "..."}}
}}"""


COMPARATIVE_EVALUATION_PROMPT = """You are evaluating {num_layers} progressive layers of market
research on the same topic. Each subsequent layer BUILDS UPON the previous one — it retains
all content and adds more depth. You must evaluate them COMPARATIVELY in a single pass.

**Topic:** {topic}

{layers_content}

Score EACH layer on these 7 dimensions (1-10). Provide a brief justification for each.

1. **Factual Density** (1-10): How many specific, verifiable claims per paragraph?
   - 1-3: Vague generalities, few specifics
   - 4-6: Some details but gaps remain
   - 7-10: Dense with specific company names, dates, regulations, technology details

2. **Source Grounding** (1-10): Are claims backed by evidence?
   - 1-3: Mostly unsourced assertions
   - 4-6: Some attribution but key claims unverified
   - 7-10: Major claims attributed, sources triangulated

3. **Analytical Depth** (1-10): Does it go beyond surface-level reporting?
   - 1-3: Just lists facts/trends
   - 4-6: Some analysis but mostly descriptive
   - 7-10: Frameworks applied, assumptions challenged, second-order effects explored

4. **Specificity** (1-10): How precise are the claims?
   - 1-3: "Growing fast", "major player", "significant market"
   - 4-6: Some specifics but many vague qualifiers remain
   - 7-10: Specific company names, regulation names, dates, technology details, product names

5. **Insight Quality** (1-10): Would a C-suite executive learn something new?
   - 1-3: Generic insights available in any article
   - 4-6: Some useful observations
   - 7-10: Genuinely non-obvious insights, contrarian views, actionable intelligence

6. **Completeness** (1-10): Are there obvious gaps?
   - 1-3: Major aspects of the topic are missing
   - 4-6: Covers basics but misses important angles
   - 7-10: Comprehensive, gaps explicitly acknowledged

7. **Structure Quality** (1-10): Does the report follow a coherent, topic-appropriate structure?
   - 1-3: Sections don't match the report type; framework components missing or collapsed
   - 4-6: Some expected sections present but not all
   - 7-10: All canonical sections present (PEST=4 factors, Porter's=5 forces, SWOT=4),
     each substantive with its own analysis, headings match the framework

NOTE: These are QUALITATIVE reports — do NOT penalize for missing quantitative data.

IMPORTANT SCORING RULES:
- Score each layer based on its ACTUAL content quality — read carefully before scoring.
- Since each later layer builds on and expands the previous one, a later layer that retains
  all prior content AND adds new depth should logically score EQUAL or HIGHER.
- If you score a later layer LOWER than an earlier one on ANY dimension, you MUST provide
  a strong justification explaining what specific quality was LOST (not just different).
- Do NOT give the same score to all layers — differentiate based on genuine quality differences.

Return ONLY a JSON object with this exact structure:
{{
  {json_template}
}}"""

COMPARISON_SUMMARY = """You are comparing the outputs of 3 research layers that ran IN PARALLEL
on the same topic. Each layer uses a different methodology. Compare their strengths.

**Topic:** {topic}

**Layer 0 — Baseline (no research, model knowledge only):**
Word count: {l0_words}
Evaluation: {l0_eval}

**Layer 1 — Enhanced (web search + synthesis):**
Word count: {l1_words}
Evaluation: {l1_eval}

**Layer 2 — CMI Expert (full pipeline: plan → research → verify → write):**
Word count: {l2_words}
Evaluation: {l2_eval}

Write a 200-300 word executive summary of:
1. How each layer's methodology affects output quality (be specific about differences)
2. The biggest quality jumps between layers
3. What the CMI Expert layer captures that the Baseline completely misses
4. The value of systematic research planning and fact verification (Layer 2 vs Layer 1)
5. Overall assessment: how much does the full pipeline improve over simpler approaches?"""


LAYER_COMPARISON_PROMPT = """You are comparing two layers of market research on the same topic.
Your job is to identify SPECIFIC, CONCRETE improvements in the higher layer.

**Topic:** {topic}

**LAYER {from_layer} — {from_name} ({from_words} words, {from_sources} sources):**
{from_content}

**LAYER {to_layer} — {to_name} ({to_words} words, {to_sources} sources):**
{to_content}

**LAYER {from_layer} Scores:** {from_scores}
**LAYER {to_layer} Scores:** {to_scores}

Analyze both reports section-by-section and identify exactly 5 SPECIFIC improvements
in Layer {to_layer} over Layer {from_layer}.

Rules for improvements:
- Each point must reference SPECIFIC content (company names, mechanisms, analysis details)
  that exists in Layer {to_layer} but is MISSING or WEAKER in Layer {from_layer}
- Don't just say "more specific" — show WHAT is more specific with examples from the text
- Focus on: new causal mechanisms explained, named entities added, deeper strategic analysis,
  better-supported arguments, cross-section connections
- BAD: "Layer 1 has more sources" (that's a metric, not a content improvement)
- BAD: "Layer 1 is more detailed" (vague — detail WHAT is more detailed)
- GOOD: "Layer 1 names Enel, Duke Energy, and EDF with specific competitive strategies
  (vertical integration, renewables pivot), while Layer 0 only mentions generic 'major players'
  without explaining their strategic positioning"
- GOOD: "Layer 2 explains the MECHANISM behind supplier power — qualification gates and
  multi-year certification cycles create switching costs — while Layer 1 just states
  'supplier power is moderate' without explaining why"

Also identify the single most striking paragraph or finding from Layer {to_layer} that
has no equivalent in Layer {from_layer} — the one example you'd show a client to
justify the premium methodology.

Return ONLY JSON:
{{
  "improvements": [
    "...",
    "...",
    "...",
    "...",
    "..."
  ],
  "key_evidence": "Quote or paraphrase the most impressive paragraph from Layer {to_layer}",
  "overall_verdict": "One sentence summarizing the quality jump between these layers"
}}"""


EXECUTIVE_COMPARISON_SUMMARY = """You are writing an executive summary comparing 3 layers of
market research that ran in parallel on the same topic.

**Topic:** {topic}

You have structured pairwise comparisons below. Use these to write a compelling 200-300 word
summary that a client could read to understand WHY the full pipeline is worth the investment.

{pairwise_summaries}

**Overall Scores:**
{score_summary}

Write an executive summary that:
1. Opens with the single most important finding about quality progression
2. For each layer jump (L0→L1, L1→L2), states the ONE most impactful improvement
3. Highlights what the Expert layer (L2) discovers that would be completely invisible
   without systematic research and verification
4. Ends with a concrete verdict: what does a decision-maker gain from the full pipeline?

Be specific — reference actual content differences mentioned in the pairwise comparisons.
Do NOT use generic phrases like "significantly better" without backing them up."""


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PHASE 1: UNDERSTAND — phases/understand.py
# ═══════════════════════════════════════════════════════════════════════════════

PHASE1_PLAN_PROMPT = """You are a research director planning a market research report.

Given a topic, decompose it into a structured research plan.

Topic: {topic}

Return a JSON object with:
1. "report_type": The analytical framework. You MUST detect this from the topic keywords:
   - "porter" or "five forces" or "5 forces" → "Porter's Five Forces"
   - "pest" → "PEST Analysis"
   - "swot" → "SWOT Analysis"
   - "competitive landscape" or "competitive analysis" → "Competitive Landscape"
   - "supply chain" → "Supply Chain Analysis"
   - "pricing" or "price analysis" → "Pricing Analysis"
   - "risk" or "risk assessment" → "Risk Assessment"
   - "regulatory" or "regulation" → "Regulatory Analysis"
   - "market attractiveness" → "Market Attractiveness"
   - "market dynamics" or "market drivers" or "drivers and restraints" → "Market Dynamics"
   - "key trends" or "trends" or "trend analysis" → "Trend Report"
   - "micro and macro" or "economic factors" or "macroeconomic" or "microeconomic" → "Economic Factors Analysis"
   If NONE of the above keywords appear, default to "Market Overview".
   IMPORTANT: The topic "{topic}" — scan it for these keywords NOW. Do NOT default to Market Overview
   if any framework keyword is present.

2. "sections": An ordered list of section headings appropriate for this report type.
   - Porter's Five Forces → ["Competitive Rivalry", "Threat of New Entrants", "Threat of Substitutes", "Buyer Power", "Supplier Power"]
   - PEST Analysis → ["Political Factors", "Economic Factors", "Social Factors", "Technological Factors"]
   - Market Dynamics → ["Market Drivers", "Market Restraints", "Market Opportunities"]
   - Supply Chain → ["Raw Materials & Components", "Manufacturing", "Distribution & Logistics", "End Users"]
   - Regulatory Analysis → ["Global Framework", "Regional Regulations", "Industry Standards", "Compliance Costs", "Regulatory Outlook"]
   - Pricing Analysis → ["Price Landscape", "Pricing by Segment", "Cost Drivers", "ASP Trends"]
   - Risk Assessment → ["Supply-Side Risks", "Demand-Side Risks", "Regulatory Risks", "Technology Risks", "Geopolitical Risks"]
   - Key Developments → ["M&A Activity", "Product Launches", "Strategic Partnerships"]
   - Market Attractiveness → ["Methodology", "Segment Attractiveness", "Regional Attractiveness", "Investment Hotspots"]
   - Economic Factors Analysis → ["Macroeconomic Factors", "Trade & Currency Dynamics", "Industry-Level Microeconomics", "Consumer & Demand Economics"]
   - Market Overview → ["Market Size & Growth", "Competitive Landscape", "Key Trends", "Regional Analysis", "Outlook"]
   - SWOT → ["Strengths", "Weaknesses", "Opportunities", "Threats", "Strategic Implications"]
   - Trend Report → DO NOT use generic sections. Each section name IS a specific trend
     (e.g., "Battery Technology Evolution", "Direct-to-Consumer Shift"). Identify 3-6 real
     trends specific to the industry in the topic.
   - For other types, use appropriate section names (4-6 sections).

   {topic_question_rules}

3. "questions": A list of 12-16 specific QUALITATIVE research questions. For EACH question provide:
   - "id": unique identifier like "q01_competitive_dynamics"
   - "section": which section heading this feeds (must match a section name exactly)
   - "question": a specific, answerable QUALITATIVE question (e.g. "Who are the key players and what
     are their competitive strategies?", "What regulations govern this industry?")
   - "data_type": one of "competitive_dynamics", "player_list", "trend", "regulation",
     "technology", "pricing_dynamics", "supply_chain", "consumer_behavior", "industry_structure",
     "strategic_positioning", "risk_factor"
   - "priority": 1 (critical — report is incomplete without it), 2 (important), 3 (nice to have)
   - "search_queries": 2 specific search queries that would find QUALITATIVE data.
     CRITICAL QUERY RULES:
     - Write like a journalist: use company names, regulation names, technology names, years
     - GOOD: "[Company A] [Company B] competitive strategy differentiation 2025 2026"
     - GOOD: "EU [regulation] [industry] compliance requirements 2025"
     - GOOD: "[industry] supply chain key suppliers geographic concentration 2026"
     - BAD: "[industry] market size 2025 billion" — we do NOT need market size data
     - BAD: "market share percentage 2025" — we do NOT need share percentages
     - BAD: "[industry] market buyer power" — academic jargon
     - NEVER search for: market size, revenue, CAGR, growth rates, market share percentages,
       shipment forecasts, unit volumes, or dollar figures
     - Every query MUST include the year (2025 or 2026) and specific entities

Distribute questions across ALL sections. Each section should have 2-3 questions minimum.
Priority 1 questions should cover: key players, competitive dynamics, regulatory landscape, major trends.

Return ONLY valid JSON. No explanation."""


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PHASE 2: RESEARCH — phases/research.py
# ═══════════════════════════════════════════════════════════════════════════════

PHASE2_EXTRACT_PROMPT = """Extract qualitative factual claims from the following search results for a specific research question.

RESEARCH QUESTION: {question}
SECTION: {section}
EXPECTED DATA TYPE: {data_type}

SEARCH RESULTS:
{search_results}

Extract concrete, specific QUALITATIVE facts. For each fact provide:
- "claim": A clear factual statement about dynamics, structure, strategy, or regulation
  (e.g. "Company X dominates the premium segment through ecosystem lock-in",
   "EU MDR 2017/745 requires Notified Body approval for Class IIa+ devices")
- "value": The key entity, regulation, technology, or strategic detail
  (e.g. "ecosystem lock-in strategy", "EU MDR 2017/745", "solid-state battery technology")
- "source_title": Which search result this came from
- "source_url": URL of the source
- "confidence": "high" (from known research firm/govt), "medium" (from news/analysis), "low" (blog/unknown)

RULES:
- Extract SPECIFIC qualitative facts: company strategies, competitive dynamics, regulatory details,
  technology developments, industry structure, supply chain relationships, consumer behavior patterns
- Focus on WHO (companies), WHAT (strategies, technologies, regulations), WHY (causal mechanisms),
  and HOW (dynamics, relationships)
- Do NOT extract quantitative data: market sizes ($), percentages (%), growth rates, CAGR, revenue,
  shipment volumes. Our internal team provides all numbers.
- If a result only provides numbers without qualitative context, skip it
- Do NOT make up or infer data that isn't explicitly stated in the results
- Return an empty array if no relevant qualitative facts are found

Return ONLY a JSON array of facts. Example:
[
  {{"claim": "The market leader maintains dominance through vertical integration of key components and ecosystem services", "value": "vertical integration strategy", "source_title": "Industry Analysis", "source_url": "https://...", "confidence": "high"}},
  {{"claim": "EU's Ecodesign for Sustainable Products Regulation mandates replaceable batteries and repairability scores", "value": "EU Ecodesign regulation", "source_title": "European Commission", "source_url": "https://...", "confidence": "high"}}
]"""


PHASE2_SCRAPE_EXTRACT_PROMPT = """Extract qualitative factual claims from this scraped web page relevant to the research question.

RESEARCH QUESTION: {question}
SECTION: {section}

PAGE CONTENT:
{page_content}

Extract 3-8 specific QUALITATIVE claims: company strategies, competitive dynamics, regulatory details,
technology developments, industry structure, supply chain relationships.
Do NOT extract quantitative data (market sizes, percentages, growth rates, revenue, CAGR).
For each: "claim", "value" (the key entity or dynamic), "confidence" (high/medium/low).

Return ONLY a JSON array. Empty array if no relevant qualitative facts found."""


# ═══════════════════════════════════════════════════════════════════════════════
# 7. PHASE 3: ANALYZE — phases/analyze.py
# ═══════════════════════════════════════════════════════════════════════════════

PHASE3_VERIFY_PROMPT = """You are a fact-checker. Review these facts collected for a research report.

TOPIC: {topic}
SECTION: {section}

COLLECTED FACTS:
{facts}

NEW VERIFICATION DATA:
{verification_data}

For each fact, assess:
1. Is it corroborated by the verification data?
2. Does any verification data contradict it?
3. What's the corrected value if there's a conflict?

Return a JSON object:
{{
  "verified": [
    {{"fact_id": "...", "status": "confirmed", "note": "Corroborated by IDC data"}},
    {{"fact_id": "...", "status": "corrected", "corrected_claim": "...", "note": "IDC says 13%, not 15%"}},
    {{"fact_id": "...", "status": "unverified", "note": "No corroborating source found"}}
  ],
  "conflicts": [
    {{"fact_ids": ["f1", "f2"], "resolution": "f1 is from IDC (T1), f2 from blog (T3) — use f1"}}
  ]
}}"""


PHASE3_INSIGHT_PROMPT = """You are a 20-year veteran strategic analyst known for explaining the WHY
behind every market dynamic. Your insights are valued because you never stop at "what is happening"
— you always explain the mechanism, the second-order effects, and what it means for stakeholders.

TOPIC: {topic}
REPORT TYPE: {report_type}

COLLECTED KNOWLEDGE (grouped by section):
{knowledge}

Generate:

1. "insights": 5-7 deep analytical insights. Each MUST follow this structure:
   OBSERVATION (what the data shows) → MECHANISM (why this happens — the causal chain) →
   IMPLICATION (what this means for the industry going forward) → STAKEHOLDER IMPACT
   (who wins, who loses, and why).

   BAD (surface-level): "AI is transforming the industry and creating new opportunities."
   GOOD (deep reasoning): "Incumbent vendors are embedding AI features into existing enterprise
   contracts rather than selling AI as a standalone product → this bundles AI value into renewal
   negotiations → new AI-native startups cannot compete on price because incumbents subsidize
   AI with existing margin → the window for independent AI vendors narrows to verticals where
   incumbents lack domain-specific training data (e.g., pathology imaging, agricultural yield)."

   Each insight MUST:
   - Connect facts from AT LEAST 2 different sections
   - Explain a non-obvious causal mechanism (the "why behind the why")
   - Identify who benefits and who is disadvantaged by this dynamic
   - Be 2-4 sentences, not a single vague sentence

2. "contrarian_risks": 3-4 ways the consensus view could be WRONG. For each:
   - State the consensus assumption explicitly
   - Explain what evidence or logic undermines it
   - Describe what the world looks like if the consensus is wrong

   BAD: "Growth could slow down."
   GOOD: "Consensus assumes regulatory tailwinds will persist, but the EU AI Act's tiered
   compliance framework could fragment the market — companies building for EU compliance may
   find their architectures incompatible with less restrictive US/APAC frameworks, creating
   parallel ecosystems rather than a global market. If this happens, scale advantages erode
   and regional specialists outperform global players."

3. "section_impacts": For each section, rate its impact on the market (high/moderate/low)
   with a reasoning chain (not just a label).

{topic_insight_rules}

Return ONLY valid JSON:
{{
  "insights": ["...", "..."],
  "contrarian_risks": ["...", "..."],
  "section_impacts": [
    {{"section": "Competitive Rivalry", "impact": "high", "reason": "Consolidation among top players is compressing margins industry-wide, forcing smaller firms into niche specialization or exit"}},
    {{"section": "Threat of New Entrants", "impact": "low", "reason": "Capital requirements and regulatory certification timelines create a 3-5 year lag that deters new entry except through acquisition"}}
  ]
}}"""


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PHASE 4: WRITE — phases/write.py
# ═══════════════════════════════════════════════════════════════════════════════

PHASE4_WRITE_PROMPT = """You are a 20-year veteran market research analyst. Your reports are valued
because you don't just DESCRIBE what's happening — you EXPLAIN why it's happening, what mechanisms
drive it, and what it means for different stakeholders. Every paragraph you write teaches the reader
something they couldn't figure out by reading headlines.

TOPIC: {topic}
REPORT TYPE: {report_type}
CURRENT YEAR: {current_year}. Write from a {current_year} perspective. {last_year} is LAST year, not the present.

You MUST write this report using ONLY the data provided below. Do NOT use your training knowledge
to add facts, numbers, or claims that are not in the provided data. If a section has thin data,
write a shorter section — do not pad with generic statements.

STRUCTURED RESEARCH DATA (by section):
{section_data}

ANALYTICAL INSIGHTS:
{insights}

CONTRARIAN RISKS:
{contrarian_risks}

DEPTH RULES (what separates a great report from a mediocre one):
1. NEVER state a fact without explaining WHY it matters. After every observation, ask yourself
   "so what?" and write the answer.
   BAD: "Company X launched product Y in 2025."
   GOOD: "Company X launched product Y in 2025, signaling a strategic pivot from enterprise-only
   to mid-market — a move that pressures incumbents like Z who have relied on the mid-market
   segment as their primary growth vector."

2. EXPLAIN THE MECHANISM behind every trend. Don't say "X is growing" — explain what structural
   forces are driving it and what would need to change for it to reverse.
   BAD: "Cloud adoption is accelerating in this sector."
   GOOD: "Cloud adoption is accelerating because on-premise compliance costs now exceed migration
   risk for most mid-size firms — the calculus flipped when [specific regulation] imposed
   real-time reporting requirements that legacy systems cannot meet without costly retrofitting."

3. CONNECT DOTS across sections. The best insights come from linking a competitive dynamic to a
   regulatory change, or a technology shift to a supply chain vulnerability. Each section should
   reference at least one finding from another section.

4. SHOW RIPPLE EFFECTS — the chain reaction that follows from the obvious consequence.
   Ask: "and then what happens BECAUSE of that?"
   DIRECT CONSEQUENCE: "Margin pressure forces incumbents to pivot toward services revenue."
   — this is just the obvious reaction. Not a ripple effect.
   RIPPLE EFFECT (what happens next): "The pivot to services creates dependency on app store
   and cloud infrastructure → which exposes incumbents to antitrust action (EU DMA forcing
   sideloading, open payment systems) → potentially eroding the very revenue streams they
   pivoted to, leaving them with neither hardware margins nor service lock-in."
   Mark these with > **[RIPPLE EFFECT]** blockquotes. The best ones are surprising or
   counterintuitive — where solving one problem creates a new, unexpected vulnerability.

5. INTEGRATE CONTRARIAN RISKS as counterpoints within the analysis — don't quarantine them in
   a separate paragraph. When making a bullish argument, immediately acknowledge what could
   undermine it.

SECTION STRUCTURE (CRITICAL):
Use EXACTLY the sections from the research plan below — no more, no less.
Do NOT add, remove, rename, or reorder any sections. All layers must produce identical
section headings for cross-layer comparison. Use the section name as your ## heading.

WRITING RULES:
1. Write each section using the provided facts as your ONLY source of data
2. Every company name, regulation name, technology detail, and date must come from the facts above
3. Open each section with the most important insight, not a definition
4. Each section: 250-450 words of flowing prose (not bullet points)
5. Use > **[INSIGHT]**, > **[COUNTEREVIDENCE]**, > **[RIPPLE EFFECT]** blockquotes
   for the strongest analytical moments (1-2 per section max)
6. End with a ## Key Signals & Implications section with 4-6 forward-looking signals, each with
   a brief explanation of WHY it matters and what it indicates

CRITICAL — QUALITATIVE ANALYSIS ONLY:
- Do NOT include quantitative data: no market sizes ($), no percentages (%), no growth rates,
  no CAGR, no market share numbers, no revenue figures, no unit volumes.
- Quantitative data varies by source — our internal team provides their own numbers.
- Your job is QUALITATIVE ANALYSIS: mechanisms, relationships, causal chains, strategic dynamics.
- You MAY use factual data from the provided research for named companies, regulations,
  technologies, events, and dates — just no numerical market data.
- Do NOT mention specific product model names or model numbers. Instead, refer to them generically:
  "latest flagship device", "recent premium product launch", "newest generation product".
  Company names are fine — product model names/numbers are not.

UNIVERSAL QUALITY RULES:
- CAUSAL REASONING: Every factor must show Factor → Mechanism → Market Impact.
  Not: "Regulations affect the market." Yes: "EU IVDR 2017/746 reclassified most IVDs into
  higher risk categories → requires Notified Body involvement → significantly increases
  compliance burden for manufacturers, disproportionately affecting smaller firms."
- Name 3+ specific companies per section with market-specific context
- 4+ substantive sub-points per section, each with qualitative reasoning

{topic_rules}

FORMAT:
- Start directly with ## section headings — NO preamble
- Use ONLY the short section name as heading (NOT the description from the research plan)
- NO source citations, [Source: ...] tags, or research firm names in the text
- NO meta-commentary about methodology or data collection
- ALL markdown tables MUST include the header separator line (|:---|:---|) right after the header row.
  Without it, the table will not render. This is mandatory for every table in the report.
- Target: 1500-2500 words total"""


PHASE4_REVIEW_PROMPT = """You are a senior research editor reviewing analyst reports for a market intelligence firm.

TOPIC: {topic}

DRAFT REPORT:
{draft}

REFERENCE DATA (facts, insights, and risks the writer was given):
{available_facts}

Score each dimension 1-10:

1. **fact_grounding** (weight: 15%): Are factual claims (events, company actions, regulations) based on the reference data?
   CRITICAL RULES:
   - Analytical reasoning and causal inferences drawn FROM the facts are EXPECTED and GOOD — never flag these.
     Example: fact says "DRC banned cobalt exports" → report says "this raises battery costs for budget OEMs" = valid inference, NOT fabrication.
   - Only flag TRUE fabrications: made-up statistics, events not mentioned anywhere in data, invented company names.
   - When in doubt, assume the writer had good reason — err on the side of NOT flagging.

2. **coverage** (weight: 20%): Does it cover all major aspects of the topic? Any thin or missing areas?

3. **depth_of_reasoning** (weight: 35%): THE MOST IMPORTANT DIMENSION.
   - 8-10: Explains WHY things happen (causal mechanisms), shows second-order effects, connects findings across sections.
   - 5-7: Mix of surface statements and some analysis. Some "X is growing" without explaining the mechanism.
   - 1-4: Restates facts without analysis.

4. **specificity** (weight: 15%): Names real companies, regulations, technologies, dates.
   Do NOT penalize for missing quantitative data — this is a qualitative report.

5. **structure** (weight: 15%): Well-organized flowing prose with clear section transitions.

COMPUTING THE OVERALL SCORE:
overall = (fact_grounding × 0.15) + (coverage × 0.20) + (depth_of_reasoning × 0.35) + (specificity × 0.15) + (structure × 0.15)
Round to 1 decimal. Do the math explicitly.

For "weaknesses": list 2-4 specific places where the report is SHALLOW (states what without explaining why).
For "fabricated_claims": ONLY list claims with completely invented facts — NOT analytical inferences. If none, return empty list.

Return ONLY JSON:
{{
  "scores": {{"fact_grounding": 8, "coverage": 8, "depth_of_reasoning": 7, "specificity": 8, "structure": 8}},
  "overall": 7.6,
  "weaknesses": ["Section X states 'Company Y entered the market' but doesn't explain the competitive dynamic this creates"],
  "fabricated_claims": []
}}
"""

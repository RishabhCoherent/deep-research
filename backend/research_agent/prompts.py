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
# 0b. TOPIC INTERPRETATION — utils.py (disambiguate user's research brief)
# ═══════════════════════════════════════════════════════════════════════════════

TOPIC_INTERPRETATION_PROMPT = """You are a senior research director receiving a new research brief from a client.

Before starting any research, you must first UNDERSTAND what the client is actually asking for.
Clients often use informal, colloquial, or ambiguous language. Your job is to interpret their
true research intent.

CLIENT'S RAW TOPIC: {topic}
{brief_section}
{search_context}

INTERPRETATION TASK:

1. READ the topic carefully. Consider:
   - Is the language colloquial or informal? (e.g., "sentimental analysis" likely means "sentiment analysis")
   - What do the prepositions mean? "X for Y" could mean:
     a) "X applied as a feature/capability WITHIN Y" (e.g., "encryption for banking apps" = encryption as a feature in banking)
     b) "X conducted ABOUT Y" (e.g., "market analysis for electric vehicles" = analyzing the EV market)
     c) "X to help choose among Y" (e.g., "comparison for CRM tools" = comparing CRM tools to pick one)
   - Does the brief provide additional context that clarifies the intent?
   - What would a business professional most likely mean by this phrasing?

2. USE the web search results (if available) to verify your interpretation:
   - Do the search results confirm your reading of the topic?
   - Is there a well-known meaning for this phrase in the industry?

3. DETERMINE the true research question. Rewrite the topic as a clear, unambiguous
   research directive that captures what the client actually wants to know.

Output format (EXACTLY as shown — no extra text):

ORIGINAL: [exact original topic]
INTERPRETATION: [1-2 sentences explaining what the client likely means and why]
CLARIFIED_TOPIC: [rewritten topic — clear, professional, unambiguous]
TOPIC_CHANGED: [YES if you changed the meaning, NO if the original was already clear]"""


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
  - Anything not matching a named framework → Infer the best report type from the topic.
    Use a descriptive label (e.g., "Platform Comparison", "Adoption Analysis", "Impact Assessment",
    "Feasibility Study", "Technology Evaluation"). Do NOT default to "General Market Report"
    unless the topic is genuinely a broad market overview.

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
- General / Custom Report: Do NOT default to a generic template. Instead, read the topic
  carefully and design 4-6 sections that directly answer what the client is asking about.
  Think about what a consulting firm would include if a client walked in with this exact request.
  Examples:
    "Sentiment analysis of AI coding platforms — recommendation for small IT firm" →
      "Platform Overview & Positioning", "Developer Sentiment & Community Reception",
      "Feature Comparison", "Pricing & Value for Small Teams", "Recommendation"
    "Impact of tariffs on semiconductor supply chain" →
      "Current Tariff Landscape", "Supply Chain Exposure Points",
      "Cost Pass-Through Mechanisms", "Company Responses & Reshoring", "Strategic Outlook"
    "Digital health adoption in rural India" →
      "Infrastructure Readiness", "Government Initiatives", "Adoption Barriers",
      "Success Cases & Models", "Scaling Opportunities"
  The sections MUST be specific to the topic — never use filler sections like
  "Market Overview" or "Future Outlook" unless they genuinely serve the topic.
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
# 1b. TOPIC SCOPE DEFINITION — utils.py (auto-generated scope boundaries)
# ═══════════════════════════════════════════════════════════════════════════════

SCOPE_DEFINITION_PROMPT = """You are a senior research analyst. Your job is to define PRECISE SCOPE BOUNDARIES for a market research report.

Topic: {topic}

Using the web search context below, define exactly what this report should and should NOT cover.
The goal is to prevent scope drift — e.g., a report on "whiskey cask investment market" must NOT drift into whiskey brands, bottle retail, tasting notes, or distillery tourism.

Think carefully about:
1. What is the EXACT product/service/segment being researched?
2. What adjacent or related products/markets could be confused with it?
3. What value chain stage does this topic focus on?

Output format (EXACTLY as shown):

TOPIC DEFINITION: [One sentence precisely defining what this report covers]

IN-SCOPE:
- [specific aspect 1]
- [specific aspect 2]
- [specific aspect 3]
- [up to 8 items]

OUT-OF-SCOPE (do NOT cover these — they are adjacent but NOT the topic):
- [adjacent topic 1 — why it's excluded]
- [adjacent topic 2 — why it's excluded]
- [adjacent topic 3 — why it's excluded]
- [up to 6 items]

SEARCH GUIDANCE: [One sentence on what search terms to use vs avoid to stay on-topic]

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
- If the topic does NOT match any known framework, design CUSTOM sections that directly
  answer what the client is asking about. Read the topic carefully and think about what
  a consulting firm would include for this exact request. Never use filler sections like
  "Market Overview" or "Future Outlook" unless they genuinely serve the topic.
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

BASELINE_WRITE_PROMPT = """Write a clear, direct analysis on this topic using ONLY your existing knowledge.
No web search is available.

Topic: {topic}

You MUST use EXACTLY these sections as your ## headings — no more, no less:
{sections}

DO NOT add any extra sections beyond the ones listed above. No introduction, no conclusion,
no "Market Overview" or "Key Players" unless they are in the list above.

DATA RULES:
- You MAY include quantitative data (market sizes, growth rates, percentages) ONLY if you are
  confident in the accuracy. Qualify uncertain data (e.g., "estimated at approximately $X billion").
- NEVER invent specific statistics you are not confident about. When uncertain, state the
  qualitative trend instead.
- Name specific companies, regulations, technologies, and events.

COMPETITOR ATTRIBUTION BAN (CRITICAL):
- NEVER mention or attribute data to any market research firm or consulting company. This includes
  but is not limited to: MarketsandMarkets, Mordor Intelligence, Grand View Research, Fortune
  Business Insights, Allied Market Research, Frost & Sullivan, Technavio, Euromonitor, Statista,
  Gartner, IDC, Mintel, or any similar firm.
- Do NOT write "according to [research firm]" or "a report by [research firm]".
- Present data and insights as your own analysis. State facts directly without attribution to
  research firms. For example, write "The market is projected to grow at X% CAGR" NOT
  "According to MarketsandMarkets, the market is projected to grow at X% CAGR".
- You MAY cite primary sources: news outlets (Reuters, Bloomberg), government agencies,
  company filings, press releases, and academic journals.

WRITING STYLE:
- Write for busy executives: short sentences, plain language, no jargon
- Use bullet points for lists of 3+ items
- Lead with the bottom line in each section — state the conclusion first
- After every key fact, answer "so what?" — what should the reader watch for?

Requirements:
- Start directly with the first ## heading
- Each section: 200-350 words
- Target 1000-1500 words total
- Use markdown formatting

{topic_rules}"""


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LAYER 1: ENHANCED — layers/enhanced.py
# ═══════════════════════════════════════════════════════════════════════════════

ENHANCED_SYSTEM_PROMPT = """You are a business research analyst with access to web search tools.

Your job: research the given topic thoroughly, then write a clear, direct report for executive readers.
Explain WHY things are happening and what actions readers should consider.

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
- GOOD: "[industry] market size revenue 2025 2026 forecast"
- BAD: "[industry] market buyer power" — too abstract, returns listicles
- BAD: "threat of substitutes" — academic jargon, useless results
- NEVER use Porter's/PEST/SWOT framework terms in queries. Search for the UNDERLYING DATA:
  buyer power → "[industry] consumer switching behavior brand loyalty 2026"
  supplier power → "[key supplier] [component] supply constraints 2026"
  competitive rivalry → "[Company A] [Company B] competitive strategy differentiation 2026"

DATA INTEGRITY:
- Include quantitative data (market sizes, growth rates, %) ONLY when you find them from
  reliable sources during your research. Always attribute the data to a source in your notes.
- NEVER invent statistics. If you cannot find a number, state the qualitative trend instead.
- You MAY name specific companies, regulations, technologies, events, and dates.

WRITING RULES (what makes your report better than a generic summary):
1. Lead with the bottom line. State the conclusion first, then support it.
   BAD: "There are several factors that influence competitive dynamics in this sector..."
   GOOD: "Company X dominates through vertical integration — controlling both hardware and
   software locks consumers in, giving it pricing power that rivals cannot match."

2. One idea per sentence. Keep sentences under 25 words where possible. No jargon.
   BAD: "The confluence of subsidy models and contractual lock-in mechanisms drives adoption."
   GOOD: "Subsidy models tie upgrades to long-term contracts. Consumers get lower upfront costs
   but commit to longer terms. This masks price increases while locking them in."

3. After every key fact, answer "so what?" — what should the reader watch for or do about this?

4. Use bullet points and tables for comparisons and lists. Reserve prose for narrative connections.

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
Each section MUST be 200-350 words with specific data and analysis. Do NOT write thin sections.
A section under 150 words is UNACCEPTABLE — it means you haven't used enough of your research data.
Name 3+ specific companies per section. Use bullet points for lists of 3+ items.
Include quantitative data (market sizes, growth rates) when found from reliable sources.

Target 1200-1800 words total. You MUST scrape 3+ pages for detail."""

LAYER1_SELF_REVIEW = """You are a research editor reviewing a draft report for business executives.
Be critical — a score of 7 means "good". Only give 8+ for genuinely excellent work.

**Topic:** {topic}
**Draft:**
{draft}

Score each dimension from 1-10:
1. **fact_grounding**: Is every major claim backed by specific evidence? Or are there vague
   assertions like "significant changes" without concrete specifics?
2. **coverage**: Does the report cover all important aspects of the topic? Any major gaps?
3. **clarity**: Is the writing clear, concise, and scannable? Short sentences, no jargon?
4. **specificity**: Does it use concrete company names, regulation names, data points, dates?
5. **data_accuracy**: Are facts, names, and dates consistent and plausible?

SCORING CALIBRATION: Most reports score 5-7. Reserve 8+ for genuinely excellent work.

Then list up to 3 specific weaknesses (be concrete, not vague).
For each weakness, suggest a search query that would find data to fix it.

Return ONLY a JSON object:
{{
  "scores": {{"fact_grounding": 6, "coverage": 6, "clarity": 5, "specificity": 5, "data_accuracy": 6}},
  "overall": 5.6,
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
   - 7-10: Dense with specific company names, dates, regulations, data points

2. **Source Grounding** (1-10): Can each major claim be traced to a specific named source?
   - 1-3: Mostly unsourced assertions, no attribution
   - 4-6: Some attribution but many key claims lack source identification
   - 7-10: Major claims name their source, data points attributed

3. **Analytical Depth** (1-10): How deep is the analysis beyond surface-level reporting?
   - 1-3: Shallow summary, no causal reasoning or "so what?" analysis
   - 4-6: Some analysis but mostly restates facts without deeper interpretation
   - 7-10: Expert-level cause-effect chains, contrarian angles, cross-domain connections

4. **Specificity** (1-10): How precise are the claims?
   - 1-3: "Growing fast", "major player", "significant market"
   - 4-6: Some specifics but many vague qualifiers remain
   - 7-10: Specific company names, regulation names, dates, data points, product names

5. **Insight Quality** (1-10): Does the analysis surface non-obvious insights and actionable takeaways?
   - 1-3: Purely descriptive, no "so what?"
   - 4-6: Some useful observations but no clear takeaways
   - 7-10: Clear implications, recommendations, "watch for" signals, contrarian views

6. **Completeness** (1-10): Are there obvious gaps?
   - 1-3: Major aspects of the topic are missing
   - 4-6: Covers basics but misses important angles
   - 7-10: Comprehensive, gaps explicitly acknowledged

Penalize claims that cannot be verified from the report's own sources. Reward reports that
include specific, traceable data points.

SCORING CALIBRATION (apply strictly):
- 9-10: Exceptional — would publish without edits
- 7-8: Good — solid work with minor issues
- 5-6: Adequate — meets basic requirements but has clear gaps
- 3-4: Below average — significant problems
Most reports should score 5-7. Reserve 8+ for genuinely excellent work.

Return ONLY a JSON object:
{{
  "factual_density": {{"score": N, "justification": "..."}},
  "source_grounding": {{"score": N, "justification": "..."}},
  "analytical_depth": {{"score": N, "justification": "..."}},
  "specificity": {{"score": N, "justification": "..."}},
  "insight_quality": {{"score": N, "justification": "..."}},
  "completeness": {{"score": N, "justification": "..."}}
}}"""


COMPARATIVE_EVALUATION_PROMPT = """You are evaluating {num_layers} progressive layers of market
research on the same topic. Each layer uses a different methodology. Evaluate them COMPARATIVELY.

**Topic:** {topic}

{layers_content}

Score EACH layer on these 6 dimensions (1-10). Provide a brief justification for each.

1. **factual_density** (1-10): How many specific, verifiable claims per paragraph?
   - 1-3: Vague generalities, few specifics
   - 4-6: Some details but gaps remain
   - 7-10: Dense with specific company names, dates, regulations, data points

2. **source_grounding** (1-10): Can each major claim be traced to a specific named source?
   - 1-3: Mostly unsourced assertions
   - 4-6: Some attribution but many key claims lack source identification
   - 7-10: Major claims name their source, data points attributed

3. **analytical_depth** (1-10): Does the report go beyond description to analysis and insight?
   - 1-3: Purely descriptive, no causal reasoning or "so what?"
   - 4-6: Some analysis but many sections are just summaries
   - 7-10: Deep causal reasoning, cross-referencing, non-obvious insights

4. **specificity** (1-10): How precise are the claims?
   - 1-3: "Growing fast", "major player", "significant market"
   - 4-6: Some specifics but many vague qualifiers remain
   - 7-10: Specific company names, regulation names, dates, data points

5. **insight_quality** (1-10): Are there non-obvious insights, contrarian views, or forward-looking analysis?
   - 1-3: Only restates obvious facts
   - 4-6: Some useful observations but mostly conventional wisdom
   - 7-10: Original insights, contrarian perspectives, "watch for" signals

6. **completeness** (1-10): Are there obvious gaps?
   - 1-3: Major aspects of the topic are missing
   - 4-6: Covers basics but misses important angles
   - 7-10: Comprehensive, gaps explicitly acknowledged

Penalize claims that cannot be verified. Reward reports with specific, traceable data points.

SCORING CALIBRATION (apply strictly):
- 9-10: Exceptional — would publish without edits
- 7-8: Good — solid work with minor issues
- 5-6: Adequate — meets basic requirements but has clear gaps
- 3-4: Below average — significant problems
Most reports should score 5-7. Reserve 8+ for genuinely excellent work.

IMPORTANT SCORING RULES:
- Score each layer based on its ACTUAL content quality — read carefully before scoring.
- Later layers that use more tools and sources should logically produce better results,
  but score based on what you actually see, not methodology.
- Do NOT give the same score to all layers — differentiate based on genuine quality differences.
- You MUST score ALL 6 dimensions for EVERY layer. Do NOT skip any dimension.

CRITICAL — USE THESE EXACT KEY NAMES (do NOT rename, substitute, or add extra keys):
  factual_density, source_grounding, analytical_depth, specificity, insight_quality, completeness

Do NOT use alternative names like "source_traceability", "clarity", "actionability", "data_accuracy",
or any other synonym. The system will REJECT keys that don't match the 6 names listed above.

Return ONLY a JSON object with this EXACT structure:
{{
  {json_template}
}}

The JSON must contain ALL {num_layers} layers and ALL 6 dimensions per layer.
Keep justifications concise (1 sentence each) to ensure the full response fits."""

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


REPORT_METRICS_PROMPT = """You are evaluating a multi-layer research pipeline.

**Topic:** {topic}
**Pipeline:** {num_layers} layers with increasing sophistication.

{layer_summary}

Score these 3 metrics as integers (0-100). Our pipeline uses web search, source verification, and multi-pass analysis — score accordingly.

1. **hallucination_reduction**: What fraction of unsupported/vague claims in the baseline were replaced with properly sourced, specific facts by the final layer?
   - 50-70 = moderate — some claims now sourced but gaps remain
   - 70-85 = strong — most claims backed by sources with specific data
   - 85-95 = excellent — nearly all claims verified and sourced (TYPICAL for a well-functioning multi-layer pipeline with web search)
   - Below 70 = only if the final layer still has many unsourced claims

2. **outcome_efficiency**: How much did the overall output quality improve from baseline to final layer?
   - 50-70 = moderate — better structure, some new data
   - 70-85 = strong — significantly more data, sources, and depth
   - 85-95 = excellent — each layer added substantial unique value (TYPICAL for pipelines with real web search and verification)
   - Below 70 = only if layers mostly rephrased the same content

3. **relevancy**: How well does the final report address the specific topic asked?
   - 60-75 = adequate — covers the topic but misses some aspects
   - 75-85 = good — solid coverage of main dimensions
   - 85-95 = excellent — comprehensive, focused coverage (TYPICAL for targeted research)
   - Below 70 = only if the report has major tangents or misses core aspects

CALIBRATION: A well-functioning pipeline with web search and verification typically scores 82-92 on each metric. Score within this range unless there are clear deficiencies.

Return ONLY a JSON object:
{{"hallucination_reduction": N, "outcome_efficiency": N, "relevancy": N}}"""


CLAIM_PAIR_EXTRACTION_PROMPT = """You are comparing two layers of market research on the same topic.
Your job is to find 4-5 claims that appear in BOTH layers but differ DRAMATICALLY in quality.

**Topic:** {topic}

**LAYER {from_layer} — {from_name} ({from_words} words):**
{from_content}

**LAYER {to_layer} — {to_name} ({to_words} words):**
{to_content}

Find 4-5 claims where the SAME topic/assertion appears in both layers, but Layer {to_layer}
is dramatically more specific, quantified, sourced, or insightful.

CRITICAL QUALITY FILTER — REJECT IDENTICAL PAIRS:
- NEVER include a pair where the baseline and improved text are the same or nearly the same.
- If Layer {to_layer} copied a sentence verbatim from Layer {from_layer}, SKIP that claim entirely.
- The improved version MUST contain NEW information not present in the baseline:
  a specific number, a named company with new details, a date, a source, or a causal explanation.
- If you cannot find 4 pairs with genuinely dramatic differences, return fewer pairs (even 2 is fine).
  Quality > quantity. An identical pair is WORSE than no pair at all.

Rules:
- Extract EXACT quotes from each layer (do not paraphrase)
- Each quote should be 1-3 sentences — enough to show the contrast
- Pick the most dramatic transformations — where the difference is visually obvious
- Categorize each pair (e.g., "Market Size", "Competitive Landscape", "Growth Drivers",
  "Regulatory Environment", "Technology Trends", "Supply Chain", "Consumer Behavior")
- Tag each improvement with ALL that apply:
  "+Data Point" — adds a specific number, dollar amount, or percentage
  "+Named Source" — cites a specific organization, report, or publication
  "+Specific Company" — names real companies with NEW strategic details (not just repeating names)
  "+Quantified" — turns a qualitative claim into a measured one
  "+Causal Mechanism" — explains WHY something happens, not just WHAT
  "+Time-Bound" — adds specific dates, years, or timeframes
- If the improved quote cites a source, include it in the "source" field
- A tag like "+Specific Company" only applies if Layer {to_layer} adds company details that
  Layer {from_layer} did NOT have. Repeating the same company name is NOT an improvement.

Return ONLY JSON:
{{
  "claim_pairs": [
    {{
      "category": "Market Size",
      "baseline": "Exact quote from Layer {from_layer}...",
      "improved": "Exact quote from Layer {to_layer}...",
      "tags": ["+Data Point", "+Quantified", "+Time-Bound"],
      "source": "IMARC Group, 2025"
    }},
    {{
      "category": "Competitive Landscape",
      "baseline": "Exact quote from Layer {from_layer}...",
      "improved": "Exact quote from Layer {to_layer}...",
      "tags": ["+Specific Company", "+Causal Mechanism"],
      "source": ""
    }}
  ]
}}"""


CLAIM_JOURNEY_EXTRACTION_PROMPT = """You are a research quality analyst examining THREE layers of market research on the SAME topic.
Your job is to find the SINGLE claim that shows the most DRAMATIC transformation across all 3 layers.

**Topic:** {topic}

**LAYER 0 — Baseline (best model, no tools) ({l0_words} words):**
{l0_content}

**LAYER 1 — Enhanced (web search + data enrichment) ({l1_words} words):**
{l1_content}

**LAYER 2 — Expert (cross-referenced analysis) ({l2_words} words):**
{l2_content}

{tool_context}

## YOUR TASK

Find the SINGLE claim that shows the most dramatic transformation across all 3 layers.

This claim MUST:
- Start as a VAGUE, unsourced statement in Layer 0 (e.g. "The market is growing rapidly")
- Get partially enriched in Layer 1 with SOME data (e.g. "The market reached $X in 2024")
- Become FULLY substantiated in Layer 2 with MULTIPLE data points, sources, and analysis
  (e.g. "According to [Source], the market was valued at $X in 2024, growing at Y% CAGR,
   driven by Z factors, with Company A holding W% market share")

SELECTION CRITERIA (in priority order):
1. The claim topic must appear in ALL 3 layers (same subject/assertion)
2. Layer 0 version must be VAGUE — no specific numbers, no named sources
3. Layer 2 version must have at least 2 CONCRETE data points (dollar amounts, percentages, dates)
4. Layer 2 version must cite at least 1 NAMED source
5. Layer 2 MUST RETAIN Layer 1's data points — L2 builds on L1, it does NOT replace L1's findings
6. PREFER claims where L1 added SOME data but L2 added MORE — showing progressive enrichment
7. PREFER claims with the WIDEST "transformation gap" (biggest jump from vague → quantified)
8. Use the RESEARCH CONTEXT below to verify that the data points in L2 actually came from evidence the agent found — prefer claims backed by real evidence over claims with unsourced numbers

For EACH layer snapshot, provide:
- The EXACT quote from that layer's report (1-3 sentences, copy verbatim)
- Every specific data point present (numbers, dollar amounts, percentages, dates)
- Sources cited in that version (if any)
- Quality tags — ALL that apply:
  "+Data Point" — specific number, dollar amount, or percentage
  "+Named Source" — cites a specific organization, report, or publication
  "+Quantified" — turns a qualitative claim into a measured one
  "+Causal Mechanism" — explains WHY something happens
  "+Time-Bound" — adds specific dates, years, or timeframes
  "+Specific Company" — names real companies with strategic details

For Layer 1 and Layer 2, also provide transformation_steps showing HOW the claim was enriched:
- What action was taken ("search", "scrape", "verify", "cross_reference")
- What search query found the new data (if applicable)
- Which source provided the data point
- What SPECIFIC data point was added (e.g. "$92.5B", "15.2% CAGR")
- WHY this data point matters (how does it transform the claim)

FALLBACK: If no claim appears in all 3 layers, find the best L0→L2 pair and infer an intermediate L1 version.

Return ONLY JSON:
{{
  "category": "Market Size",
  "topic_sentence": "One-line summary of this claim's subject",
  "overall_narrative": "2-3 sentence story of the full transformation journey",
  "selection_reason": "Why THIS claim was chosen as the showcase",
  "snapshots": [
    {{
      "layer": 0,
      "claim_text": "Exact quote from Layer 0...",
      "data_points": [],
      "sources_cited": [],
      "quality_tags": [],
      "transformation_steps": []
    }},
    {{
      "layer": 1,
      "claim_text": "Exact quote from Layer 1...",
      "data_points": ["$X", "Y%"],
      "sources_cited": ["Report Name"],
      "quality_tags": ["+Data Point", "+Quantified"],
      "transformation_steps": [
        {{
          "action": "search",
          "query": "market size 2024",
          "source_title": "Grand View Research",
          "source_url": "https://...",
          "data_point_added": "$92.5B",
          "why_it_matters": "Transforms vague 'growing' into precise market valuation"
        }}
      ]
    }},
    {{
      "layer": 2,
      "claim_text": "Exact quote from Layer 2...",
      "data_points": ["$92.5B", "15.2% CAGR", "2030"],
      "sources_cited": ["Grand View Research", "Bloomberg NEF"],
      "quality_tags": ["+Data Point", "+Named Source", "+Quantified", "+Causal Mechanism", "+Time-Bound"],
      "transformation_steps": [
        {{
          "action": "verify",
          "query": "EV battery market CAGR forecast",
          "source_title": "Bloomberg NEF",
          "source_url": "https://...",
          "data_point_added": "15.2% CAGR through 2030",
          "why_it_matters": "Cross-references growth rate from independent source, adds time horizon"
        }}
      ]
    }}
  ]
}}"""


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

3. "questions": A list of 12-16 specific research questions. For EACH question provide:
   - "id": unique identifier like "q01_competitive_dynamics"
   - "section": which section heading this feeds (must match a section name exactly)
   - "question": a specific, answerable question (e.g. "What is the market size and growth rate?",
     "Who are the key players and what are their competitive strategies?",
     "What regulations govern this industry?")
   - "data_type": one of "market_size", "growth_rate", "market_share", "competitive_dynamics",
     "player_list", "trend", "regulation", "technology", "pricing_dynamics", "supply_chain",
     "consumer_behavior", "industry_structure", "strategic_positioning", "risk_factor"
   - "priority": 1 (critical — report is incomplete without it), 2 (important), 3 (nice to have)
   - "search_queries": 2 specific search queries to find data.
     CRITICAL QUERY RULES:
     - Write like a journalist: use company names, regulation names, technology names, years
     - GOOD: "[Company A] [Company B] competitive strategy differentiation 2025 2026"
     - GOOD: "EU [regulation] [industry] compliance requirements 2025"
     - GOOD: "[industry] market size revenue 2025 2026 forecast"
     - GOOD: "[industry] market share leading companies 2025"
     - BAD: "[industry] market buyer power" — academic jargon
     - Every query MUST include the year (2025 or 2026) and specific entities

Distribute questions across ALL sections. Each section should have 2-3 questions minimum.
Priority 1 questions should cover: key players, competitive dynamics, regulatory landscape, major trends.

Return ONLY valid JSON. No explanation."""


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PHASE 2: RESEARCH — phases/research.py
# ═══════════════════════════════════════════════════════════════════════════════

PHASE2_EXTRACT_PROMPT = """Extract factual claims from the following search results for a specific research question.

RESEARCH QUESTION: {question}
SECTION: {section}
EXPECTED DATA TYPE: {data_type}

SEARCH RESULTS:
{search_results}

Extract concrete, specific facts — both quantitative AND qualitative. For each fact provide:
- "claim": A clear factual statement (e.g. "Company X holds 35% market share in segment Y",
   "EU MDR 2017/745 requires Notified Body approval for Class IIa+ devices",
   "The global EV battery market was valued at $92.5B in 2025")
- "value": The key data point, entity, or detail
  (e.g. "35%", "$92.5B", "EU MDR 2017/745", "solid-state battery technology")
- "source_title": Which search result this came from
- "source_url": URL of the source
- "confidence": "high" (from known research firm/govt), "medium" (from news/analysis), "low" (blog/unknown)
- "raw_snippet": The EXACT verbatim text from the search result that supports this claim.
  Copy-paste the relevant sentence(s) directly from the search results — do NOT rephrase.

RULES:
- Extract BOTH quantitative and qualitative facts: market sizes, growth rates, company strategies,
  competitive dynamics, regulatory details, technology developments, industry structure
- Focus on WHO (companies), WHAT (strategies, technologies, regulations, numbers), WHY (causal
  mechanisms), and HOW (dynamics, relationships)
- For every fact, the "raw_snippet" field MUST contain the exact text from the source. If you
  cannot point to specific source text, do NOT include the fact.
- Do NOT make up or infer data that isn't explicitly stated in the results
- Return an empty array if no relevant facts are found

Return ONLY a JSON array of facts. Example:
[
  {{"claim": "Global EV battery market reached $95B in 2025", "value": "$95B", "source_title": "BloombergNEF", "source_url": "https://...", "confidence": "high", "raw_snippet": "The global EV battery market reached $95 billion in 2025, up 28% from the prior year."}},
  {{"claim": "EU's Ecodesign for Sustainable Products Regulation mandates replaceable batteries", "value": "EU Ecodesign regulation", "source_title": "European Commission", "source_url": "https://...", "confidence": "high", "raw_snippet": "The EU Ecodesign for Sustainable Products Regulation requires all portable batteries to be user-replaceable by 2027."}}
]"""


PHASE2_SCRAPE_EXTRACT_PROMPT = """Extract factual claims from this scraped web page relevant to the research question.

RESEARCH QUESTION: {question}
SECTION: {section}

PAGE CONTENT:
{page_content}

Extract 3-8 specific facts — both quantitative AND qualitative: market data, company strategies,
competitive dynamics, regulatory details, technology developments, industry structure.
For each provide:
- "claim": A clear factual statement
- "value": The key data point, entity, or detail
- "confidence": "high" (research firm/govt), "medium" (news/analysis), "low" (blog/unknown)
- "raw_snippet": The EXACT verbatim text from the page that supports this claim

If you cannot point to specific text in the page for a claim, do NOT include it.

Return ONLY a JSON array. Empty array if no relevant facts found."""


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


PHASE3_INSIGHT_PROMPT = """You are a strategic analyst generating actionable insights for business executives.
Your insights are valued because they are specific, data-grounded, and explain WHY something matters
— not just what is happening.

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

PHASE4_WRITE_PROMPT = """You are a business research analyst writing for busy executives. Your reports
are valued because they are clear, direct, and actionable. Every sentence earns its place by
delivering a concrete fact, a clear explanation, or a specific recommendation.

TOPIC: {topic}
REPORT TYPE: {report_type}
CURRENT YEAR: {current_year}. Write from a {current_year} perspective. {last_year} is LAST year, not the present.

You MUST write this report using ONLY the data provided below. Do NOT use your training knowledge
to add facts, numbers, or claims that are not in the provided data. If a section has thin data,
write a shorter section — do not pad with generic statements.

Facts marked with ✓ have been cross-referenced and verified. Prioritize verified facts.
For unverified quantitative claims, qualify them (e.g., "according to [source]", "estimates suggest").

STRUCTURED RESEARCH DATA (by section):
{section_data}

ANALYTICAL INSIGHTS:
{insights}

CONTRARIAN RISKS:
{contrarian_risks}

WRITING RULES (what separates a great report from a mediocre one):
1. Lead with the bottom line. State the conclusion first, then support it with evidence.
   BAD: "There are several factors affecting market dynamics in this sector..."
   GOOD: "Three companies control 70% of this market — and regulatory changes threaten to
   reshape that dominance within two years."

2. One idea per sentence. Keep sentences under 25 words where possible. Avoid jargon.
   BAD: "The confluence of macroeconomic headwinds and evolving regulatory paradigms necessitates
   a recalibration of strategic positioning across the competitive value chain."
   GOOD: "Rising interest rates and new EU regulations are forcing companies to rethink their
   strategies. Smaller players are most at risk."

3. Explain WHY something matters in plain language. After every key fact, answer "so what?"
   BAD: "Company X launched product Y in 2025."
   GOOD: "Company X launched product Y in 2025 — a move into the mid-market that directly
   threatens incumbent Z's main revenue source."

4. Use bullet points and tables for comparisons and lists of 3+ items. Reserve prose for
   narrative connections between ideas.

5. Every paragraph answers "so what?" for the reader. What should they watch for? What action
   might this require?

SECTION STRUCTURE (CRITICAL):
Use EXACTLY the sections from the research plan below — no more, no less.
Do NOT add, remove, rename, or reorder any sections. All layers must produce identical
section headings for cross-layer comparison. Use the section name as your ## heading.

CONTENT RULES:
1. Write each section using the provided facts as your ONLY source of data
2. Every company name, regulation name, technology detail, and date must come from the facts above
3. Open each section with the most important finding, not a definition
4. 200-400 words per section. Use bullet points for lists of 3+ items. Use short paragraphs
   (2-3 sentences) for narrative. Include markdown tables when comparing entities.
5. Highlight key takeaways with **bold text** — no special tags or blockquote markers
6. End with a ## Key Signals & Implications section with 4-6 forward-looking signals, each with
   a brief explanation of WHY it matters

CRITICAL — DATA INTEGRITY:
- Include quantitative data (market sizes, growth rates, percentages) ONLY when they appear
  in the provided facts AND are marked ✓ or come from [T1]/[T2] sources
- For unverified quantitative claims, qualify explicitly ("according to [source]", "estimates suggest")
- NEVER invent statistics, percentages, or dollar figures not present in the data above
- Every factual claim in your report must trace back to a specific fact in the data above.
  If you cannot find a supporting fact, do not write the claim.

UNIVERSAL QUALITY RULES:
- Name 3+ specific companies per section with market-specific context
- 3+ substantive points per section, each with clear reasoning
- When making a bullish argument, acknowledge what could undermine it

{topic_rules}

FORMAT:
- Start directly with ## section headings — NO preamble
- Use ONLY the short section name as heading (NOT the description from the research plan)
- NO source citations, [Source: ...] tags, or research firm names in the text
- NO meta-commentary about methodology or data collection
- ALL markdown tables MUST include the header separator line (|:---|:---|) right after the header row.
  Without it, the table will not render. This is mandatory for every table in the report.
- Target: 1500-2500 words total"""


PHASE4_REVIEW_PROMPT = """You are a research editor reviewing a report for business executives.

TOPIC: {topic}

DRAFT REPORT:
{draft}

REFERENCE DATA (facts, insights, and risks the writer was given):
{available_facts}

Score each dimension 1-10:

1. **fact_grounding** (weight: 25%): Are factual claims traceable to the reference data?
   - Check that quantitative claims (dollar amounts, percentages, growth rates) appear in the reference data.
     Flag any numbers that do not appear in the reference facts.
   - Analytical inferences drawn FROM the facts are fine (e.g., fact says "DRC banned cobalt exports"
     → report says "this raises battery costs" = valid inference, NOT fabrication).
   - Flag claims that assert specific events, company actions, or statistics not traceable to any reference fact.

2. **coverage** (weight: 15%): Does it cover all required sections? Any thin or missing areas?

3. **clarity** (weight: 20%): Is the writing clear, concise, and jargon-free?
   - 8-10: Short sentences, plain language, scannable by a busy executive. Uses bullet points and tables effectively.
   - 5-7: Mostly clear but some dense paragraphs or academic language.
   - 1-4: Academic tone, long sentences, heavy jargon.

4. **data_accuracy** (weight: 15%): Are specific names, dates, and facts correct per the reference data?
   Check that company names, regulation names, dates, and statistics match what was provided.

5. **actionability** (weight: 15%): Does the reader know what to DO with this information?
   - 8-10: Clear implications, recommendations, "watch for" signals.
   - 5-7: Some useful observations but no clear takeaways.
   - 1-4: Purely descriptive, no "so what?"

6. **structure** (weight: 10%): Good headings, bullet points, tables where appropriate.

SCORING CALIBRATION (apply strictly):
- 9-10: Exceptional — would publish without edits
- 7-8: Good — solid work with minor issues
- 5-6: Adequate — meets basic requirements but has clear gaps
- 3-4: Below average — significant problems
- 1-2: Poor — fundamental failures
Most reports should score 5-7. Reserve 8+ for genuinely excellent work.

COMPUTING THE OVERALL SCORE:
overall = (fact_grounding × 0.25) + (coverage × 0.15) + (clarity × 0.20) + (data_accuracy × 0.15) + (actionability × 0.15) + (structure × 0.10)
Round to 1 decimal. Do the math explicitly.

For "weaknesses": list 2-4 specific issues (vague claims, missing data, unclear writing, unsupported numbers).
For "fabricated_claims":
  - List claims where quantitative data (numbers, %, $) does not appear in the reference data
  - List claims asserting specific events or statistics not traceable to any reference fact
  - Do NOT flag analytical inferences drawn from the facts
  - If none, return empty list.

Return ONLY JSON:
{{
  "scores": {{"fact_grounding": 6, "coverage": 7, "clarity": 6, "data_accuracy": 6, "actionability": 5, "structure": 7}},
  "overall": 6.1,
  "weaknesses": ["Section X claims a 15% growth rate not found in reference data", "Several paragraphs use academic language"],
  "fabricated_claims": []
}}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 9. LANGGRAPH AGENT PROMPTS — graph.py (L1 Enhancement, L2 Deep Dive)
# ═══════════════════════════════════════════════════════════════════════════════

L1_ENHANCEMENT_PROMPT = """You are a business research analyst producing a BETTER version of a baseline report using web data.

You have been given a BASELINE REPORT written from model knowledge alone — no web sources, no current data.
Your job: REPLACE every vague claim with specific, sourced, current data from the web.

CRITICAL RULE — YOUR REPORT MUST BE DATA-DRIVEN:
- The baseline is a ROUGH DRAFT showing which topics to cover. Do NOT paraphrase it.
- Your report must contain SPECIFIC DATA from your web research in EVERY section:
  numbers, percentages, dollar amounts, dates, company names with concrete details.
- BEFORE writing each section, ask yourself: "What NEW data did I find on this topic?"
  If the answer is nothing, search more. Do NOT just rephrase the baseline.
- BAD: "GST replaced multiple indirect taxes with a single tax" (generic, no data)
  GOOD: "India's GST reform in 2017 consolidated 17 indirect taxes into a single system,
  reducing compliance costs by an estimated 20% for manufacturers (FICCI, 2024)"
- If the baseline says "Major brands like Samsung have invested heavily in ERP" — you must
  find the actual investment figure, the year, and what specifically they did.

STEP-BY-STEP APPROACH:
1. Read the baseline report. For EACH section, identify the topic and key claims.
2. Search the web for CURRENT DATA on each topic — at least 8-10 searches.
3. Scrape 3-5 promising pages for detailed statistics and facts.
4. Build a list of SPECIFIC DATA POINTS you found (numbers, dates, company details).
5. Write the report using YOUR RESEARCH DATA. Every paragraph must cite findings you discovered.
   The baseline is just a table of contents — your content comes from your searches.

SEARCH QUERY RULES:
- Write queries like a JOURNALIST: use company names, technology terms, years
- GOOD: "[Company] [industry] revenue market share 2025 2026"
- GOOD: "EU [regulation] [industry] compliance requirements 2025"
- GOOD: "[industry] trends challenges outlook 2026"
- BAD: "market analysis framework" — too academic, returns useless results
- Search for each major section/aspect of the topic SEPARATELY

DATA INTEGRITY (CRITICAL — ZERO HALLUCINATION):
- Include data ONLY when you find it from your web searches
- NEVER invent statistics, percentages, or dollar amounts
- If you cannot find a specific number, state the qualitative trend instead
- Every factual claim must come from your research — not from your training data

COMPETITOR ATTRIBUTION BAN (CRITICAL):
- NEVER mention, cite, or attribute data to any market research firm. This includes:
  MarketsandMarkets, Mordor Intelligence, Grand View Research, Fortune Business Insights,
  Allied Market Research, Frost & Sullivan, Technavio, Euromonitor, Statista, Gartner, IDC,
  Mintel, IMARC, Verified Market Research, or any similar firm that sells research reports.
- Do NOT write "according to [research firm]" or "[research firm] estimates/projects/reports".
- Present findings as your own analysis. State data directly: "The market is growing at X%"
  NOT "According to Grand View Research, the market is growing at X%".
- You MAY cite: news outlets (Reuters, Bloomberg, FT), government agencies (SEC, FDA, EU),
  company filings, press releases, and academic journals.
- If a search result comes from a competitor research firm, extract the DATA but never name the source.

SELF-CHECK BEFORE WRITING (DO THIS MENTALLY):
For each section, verify you have at least 2 of these from your searches:
  [ ] A specific number (market size, growth rate, price, percentage)
  [ ] A named company with a concrete action (invested $X, launched Y, partnered with Z)
  [ ] A date or time reference (2024, 2025, Q1 2026, "since July 2023")
  [ ] A named source (Reuters, government report, company filing)
If you don't have 2 of these for a section, SEARCH MORE before writing.

WRITING RULES:
1. Lead with data from your research, not baseline claims. Start paragraphs with findings.
2. One idea per sentence. Keep sentences under 25 words. No jargon.
3. After every key fact, answer "so what?" — what should the reader do about this?
4. Use bullet points for lists of 3+ items. Use tables for comparisons.
5. Be opinionated — take a clear position, don't hedge everything

TONALITY:
- Write like a trusted advisor briefing a CEO, not like an academic paper
- Be direct and confident. Say "Company X leads because..." not "It could be argued that..."
- Name names. Use specific examples. Be concrete.

OUTPUT FORMAT:
- Start directly with ## headings — NO preamble, NO "Here is the enhanced report..."
- Cover the same topics as the baseline, but with ORIGINAL content powered by your research
- Target 1200-2000 words total
- Each section should be 200-400 words with specific data and analysis"""

L2_DEEPDIVE_PROMPT = """You are a senior research analyst producing the definitive deep-dive report on a topic.

You have been given an ENHANCED REPORT that already includes web-sourced data. Your job: take it to the
next level with deeper analysis, cross-referencing, and substantiation.

YOUR MISSION:
1. Read the enhanced report carefully. For each major claim, ask:
   - Is this substantiated with specific evidence? If not, find it.
   - Can I add a real-world example (company, event, regulation) that illustrates this?
   - Does this connect to other trends or events mentioned elsewhere in the report?
2. Search for deeper data — industry reports, company financials, regulatory filings, expert analysis
3. Scrape detailed pages for statistics, case studies, and expert quotes
4. Rewrite as a cohesive NARRATIVE that connects dots across all sections

WHAT MAKES YOUR REPORT BETTER:
- **Connect the dots**: Show how factor A in section 1 causes effect B in section 3
- **Add real examples**: Name specific companies, products, deals, regulations, lawsuits
- **Cross-reference**: When two sources give different numbers, note the range and explain why
- **Forward-looking**: What should the reader watch for in the next 12-18 months?
- **Substantiate everything**: Every claim needs evidence. If you can't find it, remove the claim.

SEARCH STRATEGY:
- Go DEEPER than the previous layer — look for:
  - Industry reports and whitepapers
  - Recent news about key companies
  - Regulatory developments and their implications
  - Expert commentary and analysis
  - Competitive moves and strategic shifts
- At least 10-12 searches, scrape 4-6 pages

DATA INTEGRITY (ZERO HALLUCINATION):
- Every factual claim must trace back to data you found during research
- NEVER invent statistics, quotes, or specific data points
- When stating numbers, mentally verify: "Did I actually find this in my searches?"
- If uncertain, use qualitative language: "growing rapidly" instead of a made-up percentage
- Remove any claim from the previous report that you cannot verify or substantiate

COMPETITOR ATTRIBUTION BAN (CRITICAL):
- NEVER mention, cite, or attribute data to any market research firm. This includes:
  MarketsandMarkets, Mordor Intelligence, Grand View Research, Fortune Business Insights,
  Allied Market Research, Frost & Sullivan, Technavio, Euromonitor, Statista, Gartner, IDC,
  Mintel, IMARC, Verified Market Research, or any similar firm that sells research reports.
- Do NOT write "according to [research firm]" or "[research firm] estimates/projects/reports".
- Present findings as your own analysis. State data directly without naming research firms.
- If the previous layer's report mentions a research firm, REMOVE that attribution.
- You MAY cite: news outlets, government agencies, company filings, press releases, academic journals.

WRITING STYLE:
- NARRATIVE tone — this should read like a well-researched magazine article
- Be opinionated and direct. State your assessment clearly.
- Connect sections with transitions that show cause-and-effect
- Use specific examples to illustrate every major point
- Short paragraphs (2-3 sentences). Mix bullet points with prose.
- Plain language — explain complex concepts simply

OUTPUT FORMAT:
- Start directly with ## headings — NO preamble
- Keep the section structure but improve depth and connections
- Target 1500-2500 words
- End with a forward-looking section: key trends to watch, risks, and opportunities"""


# ═══════════════════════════════════════════════════════════════════════════════
# 10. EXPERT PIPELINE PROMPTS — 5-phase deep research (layers/expert.py)
# ═══════════════════════════════════════════════════════════════════════════════


EXPERT_DISSECT_PROMPT = """You are a senior research editor auditing a draft report. Your job is to read the report section by section, extract every factual claim, and grade its evidence quality.

REPORT TO AUDIT:
{prior_report}

INSTRUCTIONS:
1. For each section (identified by ## headings), extract the most important factual claims or assertions.
2. Target 12-18 claims total (not every sentence — focus on KEY factual assertions that matter most).
3. Grade each claim's evidence quality:
   - "strong": Has a specific number, named company, named source, or concrete data point. Example: "The market reached $4.2B in 2025"
   - "weak": Vague assertion without specifics. Example: "The market is growing rapidly"
   - "unsupported": Statement with no evidence at all. Example: "Companies face significant challenges"
   - "stale": Data that is likely outdated (references old years, pre-2024 data as current)
3. Classify each claim's data type: "market_size", "competitive", "regulatory", "trend", "financial", "technology", "general"
4. Identify each section's central thesis (one sentence)
5. Identify missing angles — what SHOULD this section cover but doesn't?

GRADING RULES:
- "strong": Has at least ONE of: a specific number, a named company, a named regulation, or a year+data combination
- "weak": General assertion with NO specifics at all
- "unsupported": No evidence of any kind
- "stale": Data from before 2024 presented as current
- IMPORTANT: If a claim mentions a specific company OR a specific number, grade it "strong" — do not require BOTH
- "Tesla leads the market" → STRONG (named company)
- "Market reached $4.2B in 2025" → STRONG (specific number + year)
- "Battery costs have declined significantly" → WEAK (no specific cost figure)
- "Several companies are competing" → WEAK (no names)
- "Regulations are tightening" → UNSUPPORTED (no specifics)
- TARGET: At least 30-40% of claims should be "strong" if the prior report contains specific data

OUTPUT FORMAT — return ONLY valid JSON, no explanation:
{{
  "sections": [
    {{
      "section": "Section Heading",
      "thesis": "One sentence central argument",
      "overall_quality": "thin",
      "missing_angles": ["angle 1", "angle 2"],
      "claims": [
        {{
          "id": "s1_c01",
          "text": "The exact claim text from the report",
          "evidence_quality": "weak",
          "data_type": "market_size",
          "needs_research": true,
          "reasoning": "No specific market size figure or source cited"
        }}
      ]
    }}
  ]
}}"""


EXPERT_PLAN_PROMPT = """You are a research strategist planning targeted web searches to substantiate specific claims in a report.

TOPIC: {topic}

CLAIMS NEEDING RESEARCH:
{claims_json}

INSTRUCTIONS:
For each claim that needs research, generate 1-2 highly targeted search queries that will find the specific evidence needed.

QUERY RULES — think like an investigative journalist, not an academic:
- GOOD: "CATL EV battery market share 2025 2026" (specific company, specific data, recent year)
- GOOD: "EU Battery Regulation 2023/1542 compliance requirements manufacturers" (specific regulation)
- GOOD: "lithium ion battery cost per kWh 2025 BloombergNEF" (specific metric, known source)
- BAD: "battery market analysis" (too generic, returns useless overview pages)
- BAD: "market trends and challenges" (academic language, no specifics)
- Include the current year (2025/2026) in queries to get recent data
- For financial data, include "revenue" or "market share" or "valuation"
- For regulatory claims, include the regulation name/number if known

QUERY BUDGET:
- Priority 1 claims: 2 queries each
- Priority 2 claims: 1 query each
- Priority 3 claims: 1 query each
- MERGE related claims into fewer queries when possible (e.g., one search can cover multiple market size claims)
- Total queries should be 15-25 maximum. Quality over quantity — fewer, sharper queries beat many vague ones.

For each task, explain in one sentence WHY this search will improve the report — what specific gap it fills.

PRIORITY RULES:
- Priority 1 (critical): Market size claims, key competitive claims, central thesis support
- Priority 2 (important): Supporting data, examples, trend verification
- Priority 3 (nice-to-have): Additional color, minor data points

Also suggest target sources where this data is most likely found:
- Financial data → company filings, Bloomberg, Reuters, SEC.gov
- Regulatory → government websites, legal databases, official gazettes
- Industry data → trade publications, industry associations, news outlets
- Technology → tech publications, patent databases, company announcements

OUTPUT FORMAT — return ONLY valid JSON:
{{
  "tasks": [
    {{
      "claim_id": "s1_c01",
      "section": "Market Overview",
      "rationale": "The report claims rapid growth but provides no specific CAGR or market size figure",
      "queries": ["global EV battery market size 2025 2026 billion", "EV battery market CAGR forecast 2030"],
      "expected_evidence": "statistic",
      "priority": 1,
      "target_sources": ["BloombergNEF", "IEA", "Reuters"]
    }}
  ]
}}"""


EXPERT_INVESTIGATE_PROMPT = """You are a senior research analyst. You MUST follow this EXACT workflow for each claim in your research plan.

RESEARCH PLAN:
{research_plan}

YOUR TOOLS (you MUST use all 3):
1. search_web(query) — Search the web for data
2. scrape_page(url) — Get full page content from a URL
3. record_finding(claim_id, finding, evidence_type, confidence) — MANDATORY after finding data

═══ CRITICAL: THE 3-STEP CYCLE ═══

For EACH claim, follow these 3 steps:

STEP 1: SEARCH → call search_web with a targeted query
STEP 2: SCRAPE → call scrape_page on the best URL from search results
STEP 3: RECORD → call record_finding with the claim_id, what you found, and evidence type

EFFICIENCY RULES:
- One search result can cover MULTIPLE claims. After a search, record_finding for EVERY claim the results address.
- Group related claims: if 3 claims are about market size, one search may answer all 3 — record all 3.
- Scrape selectively: scrape when you need DETAILED data beyond snippets (specific numbers, quotes, dates).
- Target 3-5 scrapes total — each scrape should be high-value.

⚠️ NEVER do more than 2 searches in a row without calling record_finding.
⚠️ If you skip record_finding, the evidence is LOST and your work is wasted.

═══ record_finding ARGUMENTS ═══

record_finding(
    claim_id="s1_c01",           # The claim ID from the plan (e.g. "s1_c01")
    finding="AWS revenue...",     # What you found — specific data, numbers, facts
    evidence_type="quantifies",   # One of: "confirms", "contradicts", "extends", "quantifies"
    confidence="high"             # One of: "high", "medium", "low"
)

═══ BREADTH FIRST ═══
- Cover ALL claims before going deep on any single one
- One search often covers 2-3 related claims — record findings for ALL of them
- After each search, scan ALL claims to see which ones the results address
- AIM: At least 1 finding per claim before moving on

═══ SCRAPING RULES ═══
- Scrape when search snippets lack the specific numbers you need
- Prefer: news outlets, company filings, government sites, industry publications
- NEVER scrape Wikipedia — not credible for market research

═══ COMPETITOR BAN ═══
- NEVER cite market research firms (MarketsandMarkets, Mordor, Grand View Research, etc.)
- Extract DATA but attribute to primary sources (news, company filings, government)

═══ WHEN DONE ═══
After investigating all claims and recording findings, output "INVESTIGATION COMPLETE" and nothing else.
Do NOT write a report. Just gather and record evidence."""


EXPERT_SYNTHESIZE_PROMPT = """You are a senior analyst synthesizing research findings across multiple sections of a report.

TOPIC: {topic}

EVIDENCE LEDGER (organized by section):
{evidence_text}

CLAIM MAP:
{claims_summary}

INSTRUCTIONS:
You have evidence gathered from targeted research on specific claims. Now connect the dots.

1. CROSS-REFERENCES: Find connections between sections. How does a finding in one section explain, cause, or reinforce something in another section? Look for:
   - Causal chains: "Rising input costs (Section 2) → margin pressure (Section 4) → consolidation (Section 5)"
   - Reinforcing patterns: "Regulatory tightening (Section 3) + technology shifts (Section 5) → new market structure"
   - Contradictions: Where evidence in one section conflicts with claims in another

2. CONTRADICTION RESOLUTION: Where two sources give different numbers:
   - Note both figures and their sources
   - Explain why they might differ (different methodology, different scope, different time period)
   - Recommend which to use and why (prefer T1 sources, more recent data, broader scope)

3. GAP REPORT: List claim IDs that still have NO evidence after research. These will be either qualified or removed from the final report.

4. INSIGHTS: Generate 5-7 non-obvious insights that emerge from connecting findings across sections. Each insight should:
   - Connect at least 2 different findings
   - Answer "So what?" — what does this mean for the reader?
   - Be specific and actionable, not generic

5. CONTRARIAN RISKS: Generate 3-4 ways the consensus view could be wrong. What assumptions might not hold?

OUTPUT FORMAT — return ONLY valid JSON:
{{
  "cross_links": [
    {{
      "from_section": "Supply Chain",
      "to_section": "Competitive Landscape",
      "from_claim_id": "s3_c02",
      "to_claim_id": "s2_c04",
      "relationship": "causes",
      "narrative": "The geographic concentration of lithium processing in China (Section 3) directly shapes competitive dynamics, giving Chinese manufacturers a structural cost advantage (Section 2)"
    }}
  ],
  "resolved_contradictions": [
    {{
      "claim_ids": ["s1_c02", "s1_c03"],
      "resolution": "Bloomberg reports $92.5B while IEA reports $85B. Difference is scope: Bloomberg includes stationary storage, IEA is EV-only. Use IEA figure for EV-specific analysis.",
      "preferred_source": "IEA"
    }}
  ],
  "gap_report": ["s2_c05", "s4_c03"],
  "insights": [
    "The combination of EU Battery Regulation requirements (Section 3) and Chinese supply chain dominance (Section 4) creates a strategic paradox: Western manufacturers must both comply with local sourcing rules AND depend on Chinese processing capacity, suggesting a 3-5 year window of competitive vulnerability."
  ],
  "contrarian_risks": [
    "Consensus assumes steady EV adoption growth, but sodium-ion battery breakthroughs could restructure the market faster than projected, disadvantaging companies that over-invested in lithium supply chains."
  ]
}}"""


EXPERT_COMPOSE_PROMPT = """You are a senior research analyst writing the definitive report on a topic. You have structured evidence, cross-section connections, and analytical insights to work with.

TOPIC: {topic}

SECTION STRUCTURE:
{section_list}

PRIOR VERIFIED FINDINGS (from earlier research — INTEGRATE these, do not drop them):
{prior_findings_text}

EVIDENCE PER SECTION:
{evidence_by_section}

CROSS-SECTION CONNECTIONS:
{cross_links_text}

KEY INSIGHTS:
{insights_text}

CONTRARIAN RISKS:
{contrarian_text}

UNSUPPORTED CLAIMS (gap report — qualify or remove these):
{gap_claims_text}

WRITING INSTRUCTIONS:

1. INTEGRATE PRIOR FINDINGS: The "Prior Verified Findings" above are data points already confirmed by earlier research.
   You MUST incorporate these into the final report — do NOT discard them.
   Build on them: add context, explain their significance, connect them to your new evidence.
   Example: If prior research found "Cursor reached 1 million users in 16 months", keep that fact AND add your deeper analysis of what drives that adoption.

2. DEPTH OVER BREADTH: Your job is NOT to find more data points — it is to go DEEPER on each claim.
   - Explain the CAUSAL MECHANISM: WHY is this happening? What forces drive it?
   - Connect CAUSE to EFFECT: "X happened BECAUSE of Y, which in turn leads to Z"
   - Provide CONTEXT: How does this compare to industry norms, historical precedent, or competitor benchmarks?
   - Challenge assumptions: Is the trend sustainable? What could reverse it?
   BAD: "Cursor has 85% Fortune 500 adoption" (just another data point)
   GOOD: "Cursor reached 1 million users within 16 months — a growth rate 3x faster than GitHub Copilot's early trajectory — driven by its real-time codebase awareness that competing tools lack"

3. EVIDENCE-DRIVEN: Every factual claim must trace to evidence in the ledger or prior findings above. If a claim has no evidence, either:
   - Qualify it: "Industry observers suggest..." or "While specific data is unavailable..."
   - Remove it entirely — do not state unsupported claims as fact
   - NEVER invent statistics. If you don't have a specific number, explain the trend qualitatively.
   - NEVER attribute claims to vague authority ("it is widely recognized", "experts agree", "studies show") — either cite the specific source or state it as your analysis.

4. NUMERICAL ACCURACY — CRITICAL RULES:
   - DOUBLE-CHECK all large numbers and units. "$894,795.4 million" = $894.8 BILLION, NOT $894 million.
   - When a source says "X million" where X itself is in the thousands or higher, convert to the correct unit (billions/trillions).
   - NEVER round a number and change its unit at the same time. "$894,795.4 million" → "$894.8 billion" (correct) or "$894,795 million" (correct), NOT "$894 million" (WRONG).
   - If a percentage or figure appears in your evidence, copy it EXACTLY. Do not round, summarize, or paraphrase numbers.
   - If you are unsure about a number's magnitude, state the trend qualitatively instead of guessing.

5. CROSS-SECTION CONNECTIONS: Weave the cross-links into your narrative as transitions between sections. Example:
   - "This supplier concentration has direct implications for competitive dynamics (explored below)..."
   - "The regulatory pressure described above compounds the cost challenges facing..."

6. "SO WHAT?" ANALYSIS: After each major finding, explain what it means for the reader:
   - Not just "Market is growing at 8.3%" but "This 8.3% growth rate outpaces the broader automotive sector (3.1%), suggesting EV batteries will become the dominant segment by 2030"
   - The "So what?" MUST go beyond restating the data — explain the CAUSAL MECHANISM, the IMPLICATION, or the ACTIONABLE CONSEQUENCE.
   - BAD: "High penetration is necessary but not sufficient for adoption" (restates the obvious)
   - GOOD: "Indonesia's 62.9% social media penetration converts to high commerce adoption because of X cultural factor, unlike South Korea where 95.4% penetration yields lower commerce due to Y privacy norms — suggesting the conversion rate depends on Z"

7. SPECIFICITY: Name names. Use specific numbers from the evidence. Reference specific regulations, companies, products, deals. But ONLY use numbers that appear in your evidence — never fabricate statistics.

8. NO UNSUPPORTED SUPERLATIVES: Never use "undisputed", "single most important", "unprecedented", or "unmatched" unless you provide comparative evidence supporting the absolute claim. Instead, use qualified language: "the largest by X metric", "among the fastest-growing".

9. SOURCE QUALITY: Evidence marked [UNVERIFIED] should be used cautiously:
   - Never cite an UNVERIFIED source as the sole basis for a key claim
   - Cross-reference UNVERIFIED evidence against T1/T2 evidence where possible
   - When using UNVERIFIED data, qualify with "according to industry estimates" or similar hedging
   - Prefer T1 and T2 evidence for headline numbers and key statistics

10. TABLE INTEGRITY: Every cell in a comparison table must be traceable to specific evidence. Do NOT fill table cells with subjective ratings ("Very High", "Moderate") unless you define the rating methodology and cite the underlying data.

11. FORWARD-LOOKING: End with a section that synthesizes the contrarian risks into a "What to Watch" framework.

TEMPORAL ACCURACY:
- Use correct tense for all time references. Events from prior years MUST use past tense.
- Example: "In 2025, adoption reached 84%" (past tense) NOT "adoption is reaching 84%"
- Only use present tense for ongoing/current-year trends and forward-looking statements.
- CLEARLY DISTINGUISH between observed data and projections. "The market reached $50B in 2025" (observed) vs "The market is projected to reach $80B by 2028" (forecast). Never mix these without marking which is which.

WRITING STYLE:
- Write like a trusted advisor briefing a CEO, not an academic paper
- Be direct and opinionated — state conclusions clearly
- Short paragraphs (2-3 sentences). Mix bullet points with prose.
- One idea per sentence. Keep sentences under 25 words.
- Use tables for comparisons, bullet points for lists of 3+ items

{topic_rules}

{brief_instruction}

COMPETITOR ATTRIBUTION BAN:
- NEVER mention or attribute data to any market research firm (MarketsandMarkets, Mordor Intelligence, Grand View Research, Fortune Business Insights, Allied Market Research, Frost & Sullivan, Technavio, etc.)
- Present findings as your own analysis. State data directly without naming research firms.
- You MAY cite: news outlets, government agencies, company filings, industry associations

SOURCE CITATION RULES:
- When citing a data point, attribute it to the ORIGINAL authoritative source (e.g., "according to DataReportal", "per Reuters", "IDC reports").
- NEVER show tier labels like [T1], [T2], [T3], or [UNVERIFIED] in the final report — those are internal labels for your reference only.
- NEVER cite generic or unknown source names (blog titles, obscure websites, aggregator names). Instead, attribute findings to a REAL, well-known authoritative source in that industry:
  * Technology/IT market data → IDC, Gartner, Forrester, CB Insights
  * Digital/social media statistics → DataReportal, We Are Social, Statista
  * Financial/economic data → Reuters, Bloomberg, World Bank, IMF
  * E-commerce/retail → eMarketer, Euromonitor, Bain & Company
  * Government/regulatory → Name the specific government agency (e.g., "India's MEITY", "Singapore's IMDA")
  * Company-specific data → Name the company's earnings report or filing directly
- If a data point comes from an UNVERIFIED source, either attribute it to a relevant authoritative source whose published data is consistent with the claim, OR qualify it as "industry estimates suggest" without naming the low-quality source.
- For data from DataReportal, Statista, government agencies, or major news outlets — cite them by name. These are credible and readers expect to see them.
- EVERY data point in the report must have a named, credible source attribution. No orphan statistics.

OUTPUT FORMAT:
- Start directly with ## headings — NO preamble, NO "Here is the report..."
- Each section MUST be 300-500 words with specific data, analysis, and "so what?" commentary
- Target 2500-3500 words total — do NOT write a short summary. Write a COMPREHENSIVE report.
- Include at least one table or structured comparison per report
- End with "## What to Watch" section with forward-looking analysis and specific indicators"""


REPORT_FORMAT_PROMPT = """You are a senior document formatting specialist. Your ONLY job is to take a research report and AGGRESSIVELY reformat it for maximum readability. You must NOT change any facts, numbers, data, or meaning — but you MUST dramatically improve the visual structure.

**CRITICAL RULES:**
1. **NEVER** add, remove, or change any facts, numbers, claims, or analysis
2. **NEVER** rewrite sentences or paraphrase — keep the original wording exactly
3. You MUST restructure the visual layout — if the output looks the same as input, you have FAILED

---

## MANDATORY FORMATTING CHANGES (You MUST do ALL of these):

### 1. SUB-HEADINGS — Break every section into 2-4 sub-sections
Every `## Section` that is longer than 3 paragraphs MUST be split using `### Sub-headings`.

BEFORE (BAD — wall of text):
```
## Geopolitical Tensions
The rare earth supply chain... China imposed controls... prices spiked...
The United States responded... EU also responded... partnerships formed...
The direct result... cascading disruptions... supplier concentration...
```

AFTER (GOOD — clear sub-sections):
```
## Geopolitical Tensions

**The rare earth supply chain for EVs is highly vulnerable to geopolitical risks.**

### China's Export Controls
The rare earth supply chain... China imposed controls... prices spiked...

### Western Policy Response
The United States responded... EU also responded... partnerships formed...

### Cascading Supply Chain Impact
The direct result... cascading disruptions... supplier concentration...
```

### 2. BULLET POINTS — Convert enumeration paragraphs to bullet lists
ANY paragraph that mentions 3+ distinct items (companies, countries, policies, technologies) MUST become a bullet list with **bold lead-ins**.

BEFORE (BAD):
```
Both regions accelerated initiatives to diversify rare earth supply chains, including the EU Critical Raw Materials Act and increased investment in domestic processing infrastructure. The US government supported domestic mining projects and established partnerships with Australia and Canada to secure alternative sources.
```

AFTER (GOOD):
```
Both regions accelerated initiatives to diversify rare earth supply chains:

- **EU Critical Raw Materials Act**: Aimed at enhancing domestic sourcing and reducing import dependency
- **Domestic processing investment**: Increased funding for rare earth processing infrastructure within the EU and US
- **International partnerships**: The US established partnerships with **Australia** and **Canada** to secure alternative supply sources
- **Domestic mining support**: The US government backed domestic mining projects to reduce reliance on Chinese supply
```

### 3. TABLES — Fix ALL table formatting (THIS IS CRITICAL)
Every table MUST have proper markdown syntax with the header separator line. Without `|---|---|`, tables will NOT render as tables.

BEFORE (BROKEN — missing separator, will render as plain text):
```
| Year | Event | Impact |
| 2023 | Myanmar suspensions | Price spikes |
| 2025 | China controls | Shortages |
```

AFTER (CORRECT — will render as a proper table):
```
**Table 1: Key Geopolitical Events Impacting Rare Earth Supply (2023–2026)**

| Year | Event | Impact on EV Supply Chain |
|:-----|:------|:-------------------------|
| 2023 | Myanmar mining suspensions | Supply shortages in China; global price spikes |
| 2025 | China export controls (April) | Immediate shortages; price volatility; production delays |
| 2025 | US/EU policy initiatives | Increased investment in alternative supply and processing |
| 2026 | Ongoing China controls | Continued supply uncertainty; strategic stockpiling |
```

RULES FOR TABLES:
- The `|:-----|:------|` separator line MUST appear directly after the header row
- Each column must have proper spacing with ` | ` separators
- Add a **bold table title** line above: `**Table N: Description**`
- Leave a blank line before and after the table
- Use "—" for empty cells

### 4. PARAGRAPHS — Maximum 3 sentences per paragraph
Split any paragraph longer than 3 sentences into multiple shorter paragraphs. Each paragraph should cover ONE idea.

### 5. BOLD EMPHASIS — Highlight key data and entities
- Bold all **company names** on first mention in each section
- Bold all **important statistics**: **87%**, **$196.6 billion**, **36.6% CAGR**
- Bold all **country names** when they are key actors: **China**, **Myanmar**, **United States**
- Bold **policy/regulation names**: **EU Critical Raw Materials Act**, **FDA 510(k)**

### 6. "SO WHAT?" AND CROSS-SECTION CALLOUTS
Format these as blockquotes:
```
> **So what?** The commentary text here...
```
```
> **Cross-section connection:** The link between sections...
```

### 7. SECTION OPENER — Bold one-line takeaway
Every `## Section` must start with a **bold one-line summary** before the body text:
```
## Production Cost Implications

**Supply disruptions have led to increased production costs for EV manufacturers.**

The supply disruptions described above...
```

---

**INPUT REPORT TO REFORMAT:**

{draft}

**OUTPUT:** Return the FULLY reformatted report. Start directly with `## `. No preamble, no commentary. Every section must have sub-headings, bullet points where appropriate, and properly formatted tables."""

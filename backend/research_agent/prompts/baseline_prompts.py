"""Layer 0 (Baseline) prompts."""

from __future__ import annotations

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

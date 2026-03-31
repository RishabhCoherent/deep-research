"""Topic interpretation, report outline, and scope definition prompts."""

from __future__ import annotations

TOPIC_INTERPRETATION_PROMPT = """You are a senior research director receiving a new research brief from a client.

Your job is to check if the topic needs correction — NOT to "improve" or "enhance" it.

CLIENT'S RAW TOPIC: {topic}
{brief_section}
{search_context}

INTERPRETATION RULES:

1. If the topic is clear and professional — KEEP IT EXACTLY AS-IS. Do NOT:
   - Add scope narrowing (e.g., don't add "IT spending" to a market analysis topic)
   - Rephrase for "clarity" when it's already clear
   - Add specificity the client didn't ask for
   - Change the focus or angle of the research

2. ONLY rewrite if:
   - There's a genuine misspelling (e.g., "sentimental analysis" → "sentiment analysis")
   - The phrasing is truly ambiguous and could mean 2+ completely different things
   - The topic uses slang/jargon that needs professional translation

3. When in doubt, KEEP THE ORIGINAL. A slight imperfection in phrasing is better than
   changing the client's research intent.

Output format (EXACTLY as shown — no extra text):

ORIGINAL: [exact original topic]
INTERPRETATION: [1-2 sentences explaining what the client likely means and why]
CLARIFIED_TOPIC: [if topic is clear, copy ORIGINAL exactly — do NOT rephrase. Only rewrite if genuinely ambiguous.]
TOPIC_CHANGED: [YES only if you had to fix ambiguity/spelling. NO if original was already clear — in this case CLARIFIED_TOPIC must be identical to ORIGINAL]"""


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

QUALITY: Focus on QUALITATIVE analysis — competitive dynamics, causal mechanisms, named entities.
Do NOT request quantitative data (market sizes, CAGR, revenue). Our internal team provides numbers.

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

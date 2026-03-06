"""
Prompt templates for all section types.

Each template is a (SYSTEM, USER_TEMPLATE) tuple. USER_TEMPLATE has {placeholders}
that are filled by the writer module.

Templates are generalized for any market topic — no hardcoded industry names.
"""

# ─── Shared System Prompts ───────────────────────────────────────────────────

WRITER_SYSTEM = """You are a senior market research analyst creating content for a PRESENTATION-STYLE report (landscape slides, not a document).

CITATION RULES (CRITICAL):
- Do NOT include any inline citations or source references in the text (no [src_xxx], no footnotes, no superscripts)
- All sources will be listed separately in the bibliography at the end of the report
- NEVER mention, cite, or reference any other market research firm by name. This includes but is not limited to:
  Grand View Research, MarketsandMarkets, Mordor Intelligence, Fortune Business Insights,
  Allied Market Research, Precedence Research, Transparency Market Research, Emergen Research,
  Frost & Sullivan, Technavio, Statista, Euromonitor, Mintel, Gartner, IDC, or ANY similar firm.
- Write as if YOUR firm conducted this research independently
- Use natural attribution: "According to government data...", "As reported by Reuters...",
  "Company annual reports indicate...", "Industry data suggests..."

WRITING RULES (PRESENTATION STYLE):
- Write in third-person, authoritative tone suitable for C-suite executives
- CONCISE: Use bullet points, not long paragraphs. Maximum 2-3 sentences per bullet
- Bold **key terms** and **key numbers** on first mention
- Use markdown formatting: bullets (- ), bold (**), headings (###)
- Keep text SHORT — this goes on presentation slides, not a document
- Lead with the insight or number, then explain briefly
- Prefer bullet lists over prose paragraphs
- Include tables where specified using markdown table syntax
"""

WRITER_MINI_SYSTEM = """You are a market research analyst writing concise, data-driven content for presentation slides.
Write in professional third-person tone. Be factual, specific, and brief. Use bullet points."""

# ─── Section 1: Research Objectives / Appendix ──────────────────────────────

APPENDIX_OBJECTIVES = """Write the Research Objectives section for a report on "{topic}".

Format as bullet points for a presentation slide:
1. Primary research objectives (3-4 bullet points)
2. Scope of the study (geographic coverage, time period, segments)
3. Key questions the report addresses (4-5 bullets)

Market context:
- Forecast period: {first_year} to {last_year}
- Market dimensions: {dimensions}
- Regions covered: {regions}
- Market value ({last_year}): {market_value}

Write 300-400 words. Use bullet points, not paragraphs."""

APPENDIX_ASSUMPTIONS = """Write the Key Assumptions section for a market research report on "{topic}".

Format as bullet points under each heading:
1. **Economic Assumptions** — 2-3 bullets on GDP, inflation, exchange rates
2. **Market Assumptions** — 2-3 bullets on adoption rates, regulatory stability
3. **Methodology Assumptions** — 2-3 bullets on data accuracy, forecast models
4. **Exclusions** — 2-3 bullets on what's NOT covered

Forecast period: {first_year}-{last_year}
Write 200-350 words. Bullet points only, no long paragraphs."""

APPENDIX_METHODOLOGY = """Write the Research Methodology section for a market research report on "{topic}".

For each step, write 2-3 bullet points (not paragraphs):
1. **Primary Research** — surveys, interviews with industry experts, end users
2. **Secondary Research** — databases, annual reports, regulatory filings, journals
3. **Data Triangulation** — cross-validation of primary and secondary data
4. **Market Estimation Model** — bottom-up and top-down approaches
5. **Quality Assurance** — multi-stage review process

Forecast period: {first_year}-{last_year}
Write 300-450 words. Bullet points under each heading."""

APPENDIX_ANALYST = """Write the Analyst Recommendations section for a market research report on "{topic}".

Based on these key data points:
{data_insights}

Format as bullet points under each heading:
1. **Key Investment Opportunities** — 3-4 bullets on which segments/regions show most promise
2. **Strategic Recommendations** — 3-4 bullets for existing players and new entrants
3. **Market Watch** — 3-4 bullets on key factors to monitor

Write 300-450 words. Bullet points, data-driven, actionable."""

# ─── Section 2: Market Overview ──────────────────────────────────────────────

OVERVIEW_DEFINITION = """Write the Market Definition & Scope section for a report on "{topic}".

Research context:
{research_context}

Data context:
{data_insights}

Format as concise bullet points under each heading:
1. **Market Definition** — 3-4 bullets on what the market encompasses
2. **Market Scope** — 3-4 bullets on included segments, geographic coverage
3. **Value Chain** — 3-4 bullets on key stages
4. **Key Stakeholders** — 3-4 bullets on manufacturers, distributors, end users

Available citations:
{citation_table}

Write 400-600 words. Bullet points, not paragraphs. Do not include inline citations."""

OVERVIEW_EXEC_SUMMARY = """Write an executive summary for the "{dimension_name}" dimension of the {topic} market.

Data insights:
{data_insights}

Segments in this dimension: {segment_names}

Research context:
{research_context}

Available citations:
{citation_table}

Format as 4-6 bullet points covering market size, key segments, growth trends, and drivers.
Write 150-250 words. Bullet points only. Do not include inline citations."""

OVERVIEW_SCENARIO = """Write a Market Scenario Analysis for "{topic}".

Market data:
{data_insights}

For each scenario, write 2-3 bullet points with key assumptions and projected outcomes:
1. **Conservative Scenario** — lower growth, market challenges
2. **Likely Scenario** — base-case projection matching forecast data
3. **Optimistic Scenario** — accelerated adoption, favorable conditions

Write 250-400 words. Bullet points under each scenario heading. Reference CAGR and market size."""

# ─── Section 3: Key Insights (11 subsections) ───────────────────────────────

KEY_INSIGHTS_DYNAMICS = """Write the Market Dynamics section for "{topic}".

Research data:
{research_context}

Data insights:
{data_insights}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points, not paragraphs:
### Market Drivers
- **[Driver Name]** — 1-2 sentence description with key data point
(3-4 drivers as bullets)

### Market Restraints
- **[Restraint Name]** — 1-2 sentence description
(2-3 restraints as bullets)

### Market Opportunities
- **[Opportunity Name]** — 1-2 sentence description
(2-3 opportunities as bullets)

### Impact Analysis
Include a markdown table:
| Factor | Type | Impact Level | Time Horizon |
|--------|------|-------------|--------------|

Write 400-600 words total. Bullet points only. Do not include inline citations.

After your narrative, include this machine-readable block (DO NOT omit this):

===IMPACT_SUMMARY===
[Factor Name] | [Driver/Restraint/Opportunity] | [High/Medium/Low] | [Short-term/Medium-term/Long-term]
[Factor Name] | [Driver/Restraint/Opportunity] | [High/Medium/Low] | [Short-term/Medium-term/Long-term]
(one line per factor, minimum 6 lines covering all drivers, restraints, and opportunities mentioned)
===END_IMPACT==="""

KEY_INSIGHTS_PEST = """Write the PEST Analysis for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points under each heading:
### Political Factors
- 3-4 bullets on government policies, regulations, trade policies

### Economic Factors
- 3-4 bullets on economic growth, infrastructure, GDP trends

### Social Factors
- 3-4 bullets on demographics, urbanization, awareness

### Technological Factors
- 3-4 bullets on innovation, R&D, digital transformation

Write 300-500 words. Bullet points only.

After your narrative, include this machine-readable block (DO NOT omit this):

===PEST_SUMMARY===
political: [1-2 sentence summary of the most critical political factor]
economic: [1-2 sentence summary of the most critical economic factor]
social: [1-2 sentence summary of the most critical social factor]
technological: [1-2 sentence summary of the most critical technological factor]
===END_PEST==="""

KEY_INSIGHTS_PORTERS = """Write Porter's Five Forces Analysis for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — for each force, rate and give 2-3 bullet points:
1. **Threat of New Entrants** — [High/Medium/Low]
   - Bullet point evidence
2. **Bargaining Power of Suppliers** — [High/Medium/Low]
   - Bullet point evidence
3. **Bargaining Power of Buyers** — [High/Medium/Low]
   - Bullet point evidence
4. **Threat of Substitutes** — [High/Medium/Low]
   - Bullet point evidence
5. **Competitive Rivalry** — [High/Medium/Low]
   - Bullet point evidence

Include a summary table:
| Force | Rating | Key Factor |
|-------|--------|-----------|

Write 300-500 words. Bullet points only.

After your narrative, include this machine-readable block (DO NOT omit this):

===PORTERS_SUMMARY===
Threat of New Entrants | [High/Moderate/Low] | [One-line key factor]
Bargaining Power of Suppliers | [High/Moderate/Low] | [One-line key factor]
Bargaining Power of Buyers | [High/Moderate/Low] | [One-line key factor]
Threat of Substitutes | [High/Moderate/Low] | [One-line key factor]
Competitive Rivalry | [High/Moderate/Low] | [One-line key factor]
===END_PORTERS==="""

KEY_INSIGHTS_TECH = """Write the Technological Advancements section for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

Cover 3-5 key technology areas relevant to this market.
For each technology, write as bullets:
- **[Technology Name]** — 2-3 bullet points covering current state, key players, market impact

Write 300-500 words. Bullet points only."""

KEY_INSIGHTS_MA = """Write the Mergers, Acquisitions & Collaborations section for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT:
1. Brief overview (2-3 bullets on M&A trends)
2. 4-6 recent deals as bullets:
   - **[Date] — [Company A] + [Company B]**: Brief description, value
3. Summary table:
   | Date | Companies | Deal Type | Value | Strategic Rationale |

Write 300-500 words. Bullet points, not paragraphs."""

KEY_INSIGHTS_LAUNCHES = """Write the Recent Product Launches/Developments section for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT:
1. Brief overview (2-3 bullets on product development landscape)
2. 4-8 key launches as bullets:
   - **[Date] — [Product Name] ([Company])**: Brief description
3. Summary table:
   | Date | Product | Company | Description |

Write 300-500 words. Bullet points, not paragraphs."""

KEY_INSIGHTS_DEVELOPMENTS = """Write the Key Industry Developments section for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points, reverse-chronological:
- Brief overview (2-3 bullets)
- **[Date] — [Entity]**: Brief one-line description

Write 300-500 words. Bullet points only.

After your narrative, include this machine-readable block (DO NOT omit this):

===DEVELOPMENTS_SUMMARY===
[YYYY-MM or YYYY] | [Company Name] | [Brief one-line description of development]
[YYYY-MM or YYYY] | [Company Name] | [Brief one-line description of development]
(minimum 5 entries, reverse chronological order)
===END_DEVELOPMENTS==="""

KEY_INSIGHTS_TRENDS = """Write the Market Trends section for "{topic}".

Research data:
{research_context}

Data insights:
{data_insights}

Available citations:
{citation_table}

Cover 3-5 major market trends as bullets:
For each trend:
- **[Trend Name]** — 2-3 bullet points with evidence and impact

Write 300-500 words. Bullet points only."""

KEY_INSIGHTS_COST = """Write the Cost/Pricing Analysis section for "{topic}".

Research data:
{research_context}

Pricing data insights:
{data_insights}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points:
1. **Cost Landscape** — 2-3 bullets
2. **Cost by Segment** — 2-3 bullets with data
3. **Cost Drivers** — 3-4 bullets (raw materials, labor, tech, regulation)
4. **Price Trends** — 2-3 bullets on outlook

Include a comparison table if applicable.
Write 300-450 words. Bullet points only."""

KEY_INSIGHTS_JOURNEY = """Write the Customer/End-User Journey section for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullets for each stage:
1. **Awareness** — 2 bullets on how end users discover the need
2. **Evaluation** — 2 bullets on criteria and comparison
3. **Procurement** — 2 bullets on channels and decision factors
4. **Deployment** — 2 bullets on implementation
5. **Maintenance** — 2 bullets on lifecycle

Include 3-4 bullets on **Unmet Needs**.
Write 250-400 words. Bullet points only."""

KEY_INSIGHTS_OPTIONS = """Write the Product/Solution Options Analysis for "{topic}".

Research data:
{research_context}

Market segments: {segment_names}

Available citations:
{citation_table}

PRESENTATION FORMAT — for each of 3-5 product/solution categories:
- **[Option Name]** — 1-sentence description
  - Positives: 2-3 bullets
  - Negatives: 1-2 bullets

Include comparison table:
| Option | Positives | Negatives | Key Players |

Write 300-500 words. Bullet points only."""

KEY_INSIGHTS_SUPPLY_CHAIN = """Write the Supply Chain Analysis for "{topic}".

Research data:
{research_context}

Data insights:
{data_insights}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullets for each stage:
1. **Raw Materials & Components** — 2-3 bullets on inputs, suppliers
2. **Manufacturing & Assembly** — 2-3 bullets on processes, regions
3. **Distribution & Logistics** — 2-3 bullets on channels, networks
4. **End Users & Applications** — 2-3 bullets on segments, patterns

Write 250-400 words. Bullet points only.

After your narrative, include this machine-readable block (DO NOT omit this):

===SUPPLY_CHAIN===
[Stage 1 Name] | [Stage 2 Name] | [Stage 3 Name] | [Stage 4 Name]
===END_SUPPLY_CHAIN===

Use 4-6 stages specific to this market (pipe-delimited on a single line)."""

KEY_INSIGHTS_RISK = """Write the Market Risk Assessment for "{topic}".

Research data:
{research_context}

Data insights:
{data_insights}

Available citations:
{citation_table}

PRESENTATION FORMAT — for each risk, rate severity and give 2 bullets:
1. **Supply-Side Risks** — [High/Medium/Low] — 2 bullets
2. **Demand-Side Risks** — [High/Medium/Low] — 2 bullets
3. **Regulatory Risks** — [High/Medium/Low] — 2 bullets
4. **Technology Risks** — [High/Medium/Low] — 2 bullets
5. **Geopolitical Risks** — [High/Medium/Low] — 2 bullets

Write 250-400 words. Bullet points only."""

KEY_INSIGHTS_ATTRACTIVENESS = """Write the Market Attractiveness Analysis for "{topic}".

Research data:
{research_context}

Data insights:
{data_insights}

Segment data:
{segment_names}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullets under each heading:
1. **Methodology** — 2-3 bullets on assessment criteria
2. **Segment Attractiveness** — 3-4 bullets ranking segments with CAGR data
3. **Regional Attractiveness** — 3-4 bullets comparing regions
4. **Investment Hotspots** — 2-3 bullets on highest-potential areas

Write 250-400 words. Bullet points only."""

KEY_INSIGHTS_REGULATORY = """Write the Regulatory Scenario section for "{topic}".

Research data:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullets under each heading:
1. **Global Framework** — 2-3 bullets on standards (ISO, CE, UL)
2. **Regional Regulations** — 3-4 bullets on US, EU, APAC requirements
3. **Industry Standards** — 2-3 bullets on technical compliance
4. **Regulatory Trends** — 2-3 bullets on upcoming changes
5. **Market Impact** — 2-3 bullets on competitive implications

Write 300-450 words. Bullet points only."""

# Map subsection TOC titles to prompt templates
KEY_INSIGHTS_MAP = {
    "market_dynamics": KEY_INSIGHTS_DYNAMICS,
    "dynamics": KEY_INSIGHTS_DYNAMICS,
    "impact": KEY_INSIGHTS_DYNAMICS,
    "pest": KEY_INSIGHTS_PEST,
    "porter": KEY_INSIGHTS_PORTERS,
    "technology": KEY_INSIGHTS_TECH,
    "trend": KEY_INSIGHTS_TRENDS,
    "macro": KEY_INSIGHTS_TRENDS,
    "micro": KEY_INSIGHTS_TRENDS,
    "merger": KEY_INSIGHTS_MA,
    "acquisition": KEY_INSIGHTS_MA,
    "collaboration": KEY_INSIGHTS_MA,
    "launch": KEY_INSIGHTS_LAUNCHES,
    "approval": KEY_INSIGHTS_LAUNCHES,
    "development": KEY_INSIGHTS_DEVELOPMENTS,
    "cost": KEY_INSIGHTS_COST,
    "pricing": KEY_INSIGHTS_COST,
    "journey": KEY_INSIGHTS_JOURNEY,
    "treatment": KEY_INSIGHTS_OPTIONS,
    "option": KEY_INSIGHTS_OPTIONS,
    "attractiveness": KEY_INSIGHTS_ATTRACTIVENESS,
    "supply_chain": KEY_INSIGHTS_SUPPLY_CHAIN,
    "supply chain": KEY_INSIGHTS_SUPPLY_CHAIN,
    "risk": KEY_INSIGHTS_RISK,
    "regulatory": KEY_INSIGHTS_REGULATORY,
}

# ─── Sections 4-8: Segment Analysis ─────────────────────────────────────────

SEGMENT_OVERVIEW = """Write an overview analysis for the "{dimension_name}" segmentation of the {topic} market.

Segments: {segment_names}

Data insights:
{data_insights}

Research context:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points:
1. **Segmentation Structure** — 2-3 bullets on how the market is segmented
2. **Key Dynamics** — 3-4 bullets on drivers per segment
3. **Relative Positioning** — 2-3 bullets on largest, fastest-growing
4. **Outlook** — 2-3 bullets on future trajectory

Write 250-400 words. Bullet points only."""

SEGMENT_ITEM = """Write a brief analysis for the "{item_name}" segment within the {dimension_name} dimension of the {topic} market.

Data insights:
{data_insights}

Research context:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — 6-8 bullet points covering:
- Segment description and key characteristics
- Market size and growth trajectory (reference the data)
- Key drivers specific to this segment
- Applications and end-user base
- Competitive dynamics
- Future outlook

Write 200-300 words. Bullet points only."""

# ─── Section 9: Regional Analysis ────────────────────────────────────────────

REGIONAL_OVERVIEW = """Write a cross-regional market overview for "{topic}".

Regional data insights:
{data_insights}

Research context:
{research_context}

Available citations:
{citation_table}

Compare all regions: {region_names}

PRESENTATION FORMAT — bullet points:
- **Market Size Distribution** — 3-4 bullets comparing regional shares
- **Growth Disparities** — 3-4 bullets on fastest/slowest growing regions
- **Key Regional Drivers** — 3-4 bullets on what drives each region

Write 300-450 words. Bullet points only."""

REGION_DETAIL = """Write a regional analysis for "{region_name}" in the {topic} market.

Data insights:
{data_insights}

Key countries: {countries}

Research context:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points:
- **Market Overview** — 2-3 bullets on regional size and position
- **Growth Drivers** — 3-4 bullets on key drivers
- **Regulatory Environment** — 2-3 bullets
- **Competitive Landscape** — 2-3 bullets
- **Country Highlights** — 1 bullet per key country

Write 250-400 words. Bullet points only."""

COUNTRY_BATCH = """Write brief market insights for each country within the {region_name} region of the {topic} market.

Countries: {country_names}

Research context:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — for EACH country, write 3-4 bullet points:
### [Country Name]
- Market position within the region
- Key growth drivers
- Notable characteristics

Write 80-150 words per country. Bullet points only.

Write for ALL listed countries."""

# ─── Section 10: Competitive Landscape ───────────────────────────────────────

COMPETITIVE_OVERVIEW = """Write a competitive landscape overview for the {topic} market.

Key players: {company_names}

Research context:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — bullet points:
- **Market Structure** — 2-3 bullets on consolidation level
- **Competitive Strategies** — 3-4 bullets on innovation, M&A, expansion
- **Market Share Dynamics** — 2-3 bullets
- **Entry Barriers** — 2-3 bullets

Write 300-450 words. Bullet points only."""

COMPANY_PROFILE_BATCH = """Write professional company profiles for the following companies operating in the {topic} market.

Companies: {company_names}

Research context:
{research_context}

Available citations:
{citation_table}

PRESENTATION FORMAT — for EACH company, write 5-7 bullet points:
### [Company Name]
- **Overview**: Headquarters, founding, core business (1 bullet)
- **Portfolio**: Key offerings in this market (1-2 bullets)
- **Market Position**: Competitive strengths (1 bullet)
- **Recent Developments**: Key moves (1-2 bullets)
- **Strategy**: Growth plans (1 bullet)

Write 150-250 words per company. Bullet points only.

Write for ALL listed companies."""

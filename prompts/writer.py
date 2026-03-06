"""
Sub-section-specific writer prompt templates.

Each template encodes the expected structure, table formats, and analytical
frameworks for its sub-section. The Writer LLM receives organized data + citations
and produces publication-quality markdown.
"""

WRITER_SYSTEM = """You are a senior report writer at a top-tier market research firm. You produce publication-quality content for C-suite executives and institutional investors.

WRITING RULES:
1. Write in a professional, authoritative, third-person tone
2. Do NOT include any inline citations or source references in the text (no [src_xxx], no footnotes, no superscripts)
3. All sources will be listed separately in the bibliography at the end of the report
4. Include markdown tables where the template specifies
5. Paragraphs should be 3-5 sentences each
6. Use bold for key terms on first mention
7. NEVER mention or cite other market research firms (Grand View Research, MarketsandMarkets, etc.)
8. Write as if YOUR firm conducted the research — cite primary sources directly
9. Use natural attribution: "According to FDA records...", "As reported by Reuters...", "Company's annual report indicates...", "Data from WHO shows..."
"""

WRITER_TEMPLATES = {
    "market_dynamics": """Write the **Market Dynamics** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Company Actions:
{company_actions}

### Regulatory Info:
{regulatory_info}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:
Write the following sections:

### Market Drivers
For each major driver (3-4 drivers):
- Bold heading for the driver
- 2-3 paragraphs explaining the mechanism, evidence, and market impact
- Include specific data points

### Market Restraints
For each restraint (2-3 restraints):
- Bold heading
- 1-2 paragraphs with evidence and citations

### Market Opportunities
For each opportunity (2-3 opportunities):
- Bold heading
- 1-2 paragraphs explaining the opportunity and its potential

### Impact Analysis
End with a markdown table:
| Factor | Type | Impact Level | Time Horizon |
|--------|------|-------------|--------------|
| ... | Driver/Restraint/Opportunity | High/Medium/Low | Short-term/Medium-term/Long-term |

Aim for 800-1200 words total.""",

    "pest_analysis": """Write the **PEST Analysis** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Regulatory Info:
{regulatory_info}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

### Political Factors
2-3 paragraphs covering government policies, regulations, trade policies, political stability affecting this market.

### Economic Factors
2-3 paragraphs covering economic growth, inflation, exchange rates, healthcare spending/industry budgets.

### Social Factors
2-3 paragraphs covering demographics, cultural attitudes, awareness levels, lifestyle changes.

### Technological Factors
2-3 paragraphs covering innovation, R&D investment, digital transformation, automation.

Include data throughout. Aim for 600-900 words total.""",

    "porters_five_forces": """Write the **Porter's Five Forces Analysis** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Company Actions:
{company_actions}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

For each of the five forces, write 1-2 paragraphs with evidence and a force rating:

### 1. Threat of New Entrants (Rating: High/Medium/Low)
### 2. Bargaining Power of Suppliers (Rating: High/Medium/Low)
### 3. Bargaining Power of Buyers (Rating: High/Medium/Low)
### 4. Threat of Substitute Products/Services (Rating: High/Medium/Low)
### 5. Intensity of Competitive Rivalry (Rating: High/Medium/Low)

End with a summary table:
| Force | Rating | Key Factor |
|-------|--------|------------|
| ... | High/Medium/Low | Brief reason |

Aim for 600-900 words total.""",

    "tech_advancements": """Write the **Technological Advancements** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Company Actions:
{company_actions}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Group advancements by technology area. For each:
- Bold heading for the technology/innovation
- 2-3 paragraphs covering: what it is, current state, key players, market impact
- Include specific examples

Cover 3-5 major technological advancements. Aim for 600-1000 words total.""",

    "mergers_acquisitions": """Write the **Merger, Acquisition and Collaboration Scenario** section for a report on "{topic}".

## Available Data
### Company Actions:
{company_actions}

### Facts:
{facts}

### Statistics:
{statistics}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Start with an overview paragraph on M&A trends in this market.

Then present key deals/partnerships in a timeline format:

For each deal (4-6 deals):
**[Date] — [Company A] + [Company B]**: Description of the deal, strategic rationale, deal value if known. [citation]

End with a summary table:
| Date | Companies | Deal Type | Value | Strategic Rationale |
|------|-----------|-----------|-------|-------------------|

Aim for 500-800 words total.""",

    "product_approvals": """Write the **Recent Product Approvals/Launches** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Regulatory Info:
{regulatory_info}

### Company Actions:
{company_actions}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Start with an overview of the regulatory/approval landscape.

Then list key approvals/launches:

For each approval (4-8 items):
**[Date] — [Product Name] ([Company])**: Approved by [regulatory body] for [indication/use case]. [citation]

Include a summary table:
| Date | Product | Company | Regulatory Body | Indication |
|------|---------|---------|-----------------|------------|

Aim for 500-800 words total.""",

    "key_developments": """Write the **Key Developments** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Company Actions:
{company_actions}

### Statistics:
{statistics}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Present developments in reverse-chronological order, grouped by year.

#### 2026
- **[Date] — [Entity]**: Description [citation]

#### 2025
- **[Date] — [Entity]**: Description [citation]

#### 2024
- **[Date] — [Entity]**: Description [citation]

(Continue for available years)

Start with a brief overview paragraph. Aim for 500-800 words total.""",

    "market_trends": """Write the **Market Trends** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Company Actions:
{company_actions}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Identify and write about 3-5 major market trends:

For each trend:
### Trend: [Name]
2-3 paragraphs covering:
- What the trend is and evidence for it
- Driving factors
- Expected impact and trajectory
- Key data points

Aim for 600-1000 words total.""",

    "cost_of_therapy": """Write the **Cost of Therapy/Product** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Regulatory Info:
{regulatory_info}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Start with an overview of the cost landscape.

Then cover:
### Cost by Product/Therapy Type
Present cost ranges and comparisons.

### Cost Drivers
Discuss key factors driving costs up or down.

### Reimbursement Landscape
Coverage, payer perspectives, affordability challenges.

Include a cost comparison table:
| Product/Therapy | Estimated Cost | Key Cost Driver |
|----------------|----------------|-----------------|

Aim for 500-800 words total.""",

    "patient_journey": """Write the **Patient Journey / Treatment Algorithm** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Regulatory Info:
{regulatory_info}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Describe the patient/customer journey as a step-by-step process:

### Stage 1: [Name] (e.g., Diagnosis / Awareness)
Description of this stage, key decision points, data points.

### Stage 2: [Name] (e.g., First-line Treatment / Evaluation)
Description, treatment options at this stage.

### Stage 3: [Name] (e.g., Second-line / Advanced Treatment)
Description, escalation criteria.

### Stage 4: [Name] (e.g., Follow-up / Maintenance)
Long-term management.

### Unmet Needs
Key gaps and unmet needs identified in the journey.

Aim for 500-800 words total.""",

    "treatment_options": """Write the **Treatment Options Analysis** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Company Actions:
{company_actions}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

## Required Structure:

Compare the main treatment/product options available in this market.

For each option (3-5 options):
### Option: [Name]
- Description and mechanism
- Key advantages (positives)
- Key disadvantages (negatives)
- Market positioning

End with a comparison table:
| Option | Positives | Negatives | Key Players |
|--------|-----------|-----------|-------------|

Aim for 600-900 words total.""",
}

# Fallback for any sub-section not explicitly defined
DEFAULT_WRITER_TEMPLATE = """Write the **{subsection_name}** section for a report on "{topic}".

## Available Data
### Facts:
{facts}

### Statistics:
{statistics}

### Company Actions:
{company_actions}

### Analyst Key Findings:
{key_findings}

### Analyst Synthesis:
{analysis_notes}

### Citation Reference Table:
{citation_table}

Write a professional analysis covering the key points from the available data.
Do not include inline citations. Aim for 600-900 words total."""

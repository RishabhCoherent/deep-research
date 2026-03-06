"""Prompt templates for the Analyst agent."""

ANALYST_SYSTEM = """You are a senior market analyst at a top-tier research firm.

Your role: Take organized data for a report sub-section and add analytical depth — identify patterns, assess impact, draw strategic conclusions, and generate key findings.

You do NOT fabricate data. You synthesize, analyze, and interpret the data provided.

Your analysis should:
1. Identify 3-5 key findings from the data
2. Assess impact levels where relevant (High/Medium/Low)
3. Draw connections between different data points
4. Identify emerging patterns or trends
5. Note any gaps in the data that should be acknowledged

Write your analysis notes in a professional, authoritative tone suitable for C-suite executives.
"""

ANALYST_PROMPTS = {
    "market_dynamics": """Analyze the organized data for Market Dynamics of "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key findings
2. analysis_notes: A synthesis paragraph covering:
   - Which drivers are strongest and why
   - Which restraints pose the biggest challenge
   - Which opportunities are most actionable
   - Impact assessment for each factor (High/Medium/Low)
   - Time horizon for each factor (Short-term: 1-2yr, Medium-term: 3-5yr, Long-term: 5+yr)

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "pest_analysis": """Analyze the organized data for PEST Analysis of "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key findings
2. analysis_notes: Synthesis covering Political, Economic, Social, and Technological factors.
   For each PEST dimension, identify:
   - The most significant factor
   - Whether it's a tailwind or headwind for the market
   - Expected trajectory (improving/stable/worsening)

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "porters_five_forces": """Analyze the organized data for Porter's Five Forces of "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key findings
2. analysis_notes: Rate each force and explain:
   - Threat of New Entrants: High/Medium/Low
   - Bargaining Power of Suppliers: High/Medium/Low
   - Bargaining Power of Buyers: High/Medium/Low
   - Threat of Substitutes: High/Medium/Low
   - Competitive Rivalry: High/Medium/Low
   Include reasoning for each rating based on the data.

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "tech_advancements": """Analyze the organized data for Technological Advancements in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key technology trends or breakthroughs
2. analysis_notes: Synthesis covering:
   - Most impactful technologies and their maturity stage
   - Technology adoption timeline estimates
   - Competitive advantage implications

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "mergers_acquisitions": """Analyze the organized data for M&A and Collaborations in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key M&A/partnership trends
2. analysis_notes: Synthesis covering:
   - Dominant deal types (horizontal/vertical integration, licensing, JVs)
   - Strategic rationale patterns
   - Impact on market consolidation

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "product_approvals": """Analyze the organized data for Recent Product Approvals/Launches in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key approval/launch highlights
2. analysis_notes: Synthesis covering:
   - Regulatory approval trends (acceleration/slowdown)
   - Key therapeutic areas or product categories gaining traction
   - Geographic approval patterns

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "key_developments": """Analyze the organized data for Key Developments in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 most significant developments
2. analysis_notes: Synthesis covering:
   - Timeline patterns (accelerating/decelerating activity)
   - Most active companies/organizations
   - Strategic implications of recent developments

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "market_trends": """Analyze the organized data for Market Trends in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 dominant trends
2. analysis_notes: Synthesis covering:
   - Trend strength and momentum
   - Expected duration and impact
   - Interconnections between trends

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "cost_of_therapy": """Analyze the organized data for Cost of Therapy/Product in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key cost insights
2. analysis_notes: Synthesis covering:
   - Cost ranges and variations by product/therapy type
   - Cost drivers and trends (increasing/decreasing)
   - Reimbursement landscape
   - Cost-effectiveness considerations

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "patient_journey": """Analyze the organized data for Patient Journey / Treatment Algorithm in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key insights about the patient/customer journey
2. analysis_notes: Synthesis covering:
   - Key decision points in the journey
   - Unmet needs at each stage
   - Where this market's products/therapies fit in the algorithm

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",

    "treatment_options": """Analyze the organized data for Treatment Options Analysis in "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key comparative insights
2. analysis_notes: Synthesis covering:
   - Comparative advantages/disadvantages of each option
   - Market positioning of key options
   - Emerging options that could disrupt current landscape

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}""",
}

# Default fallback for any sub-section not explicitly defined
DEFAULT_ANALYST_PROMPT = """Analyze the organized data for "{subsection_name}" in the context of "{topic}".

Data:
{organized_data}

Provide:
1. key_findings: List of 3-5 key findings
2. analysis_notes: A professional synthesis paragraph with strategic insights

Return JSON: {{"key_findings": [...], "analysis_notes": "..."}}"""

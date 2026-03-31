"""Phase 1-4 prompts (legacy pipeline)."""

from __future__ import annotations

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

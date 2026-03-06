"""
Prompt templates for each research layer.

These encode the methodology of an experienced (20-30 year) market researcher,
progressively adding depth at each layer.
"""


# ─── Dynamic Section Generation ──────────────────────────────────────────────
# No hardcoded section templates. The LLM decides the right structure based
# on the topic. Works for ANY topic: Porter's, PEST, SWOT, BCG Matrix,
# Value Chain, market trends, competitive analysis, market entry, etc.


# ─── Layer 0: Baseline ─────────────────────────────────────────────────────────
# Pure LLM knowledge, no research. This is the control group.

LAYER0_SYSTEM = """You are a market research analyst writing a professional report.
You produce clean, publication-ready report sections — never conversational text.
Do NOT include preamble like "Here's an analysis" or "Let me break this down".
Start directly with the report content using markdown headings and structured sections."""

LAYER0_USER = """Write a professional market research report on:

**Topic:** {topic}

SECTION STRUCTURE:
Create 3-5 well-organized sections using markdown ## headings.
EVERY section MUST be directly about the topic: "{topic}".
- If the topic requests a specific framework (Porter's Five Forces, PEST, SWOT, BCG Matrix,
  Value Chain, Ansoff Matrix, etc.), use that framework's standard components as your sections.
  Use ONLY that framework's exact components as sections — do NOT add components from a
  different or extended version of the framework. Stick to exactly what the topic names.
- If the topic is about trends, ALL sections should be about different trends or trend drivers.
- If the topic is about macro-economic factors, ALL sections should be about macro-economic factors.
- Do NOT add generic filler sections like "Market Overview", "Competitive Landscape",
  "Strategic Implications", or "Future Outlook" unless the topic specifically asks for them.
- Every section heading should clearly relate to the topic.

Write 400-600 words of substantive, analytical content. Be specific — cite numbers,
percentages, and concrete examples where you can.

IMPORTANT:
- Write ONLY the report content. Do NOT include any conversational preamble,
  introduction like "Here's..." or "I'll analyze...", or concluding remarks.
- Do NOT mention any research firm, data provider, or industry tracker by name
  (IDC, Gartner, Statista, Counterpoint, etc.). Present data as established facts.
- Do NOT include any source citations or [Source: ...] tags.
- The output should read as a standalone, authoritative professional report section."""


# ─── Layer 1: Research Agent ───────────────────────────────────────────────────
# Adds web research: search → gather → synthesize with real sources.
# Mimics: Junior researcher doing a first pass — gathering facts and recent data.

LAYER1_SYSTEM = """You are a market research analyst producing a professional report grounded in real data.
You write clean, publication-ready report sections — never conversational text.
Do NOT include preamble like "Here's an analysis" or "Based on the research data".
Start directly with the report content using markdown headings.

DATA QUALITY RULES (CRITICAL — follow strictly):
- Sources are labeled with credibility tiers: TIER-1 HIGH-CREDIBILITY (IDC, Counterpoint,
  Statista, Reuters, Bloomberg, government), TIER-2 RELIABLE (known news/tech sites),
  TIER-3 UNVERIFIED (unknown aggregators, SEO sites, small market research vendors).
- ALWAYS prefer TIER-1 data over TIER-2/3 when numbers conflict.
- If a TIER-3 source claims a wildly different number (e.g., market size 2x larger than
  TIER-1 sources), IGNORE the TIER-3 number entirely and use TIER-1 data.
- When multiple sources give different figures for the same metric, report the TIER-1 figure
  as the primary number. You may note the range if useful.
- Do NOT cite a single obscure source for a major claim (market size, growth rate, market share)
  without corroboration from at least one TIER-1 or TIER-2 source.

DATA TYPE AWARENESS (CRITICAL):
- MARKET SHARE data comes in different types that must NEVER be confused:
  * SHIPMENT SHARE (from industry trackers) = units shipped as % of total. This is the standard.
  * USAGE/TRAFFIC SHARE (from web analytics like StatCounter) = website visits by device. NOT the same.
  * REVENUE SHARE = dollar value as % of total market revenue.
- For competitive landscape analysis, ALWAYS use SHIPMENT SHARE, not usage/traffic share.
- If a source gives market share numbers that seem unusually high for a company (e.g., Apple >25%
  annual share), verify it is shipment share not web traffic share.

SYNTHESIS RULES:
- Ground every major claim in source data
- Include specific numbers, dates, and company names from your sources
- Distinguish between verified facts and inferences
- Prioritize recency — newer data > older data
- Cross-check key figures: if only one source gives a number and it seems unusually
  high or low, flag it as unverified rather than stating it as fact

OUTPUT RULES:
- Do NOT include any inline citations, source attributions, or [Source: ...] tags in the report.
- Do NOT mention the names of any research firms, market research companies, data providers,
  or industry trackers (e.g., IDC, Counterpoint, Statista, Gartner, etc.) in the report text.
  Use the data from these sources but never name them.
- The report should read as an authoritative, self-contained analysis with no visible sourcing."""

LAYER1_USER = """Produce a professional, source-grounded market research report on:

**Topic:** {topic}

**Research Data:**
{research_context}

SECTION STRUCTURE:
Create 3-5 well-organized sections using markdown ## headings.
EVERY section MUST be directly about the topic: "{topic}".
- If the topic requests a specific framework (Porter's Five Forces, PEST, SWOT, BCG Matrix,
  Value Chain, Ansoff Matrix, etc.), use that framework's standard components as your sections.
  Use ONLY that framework's exact components as sections — do NOT add components from a
  different or extended version of the framework. Stick to exactly what the topic names.
- If the topic is about trends, ALL sections should be about different trends or trend drivers.
- If the topic is about macro-economic factors, ALL sections should be about macro-economic factors.
- Do NOT add generic filler sections like "Market Overview", "Competitive Landscape",
  "Strategic Implications", or "Future Outlook" unless the topic specifically asks for them.
- Every section heading should clearly relate to the topic.

Write 500-800 words with specific numbers and dates.

IMPORTANT:
- Write ONLY the report content. Do NOT include any conversational preamble,
  introduction, or meta-commentary about the analysis.
- Do NOT include any [Source: ...] citations or source attributions in the text.
- Do NOT mention the names of research firms or data providers (IDC, Counterpoint,
  Statista, Gartner, etc.). Use their data but never name them.
- The output must read as a standalone, authoritative professional report section."""

LAYER1_QUERY_GEN = """Generate 5 focused search queries to research this market topic thoroughly.
Each query should target a different aspect. Include the year {current_year} in at least 3 queries
to ensure you find the most recent data.

CRITICAL RULES:
- ALL 5 queries MUST be directly relevant to the specific topic: "{topic}".
- Query 1 should target the most important data for the SPECIFIC ANGLE the topic asks about.
  Examples:
    - Topic "macro-economic factors..." → "macro-economic impact smartphone market {current_year}"
    - Topic "supply chain analysis..." → "smartphone supply chain disruption forecast {current_year}"
    - Topic "key market trends..." → "smartphone market trends {current_year}"
    - Topic "Porter's analysis..." → "smartphone market competitive forces analysis {current_year}"
- Queries 2-5 should cover different facets OF THE SAME TOPIC ANGLE — not generic market data.
- Include {current_year} in at least 3 queries.
- Do NOT search for generic "shipments forecast" or "market share" unless the topic specifically
  asks about shipments or competitive landscape. Stay on the topic's angle.
- Use specific terms relevant to the topic — not generic market research terms.

Topic: {topic}

Return ONLY a JSON array of 5 query strings, nothing else.
Example: ["query 1", "query 2", "query 3", "query 4", "query 5"]"""


# ─── Layer 2: Analysis Agent ──────────────────────────────────────────────────
# Adds: cross-referencing, framework application, gap identification, quantification.
# Mimics: Mid-career researcher who validates sources, applies frameworks, fills gaps.

LAYER2_SYSTEM = """You are a senior market research analyst (15+ years experience) performing
deep analysis. You produce clean, publication-ready report sections — never conversational text.
Do NOT include preamble like "Here's an analysis" or "Based on the research data".
Start directly with the report content using markdown headings.

Your methodology:
1. VERIFY THEN RETAIN — Your output should be a SUPERSET of the prior research, BUT you must
   first VERIFY key data points. If the prior research cites a figure from an obscure or
   TIER-3 source that contradicts well-known TIER-1 sources (IDC, Statista, Counterpoint,
   Bloomberg, Reuters), CORRECT the figure using the TIER-1 data. Do NOT blindly retain
   numbers that are wrong. Retain all VERIFIED data points — never drop correct content.
2. TRIANGULATE — Cross-reference claims across 3+ sources. If the prior research says
   "market size is $X" but your additional research shows most sources say "$Y", use $Y
   and note the correction. Flag contradictions explicitly.
3. QUANTIFY — Every claim needs a number. Market size, growth rate, share %, CAGR,
   YoY change, adoption rate. If sources disagree on numbers, report the range and
   indicate which source is most credible.
4. APPLY FRAMEWORKS ONLY WHEN REQUESTED — Use Porter's Five Forces, PEST, Value Chain,
   SWOT ONLY if the topic explicitly asks for a specific framework analysis.
   For general topics (e.g., "key market trends", "market overview"), focus on
   trend analysis, quantification, and strategic implications instead of forcing
   frameworks. Don't just list factors — analyze their interaction.
5. FILL GAPS — Identify what the research DOESN'T cover. What questions remain? What data
   is missing? What assumptions are being made?
6. CONTEXTUALIZE — Put numbers in context. "Growing at 8%" means nothing without knowing
   the industry average, historical trend, and comparable markets.

DATA TYPE AWARENESS (CRITICAL):
- MARKET SHARE data comes in different types that must NEVER be confused:
  * SHIPMENT SHARE (industry trackers) = units shipped as % of total. This is the STANDARD metric.
  * USAGE/TRAFFIC SHARE (web analytics) = website visits by device brand. NOT the same as market share.
  * REVENUE SHARE = dollar value as % of total revenue.
- For competitive analysis, ALWAYS use SHIPMENT SHARE. If prior research reports market shares
  that seem inflated (e.g., Apple >25% annual share), it may be using web traffic data instead
  of shipment data. CORRECT it using shipment share data from industry trackers.

MATH CONSISTENCY RULE (CRITICAL):
- CAGR over a 1-year period MUST equal the annual growth/decline rate. If shipments drop
  13% from 2025 to 2026, the CAGR from 2025 to 2026 is -13%, NOT some smaller number.
- For multi-year CAGR, use: CAGR = (end_value / start_value)^(1/years) - 1
- When claiming "over X%" or "more than X%", ensure the actual data supports being ABOVE X,
  not just close to it. If combined market share is 39%, say "nearly 40%" not "over 40%".
- Always sanity-check computed metrics against the raw numbers before stating them.

DATA INTEGRITY RULE: If you find that the prior research contains a data point that seems
implausible (e.g., market size drastically different from consensus, market share percentages
that don't add up, growth rates that defy logic), you MUST correct it using the best available
data. Accuracy is more important than retention.

CITATION RULE: Do NOT include ANY source citations, [Source: ...] tags, or research firm names
in your output. Strip any that appear in the prior research. Never mention IDC, Counterpoint,
Statista, Gartner, Canalys, Omdia, or any other research/data firm by name. Present all data
as authoritative established facts with no visible sourcing."""

LAYER2_USER = """Produce an in-depth analytical market research report on:

**Topic:** {topic}

**Prior Research (YOU MUST RETAIN ALL OF THIS DATA):**
{layer1_content}

**Additional Research Data:**
{additional_research}

**Claim Verification Results (CRITICAL — use these to correct errors):**
{verification_results}

VERIFICATION RULES:
- If a claim is marked DISPUTED, use the corrected value from verification evidence.
- If a claim is marked CONFIRMED, retain the original value with high confidence.
- If a claim is marked UNVERIFIED, present it cautiously or note the range of estimates.
- NEVER retain a disputed figure from the prior research when verification evidence contradicts it.

CONTENT RULES:
1. RETAIN all verified data points from the Prior Research — company names, dates, and
   figures that are corroborated by your Additional Research Data.
2. CORRECT any figures in the Prior Research that contradict TIER-1 sources. If Prior Research
   says "$1.5T market" but TIER-1 sources consistently say "$500-600B", use the TIER-1
   figure. ACCURACY TRUMPS RETENTION.
3. VERIFY market shares add up logically (top 2-3 players shouldn't exceed 100%, etc.).
4. ADD analytical depth ON TOP of verified content.
5. STRIP any [Source: ...] citations or research firm names (IDC, Counterpoint, Statista,
   Gartner, etc.) that may appear in the Prior Research. Your output must contain ZERO
   source attributions or research firm mentions. Present data as established facts.

Structure the report using markdown ## headings. Choose sections that directly serve the topic.

SECTION RULES:
- EVERY section MUST be directly about the topic: "{topic}".
- If the topic requests a specific framework (Porter's Five Forces, PEST, SWOT, BCG Matrix,
  Value Chain, etc.), use ONLY that framework's components as your sections.
  Do NOT add components from a different or extended version of the framework.
  Stick to exactly what the topic names.
- If the topic is about trends, ALL sections should cover different trends.
- If the topic is about macro-economic factors, ALL sections should be about macro-economic factors.
- Do NOT add generic filler sections like "Executive Summary", "Market Overview",
  "Competitive Dynamics", or "Contextualized Outlook" unless the topic asks for them.
- You MAY include a brief "Key Data Points" section to preserve verified numbers from prior
  research, but ONLY if the data is directly relevant to the topic.
- End with a short "Data Confidence" subsection (### not ##) noting any gaps within the topic scope.

Include ALL verified data points from prior research that are relevant to the topic.
Cross-reference and triangulate figures. Add ranges where data disagrees.

Write 800-1200 words. Every paragraph should add analytical depth ON TOP of the retained facts.
Stay STRICTLY on the topic: {topic}. Do NOT add sections about subjects the topic does not ask for.

IMPORTANT:
- Write ONLY the report content. Do NOT include any conversational preamble like
  "Here's how I would elevate this" or "Let me analyze". Do NOT reference the previous
  layer or the analysis process.
- Do NOT include ANY [Source: ...] citations, source attributions, or references in the text.
- Do NOT mention ANY research firm, data provider, or industry tracker by name (IDC,
  Counterpoint, Statista, Gartner, Canalys, Omdia, etc.). Use their data but never name them.
- The output must read as a standalone, authoritative professional report with no visible sourcing."""

LAYER2_GAP_QUERIES = """Based on this market analysis, identify the biggest knowledge gaps
and generate targeted search queries to fill them.

**Analysis so far:**
{current_analysis}

**Topic:** {topic}

Identify 3-5 specific gaps in the analysis (missing data, unverified claims,
under-explored angles) and generate a search query for each.

Return as JSON array of objects:
[
  {{"gap": "description of what's missing", "query": "search query to fill it"}},
  ...
]"""

LAYER2_CLAIM_EXTRACTION = """Extract the key numerical/factual claims from this market research report.
Focus on claims that are verifiable: market sizes, growth rates, market shares, specific dates,
company rankings, regulatory events.

**Report:**
{layer1_content}

Return a JSON array of claim objects. Extract 6-10 of the MOST IMPORTANT claims.
Each object: {{"claim": "short description", "value": "the specific number or fact", "search_query": "query to verify this"}}

PRIORITY ORDER (extract these FIRST — they are the most error-prone):
1. FORECASTS and PROJECTIONS — any claim about future market size, shipment decline/growth,
   or revenue projections. These are the most likely to be stale or outdated.
   ALWAYS extract the primary market forecast (e.g., "2026 shipment decline of X%").
2. YEAR-OVER-YEAR GROWTH/DECLINE RATES — these change frequently as new data is released.
3. MARKET SHARES — specific company share percentages.
4. MARKET SIZE — dollar values or unit volumes.
5. Other verifiable claims (dates, rankings, events).

IMPORTANT RULES FOR search_query:
- For FORECAST/PROJECTION claims, include "latest" or "updated" in the query to avoid
  finding stale forecasts. Example: "smartphone shipments forecast 2026 latest IDC"
  not "smartphone shipments 2026".
- For MARKET SHARE claims, ALWAYS include the word "shipment" in the query to get unit shipment
  share (the industry standard), NOT web traffic or usage share. Example: "Apple smartphone
  shipment market share 2025" not "Apple market share".
- For MARKET SIZE claims, specify "revenue" or "shipments" to be precise.
- For GROWTH RATE claims, include the specific time period (quarter or year).
- Include the year or quarter in every query for temporal precision.

Example:
[
  {{"claim": "2026 smartphone shipment forecast", "value": "-0.9% decline in 2026", "search_query": "global smartphone shipments forecast 2026 latest decline percentage IDC Counterpoint"}},
  {{"claim": "Apple market share", "value": "20% global share in 2025", "search_query": "Apple smartphone shipment market share 2025 percentage IDC Counterpoint"}}
]"""


# ─── Layer 3: Expert Agent ─────────────────────────────────────────────────────
# Adds: assumption challenging, second-order effects, cross-industry parallels,
# contrarian perspectives, expert-level synthesis.
# Mimics: 25+ year veteran who challenges conventional wisdom and sees what others miss.

LAYER3_SYSTEM = """You are a world-class market research director with 25+ years of experience.
You produce authoritative, C-suite-ready strategic reports — never conversational text.
Do NOT include preamble like "Here's how I would..." or "Let me take your analysis...".
Start directly with the report content using markdown headings.

CARDINAL RULE: Your output must RETAIN every VERIFIED data point from the prior analysis.
Every corroborated number, percentage, company name, market size, growth rate, CAGR, and
framework score must appear. If you detect an implausible figure (e.g., a market size 2-3x
larger than industry consensus), CORRECT it. ACCURACY is paramount — a correct $500B figure
is infinitely better than a retained $1.5T error.

CITATION RULE: Do NOT include ANY source citations, [Source: ...] tags, or research firm names
in your output. Strip any that appear in the prior analysis. Never mention IDC, Counterpoint,
Statista, Gartner, Canalys, Omdia, or any other research/data firm by name. Present all data
as authoritative established facts with no visible sourcing.

YOUR ANALYTICAL APPROACH:
1. VERIFY THEN RETAIN — Preserve every factual claim that is corroborated. If a number comes
   from a low-credibility source and contradicts TIER-1 data (IDC, Statista, Counterpoint,
   Bloomberg), correct it. Your report is longer and more detailed, never shorter or vaguer.
2. CHALLENGE ASSUMPTIONS — Surface hidden assumptions. Question foundations, not just numbers.
3. SECOND-ORDER EFFECTS — Analyze cascading impacts across downstream industries and supply chains.
4. CROSS-INDUSTRY PARALLELS — Draw from analogous markets to identify patterns and predict outcomes.
5. CONTRARIAN PERSPECTIVE — Present the bear case. What if consensus is wrong?
6. SIGNAL VS. NOISE — Identify the 3-4 signals that actually matter for trajectory.
7. SYNTHESIS — Weave all dimensions into a cohesive, actionable strategic narrative."""

LAYER3_USER = """Produce an expert-level strategic market research report on:

**Topic:** {topic}

**Prior Analysis (RETAIN ALL VERIFIED DATA — EVERY NUMBER AND NAME, BUT STRIP ALL CITATIONS):**
{layer2_content}

**Additional Research:**
{expert_research}

CONTENT RULES:
1. RETAIN all verified data — every corroborated market size, growth rate, CAGR, company
   name, market share, and framework score from the Prior Analysis.
2. CORRECT any remaining data errors. As a world-class expert, sanity-check all figures:
   Do market shares sum to reasonable totals? Does the market size align with known industry
   benchmarks? Are growth rates plausible given the sector maturity? Fix any errors.
3. PRESERVE precision. Keep "$537B at 7.4% CAGR" exact — not "approximately $500B".
   But if a figure is clearly wrong (e.g., 2-3x industry consensus), correct it.
4. ADD expert strategic depth ON TOP of verified content. Your word count should be HIGHER
   than the prior analysis because you are adding new sections while keeping everything.
5. STRIP ALL CITATIONS. Remove every [Source: ...] tag, every research firm name, every
   data provider mention from the prior analysis. Your output must have ZERO visible
   sourcing. Present everything as authoritative established analysis.

Structure the report using markdown ## headings. Choose sections that directly serve the topic.

SECTION RULES:
- EVERY section MUST be directly about the topic: "{topic}".
- If the topic requests a specific framework (Porter's Five Forces, PEST, SWOT, BCG Matrix,
  Value Chain, etc.), use ONLY that framework's components as your sections.
  Do NOT add components from a different or extended version of the framework.
  Stick to exactly what the topic names.
- If the topic is about trends, dedicate each ## section to a specific trend.
- If the topic is about macro-economic factors, dedicate each ## section to a specific factor.
- Do NOT add generic filler sections like "Strategic Overview", "Market Analysis & Quantification",
  "Strategic Implications", or "Outlook" unless the topic specifically asks for them.
- Retain ALL verified data points from the prior analysis, but place them WITHIN the relevant
  topic sections — not in a separate generic "Market Data" section.

EXPERT DIMENSIONS — weave these INTO each section naturally, do NOT create separate sections:
- Hidden assumptions and their validity (strong/moderate/weak)
- Second-order effects specific to the topic
- Contrarian perspectives where they illuminate the analysis
- Key signals to watch (leading indicators specific to the topic)
Example: For Porter's "Threat of Substitutes", discuss the hidden assumption that current
substitutes are the main threat, then note a contrarian view about an emerging substitute
category — all within that same section.

End with a brief ## Key Signals & Implications section (3-4 bullets) only if space allows.

Write 1200-1800 words. This MUST be longer than the prior analysis because you are adding
expert depth while keeping all verified data.
Stay STRICTLY on the topic: {topic}. Do NOT add sections about subjects the topic does not ask for.

CRITICAL:
- Write ONLY the report content. Do NOT include ANY conversational preamble like
  "Here's how I would elevate this", "Absolutely", "Let me transform this", "Certainly",
  or meta-commentary about the analysis process. Do NOT reference "the previous analysis"
  or "Layer 2".
- Do NOT include ANY [Source: ...] citations or source attributions anywhere in the text.
- Do NOT mention ANY research firm, data provider, or industry tracker by name.
- The output must be a standalone, authoritative professional report with no visible sourcing."""

LAYER3_CONTRARIAN_QUERIES = """You are an expert market researcher looking for contrarian
evidence and second-order effects related to this analysis.

**Analysis:**
{current_analysis}

**Topic:** {topic}

Generate 3-4 search queries that look for:
- Evidence AGAINST the consensus view
- Disruptive technologies or business models that could change the market
- Historical parallels from other industries
- Regulatory or geopolitical risks not commonly discussed

Return as JSON array of query strings.
Example: ["query 1", "query 2", "query 3"]"""


# ─── Comparison & Evaluation ──────────────────────────────────────────────────

EVALUATION_PROMPT = """Evaluate this market research analysis on the following dimensions.
Score each dimension from 1-10 and provide a brief justification.

**Topic:** {topic}
**Layer:** {layer_name}
**Content:**
{content}

Evaluate on:

1. **Factual Density** (1-10): How many specific, verifiable claims per paragraph?
   - 1-3: Vague generalities, few specifics
   - 4-6: Some data points but gaps remain
   - 7-10: Dense with specific numbers, dates, company names

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
   - 4-6: Some numbers but many vague qualifiers remain
   - 7-10: Specific %, $, dates, company names, product names

5. **Insight Quality** (1-10): Would a C-suite executive learn something new?
   - 1-3: Generic insights available in any article
   - 4-6: Some useful observations
   - 7-10: Genuinely non-obvious insights, contrarian views, actionable intelligence

6. **Completeness** (1-10): Are there obvious gaps?
   - 1-3: Major aspects of the topic are missing
   - 4-6: Covers basics but misses important angles
   - 7-10: Comprehensive, gaps explicitly acknowledged

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
research on the same topic. Each subsequent layer BUILDS UPON the previous one — it retains
all content and adds more depth. You must evaluate them COMPARATIVELY in a single pass.

**Topic:** {topic}

{layers_content}

Score EACH layer on these 6 dimensions (1-10). Provide a brief justification for each.

1. **Factual Density** (1-10): How many specific, verifiable claims per paragraph?
   - 1-3: Vague generalities, few specifics
   - 4-6: Some data points but gaps remain
   - 7-10: Dense with specific numbers, dates, company names

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
   - 4-6: Some numbers but many vague qualifiers remain
   - 7-10: Specific %, $, dates, company names, product names

5. **Insight Quality** (1-10): Would a C-suite executive learn something new?
   - 1-3: Generic insights available in any article
   - 4-6: Some useful observations
   - 7-10: Genuinely non-obvious insights, contrarian views, actionable intelligence

6. **Completeness** (1-10): Are there obvious gaps?
   - 1-3: Major aspects of the topic are missing
   - 4-6: Covers basics but misses important angles
   - 7-10: Comprehensive, gaps explicitly acknowledged

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

COMPARISON_SUMMARY = """You are comparing the outputs of 4 progressive research layers
on the same topic. Summarize how each layer improved upon the previous one.

**Topic:** {topic}

**Layer 0 — Baseline (no research):**
Word count: {l0_words}
Evaluation: {l0_eval}

**Layer 1 — Research Agent (web search + synthesis):**
Word count: {l1_words}
Evaluation: {l1_eval}

**Layer 2 — Analysis Agent (cross-reference + frameworks):**
Word count: {l2_words}
Evaluation: {l2_eval}

**Layer 3 — Expert Agent (assumption challenging + contrarian views):**
Word count: {l3_words}
Evaluation: {l3_eval}

Write a 200-300 word executive summary of:
1. How each layer improved on the previous one (be specific about what was added)
2. The biggest quality jumps between layers
3. What the Layer 3 output captures that Layer 0 completely misses
4. Overall assessment: does progressive layering genuinely improve quality?"""


# ─── Agentic Prompts: Layer 1 ────────────────────────────────────────────────

LAYER1_PLAN = """You are a research planner. Given a market research topic, break it down
into sub-areas that need to be researched separately.

**Topic:** {topic}

For each sub-area, generate 2 targeted search queries that would find the most relevant,
recent data. Include the year {current_year} in at least one query per sub-area.

RULES:
- Create 4-6 sub-areas that are directly relevant to the topic.
- Sub-areas should cover different facets of the SAME topic — not generic market research.
- If the topic asks for a specific framework (Porter's, PEST, SWOT, etc.), each sub-area
  should correspond to a component of that framework.
- Do NOT add sub-areas that are off-topic (e.g., "competitive landscape" for a macro-economic topic).

Return ONLY a JSON object:
{{
  "sub_areas": [
    {{"name": "sub-area name", "queries": ["query 1", "query 2"]}}
  ]
}}"""

LAYER1_COVERAGE_EVAL = """You are evaluating research coverage for a market research report.

**Topic:** {topic}

**Planned sub-areas:**
{sub_areas}

**Research data gathered so far:**
{research_context}

For each sub-area, rate how well the gathered research covers it (0-100).
- 80-100: Well covered, specific data and facts found
- 50-79: Partially covered, some data but gaps remain
- 0-49: Poorly covered, little or no relevant data

For any sub-area scoring below 60, generate ONE targeted search query to fill the gap.

Return ONLY a JSON object:
{{
  "coverage": [
    {{"sub_area": "name", "score": 75, "gap_query": "query or null"}}
  ],
  "overall_coverage": 68
}}"""

LAYER1_SELF_REVIEW = """You are a harsh but fair research editor reviewing a draft report.
Be critical — a score of 7 means "acceptable, not great". Only give 9+ for genuinely excellent work.

**Topic:** {topic}
**Draft:**
{draft}

Score each dimension from 1-10:
1. **factual_grounding**: Is every major claim backed by specific data (numbers, dates, sources)?
   Or are there vague assertions like "significant growth" without numbers?
2. **coverage**: Does the report cover all important aspects of the topic? Any major gaps?
3. **specificity**: Does it use concrete numbers, company names, dates? Or is it generic?
4. **structure**: Are sections well-organized and directly relevant to the topic?

Then list up to 3 specific weaknesses (be concrete, not vague).
For each weakness, suggest a search query that would find data to fix it.

Return ONLY a JSON object:
{{
  "scores": {{"factual_grounding": 7, "coverage": 6, "specificity": 5, "structure": 8}},
  "overall": 6.5,
  "weaknesses": ["Missing specific market size data for 2026", "No company examples given"],
  "suggested_queries": ["smartphone market size 2026 forecast", "top smartphone companies market share 2026"]
}}"""

LAYER1_REFINE = """You are improving a market research draft based on editorial feedback.

**Topic:** {topic}

**Current Draft:**
{draft}

**Weaknesses to Fix:**
{weaknesses}

**Additional Research Data:**
{new_context}

RULES:
1. Fix each listed weakness using the new research data.
2. RETAIN all correct content from the current draft — do NOT remove good data.
3. Add missing data points from the new research.
4. The revised report should be LONGER and MORE DETAILED than the current draft.
5. Keep the same section structure unless it was flagged as a weakness.
6. Stay strictly on the topic: {topic}.

Write ONLY the improved report content. No preamble or meta-commentary."""


# ─── Agentic Prompts: Layer 2 ────────────────────────────────────────────────

LAYER2_CRITICAL_READ = """You are a 10-year veteran market analyst critically reading a junior
researcher's draft. Your job is to find every problem so it can be fixed.

**Topic:** {topic}

**Layer 1 Draft:**
{layer1_content}

Identify:
1. **weak_claims**: Claims that lack evidence, cite vague sources, or seem unsubstantiated.
   For each, explain the problem and provide a verification search query.
2. **logical_gaps**: Missing logical connections or "so what?" analysis that should be there.
3. **missing_dimensions**: Important aspects of the topic that are completely absent.
   For each, provide a search query to find the missing data.
4. **implausible_data**: Numbers or facts that seem wrong, outdated, or inconsistent.
   For each, explain why it's suspicious and provide a fact-check query.

Return ONLY a JSON object:
{{
  "weak_claims": [{{"claim": "...", "problem": "...", "query": "..."}}],
  "logical_gaps": ["gap 1", "gap 2"],
  "missing_dimensions": [{{"dimension": "...", "query": "..."}}],
  "implausible_data": [{{"data": "...", "why": "...", "query": "..."}}]
}}"""

LAYER2_RESEARCH_PLAN = """You are planning targeted research to fix problems in a market analysis.

**Topic:** {topic}

**Problems Found:**
{critical_reading}

Prioritize the top 5-7 most impactful problems to fix. For each, generate a precise search query
and classify it as "verify" (checking an existing claim) or "fill" (adding missing data).

Return ONLY a JSON object:
{{
  "research_tasks": [
    {{"type": "verify", "target": "market size claim of $500B", "query": "global smartphone market size 2026", "priority": 1}},
    {{"type": "fill", "target": "missing CAGR data", "query": "smartphone market CAGR forecast 2026-2030", "priority": 2}}
  ]
}}"""

LAYER2_SELF_REVIEW = """You are a research director about to present this analysis to a client.
Be critical — a score of 7 means "acceptable, not great". Only give 9+ for genuinely excellent work.

**Topic:** {topic}
**Analysis Draft:**
{draft}

Score each dimension from 1-10:
1. **data_integrity**: Are corrected numbers actually better than Layer 1's? Are key figures triangulated?
2. **analytical_depth**: Does it go beyond Layer 1, adding genuine insight? Or does it just rephrase?
3. **quantification**: Is every claim backed by a specific number?
4. **framework_application**: If the topic asks for a framework, is it applied rigorously?
5. **completeness**: Are the gaps identified in the critical reading actually filled?

List up to 3 remaining weaknesses with search queries to fix them.

Return ONLY a JSON object:
{{
  "scores": {{"data_integrity": 7, "analytical_depth": 6, "quantification": 8, "framework_application": 7, "completeness": 6}},
  "overall": 6.8,
  "weaknesses": ["Still missing regional breakdown data", "Framework application is superficial"],
  "suggested_queries": ["smartphone market regional breakdown 2026 Asia Europe Americas"]
}}"""

LAYER2_REFINE = """You are improving a market analysis based on a research director's feedback.

**Topic:** {topic}

**Current Analysis:**
{draft}

**Weaknesses to Fix:**
{weaknesses}

**Additional Research Data:**
{new_context}

**Layer 1 Content (for reference — retain all verified data):**
{layer1_content}

RULES:
1. Fix each listed weakness using the new research data.
2. RETAIN all verified data from the current analysis and Layer 1 — do NOT remove correct numbers.
3. Add deeper analytical insight, not just more data.
4. The revised analysis should be LONGER and MORE RIGOROUS than the current draft.
5. Stay strictly on the topic: {topic}.

Write ONLY the improved analysis. No preamble or meta-commentary."""


# ─── Agentic Prompts: Layer 3 ────────────────────────────────────────────────

LAYER3_EXPERT_CRITIQUE = """You are a 25-year industry veteran and strategic advisor. Read this
analysis with extreme skepticism. Your job is to find what everyone else misses.

**Topic:** {topic}

**Layer 2 Analysis:**
{layer2_content}

Identify:
1. **assumptions**: 3-5 hidden assumptions the analysis takes for granted. For each:
   - State the assumption explicitly
   - Rate validity: strong / moderate / weak / flawed
   - Explain what happens if the assumption breaks
   - Provide a search query to find evidence for or against it
2. **second_order_effects**: 2-3 cascading effects the analysis misses entirely.
   For each, provide a search query.
3. **cross_industry_parallels**: 1-2 analogous situations from other industries that
   illuminate this topic. For each, provide a search query.
4. **biggest_blind_spot**: The single most dangerous thing this analysis overlooks.
   Provide a search query.

Return ONLY a JSON object:
{{
  "assumptions": [{{"assumption": "...", "validity": "moderate", "if_breaks": "...", "query": "..."}}],
  "second_order_effects": [{{"effect": "...", "query": "..."}}],
  "cross_industry_parallels": [{{"parallel": "...", "query": "..."}}],
  "biggest_blind_spot": {{"description": "...", "query": "..."}}
}}"""

LAYER3_CSUITE_REVIEW = """You are the CEO of a Fortune 500 company. Your VP of Strategy just
handed you this report. Be demanding — a score of 7 means "I'd send this back for revisions".
Only give 9+ if you'd forward it to your board.

**Topic:** {topic}
**Expert Report:**
{draft}

Score each dimension from 1-10:
1. **strategic_value**: Do you learn something you didn't already know? Any genuine surprises?
2. **assumption_transparency**: Are hidden assumptions surfaced clearly, not buried?
3. **contrarian_credibility**: Are bear cases substantive and evidence-based, or strawmen?
4. **actionability**: Can you make a real decision based on this? Are signals to watch specific?
5. **presentation_quality**: Would you be proud to share this with your board?

List up to 3 specific improvements.
For each, suggest a search query that would find data to strengthen the point.

Return ONLY a JSON object:
{{
  "scores": {{"strategic_value": 7, "assumption_transparency": 6, "contrarian_credibility": 8, "actionability": 7, "presentation_quality": 7}},
  "overall": 7.0,
  "weaknesses": ["Assumptions listed but not deeply tested", "Missing a concrete decision framework"],
  "suggested_queries": ["smartphone market strategic inflection points 2026"]
}}"""

LAYER3_REFINE = """You are refining an expert strategic report based on C-suite feedback.

**Topic:** {topic}

**Current Report:**
{draft}

**CEO Feedback (weaknesses to address):**
{weaknesses}

**Additional Research Data:**
{new_context}

**Layer 2 Analysis (retain all verified data):**
{layer2_content}

RULES:
1. Address each CEO concern with SUBSTANCE — not by adding fluff, but by adding genuine
   strategic insight backed by the new research data.
2. RETAIN all verified data from the current report and Layer 2.
3. Strengthen assumptions with evidence. Make contrarian views more credible.
4. Add specific, actionable signals and decision frameworks.
5. The revised report should demonstrate clear expert-level thinking.
6. Stay strictly on the topic: {topic}.

Write ONLY the improved report. No preamble or meta-commentary."""

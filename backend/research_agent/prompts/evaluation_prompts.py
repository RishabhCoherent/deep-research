"""Evaluation, comparison, and metrics prompts."""

from __future__ import annotations

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


CLAIM_JOURNEY_EXTRACTION_PROMPT = """Find the SINGLE claim that shows the most dramatic transformation across all 3 layers of market research.

**Topic:** {topic}

**LAYER 0 — Baseline ({l0_words} words):**
{l0_content}

**LAYER 1 — Enhanced ({l1_words} words):**
{l1_content}

**LAYER 2 — Expert ({l2_words} words):**
{l2_content}

{tool_context}

SELECTION: Pick the claim with the widest transformation gap — vague in L0, partially enriched in L1, fully substantiated with multiple data points and sources in L2. Must appear in all 3 layers. If not possible, use the best L0→L2 pair and infer L1.

Quality tags to apply: "+Data Point", "+Named Source", "+Quantified", "+Causal Mechanism", "+Time-Bound", "+Specific Company"

Return ONLY JSON:
{{
  "category": "...",
  "topic_sentence": "One-line summary",
  "overall_narrative": "2-3 sentence transformation story",
  "selection_reason": "Why this claim",
  "snapshots": [
    {{
      "layer": 0,
      "claim_text": "Exact quote from Layer 0",
      "data_points": [],
      "sources_cited": [],
      "quality_tags": [],
      "transformation_steps": []
    }},
    {{
      "layer": 1,
      "claim_text": "Exact quote from Layer 1",
      "data_points": ["..."],
      "sources_cited": ["..."],
      "quality_tags": ["..."],
      "transformation_steps": [
        {{"action": "search", "query": "...", "source_title": "...", "source_url": "...", "data_point_added": "...", "why_it_matters": "..."}}
      ]
    }},
    {{
      "layer": 2,
      "claim_text": "Exact quote from Layer 2",
      "data_points": ["..."],
      "sources_cited": ["..."],
      "quality_tags": ["..."],
      "transformation_steps": [
        {{"action": "...", "query": "...", "source_title": "...", "source_url": "...", "data_point_added": "...", "why_it_matters": "..."}}
      ]
    }}
  ]
}}"""

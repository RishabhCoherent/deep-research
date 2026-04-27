You are structuring an opinionated, thesis-driven research report for a senior reader who will act on it.

TODAY'S DATE: {today_iso}

TOPIC: {topic}

{topic_profile_block}

CONSOLIDATED CLAIMS (numerical evidence collected by upstream agents):
{claims_block}

DIMENSIONAL CLUSTERS (multi-source consensus from a6.5; "high"/"medium" consensus = trusted):
{clusters_block}

THEMES (qualitative groupings produced by a6's theme clusterer):
{themes_block}

YOUR JOB
=========
Produce the structural OUTLINE for an analyst-grade report on this topic. The
prose-writing pass that runs after you will use this outline as a hard
scaffold — every section you specify here will be written; nothing you omit
will appear.

REQUIRED SECTIONS:
- Executive Summary (verdicts only — no numbers, no detail)
- 3-5 analytical sections (each with a clear thesis + evidence + so_what)
- Contrarian View (2-3 bold non-consensus claims at the end of the report)

QUALITY RULES:
1. Each section must argue ONE thesis. Multiple ideas = split into separate sections.
2. Include AT LEAST ONE framework_table (comparison matrix, risk grid, taxonomy)
   somewhere across the sections. Frameworks are the artefacts readers remember.
3. Include AT LEAST ONE causal_chain_rows entry across the sections. Cause →
   effect → implication forces a real argument rather than fact-listing.
4. Include 1-3 case_studies across the sections — concrete company /
   jurisdiction / cohort examples that PROVE the thesis. Skip if you have no
   concrete examples in the evidence.
5. so_what is the ONE-line answer to "what should the reader do differently?"
   — strategic, not a summary.
6. evidence_ids_to_cite assigns each piece of upstream evidence to ONE section
   only. Do not double-count.
7. MERGE overlapping sections. Fewer deeper sections > many thin ones.
8. DROP sections with zero evidence. Do not pad.

DOMAIN HONESTY:
The topic profile above tells you what KIND of topic this is. If the topic is
clinical research, the framework table might be a 'response rate by cohort'
matrix; for policy it might be 'incentive structure by country'; for market
it might be 'segment size + growth + risk'. Pick framework / chain / case
study shapes that fit the domain — do NOT default to market-research framings
when the topic isn't market.

CONTRARIAN VIEW:
Only emit 2-3 contrarian claims if the evidence genuinely supports them. If
the evidence is consistent with consensus, return an empty contrarian_claims
list and the prose pass will omit the section.

KEY STATS:
Identify the most important verified numbers from the dimensional clusters
(prefer multi-source consensus values) and from validated claims. List the
ones that MUST appear in the final report by their literal value. The prose
pass will be required to cite all of them.

OUTPUT
=======
Return a single JSON object matching this shape (strict schema enforced):

{{
  "sections": [
    {{
      "heading": "## Section Title",
      "thesis": "the ONE argument this section makes",
      "framework_table": {{
        "title": "Framework name",
        "headers": ["Column 1 header", "Column 2 header", ...],
        "rows": [
          {{"label": "Row label", "cells": ["cell 1", "cell 2", ...]}}
        ]
      }} | null,
      "causal_chain_rows": [
        {{"cause": "...", "effect": "...", "implication": "..."}}
      ],
      "case_studies": [
        {{"title": "Case Study: ...", "body": "150-300 word narrative"}}
      ],
      "so_what": "one-line strategic implication",
      "evidence_ids_to_cite": ["claim_idx_3", "claim_idx_7", ...],
      "prose": ""
    }}
  ],
  "contrarian_claims": ["..."],
  "key_stats": ["specific verified numbers that MUST appear"],
  "target_word_count": 2500
}}

target_word_count = max(2000, num_sections * 600). Aim for 2000-3500 words.

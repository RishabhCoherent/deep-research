{PLAYBOOK}

## Your specific job
Write an 800-1500 word bottom-up analyst narrative from the pre-grouped themes.

CRITICAL: This is BOTTOM-UP. You MUST:
  1. Start with a theme paragraph (not a generic intro paragraph).
  2. Write one substantive paragraph per theme (with numbers, dates, company names).
  3. Write a brief executive-summary paragraph LAST — as a synthesis, not an intro.
  4. Cite claims inline with [N] footnote notation. [1], [2], ... match the footnotes list.
  5. Never invent numbers — only use values from the provided themes and claims.

Structure:
```
## [Theme 1 Name]
<paragraph with specific numbers cited as [N]>

## [Theme 2 Name]
<paragraph with specific numbers cited as [N]>

... (one section per theme)

## Executive Summary
<synthesis paragraph drawing on all themes>
```

Footnote format — return a footnotes list alongside the narrative:
  [{n: 1, citation: {url: "...", title: "...", authority_tier: "..."}}, ...]
  - n must match the [N] used in narrative
  - n must start at 1, be sequential, and unique

Rules:
  - 800 ≤ word count ≤ 1500.
  - Every [N] in narrative must have a matching footnote entry.
  - Open each section with the theme's most surprising or quantified finding.
  - Executive summary must be the LAST section.
  - Return ONLY valid JSON matching ConsolidatedNarrative:
    {narrative: str, footnotes: [Footnote, ...]}.

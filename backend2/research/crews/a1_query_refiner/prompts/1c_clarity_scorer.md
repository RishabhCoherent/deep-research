{PLAYBOOK}

## Your specific job
Score each of the 4 variants on three dimensions:
  - specificity    (0-10): how narrowly scoped vs woolly
  - scope_clarity  (0-10): geography + time horizon both named
  - answerability  (0-10): how likely a senior analyst could answer in one brief

composite = 0.4*specificity + 0.3*scope_clarity + 0.3*answerability

Return ONLY valid JSON matching ScoredBundle, with `scored` SORTED DESC by composite.
Write a one-sentence `reason` per variant (≤ 30 words).

Raw query:
<<<{raw_query}>>>

Variants (as JSON):
{variants_json}

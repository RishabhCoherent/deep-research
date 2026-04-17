{PLAYBOOK}

## Your specific job
Score each question on two dimensions (0-10):
  - info_value    : how much the final brief improves if this question is answered well
  - answerability : how cheaply a downstream research agent (web search + Tavily) can answer it

composite = 0.6 * info_value + 0.4 * answerability   (round to 2 decimal places)

Then:
  - Drop near-duplicates: if two questions target the same metric+geography+timeframe,
    keep only the higher-composite one.
  - Truncate to AT MOST 15 items.
  - Ensure AT LEAST 8 items remain. If fewer than 8 survive deduplication,
    relax your dedup threshold and restore borderline items.
  - Sort DESC by composite.
  - Each `reason` must be ≤ 30 words explaining why this composite score was given.
  - Carry forward all original fields: text, category, metric_hint, geography,
    time_frame, source from the input.

Return ONLY valid JSON matching PrioritizedQuestions.

Chosen refined query:
<<<{chosen_query}>>>

Questions to score and rank (as JSON):
{questions_json}

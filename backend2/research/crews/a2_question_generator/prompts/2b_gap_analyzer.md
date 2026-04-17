{PLAYBOOK}

{CHECKLIST}

## Your specific job
You are filling gaps. Keep ALL existing items in `questions` unchanged.
Then ADD new items (with source="gap_fill") for any must-have row from the
checklist above (for intent "{intent}") that is NOT already covered.

Rules:
  - Do not duplicate. If a checklist row is already addressed by an existing
    decomposer question (same category or clearly same meaning), skip it.
  - New items must still be ATOMIC and carry category / metric_hint / geography / time_frame.
  - Add at most 5 new items. If more gaps exist, prioritise the ones closest to the intent.
  - source must be "gap_fill" on every new item.
  - Return ONLY valid JSON matching GappedQuestions (same schema as input, just potentially longer).

Existing drafts (as JSON):
{drafts_json}

Chosen refined query:
<<<{chosen_query}>>>

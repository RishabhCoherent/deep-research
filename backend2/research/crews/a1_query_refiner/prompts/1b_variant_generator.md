{PLAYBOOK}

## Your specific job
Produce EXACTLY 4 refined queries. Each must hit a DIFFERENT analyst angle.
All 4 angles must appear exactly once: size_segmentation, drivers_constraints,
competitive_share, outlook_scenarios.

Rules:
  - Each query ≤ 35 words.
  - Each must be scope-bounded (geography AND time — e.g. "Global 2025-2026").
  - The classifier identified intent = {intent}. Let this bias the PHRASING of
    each variant while still preserving the four distinct angles.
  - Do NOT duplicate wording across variants.
  - Do NOT invent companies, numbers, or events.
  - Return ONLY valid JSON matching VariantBundle.

Classifier reasoning (for context only — do not quote):
{reasoning}

Raw query:
<<<{raw_query}>>>

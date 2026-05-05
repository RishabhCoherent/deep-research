{PLAYBOOK}

## Your specific job
You are STRUCTURING numeric claims that have already been found by a deterministic prefilter. For each candidate in `candidates_json`, emit ONE NumericClaim — unless the candidate is obvious noise (table cell, page number, version string), in which case drop it.

You do NOT need to find numbers. The prefilter already did that. Your job is to fill in the qualifiers and write a clean metric noun phrase.

For each candidate, build a NumericClaim with:

  - metric:      short noun phrase describing what is being measured.
                 Use the candidate's surrounding_window + entity_hints to
                 phrase it. E.g. for sentence "Tata's ₹91,000 crore investment
                 in semiconductor fab" → metric = "Tata semiconductor fab investment".
  - value:       prefer candidate.raw_value (already parsed). BUT if the
                 sentence_text obviously implies a different magnitude (e.g.
                 raw_value=100000 but sentence says "₹1 Lakh Crore" which is
                 1e12; or raw_value=10 but sentence says "$10 billion" =
                 1e10), correct it. Output the actual numeric value the
                 sentence states.
  - unit:        normalise candidate.raw_unit into a clean short string
                 ("USD billion", "% YoY", "GWh", "INR crore", "USD/kWh"). If
                 raw_unit is empty/garbled, infer from the sentence text.
  - as_of:       ISO date if stated in the sentence or surrounding_window
                 ("2024", "2024-Q1", "2030"); null if absent. Use 4-digit years.
  - scope:       geographic scope from entity_hints.GPE or sentence text
                 ("India", "global", "US", "APAC"); null if absent.
  - raw_excerpt: COPY candidate.sentence_text VERBATIM. Do NOT paraphrase,
                 truncate, or alter casing. The verbatim-in-passage validator
                 will reject any claim where this rule is broken.
  - citation:    from passage_map_json[<candidate.passage_idx>], populate:
                 url, title, publisher, published, accessed, authority_tier.
  - qualifiers:  Wikidata-style open dict. CRITICAL: cross-source
                 consistency matters more than richness. Two claims about
                 the same fact MUST get IDENTICAL `subject` and
                 `metric_kind` strings, otherwise they fail to cluster.

                 ALWAYS emit (these two are the clustering identity):

                 subject:       the broad topic-level entity. Use a SHORT
                                canonical phrase based on the chosen_query
                                ("india semiconductor market", "ev battery
                                pack", "us solar tax credit"). All
                                lowercase. NO articles ("the"). NO source-
                                specific names ("Tata's fab" → "india
                                semiconductor fab"). Aim for the SAME
                                subject string across as many claims as
                                possible — the broader, the more
                                clusterable.

                 metric_kind:   pick EXACTLY ONE from this fixed list — no
                                variations, no plurals, no synonyms:
                                  market_size, investment_amount,
                                  growth_rate, cagr, production_capacity,
                                  workforce, market_share, price,
                                  export_value, import_value, plant_count,
                                  unit_count, percentage_share, gdp_share
                                If none fits, use the closest match
                                anyway. Do NOT invent custom keys
                                ("investment_commitment", "market_value",
                                "budget_allocation" — all wrong; use
                                investment_amount or market_size).

                 Emit ONLY when EXPLICITLY stated in the sentence text
                 (NOT inferred from context):

                 segment:       only when the sentence names a specific
                                sub-segment ("lfp cells", "wafer fab").
                                Skip if generic.
                 fiscal_period: only for explicit "FY2024" / "Q3 2024".

                 Do NOT emit `is_forecast`, `geography`, or `scope` as
                 qualifiers — those go in the top-level NumericClaim
                 fields (`scope` for geography, `as_of` for the year).
                 Emitting them in qualifiers fragments clustering.

                 EMPTY qualifiers dict is acceptable when the sentence
                 doesn't support the required keys.

CRITICAL RULES:
  - raw_excerpt MUST equal candidate.sentence_text byte-for-byte.
  - Do NOT invent qualifiers — only fill keys you can support from the
    sentence or its surrounding_window.
  - If two candidates share the same sentence_text but have different values
    (e.g. a range "$10-12B" was split into two candidates), keep both — they
    are separate claims with the same excerpt.
  - DROP a candidate only if the sentence is obvious noise:
      * page numbers, footer references ("Page 5 of 17", "Source: [2]")
      * version strings ("v3.4.0", "rev 2.1")
      * pure table cells with no subject ("23.4 | 12.1 | 5.6")
      * the number is part of an irrelevant aside ("call us at +1-800-...")
  - When in doubt, KEEP the candidate. Stage 3 validation will catch
    excerpt-grounding errors; you should err on the side of yield.
  - Output ALL viable candidates. There is NO upper limit on claim count.

Return ONLY valid JSON matching ExtractedClaims with all viable candidates structured. Close all brackets properly.

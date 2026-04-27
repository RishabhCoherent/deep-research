{PLAYBOOK}

## Your specific job
For each conflict candidate where two or more claims share the SAME authority tier,
identify which claim is backed by the **most recently published source** — i.e. the
claim whose *citation* is newest, NOT the claim whose forecast year is latest.

Two date fields exist and are EASY TO CONFUSE — read carefully:

  - `claim.citation.published`  = when the source document was published (publication date).
                                  THIS is what "most recent source" means.
  - `claim.as_of`               = the calendar year or date the claim's number is ABOUT
                                  (e.g. "market revenue in 2025" -> as_of=2025;
                                   "projected size by 2033" -> as_of=2033).
                                  A forecast for 2033 does NOT mean the source is from 2033.

When ranking recency, ALWAYS use `citation.published` first.
Use `as_of` ONLY as a tiebreaker when two citations share the same published date.
A 2033 forecast published in 2026 is NEWER than a 2025 data point published in 2024.

Steps:
1. For each ConflictCandidate:
   a. Find the highest authority tier in the group.
   b. Among claims with that tier, find the most recently PUBLISHED one
      (by citation.published). Ties -> use as_of as tiebreaker.
   c. Set recency_winner_idx to the 0-based index of that claim in the claims list.
   d. If all claims have different tiers, set recency_winner_idx = index of the highest-tier claim.

Date format rules:
  - ISO: "2026-03-12" or "2026-02" or "2026" (partial dates -> earliest day of period).
  - If `citation.published` is missing for every claim in the group, fall back to `as_of`.
  - If no usable date exists for any claim, set recency_winner_idx = 0.

Writing rejection reasons (for downstream 7d Resolver):
  - NEVER cite a forecast year as "older" — e.g. do NOT write "older source (2033 vs 2025)"
    when those are as_of forecast years. Write "same tier, source published earlier
    (2024-11 vs 2026-02)" only if you actually see two distinct publication dates.
  - If you can't tell from the data, say "same tier, insufficient publication-date info".

Rules:
  - Every ConflictCandidate must have recency_winner_idx set (not null).
  - Return ONLY valid JSON matching RecencyResult: {candidates: [ConflictCandidate, ...]}.

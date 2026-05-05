"""Replay the Scottish whiskey run's outline through the framework-table
grounding validator and report which rows it would drop. Throwaway script."""
import json
from research.core.types import (
    NumericClaim, Citation, AuthorityTier,
    OutlineSection, ReportOutline, FrameworkTable, FrameworkRow,
)
from research.crews.a6_consolidator.compose_two_pass import (
    _ground_framework_tables, _build_evidence_number_set,
)

raw = json.load(open("c:/tmp/audit.json", encoding="utf-8"))

# Re-hydrate validated_claims (or topic+market+news) into NumericClaim objects
all_claim_dicts = (
    (raw.get("validated_claims") or [])
    or (raw.get("topic_claims") or []) + (raw.get("market_claims") or []) + (raw.get("news_claims") or [])
)
claims: list[NumericClaim] = []
for c in all_claim_dicts:
    cit = c.get("citation") or {}
    try:
        claims.append(NumericClaim(
            metric=c.get("metric") or "",
            value=c.get("value") or 0.0,
            unit=c.get("unit") or "",
            as_of=c.get("as_of"),
            scope=c.get("scope"),
            raw_excerpt=c.get("raw_excerpt") or "",
            citation=Citation(
                url=cit.get("url") or "",
                title=cit.get("title"),
                publisher=cit.get("publisher"),
                published=cit.get("published"),
                accessed=cit.get("accessed") or "",
                authority_tier=AuthorityTier(cit.get("authority_tier", "blog")),
            ),
            qualifiers=c.get("qualifiers") or {},
        ))
    except Exception as e:
        print("skipped claim:", e)

clusters = raw.get("dimensional_clusters") or []

# Re-hydrate the outline from the saved report
outline_raw = (raw.get("consolidated") or {}).get("outline") or {}
sections = []
for s in outline_raw.get("sections") or []:
    ft_raw = s.get("framework_table")
    ft = None
    if ft_raw:
        ft = FrameworkTable(
            title=ft_raw.get("title") or "",
            headers=ft_raw.get("headers") or [],
            rows=[FrameworkRow(label=r.get("label") or "",
                               cells=r.get("cells") or [])
                  for r in ft_raw.get("rows") or []],
        )
    sections.append(OutlineSection(
        heading=s.get("heading") or "",
        thesis=s.get("thesis") or "",
        framework_table=ft,
    ))

outline = ReportOutline(sections=sections)

ev = _build_evidence_number_set(claims, clusters)
print(f"evidence number set size: {len(ev)}")
print()
print("=== BEFORE grounding ===")
for i, s in enumerate(outline.sections):
    if s.framework_table:
        print(f"Section {i+1}: {s.framework_table.title}")
        for r in s.framework_table.rows:
            print(f"  {r.label}: {r.cells}")

_ground_framework_tables(outline, claims, clusters)

print()
print("=== AFTER grounding (rows that should remain) ===")
for i, s in enumerate(outline.sections):
    if s.framework_table:
        print(f"Section {i+1}: {s.framework_table.title}")
        for r in s.framework_table.rows:
            print(f"  {r.label}: {r.cells}")
    else:
        print(f"Section {i+1}: (table dropped entirely)")

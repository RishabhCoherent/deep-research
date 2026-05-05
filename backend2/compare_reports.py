"""Compare a legacy backend L2 report against a backend2 brief on report
shape, citation discipline, structural depth, numeric density.

Usage: python compare_reports.py
"""
import json
import re

LEGACY = "c:/tmp/legacy_glp1.json"
BACKEND2 = "c:/tmp/audit.json"   # Scottish whiskey backend2 run

H2 = re.compile(r"^##\s+([^\n]+)", re.MULTILINE)
H3 = re.compile(r"^###\s+([^\n]+)", re.MULTILINE)
TABLE = re.compile(
    r"(?:^\|[^\n]*\|\s*\n^\|[\s\-:|]+\|\s*\n(?:^\|[^\n]*\|\s*\n)+)",
    re.MULTILINE,
)
CITATION = re.compile(r"\[\d+\]|\[\^\d+\]")
URL = re.compile(r"https?://\S+")
NUMERIC = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s*(?:%|million|billion|trillion|M|B|K)?", re.IGNORECASE)
BULLET = re.compile(r"^\s*[-*]\s", re.MULTILINE)


def metrics(label: str, content: str) -> dict:
    return {
        "label":     label,
        "words":     len(content.split()),
        "h2":        len(H2.findall(content)),
        "h3":        len(H3.findall(content)),
        "tables":    len(TABLE.findall(content)),
        "citations": len(CITATION.findall(content)),
        "urls":      len(set(URL.findall(content))),
        "numeric":   len(NUMERIC.findall(content)),
        "bullets":   len(BULLET.findall(content)),
    }


def main():
    legacy_raw = json.load(open(LEGACY, encoding="utf-8"))
    legacy_report = legacy_raw.get("report") or {}
    L2 = next((l for l in (legacy_report.get("layers") or []) if l.get("layer") == 2), {})
    legacy_content = L2.get("content", "") or ""

    backend2_raw = json.load(open(BACKEND2, encoding="utf-8"))
    b2_consolidated = backend2_raw.get("consolidated") or {}
    b2_content = b2_consolidated.get("narrative") or ""

    L = metrics("legacy_L2", legacy_content)
    B = metrics("backend2", b2_content)

    print("=" * 72)
    print(f"{'METRIC':<24} {'LEGACY (L2)':<18} {'BACKEND2':<18} {'ratio':<10}")
    print("=" * 72)
    keys = ["words", "h2", "h3", "tables", "citations", "urls", "numeric", "bullets"]
    for k in keys:
        a, b = L[k], B[k]
        ratio = (b / a) if a else float("nan")
        print(f"  {k:<22} {a:<18} {b:<18} {ratio:.2f}x")
    print()

    # outline structural artefacts (backend2-specific)
    outline = b2_consolidated.get("outline") or {}
    sections = outline.get("sections") or []
    n_thesis = sum(1 for s in sections if s.get("thesis"))
    n_fw = sum(1 for s in sections if s.get("framework_table"))
    n_causal = sum(len(s.get("causal_chain_rows") or []) for s in sections)
    n_cs = sum(len(s.get("case_studies") or []) for s in sections)
    n_so_what = sum(1 for s in sections if s.get("so_what"))
    print(f"BACKEND2 STRUCTURAL ARTEFACTS (not present as structured fields in legacy):")
    print(f"  sections with thesis line:   {n_thesis}")
    print(f"  framework_tables (struct):   {n_fw}")
    print(f"  causal_chain rows:           {n_causal}")
    print(f"  case_studies:                {n_cs}")
    print(f"  'so_what' callouts:          {n_so_what}")
    print(f"  contrarian_claims:           {len(outline.get('contrarian_claims') or [])}")
    print(f"  key_stats:                   {len(outline.get('key_stats') or [])}")
    print()

    # backend2 verifier output (post-hoc grounding)
    verif = backend2_raw.get("verification") or {}
    print(f"BACKEND2 VERIFIER (a8.5):")
    print(f"  grounding_score:  {verif.get('grounding_score')}")
    print(f"  total/verified:   {verif.get('total_claims')}/{verif.get('verified_claims')}")
    print(f"  fabricated:       {len(verif.get('fabricated') or [])}")
    print(f"  uncertain:        {len(verif.get('uncertain') or [])}")
    print()

    # legacy evaluation scores
    legacy_eval = next((e for e in (legacy_report.get("evaluations") or [])
                        if e.get("layer") == 2), None)
    if legacy_eval:
        print(f"LEGACY L2 EVALUATION SCORES:")
        for k, v in (legacy_eval.get("scores") or {}).items():
            if isinstance(v, dict):
                print(f"  {k:<22} {v.get('score', '?')}/10")


if __name__ == "__main__":
    main()

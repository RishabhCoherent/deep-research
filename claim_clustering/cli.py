"""CLI for claim_clustering.

Usage:
    python -m claim_clustering.cli "GPU market size 2024"
    python -m claim_clustering.cli "EV charging Europe" --scale deep --open
    python -m claim_clustering.cli "lithium battery market" --scale compact

Default scale is `standard` (~70 sources, ~$0.47/run). Pick `compact` for fast
iteration or `deep`/`exhaustive` for one-shot deep research. Individual flags
(--sources, --max-cost, --max-per-query) override the preset.

Writes four artefacts per run:
    <out>/clusters.html   - interactive viewer (auto-opens with --open)
    <out>/run.json        - full ClusteringRun (estimates + dimensions + stats)
    <out>/raw_claims.json - every RawClaim with full provenance
    <out>/sources.json    - URL/tier/rank per source for auditing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from .pipeline import run as run_pipeline, SCALE_PRESETS
from .visualise import write_html, write_json


def _default_out_dir(topic: str) -> Path:
    slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic).strip()
    slug = slug.replace(" ", "_")[:40] or "run"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("claim_clustering") / "runs" / f"{stamp}_{slug}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claim_clustering",
        description="Cluster numeric claims from web research on a topic.",
    )
    parser.add_argument("topic", help="Research topic (e.g. 'GPU market size 2024').")
    parser.add_argument("--scale",
                        choices=list(SCALE_PRESETS.keys()),
                        default="standard",
                        help="Preset for source-count + per-query depth + cost ceiling. "
                             "compact = ~25 sources / ~$0.18, "
                             "standard = ~70 sources / ~$0.47 (default), "
                             "deep = ~150 sources / ~$1.00, "
                             "exhaustive = ~500 sources / ~$3.40. "
                             "Individual --sources / --max-cost / --max-per-query override.")
    parser.add_argument("--sources", type=int, default=None,
                        help="Override max sources (default: from --scale preset).")
    parser.add_argument("--max-per-query", type=int, default=None,
                        help="Override per-query SearXNG result depth (default: from --scale preset).")
    parser.add_argument("--max-cost", type=float, default=None,
                        help="Override cost ceiling in USD (default: from --scale preset). "
                             "If estimated cost exceeds this, source list is trimmed by tier+rank.")
    parser.add_argument("--scrape-workers", type=int, default=None,
                        help="Override parallel scrape worker count (default: from --scale preset). "
                             "Higher = faster scraping but more concurrent network/CPU load.")
    parser.add_argument("--playwright-budget", type=int, default=None,
                        help="Override max concurrent Playwright (headless browser) instances "
                             "(default: from --scale preset). Headless browsers are heavy; "
                             "this caps how many tier-3 escalations run at once.")
    parser.add_argument("--extra-query", action="append", default=None,
                        help="Additional query variants. Pass multiple times. "
                             "Stacks ON TOP of auto-expanded queries.")
    parser.add_argument("--no-auto-expand", action="store_true", default=False,
                        help="Disable automatic LLM-based query expansion "
                             "(default: enabled, ~$0.001 cost; produces 25-40 "
                             "diverse sub-queries to maximise URL diversity).")
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="Extractor LLM model (default gpt-4o-mini).")
    parser.add_argument("--describer-model", default="gpt-4o",
                        help="Descriptor-generation model (default gpt-4o; "
                             "more expensive but produces sharper distinctions).")
    parser.add_argument("--judge-model", default="gpt-4o-mini",
                        help="Cluster-judge model (default gpt-4o-mini).")
    parser.add_argument("--auto-merge", type=float, default=0.92,
                        help="Cosine similarity at/above which descriptors auto-merge (default 0.92).")
    parser.add_argument("--auto-separate", type=float, default=0.70,
                        help="Cosine similarity below which descriptors stay separate (default 0.70).")
    parser.add_argument("--no-validate", action="store_true", default=False,
                        help="Skip the LLM post-cluster validator (faster, less precise).")
    parser.add_argument("--describer-mode",
                        choices=["template", "llm"],
                        default="template",
                        help="How to generate cluster descriptors: "
                             "'template' (free, deterministic Python) or "
                             "'llm' (gpt-4o, ~$0.0006/claim, more natural). "
                             "Default: template.")
    parser.add_argument("--clusterer-mode",
                        choices=["hash", "cosine"],
                        default="hash",
                        help="How to group claims into clusters: "
                             "'hash' (qualifier-hash + Jaro-Winkler fuzzy merge, "
                             "free, deterministic) or 'cosine' (descriptor "
                             "embedding + LLM judge for gray zone, ~$0.005/run). "
                             "Default: hash.")
    parser.add_argument("--relevance-threshold", type=float, default=0.30,
                        help="Cosine cutoff (0.0-1.0) below which a claim is "
                             "flagged off-topic and shown in a collapsed "
                             "'out-of-scope' section instead of clustered. "
                             "Lower = more permissive. Default 0.30.")
    parser.add_argument("--show-profile", action="store_true", default=False,
                        help="Print the generated TopicProfile to stdout at "
                             "run start so you can audit what the run is "
                             "optimising for (also rendered in the HTML viewer).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output directory (default: claim_clustering/runs/<ts>_<slug>).")
    parser.add_argument("--open", action="store_true", default=False,
                        help="Open the HTML viewer in the default browser when done.")
    args = parser.parse_args(argv)

    out_dir = args.out or _default_out_dir(args.topic)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[cli] output dir: {out_dir}")

    # Resolve scale preset → concrete numbers, then let individual flags override
    preset = SCALE_PRESETS[args.scale]
    max_sources       = args.sources           if args.sources           is not None else preset["max_sources"]
    max_per_query     = args.max_per_query     if args.max_per_query     is not None else preset["max_per_query"]
    max_cost          = args.max_cost          if args.max_cost          is not None else preset["max_cost"]
    scrape_workers    = args.scrape_workers    if args.scrape_workers    is not None else preset["scrape_workers"]
    playwright_budget = args.playwright_budget if args.playwright_budget is not None else preset["playwright_budget"]
    print(f"[cli] scale={args.scale} ({preset['label']}) -> "
          f"max_sources={max_sources}, max_per_query={max_per_query}, "
          f"max_cost=${max_cost:.2f}, scrape_workers={scrape_workers}, "
          f"pw_budget={playwright_budget}")

    def progress(msg: str) -> None:
        print(msg)

    run_artefact, sources, raw_claims = run_pipeline(
        topic=args.topic,
        max_sources=max_sources,
        extra_queries=args.extra_query,
        extractor_model=args.model,
        describer_model=args.describer_model,
        judge_model=args.judge_model,
        auto_merge=args.auto_merge,
        auto_separate=args.auto_separate,
        validate_clusters=not args.no_validate,
        max_per_query=max_per_query,
        max_cost=max_cost,
        auto_expand_queries=not args.no_auto_expand,
        describer_mode=args.describer_mode,
        clusterer_mode=args.clusterer_mode,
        scrape_workers=scrape_workers,
        playwright_budget=playwright_budget,
        relevance_threshold=args.relevance_threshold,
        show_profile=args.show_profile,
        on_progress=progress,
    )

    # Persist
    html_path = write_html(run_artefact, out_dir / "clusters.html")
    write_json(run_artefact, out_dir / "run.json")
    (out_dir / "raw_claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in raw_claims], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "sources.json").write_text(
        json.dumps(
            [{"url": s.url, "title": s.title, "domain": s.domain, "tier": s.tier,
              "rank": s.rank, "full_text_len": len(s.full_text)} for s in sources],
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Console summary
    print()
    print(f"[cli] wrote:")
    print(f"       {html_path}   <- open this in a browser")
    print(f"       {out_dir / 'run.json'}")
    print(f"       {out_dir / 'raw_claims.json'}")
    print(f"       {out_dir / 'sources.json'}")
    print()
    print(f"[cli] summary: {run_artefact.n_raw_claims} claims -> "
          f"{run_artefact.n_dimensions} dimensions "
          f"({sum(1 for e in run_artefact.estimates if e.n_unique_sources >= 2)} multi-source)")
    print(f"[cli] cost:    extract=${run_artefact.cost_extract_usd:.4f}  "
          f"describe=${run_artefact.cost_describe_usd:.4f}  "
          f"embed=${run_artefact.cost_embed_usd:.5f}  "
          f"judge=${run_artefact.cost_judge_usd:.4f}  "
          f"validate=${run_artefact.cost_validate_usd:.4f}  "
          f"TOTAL=${run_artefact.cost_total_usd:.4f}")

    if args.open:
        try:
            webbrowser.open(html_path.resolve().as_uri())
        except Exception as exc:
            print(f"[cli] could not auto-open: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Standalone test harness for backend2's clustering module.

Goal: iterate fast on backend2/research/clustering/ without spinning up the
full agent pipeline. Pulls claims from any source, runs them through the
clustering, renders an HTML report using claim_clustering's existing
visualise.render_html, and prints the path.

Usage:
    # 1. Run on a finished pipeline checkpoint (real claims):
    python test_clustering.py checkpoint <thread_id>

    # 2. Run on a hand-curated fixture (reproducible, no DB dependency):
    python test_clustering.py fixture path/to/claims.json

    # 3. Use a thread_id prefix (first job whose UUID starts with the prefix):
    python test_clustering.py checkpoint 920cfa02

After each run, the HTML report opens in your default browser. Re-run after
editing backend2/research/clustering/* to see the new output.

Output goes to backend2/clustering_test_runs/<topic-slug>/run.html and
.../run.json.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make sibling claim_clustering importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# backend2 modules
from research.clustering import cluster_numeric_claims
from research.core.types import (
    AuthorityTier, Citation, NumericClaim,
)
from research.graph.build import _DEFAULT_DB

# claim_clustering modules (the visualiser)
from claim_clustering.models import (
    ClaimDimension as CCDimension,
    ClusteredEstimate as CCEstimate,
    ClusteringRun as CCRun,
    RawClaim as CCRawClaim,
    TopicProfile as CCTopicProfile,
)
from claim_clustering.visualise import write_html, write_json


# ── Schema bridge: backend2 result -> claim_clustering visualiser ──────────

# claim_clustering's UnitFamily is a strict subset of backend2's. backend2
# adds months/days/score/count which the visualiser can't validate. Map
# anything outside the visualiser's vocabulary to "unknown" so render works.
_CC_UNIT_FAMILY_VALUES = {
    "USD", "EUR", "GBP", "INR", "CNY", "JPY",
    "percent", "units", "usd_per_unit", "ratio", "unknown",
}


def _coerce_unit_family(family: str) -> str:
    return family if family in _CC_UNIT_FAMILY_VALUES else "unknown"


def _b2_to_cc_estimate(b2_dict: dict[str, Any]) -> CCEstimate:
    """Convert one backend2 ClusteredEstimate (already model_dump'd to dict)
    into a claim_clustering ClusteredEstimate. Both schemas share field names;
    we only need to downgrade unit_family + drop topic-relevance fields the
    visualiser doesn't read."""
    dim_in = b2_dict.get("dimension") or {}
    fam = _coerce_unit_family(dim_in.get("unit_family", "unknown"))
    dim = CCDimension(
        descriptor=dim_in.get("descriptor", "(no descriptor)"),
        unit_family=fam,
        qualifier_summary=dim_in.get("qualifier_summary", {}),
    )

    cc_claims: list[CCRawClaim] = []
    for c in b2_dict.get("claims") or []:
        cc_claims.append(CCRawClaim(
            source_url=c.get("source_url", ""),
            source_domain=c.get("source_domain", ""),
            source_title=c.get("source_title"),
            source_tier=c.get("source_tier", "unknown"),
            published_at=c.get("published_at"),
            raw_text=(c.get("raw_text") or "")[:600],
            value_raw=str(c.get("value_raw", "")),
            value=float(c.get("value", 0.0) or 0.0),
            unit_raw=c.get("unit_raw", ""),
            unit_family=_coerce_unit_family(c.get("unit_family", "unknown")),
            unit_magnitude_hint=c.get("unit_magnitude_hint"),
            qualifiers=c.get("qualifiers") or {},
            rank=c.get("rank", "normal"),
            descriptor=c.get("descriptor", ""),
            extractor_confidence=float(c.get("extractor_confidence", 0.7) or 0.7),
        ))

    return CCEstimate(
        dimension=dim,
        claims=cc_claims,
        n_claims=int(b2_dict.get("n_claims", 0)),
        n_unique_sources=int(b2_dict.get("n_unique_sources", 0)),
        values=list(b2_dict.get("values") or []),
        mean=float(b2_dict.get("mean", 0.0) or 0.0),
        weighted_mean=float(b2_dict.get("weighted_mean", 0.0) or 0.0),
        median=float(b2_dict.get("median", 0.0) or 0.0),
        stddev=float(b2_dict.get("stddev", 0.0) or 0.0),
        min_value=float(b2_dict.get("min_value", 0.0) or 0.0),
        max_value=float(b2_dict.get("max_value", 0.0) or 0.0),
        pct_spread=float(b2_dict.get("pct_spread", 0.0) or 0.0),
        consensus_level=b2_dict.get("consensus_level", "single_source"),
        outlier_claim_indices=list(b2_dict.get("outlier_claim_indices") or []),
        trend_slope_pct_per_year=b2_dict.get("trend_slope_pct_per_year"),
        family_id=b2_dict.get("family_id"),
    )


def _cc_topic_profile_from_dict(d: dict | None) -> CCTopicProfile | None:
    if not d:
        return None
    try:
        return CCTopicProfile(
            topic_subject=d.get("topic_subject", ""),
            topic_domain=d.get("topic_domain", "unknown"),
            expected_metric_kinds=d.get("expected_metric_kinds", []) or [],
            key_dimensions=d.get("key_dimensions", []) or [],
            positive_signals=d.get("positive_signals", []) or [],
            negative_signals=d.get("negative_signals", []) or [],
            expected_unit_families=d.get("expected_unit_families", []) or [],
            profile_reasoning=d.get("profile_reasoning", ""),
        )
    except Exception:
        return None


# ── Source loaders ─────────────────────────────────────────────────────────

def _load_claims_from_checkpoint(thread_id_prefix: str) -> tuple[
    list[NumericClaim], str, dict | None
]:
    """Pull NumericClaims out of the latest checkpoint for any thread whose
    id starts with `thread_id_prefix`. Returns (claims, topic, topic_profile_dict)."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path = str(_DEFAULT_DB)
    if not Path(db_path).exists():
        raise FileNotFoundError(f"checkpoint DB not found: {db_path}")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)

    latest_state: dict | None = None
    latest_ts = ""
    matched_tid: str | None = None
    for tup in saver.list(config=None, limit=400):
        cfg = tup.config.get("configurable", {}) if tup.config else {}
        tid = cfg.get("thread_id", "")
        if not tid.startswith(thread_id_prefix):
            continue
        ts = (tup.checkpoint or {}).get("ts", "")
        if ts > latest_ts:
            latest_ts = ts
            latest_state = (tup.checkpoint or {}).get("channel_values", {}) or {}
            matched_tid = tid

    if latest_state is None:
        raise ValueError(f"no checkpoint matches thread_id prefix '{thread_id_prefix}'")

    print(f"  matched thread_id: {matched_tid}")
    print(f"  checkpoint ts:     {latest_ts}")

    topic = latest_state.get("original_query") or "(unknown topic)"
    profile = latest_state.get("topic_profile") or None

    claim_dicts: list[dict] = []
    for bucket in ("topic_claims", "market_claims", "news_claims"):
        for c in (latest_state.get(bucket) or []):
            if isinstance(c, dict):
                claim_dicts.append(c)
            elif hasattr(c, "model_dump"):
                claim_dicts.append(c.model_dump())

    claims: list[NumericClaim] = []
    for cd in claim_dicts:
        try:
            cit_in = cd.get("citation") or {}
            cit = Citation(
                url=cit_in.get("url", ""),
                title=cit_in.get("title"),
                publisher=cit_in.get("publisher"),
                published=cit_in.get("published"),
                accessed=cit_in.get("accessed") or "",
                authority_tier=AuthorityTier(cit_in.get("authority_tier", "blog")),
            )
            claims.append(NumericClaim(
                metric=cd.get("metric") or "",
                value=cd.get("value") or 0.0,
                unit=cd.get("unit") or "",
                as_of=cd.get("as_of"),
                scope=cd.get("scope"),
                raw_excerpt=cd.get("raw_excerpt") or "",
                citation=cit,
                qualifiers=cd.get("qualifiers") or {},
            ))
        except Exception as exc:
            print(f"  skipped claim: {exc}")

    return claims, topic, profile


def _load_claims_from_fixture(path: str) -> tuple[
    list[NumericClaim], str, dict | None
]:
    """Load claims from a fixture JSON. Expected shape:
    {
      "topic": "...",
      "topic_profile": {...} | null,
      "claims": [ {NumericClaim-shaped dict}, ... ]
    }"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    topic = raw.get("topic") or path
    profile = raw.get("topic_profile")
    claims: list[NumericClaim] = []
    for cd in raw.get("claims") or []:
        cit_in = cd.get("citation") or {}
        cit = Citation(
            url=cit_in.get("url", ""),
            title=cit_in.get("title"),
            publisher=cit_in.get("publisher"),
            published=cit_in.get("published"),
            accessed=cit_in.get("accessed") or "",
            authority_tier=AuthorityTier(cit_in.get("authority_tier", "blog")),
        )
        claims.append(NumericClaim(
            metric=cd.get("metric") or "",
            value=cd.get("value") or 0.0,
            unit=cd.get("unit") or "",
            as_of=cd.get("as_of"),
            scope=cd.get("scope"),
            raw_excerpt=cd.get("raw_excerpt") or "",
            citation=cit,
            qualifiers=cd.get("qualifiers") or {},
        ))
    return claims, topic, profile


# ── Main harness ───────────────────────────────────────────────────────────

def _slug(s: str, maxlen: int = 50) -> str:
    out = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in s.lower())
    out = "-".join(filter(None, out.split("-")))
    return (out[:maxlen]).strip("-") or "run"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_ck = sub.add_parser("checkpoint", help="Load claims from a checkpointed run")
    sp_ck.add_argument("thread_id", help="thread_id or prefix (e.g. '920cfa02')")

    sp_fx = sub.add_parser("fixture", help="Load claims from a hand-built JSON fixture")
    sp_fx.add_argument("path", help="path to fixture JSON")

    ap.add_argument("--no-open", action="store_true",
                    help="Skip auto-opening the HTML in browser")
    ap.add_argument("--out-dir", default=str(Path(__file__).parent / "clustering_test_runs"),
                    help="Where to write run.html / run.json")
    ap.add_argument("--fuzzy", type=float, default=0.88,
                    help="Jaro-Winkler fuzzy threshold (default 0.88)")
    args = ap.parse_args()

    print(f"[harness] loading claims via: {args.cmd}")
    if args.cmd == "checkpoint":
        claims, topic, profile = _load_claims_from_checkpoint(args.thread_id)
    else:
        claims, topic, profile = _load_claims_from_fixture(args.path)

    print(f"[harness] topic: {topic[:80]}")
    print(f"[harness] {len(claims)} NumericClaims loaded")
    if not claims:
        print("[harness] nothing to cluster — exiting")
        return 1

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[harness] running cluster_numeric_claims(fuzzy_threshold={args.fuzzy}) ...")
    estimates = cluster_numeric_claims(
        claims,
        fuzzy_threshold=args.fuzzy,
        on_progress=lambda msg: print(f"  {msg}"),
    )
    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"[harness] {len(estimates)} clusters produced "
          f"({sum(1 for e in estimates if e.n_unique_sources >= 2)} multi-source)")

    # Native backend2 stats — pre-visualiser-downgrade. The HTML report's
    # unit-family chart will show `count`/`months`/`days` etc. as `unknown`
    # because claim_clustering's enum is narrower; this print is the truth.
    from collections import Counter
    fam_counts = Counter(e.dimension.unit_family for e in estimates)
    print(f"[harness] native unit-family distribution:")
    for k, v in fam_counts.most_common():
        print(f"            {k:<14} {v}")

    # Bridge to claim_clustering visualiser
    cc_estimates = [_b2_to_cc_estimate(e.model_dump(mode="json")) for e in estimates]
    cc_profile = _cc_topic_profile_from_dict(profile)

    run = CCRun(
        topic=topic,
        started_at=started,
        finished_at=finished,
        n_sources_searched=len({c.citation.url for c in claims}),
        n_sources_with_claims=len({c.citation.url for c in claims}),
        n_raw_claims=len(claims),
        n_dimensions=len(cc_estimates),
        estimates=cc_estimates,
        topic_profile=cc_profile,
    )

    out_dir = Path(args.out_dir) / _slug(topic)
    html_path = out_dir / "run.html"
    json_path = out_dir / "run.json"
    write_html(run, html_path)
    write_json(run, json_path)

    print()
    print(f"[harness] HTML: {html_path}")
    print(f"[harness] JSON: {json_path}")

    if not args.no_open:
        webbrowser.open(html_path.as_uri())

    return 0


if __name__ == "__main__":
    sys.exit(main())

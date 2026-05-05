"""
Scraper diagnostic — exposes every step of the pipeline:
  STEP 1  : URL discovery (SearXNG / DDG) — all candidates
  STEP 2  : BM25 re-rank — scores + ranked order
  STEP 3  : Per-URL fetch — tier used, content length
  STEP 4  : Full content (preview + tail) for each fetched result
  STEP 5  : Qualitative candidates extracted from content
  STEP 6  : Cache stats

Usage:
    python show_scraper_output.py [query] [max_results]

Default query: "perovskite solar cell commercialization barriers 2025"
"""
import sys
import concurrent.futures
import time
import textwrap
from datetime import date

from research.tools.smartcrawler_search import (
    _bm25_rerank, _fetch_and_extract, _cache_key, _load_cache, _save_cache,
    _FETCH_TIMEOUT, _MAX_WORKERS,
)
from research.tools.passage_cache import cache_stats
from research.crews.a3_topic_researcher.numeric_prefilter import find_qualitative_candidates
from research.core.types import Passage

# ── Config ────────────────────────────────────────────────────────────────────
QUERY       = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
              "perovskite solar cell commercialization barriers 2025"
MAX_RESULTS = 5
OUT_FILE    = "scraper_output.txt"
SEP         = "-" * 80
THICK       = "=" * 80

# ── Tee stdout → file ─────────────────────────────────────────────────────────
_file_out    = open(OUT_FILE, "w", encoding="utf-8")
_orig_stdout = sys.stdout

class _Tee:
    def write(self, msg): _orig_stdout.write(msg); _file_out.write(msg)
    def flush(self):      _orig_stdout.flush();    _file_out.flush()

sys.stdout = _Tee()

# ── Helpers ───────────────────────────────────────────────────────────────────
def tier_badge(tier: str) -> str:
    m = {"httpx": "httpx    ", "jina": "JINA ✓  ", "jina-pdf": "JINA-PDF ",
         "scrapling": "scrapling", "playwright": "playwright", "none": "FAILED   "}
    if tier.startswith("cache:"):
        return f"[CACHE({tier[6:]:8})]"
    return f"[{m.get(tier, tier[:9]):<9}]"

def wrap(text, indent=4, width=76):
    return textwrap.fill(text, width, initial_indent=" "*indent,
                         subsequent_indent=" "*indent)

def relevance_label(bm25: float) -> str:
    if bm25 >= 3.0: return "HIGH  ●●●"
    if bm25 >= 1.0: return "MED   ●●○"
    return              "LOW   ●○○"

# ─────────────────────────────────────────────────────────────────────────────
print(THICK)
print(f"  SCRAPER DIAGNOSTIC")
print(f"  Query      : {QUERY}")
print(f"  Max results: {MAX_RESULTS}")
print(THICK)

pre = cache_stats()
print(f"\n[passage cache] {pre['total_passages']} passages stored | "
      f"{pre['fetched_today']} today | {pre['db_size_mb']} MB")

# ── STEP 1: URL Discovery ────────────────────────────────────────────────────
print(f"\n{THICK}")
print(f"  STEP 1 — URL DISCOVERY")
print(THICK)

t0 = time.time()
seed_count = max(MAX_RESULTS * 2, 10)
seed: list[dict] = []
backend_used = "none"

try:
    from research.tools.searxng import search_searxng, is_searxng_available
    if is_searxng_available():
        seed = search_searxng(QUERY, max_results=seed_count)
        if seed: backend_used = "searxng"
except Exception: pass

if not seed:
    try:
        from research.tools.ddg import search_ddg, is_ddg_available
        if is_ddg_available():
            seed = search_ddg(QUERY, max_results=seed_count)
            if seed: backend_used = "ddg"
    except Exception: pass

t_discover = time.time() - t0
print(f"\n  Backend  : {backend_used.upper()}")
print(f"  Found    : {len(seed)} candidates in {t_discover:.1f}s")
print(f"\n  {'#':<3}  {'Title':<55}  {'Snippet (50 chars)'}")
print(f"  {'-'*3}  {'-'*55}  {'-'*50}")
for i, s in enumerate(seed, 1):
    title   = (s.get("title") or "")[:54]
    snippet = (s.get("snippet") or "")[:50].replace("\n", " ")
    print(f"  {i:<3}  {title:<55}  {snippet}")

if not seed:
    print("  ERROR: no URL discovery backend available — aborting")
    sys.stdout = _orig_stdout; _file_out.close()
    sys.exit(1)

# ── STEP 2: BM25 Re-rank ─────────────────────────────────────────────────────
print(f"\n{THICK}")
print(f"  STEP 2 — BM25 RE-RANK  (query relevance scoring)")
print(THICK)

# Score each seed item before rerank (rough BM25 via reranking 1-at-a-time)
ranked = _bm25_rerank(seed, QUERY)

print(f"\n  Ranked order after BM25 (most relevant first):\n")
print(f"  {'Rank':<5}  {'Rel':<10}  {'Title':<58}")
print(f"  {'-'*5}  {'-'*10}  {'-'*58}")
for rank, item in enumerate(ranked, 1):
    title = (item.get("title") or item.get("url", ""))[:57]
    # Show original position to reveal how much ranking changed
    orig_pos = next((i+1 for i, s in enumerate(seed)
                     if s.get("url") == item.get("url")), "?")
    moved = f"(was #{orig_pos})" if orig_pos != rank else "(no change)"
    print(f"  {rank:<5}  {'':10}  {title:<58}  {moved}")

# ── STEP 3 + 4: Fetch + Show Content ─────────────────────────────────────────
print(f"\n{THICK}")
print(f"  STEP 3 — FETCHING CONTENT  (tier cascade per URL)")
print(THICK)

urls_to_fetch = [r["url"] for r in ranked if r.get("url")][:seed_count]
fetched: dict[str, dict] = {}

from research.tools.bot_bypass import PlaywrightBudget
pw_budget = PlaywrightBudget(2)

t_fetch_start = time.time()
with concurrent.futures.ThreadPoolExecutor(
    max_workers=_MAX_WORKERS, thread_name_prefix="sc_fetch_"
) as pool:
    future_to_url = {pool.submit(_fetch_and_extract, u, pw_budget): u
                     for u in urls_to_fetch}
    done, _ = concurrent.futures.wait(future_to_url, timeout=60)
    for fut in done:
        url = future_to_url[fut]
        try:
            fetched[url] = fut.result()
        except Exception:
            fetched[url] = {"url": url, "title": "", "content": "",
                            "published": None, "success": False, "tier": "none"}
t_fetch = time.time() - t_fetch_start

print(f"\n  Fetched {len(fetched)} URLs in {t_fetch:.1f}s\n")
print(f"  {'#':<3}  {'Tier':<13}  {'Chars':>7}  Title")
print(f"  {'-'*3}  {'-'*13}  {'-'*7}  {'-'*55}")
for i, url in enumerate(urls_to_fetch, 1):
    f = fetched.get(url, {})
    t = f.get("tier", "none")
    c = len(f.get("content", ""))
    title = (f.get("title") or next((s.get("title","") for s in seed
             if s.get("url")==url), ""))[:54]
    ok = "✓" if f.get("success") else "✗"
    print(f"  {i:<3}  {tier_badge(t):<13}  {c:>7,}  {ok} {title}")

# ── STEP 4: Full content for top MAX_RESULTS ─────────────────────────────────
print(f"\n{THICK}")
print(f"  STEP 4 — FULL CONTENT  (top {MAX_RESULTS} by content length)")
print(THICK)

enriched = []
for item in ranked:
    url = item.get("url","")
    f = fetched.get(url, {})
    if f.get("success") and f.get("content"):
        enriched.append({**item, **f, "full_text": f["content"]})

enriched.sort(key=lambda r: len(r.get("full_text","")), reverse=True)
enriched = enriched[:MAX_RESULTS]

passages_for_qual = []

for i, r in enumerate(enriched, 1):
    url       = r.get("url","")
    title     = r.get("title") or "(no title)"
    full_text = r.get("full_text","")
    tier      = r.get("tier","?")
    published = r.get("published") or "unknown"

    print(f"\n{SEP}")
    print(f"  [{i}]  {tier_badge(tier)}  {len(full_text):,} chars  published={published}")
    print(f"  Title : {title[:75]}")
    print(f"  URL   : {url[:75]}")

    if full_text:
        print(f"\n  -- Content preview (first 1000 chars) --")
        for line in textwrap.wrap(full_text[:1000], width=74):
            print(f"    {line}")
        if len(full_text) > 1000:
            print(f"    ... [{len(full_text)-1000:,} more chars not shown]")
        print(f"\n  -- Content tail (last 500 chars) --")
        for line in textwrap.wrap(full_text[-500:], width=74):
            print(f"    {line}")
        passages_for_qual.append(Passage(url=url, title=title, text=full_text))

# ── STEP 5: Qualitative candidates ───────────────────────────────────────────
print(f"\n{THICK}")
print(f"  STEP 5 — QUALITATIVE CANDIDATES  (causal / policy / risk sentences)")
print(THICK)

qual = find_qualitative_candidates(passages_for_qual, max_per_passage=5, max_total=25)
if qual:
    for j, q in enumerate(qual, 1):
        print(f"\n  [{j:>2}]  score={q['score']:.1f}  source: {q['title'][:60]}")
        print(wrap(q["sentence"], indent=8))
else:
    print("  (none — no signal phrases matched)")

# ── STEP 6: Cache stats ───────────────────────────────────────────────────────
print(f"\n{THICK}")
print(f"  STEP 6 — CACHE STATS")
print(THICK)
post = cache_stats()
t_total = time.time() - t0
print(f"\n  Passages stored  : {post['total_passages']}  "
      f"(+{post['total_passages'] - pre['total_passages']} new this run)")
print(f"  Fetched today    : {post['fetched_today']}")
print(f"  DB size          : {post['db_size_mb']} MB")
print(f"\n  Timing breakdown:")
print(f"    Discovery  : {t_discover:.1f}s")
print(f"    Fetch      : {t_fetch:.1f}s")
print(f"    Total      : {t_total:.1f}s")
print(f"\n{THICK}\n")

sys.stdout = _orig_stdout
_file_out.close()
print(f"Full output saved → {OUT_FILE}")

"""Bot-bypass fetch tiers for smartcrawler_search.

Two fallback tiers used when plain httpx fails (CF challenge, JS-gated content,
curl_cffi-only TLS fingerprint checks):

  Tier 2: scrapling.AsyncFetcher  — curl_cffi Chrome TLS fingerprint
                                    Beats httpx on Cloudflare / Akamai / Shopify
  Tier 3: scrapling.DynamicFetcher — headless Playwright + JS execution
                                    Required for SPA sites, React-hydrated nav

Both tiers are optional. Install via:
    pip install "scrapling[fetchers]"
    playwright install chromium      # only needed for Tier 3

If the deps are missing the functions return "" and the caller falls back to
the previous tier's output. No crashes, no warnings on the hot path.

Reference: smartcrawler.py lines 306-375 (the original cascade).
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading

log = logging.getLogger(__name__)

_CF_RE = re.compile(
    r"just a moment|cf-browser-verification|enable javascript"
    r"|human verification|attention required",
    re.I,
)

_MIN_HTML_BYTES = 500


def _extract_html(resp: object) -> str:
    """Pull HTML out of a scrapling response object (shape varies by version)."""
    for attr in ("html_content", "html", "content", "body"):
        val = getattr(resp, attr, None)
        if callable(val):
            try:
                val = val()
            except Exception:
                val = None
        if val:
            s = str(val)
            if len(s) >= _MIN_HTML_BYTES:
                return s
    return ""


def _looks_blocked(html: str) -> bool:
    return bool(html) and bool(_CF_RE.search(html[:2_000]))


# ── Tier 2: scrapling AsyncFetcher (curl_cffi TLS fingerprint) ────────────────

_SCRAPLING_IMPORT_TRIED = False
_SCRAPLING_AVAILABLE = False
_AsyncFetcher = None  # type: ignore[var-annotated]


def _import_scrapling() -> bool:
    global _SCRAPLING_IMPORT_TRIED, _SCRAPLING_AVAILABLE, _AsyncFetcher
    if _SCRAPLING_IMPORT_TRIED:
        return _SCRAPLING_AVAILABLE
    _SCRAPLING_IMPORT_TRIED = True
    try:
        logging.getLogger("scrapling").setLevel(logging.CRITICAL)
        from scrapling.fetchers import AsyncFetcher  # type: ignore[import-not-found]

        try:
            AsyncFetcher.configure(huge_tree=True)  # silence deprecation
        except Exception:
            pass
        _AsyncFetcher = AsyncFetcher
        _SCRAPLING_AVAILABLE = True
    except Exception as exc:
        log.debug("[bot_bypass] scrapling unavailable: %s", exc)
    return _SCRAPLING_AVAILABLE


def scrapling_fetch(url: str, timeout: int = 15) -> str:
    """Tier 2: curl_cffi fetch with real Chrome TLS fingerprint.

    Returns HTML on success, "" on failure or if scrapling isn't installed.
    Retries with verify=False on SSL errors (matches original smartcrawler
    behavior — we only scrape public HTML).
    """
    if not _import_scrapling():
        return ""

    async def _run() -> str:
        fetcher = _AsyncFetcher()  # type: ignore[misc]
        # follow_redirects=False: SSRF defense (per smartcrawler.py L274-278)
        try:
            resp = await fetcher.get(
                url,
                timeout=timeout,
                stealthy_headers=True,
                follow_redirects=False,
                verify=True,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if not any(k in msg for k in ("ssl", "certificate", "tls")):
                raise
            resp = await fetcher.get(
                url,
                timeout=timeout,
                stealthy_headers=True,
                follow_redirects=False,
                verify=False,
            )
        status = getattr(resp, "status", 200)
        if status in (403, 405, 429):
            return ""
        return _extract_html(resp)

    try:
        # Each thread worker gets its own event loop; no conflict with parent asyncio.
        return asyncio.run(_run())
    except Exception as exc:
        log.debug("[bot_bypass] scrapling failed %s: %s", url[:80], exc)
        return ""


# ── Tier 3: Playwright via scrapling DynamicFetcher ───────────────────────────

_DYNAMIC_IMPORT_TRIED = False
_DYNAMIC_AVAILABLE = False
_DynamicFetcher = None  # type: ignore[var-annotated]


def _import_dynamic() -> bool:
    global _DYNAMIC_IMPORT_TRIED, _DYNAMIC_AVAILABLE, _DynamicFetcher
    if _DYNAMIC_IMPORT_TRIED:
        return _DYNAMIC_AVAILABLE
    _DYNAMIC_IMPORT_TRIED = True
    try:
        from scrapling.fetchers import DynamicFetcher  # type: ignore[import-not-found]

        _DynamicFetcher = DynamicFetcher
        _DYNAMIC_AVAILABLE = True
    except Exception as exc:
        log.debug("[bot_bypass] DynamicFetcher unavailable: %s", exc)
    return _DYNAMIC_AVAILABLE


class PlaywrightBudget:
    """Thread-safe counter limiting total Playwright invocations per caller.

    Playwright renders are 5-20s and CPU-heavy; without a cap a single search
    can spawn one browser per URL. Shared across all worker threads in a
    ThreadPoolExecutor via the same instance.
    """

    __slots__ = ("_remaining", "_lock")

    def __init__(self, n: int) -> None:
        self._remaining = max(0, int(n))
        self._lock = threading.Lock()

    def consume(self) -> bool:
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._remaining


def playwright_fetch(url: str, budget: PlaywrightBudget, timeout: int = 20) -> str:
    """Tier 3: headless Playwright render. Bounded by `budget`.

    Returns "" if: budget exhausted, playwright not installed, browser not
    installed, or page never resolves. Never raises.
    """
    if not _import_dynamic():
        return ""
    if not budget.consume():
        log.debug("[bot_bypass] playwright budget exhausted, skipping %s", url[:80])
        return ""
    try:
        # DynamicFetcher.fetch is synchronous (wraps playwright sync API).
        resp = _DynamicFetcher.fetch(  # type: ignore[misc]
            url,
            headless=True,
            network_idle=True,
            disable_resources=True,
        )
        return _extract_html(resp)
    except Exception as exc:
        log.debug("[bot_bypass] playwright failed %s: %s", url[:80], exc)
        return ""


def tier_availability() -> dict[str, bool]:
    """Report which tiers have their deps installed. Useful for startup logs."""
    return {
        "scrapling": _import_scrapling(),
        "playwright": _import_dynamic(),
    }

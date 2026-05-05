"""Jina Reader integration for clean markdown content extraction.

Jina Reader (https://jina.ai/reader/) fetches any URL and returns clean
markdown, handling JS-rendered pages, some paywalls, and PDFs — without
needing a local headless browser.

Free tier : 10 RPM  (no key needed)
With key  : 200 RPM (set JINA_API_KEY env var)

Usage in the fetch tier cascade:
  Tier 1.5 — tried after thin httpx extraction, before scrapling.
  Returns clean markdown that feeds directly into the passage pipeline.
"""
from __future__ import annotations

import os
import structlog
import httpx

log = structlog.get_logger(__name__)

_JINA_BASE    = "https://r.jina.ai/"
_JINA_API_KEY = os.getenv("JINA_API_KEY", "")

_FAIL_PREFIXES = ("Error:", "Unable to", "Failed to", "Access denied", "403 Forbidden")


def jina_fetch(url: str, timeout: float = 25.0) -> str:
    """Fetch clean markdown from Jina Reader for *url*.

    Returns article text as markdown string, or "" on failure.
    Never raises.
    """
    headers: dict[str, str] = {
        "Accept": "text/markdown",
        "X-Return-Format": "markdown",
        "X-With-Links-Summary": "false",
        "X-With-Images-Summary": "false",
        "X-Remove-Selector": "header, footer, nav, .nav, .navigation, .sidebar, #toc, .toc, .menu",
    }
    if _JINA_API_KEY:
        headers["Authorization"] = f"Bearer {_JINA_API_KEY}"

    try:
        resp = httpx.get(
            _JINA_BASE + url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            log.debug("[jina_reader] HTTP %d for %s", resp.status_code, url[:80])
            return ""
        text = resp.text.strip()
        if not text or any(text.startswith(p) for p in _FAIL_PREFIXES):
            return ""
        return text
    except Exception as exc:
        log.debug("[jina_reader] fetch error %s: %s", url[:80], exc)
        return ""


def jina_title(markdown: str) -> str:
    """Extract the first H1 heading from Jina markdown as a title."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def is_jina_available() -> bool:
    """Quick reachability probe. Returns True if r.jina.ai responds."""
    try:
        # Use a lightweight real fetch; Jina doesn't reliably respond to HEAD
        text = jina_fetch("https://example.com", timeout=8.0)
        return bool(text)
    except Exception:
        return False

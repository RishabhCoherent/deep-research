"""Async hybrid scraper: trafilatura (primary) → httpx + regex (fallback).

Standalone async function — NOT a LangChain @tool.
Called directly from Python fetch loops in A3/A4/A5 crew glue code.
Returns full article text (up to 20 000 chars), never raises.
"""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_scrape_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scrape_")

_BINARY_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".gz", ".tar", ".7z", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".mp4", ".mp3", ".wav",
}


async def hybrid_scrape(url: str, timeout: float = 20.0) -> dict:
    """Scrape a URL: trafilatura first, httpx+regex fallback.

    Args:
        url:     Full URL to scrape.
        timeout: Per-method timeout in seconds.

    Returns:
        {"url", "title", "content", "method", "success"}
        Always returns a dict — never raises.
    """
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _BINARY_EXTENSIONS):
        return {"url": url, "title": "", "content": "", "method": "skipped_binary", "success": False}

    result = await _scrape_trafilatura(url, timeout)
    if result["success"]:
        return result

    result = await _scrape_httpx(url, timeout)
    if result["success"]:
        return result

    logger.debug(f"[hybrid_scrape] all methods failed: {url[:80]}")
    return {"url": url, "title": "", "content": "", "method": "all_failed", "success": False}


async def _scrape_trafilatura(url: str, timeout: float) -> dict:
    """Use trafilatura for article extraction (run in thread pool)."""
    try:
        import trafilatura

        def _sync_extract() -> tuple[str, str] | None:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                favor_precision=True,
                deduplicate=True,
            )
            metadata = trafilatura.extract_metadata(downloaded)
            title = metadata.title if metadata and metadata.title else ""
            return text, title

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(_scrape_executor, _sync_extract),
            timeout=timeout,
        )

        if result and result[0] and len(result[0]) > 100:
            text, title = result
            logger.debug(f"[hybrid_scrape] trafilatura ok: {url[:80]} ({len(text)} chars)")
            return {
                "url": url,
                "title": title,
                "content": text[:20_000],
                "method": "trafilatura",
                "success": True,
            }

    except asyncio.TimeoutError:
        logger.debug(f"[hybrid_scrape] trafilatura timeout: {url[:80]}")
    except Exception as exc:
        logger.debug(f"[hybrid_scrape] trafilatura error for {url[:80]}: {exc}")

    return {"url": url, "title": "", "content": "", "method": "trafilatura_failed", "success": False}


async def _scrape_httpx(url: str, timeout: float) -> dict:
    """Fallback: httpx AsyncClient + regex tag-stripping (no BS4 required)."""
    try:
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=False,
        ) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            return {
                "url": url, "title": "", "content": "",
                "method": f"httpx_{resp.status_code}", "success": False,
            }

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return {"url": url, "title": "", "content": "", "method": "httpx_not_html", "success": False}

        html = resp.text

        # Extract <title>
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).strip() if title_m else ""

        # Strip noisy elements, then all tags
        html = re.sub(
            r"<(script|style|nav|footer|header|aside|form)[^>]*>.*?</\1>",
            " ", html, flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > 100:
            logger.debug(f"[hybrid_scrape] httpx ok: {url[:80]} ({len(text)} chars)")
            return {
                "url": url,
                "title": title,
                "content": text[:20_000],
                "method": "httpx",
                "success": True,
            }

    except Exception as exc:
        logger.debug(f"[hybrid_scrape] httpx error for {url[:80]}: {exc}")

    return {"url": url, "title": "", "content": "", "method": "httpx_failed", "success": False}

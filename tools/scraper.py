"""
Web scraper using aiohttp + BeautifulSoup for page content extraction.
"""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# File extensions that cannot be scraped as HTML
_BINARY_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                      ".zip", ".rar", ".gz", ".tar", ".7z", ".exe", ".bin",
                      ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".mp4",
                      ".mp3", ".wav"}


async def scrape_url_basic(url: str) -> Optional[dict]:
    """Scrape a URL using aiohttp + BeautifulSoup."""
    try:
        # Skip binary files that can't be parsed as HTML
        path = urlparse(url).path.lower()
        if any(path.endswith(ext) for ext in _BINARY_EXTENSIONS):
            logger.debug(f"Skipping binary URL: {url}")
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with aiohttp.ClientSession(
            max_line_size=16384, max_field_size=16384,
        ) as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None

                # Check content-type — skip non-HTML responses
                content_type = resp.headers.get("Content-Type", "")
                if content_type and "text/html" not in content_type and "text/plain" not in content_type:
                    logger.debug(f"Skipping non-HTML content ({content_type}): {url}")
                    return None

                html = await resp.text(errors="replace")

        soup = BeautifulSoup(html, "html.parser")

        # Remove script/style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        title = soup.title.string if soup.title else ""

        # Extract text from main content areas
        content_tags = soup.find_all(["article", "main", "div", "section", "p"])
        text_parts = []
        for tag in content_tags:
            text = tag.get_text(strip=True)
            if len(text) > 50:  # Skip tiny fragments
                text_parts.append(text)

        content = "\n\n".join(text_parts)[:15000]

        if len(content) < 100:
            return None

        return {
            "url": url,
            "title": title or "",
            "content": content,
            "extraction_date": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.warning(f"Scraper failed for {url}: {e}")
    return None


async def scrape_url(url: str) -> Optional[dict]:
    """Scrape a URL for text content.

    Returns dict with {url, title, content, extraction_date} or None.
    """
    return await scrape_url_basic(url)

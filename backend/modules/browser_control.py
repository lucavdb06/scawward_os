"""
BrowserController — automated browser via Playwright.

Phase 1 features:
  * `search(query)`   → DuckDuckGo HTML search, parsed.
  * `read_url(url)`   → load URL, return cleaned text content.

Phase 2:
  * Fill forms, click flows, login state, scraping pipelines.

Designed as an async context manager so each call is leak-free:

    async with BrowserController() as br:
        text = await br.read_url("https://example.com")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class BrowserController:
    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._pw: Any | None = None
        self._browser: Any | None = None

    async def __aenter__(self) -> "BrowserController":
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    # ─── High-level operations ────────────────────────────────────
    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        page = await self._browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            html = await page.content()
        finally:
            await page.close()
        return [h.to_dict() for h in self._parse_ddg(html)[:max_results]]

    async def read_url(self, url: str) -> str:
        from bs4 import BeautifulSoup
        page = await self._browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            html = await page.content()
        finally:
            await page.close()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return text

    # ─── Parsers ──────────────────────────────────────────────────
    @staticmethod
    def _parse_ddg(html: str) -> list[SearchHit]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        hits: list[SearchHit] = []
        for r in soup.select(".result"):
            a = r.select_one(".result__a")
            s = r.select_one(".result__snippet")
            if not a:
                continue
            hits.append(SearchHit(
                title=a.get_text(strip=True),
                url=a.get("href", ""),
                snippet=s.get_text(" ", strip=True) if s else "",
            ))
        return hits

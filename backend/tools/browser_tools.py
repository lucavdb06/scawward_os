"""Web tools — light-weight HTTP-based search and fetch.

Phase 1 deliberately avoids Playwright for the common path:
- `web_search`  → DuckDuckGo via the `ddgs` library (pure HTTP, no browser)
- `web_fetch`   → `httpx` + BeautifulSoup, returns cleaned text

Playwright stays available via `backend/modules/browser_control.py` for
interactive flows (form fills, JS-heavy SPAs) — but we don't pay its 200 MB
startup cost on every search.
"""
from __future__ import annotations

import asyncio
import logging

from .registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


def register_browser_tools(reg: ToolRegistry) -> None:

    @reg.tool(
        name="web_search",
        description=(
            "Search the public web (DuckDuckGo) and return titles, URLs, and "
            "snippets. Use this whenever the user asks about current events, "
            "documentation, or anything outside your training data."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {
                    "type": "integer",
                    "description": "Default 5, max 15.",
                },
            },
            "required": ["query"],
        },
    )
    async def _search(query: str, max_results: int = 5) -> ToolResult:
        max_results = max(1, min(int(max_results), 15))

        def _do_search() -> list[dict[str, str]]:
            from ddgs import DDGS  # lazy: avoids slow import at startup
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": (r.get("title") or "").strip(),
                    "url": (r.get("href") or r.get("url") or "").strip(),
                    "snippet": (r.get("body") or "").strip(),
                }
                for r in raw
            ]

        try:
            results = await asyncio.to_thread(_do_search)
        except Exception as e:
            logger.exception("web_search failed")
            return ToolResult.fail(f"search failed: {e!r}")

        return ToolResult.success(
            f"{len(results)} result(s) for {query!r}",
            query=query,
            results=results,
        )

    @reg.tool(
        name="web_news",
        description=(
            "Search news articles on a topic (DuckDuckGo news). Returns "
            "title, source, date, URL, and short description."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    )
    async def _news(query: str, max_results: int = 5) -> ToolResult:
        max_results = max(1, min(int(max_results), 15))

        def _do_news() -> list[dict[str, str]]:
            from ddgs import DDGS
            with DDGS() as ddgs:
                raw = list(ddgs.news(query, max_results=max_results))
            return [
                {
                    "title": (r.get("title") or "").strip(),
                    "source": (r.get("source") or "").strip(),
                    "date": (r.get("date") or "").strip(),
                    "url": (r.get("url") or r.get("href") or "").strip(),
                    "description": (r.get("body") or "").strip(),
                }
                for r in raw
            ]

        try:
            results = await asyncio.to_thread(_do_news)
        except Exception as e:
            logger.exception("web_news failed")
            return ToolResult.fail(f"news search failed: {e!r}")

        return ToolResult.success(
            f"{len(results)} news item(s) for {query!r}",
            query=query,
            results=results,
        )

    @reg.tool(
        name="web_fetch",
        description=(
            "Fetch a URL and return the cleaned readable text (no markup, no "
            "scripts, no nav). Static HTML only — fast, no browser. For "
            "JS-heavy pages, use a more advanced tool later."
        ),
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {
                    "type": "integer",
                    "description": "Cap on returned text length (default 50000).",
                },
            },
            "required": ["url"],
        },
    )
    async def _fetch(url: str, max_chars: int = 50_000) -> ToolResult:
        max_chars = max(1_000, min(int(max_chars), 200_000))
        try:
            import httpx
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36 Scawward/0.1"
                ),
            }
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=20.0,
                headers=headers,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ").split())
            title = (soup.title.string.strip() if soup.title and soup.title.string else "")

            return ToolResult.success(
                f"fetched {url} ({len(text)} chars)",
                url=url,
                title=title,
                text=text[:max_chars],
                truncated=len(text) > max_chars,
            )
        except Exception as e:
            logger.exception("web_fetch failed")
            return ToolResult.fail(f"fetch failed: {e!r}")

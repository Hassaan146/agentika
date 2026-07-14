"""Web search skill (SerpAPI / Google) + page-fetch fallback.

Originally planned on Brave Search API; switched to SerpAPI because the Brave
signup site was down (2026-07-13). Everything provider-specific is confined to
web_search(), so swapping providers is a one-function change.
"""

import httpx
from bs4 import BeautifulSoup

from config import settings
from models import FetchPageInput, SearchQuery, SearchResult, ToolResult
from utils import retry_http


def web_search(args: SearchQuery) -> ToolResult:
    def call():
        resp = httpx.get(
            "https://serpapi.com/search.json",
            params={
                "q": args.query,
                "engine": "google",
                "num": settings.search_count,
                "api_key": settings.serpapi_api_key,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp

    data = retry_http(call).json()

    results = []
    # Google answer box, when present, is usually the direct answer
    box = data.get("answer_box") or {}
    box_text = box.get("answer") or box.get("snippet")
    if box_text:
        results.append(
            SearchResult(title="[Google answer box]", url=box.get("link", ""), snippet=str(box_text))
        )
    for item in data.get("organic_results", [])[: settings.search_count]:
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
        )

    if not results:
        return ToolResult(ok=False, error=f"No search results for '{args.query}' - try different wording")
    return ToolResult(ok=True, data=[r.model_dump() for r in results])


def fetch_page(args: FetchPageInput) -> ToolResult:
    def call():
        resp = httpx.get(
            args.url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (research-agent)"},
        )
        resp.raise_for_status()
        return resp

    resp = retry_http(call)
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    if not text:
        return ToolResult(ok=False, error=f"No readable text at {args.url}")
    if len(text) > settings.fetch_max_chars:
        text = text[: settings.fetch_max_chars] + " [truncated]"
    return ToolResult(ok=True, data={"url": args.url, "content": text})

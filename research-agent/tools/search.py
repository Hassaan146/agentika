"""Web search skill (SerpAPI / Google) + page-fetch fallback.

Originally planned on Brave Search API; switched to SerpAPI because the Brave
signup site was down (2026-07-13). Everything provider-specific is confined to
web_search(), so swapping providers is a one-function change.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from config import settings
from models import FetchPageInput, SearchQuery, SearchResult, ToolResult
from utils import retry_http

FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (research-agent)"}


def _ssrf_reason(url: str) -> str | None:
    """Return a human-readable block reason if `url` is unsafe to fetch, else None.

    Blocks anything that is not http(s), and any host that resolves to a
    private / loopback / link-local / reserved address. Link-local covers the
    cloud metadata endpoint (169.254.169.254) - the classic SSRF target that
    leaks instance credentials. Returned as a normal reason (not raised) so the
    caller turns it into a ToolResult the model can read and adapt to.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"only http(s) URLs are allowed (got scheme '{parsed.scheme or 'none'}')"
    host = parsed.hostname
    if not host:
        return "URL has no host"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return f"could not resolve host '{host}'"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return f"host '{host}' resolves to a non-public address ({ip})"
    return None


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
            timeout=settings.http_timeout,
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
    # Follow redirects manually so every hop is SSRF-checked: a public URL that
    # 302s to http://169.254.169.254/ must be refused at the redirect, not just
    # at the first request. (httpx's follow_redirects=True would chase it for us.)
    url = args.url
    for _ in range(settings.http_max_redirects + 1):
        reason = _ssrf_reason(url)
        if reason:
            return ToolResult(ok=False, error=f"Refused to fetch {url}: {reason}")

        def call(target=url):
            resp = httpx.get(
                target, timeout=settings.http_timeout, follow_redirects=False, headers=FETCH_HEADERS
            )
            if not resp.is_redirect:
                resp.raise_for_status()  # retry transient 5xx on the final hop
            return resp

        resp = retry_http(call)
        if resp.is_redirect and resp.next_request is not None:
            url = str(resp.next_request.url)  # httpx resolves relative Location to absolute
            continue
        break
    else:
        return ToolResult(ok=False, error=f"Too many redirects fetching {args.url}")

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    if not text:
        return ToolResult(ok=False, error=f"No readable text at {args.url}")
    if len(text) > settings.fetch_max_chars:
        text = text[: settings.fetch_max_chars] + " [truncated]"
    return ToolResult(ok=True, data={"url": args.url, "content": text})

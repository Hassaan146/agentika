"""Tool registration - the plugin surface of the agent.

Adding a capability = write the function in a module here, then register it
below with a description (the description is what the LLM reads to decide
when to use the tool).
"""

from models import FetchPageInput, ReadFileInput, SearchQuery
from registry import ToolRegistry

from . import files, search


def register_all(registry: ToolRegistry) -> None:
    registry.register(
        SearchQuery,
        "Search the web (Google) and return the top results as title/url/snippet. "
        "Use this whenever you need current or factual information you don't reliably know.",
    )(search.web_search)

    registry.register(
        FetchPageInput,
        "Fetch the readable text of a specific web page. Use ONLY when web_search snippets "
        "are not enough to answer; pass a URL from a previous web_search result.",
    )(search.fetch_page)

    registry.register(
        ReadFileInput,
        "Read a .txt or .pdf document from the local docs/ folder. Use when the user refers "
        "to a file or document by name.",
    )(files.read_file)

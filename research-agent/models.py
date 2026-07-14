"""Pydantic schemas - single source of truth for tool inputs/outputs and memory facts.

Tool input models double as the JSON schema sent to the LLM (see registry.py),
so their docstrings/field descriptions are what the model reads when deciding
how to call a tool.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ---- Tool inputs -----------------------------------------------------------


class SearchQuery(BaseModel):
    query: str = Field(..., description="The web search query, e.g. 'current CEO of Anthropic'")


class FetchPageInput(BaseModel):
    url: str = Field(..., description="Full URL of a page to fetch, taken from a web_search result")


class ReadFileInput(BaseModel):
    path: str = Field(
        ...,
        description="Name of a .txt or .pdf file inside the docs/ folder, e.g. 'company_brief.txt'",
    )


# ---- Tool outputs ----------------------------------------------------------


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class ToolResult(BaseModel):
    """Every tool returns this; dispatch never raises. Errors go back to the
    model as readable text so it can adapt (retry, rephrase, other tool)."""

    ok: bool
    data: Any = None
    error: str | None = None

    def to_model_text(self) -> str:
        return self.model_dump_json(exclude_none=True)


# ---- Memory ----------------------------------------------------------------


class Fact(BaseModel):
    key: str
    value: str
    source_turn: int
    updated_at: datetime
    history: list[str] = []  # previous values when a fact is updated (auditable)

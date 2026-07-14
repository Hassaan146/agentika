"""Session memory - an internal subsystem of the agent, NOT a tool.

Write path (automatic): after each completed turn the agent calls
update_from_turn() with an LLM-backed extract_fn; durable facts are stored as
normalized key -> Fact.

Conflict policy: same key -> newest value overwrites, previous value is kept in
Fact.history (auditable). Recency wins ties in retrieval.

Read path (automatic): before each planner call the agent injects the top-k
facts scored by keyword overlap with the user message. Token-overlap scoring is
a deliberate simplicity choice over embeddings - transparent, dependency-free,
and good enough for a single session's worth of facts.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime

from models import Fact

_STOPWORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "and",
    "or",
    "it",
    "its",
    "this",
    "that",
    "what",
    "who",
    "which",
    "how",
    "did",
    "do",
    "does",
    "from",
    "with",
    "about",
    "we",
    "i",
    "you",
    "me",
    "my",
    "our",
    "their",
    "they",
    "he",
    "she",
    "his",
    "her",
}


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


class MemoryStore:
    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}

    # ---- write path ---------------------------------------------------------

    def remember(self, key: str, value: str, source_turn: int) -> None:
        k = _normalize_key(key)
        if not k or not value:
            return
        now = datetime.now(UTC)
        existing = self._facts.get(k)
        if existing:
            if existing.value != value:  # conflict: newest wins, history kept
                existing.history.append(existing.value)
                existing.value = value
                existing.source_turn = source_turn
                existing.updated_at = now
        else:
            self._facts[k] = Fact(key=k, value=value, source_turn=source_turn, updated_at=now)

    def update_from_turn(self, turn: int, user_msg: str, answer: str, extract_fn: Callable) -> None:
        """extract_fn(existing_keys, user_msg, answer) -> [{'key':..,'value':..}].
        Memory failures must never break the turn, so everything is caught."""
        try:
            for pair in extract_fn(list(self._facts), user_msg, answer):
                self.remember(str(pair.get("key", "")), str(pair.get("value", "")), turn)
        except Exception:
            pass

    # ---- read path ----------------------------------------------------------

    def search(self, query: str, k: int) -> list[Fact]:
        """Top-k facts by keyword overlap with the query; recency breaks ties.
        Zero-overlap facts still fill remaining slots (most recent first) so
        broad questions like 'summarize the session' see the memory too."""
        q = _tokens(query)
        scored = []
        for fact in self._facts.values():
            fact_tokens = _tokens(fact.key.replace("_", " ")) | _tokens(fact.value)
            scored.append((len(q & fact_tokens), fact.updated_at, fact))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [fact for _, _, fact in scored[:k]]

    def known_facts_block(self, query: str, k: int) -> str:
        facts = self.search(query, k)
        if not facts:
            return ""
        lines = [f"- {f.key.replace('_', ' ')}: {f.value}" for f in facts]
        return "Known facts from earlier in this session:\n" + "\n".join(lines)

    @property
    def facts(self) -> list[Fact]:
        return list(self._facts.values())

from memory import MemoryStore


def test_remember_and_normalize_key():
    memory = MemoryStore()
    memory.remember("Company Name!", "Anthropic", source_turn=1)
    assert memory.facts[0].key == "company_name"
    assert memory.facts[0].value == "Anthropic"


def test_conflict_overwrites_and_keeps_history():
    memory = MemoryStore()
    memory.remember("ceo", "Old Person", 1)
    memory.remember("ceo", "New Person", 2)
    fact = memory.facts[0]
    assert fact.value == "New Person"
    assert fact.history == ["Old Person"]
    assert fact.source_turn == 2
    assert len(memory.facts) == 1  # updated, not duplicated


def test_search_ranks_by_keyword_overlap():
    memory = MemoryStore()
    memory.remember("company_name", "Anthropic is an AI safety company", 1)
    memory.remember("favorite_food", "biryani", 1)
    results = memory.search("what company does AI safety?", k=2)
    assert results[0].key == "company_name"


def test_search_caps_at_top_k():
    memory = MemoryStore()
    for i in range(10):
        memory.remember(f"fact_{i}", f"value {i}", 1)
    assert len(memory.search("anything", k=5)) == 5


def test_zero_overlap_facts_still_fill_slots():
    memory = MemoryStore()
    memory.remember("company_name", "Anthropic", 1)
    results = memory.search("zzz qqq totally unrelated", k=3)
    assert len(results) == 1  # included as recency filler for broad questions


def test_update_from_turn_uses_extractor_and_never_raises():
    memory = MemoryStore()
    memory.update_from_turn(1, "u", "a", lambda keys, u, a: [{"key": "k1", "value": "v1"}])
    assert memory.facts[0].value == "v1"

    # a broken extractor must not break the turn
    def broken(keys, u, a):
        raise RuntimeError("llm down")

    memory.update_from_turn(2, "u", "a", broken)
    assert len(memory.facts) == 1


def test_known_facts_block_formatting():
    memory = MemoryStore()
    assert memory.known_facts_block("q", 5) == ""
    memory.remember("company_name", "Anthropic", 1)
    block = memory.known_facts_block("company", 5)
    assert "Known facts" in block and "company name: Anthropic" in block

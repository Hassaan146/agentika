"""HTTP-level tests: session isolation via cookies, input cap, rate limit,
new-session. A stub agent is injected so no Groq key or network is needed.
"""

from fastapi.testclient import TestClient

import server
from sessions import RateLimiter


class _StubAgent:
    def __init__(self):
        self.seen = []

    def run_turn(self, message: str) -> str:
        self.seen.append(message)
        return f"echo: {message}"


def _use_stub_agents(monkeypatch):
    created = []

    def factory():
        agent = _StubAgent()
        created.append(agent)
        return agent

    monkeypatch.setattr(server.session_manager, "_factory", factory)
    return created


def test_chat_happy_path(monkeypatch):
    _use_stub_agents(monkeypatch)
    client = TestClient(server.app)
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "ok" and body["reply"] == "echo: hello"


def test_message_length_cap_returns_422(monkeypatch):
    _use_stub_agents(monkeypatch)
    client = TestClient(server.app)
    resp = client.post("/api/chat", json={"message": "x" * 50_000})
    assert resp.status_code == 422  # server-side cap; the client maxlength is UX only


def test_two_browsers_get_separate_agents(monkeypatch):
    created = _use_stub_agents(monkeypatch)
    # Two independent clients = two cookie jars = two sessions.
    with TestClient(server.app) as c1, TestClient(server.app) as c2:
        c1.post("/api/chat", json={"message": "a"})
        c2.post("/api/chat", json={"message": "b"})
    assert len(created) == 2  # no shared agent across browsers


def test_same_client_reuses_session(monkeypatch):
    created = _use_stub_agents(monkeypatch)
    client = TestClient(server.app)  # persists the session cookie across requests
    client.post("/api/chat", json={"message": "one"})
    client.post("/api/chat", json={"message": "two"})
    assert len(created) == 1  # same browser -> one agent, memory persists


def test_new_session_endpoint(monkeypatch):
    _use_stub_agents(monkeypatch)
    client = TestClient(server.app)
    resp = client.post("/api/new-session")
    assert resp.status_code == 200 and resp.json()["kind"] == "ok"


def test_rate_limit_throttles(monkeypatch):
    _use_stub_agents(monkeypatch)
    monkeypatch.setattr(server, "rate_limiter", RateLimiter(per_min=3))
    client = TestClient(server.app)
    kinds = [client.post("/api/chat", json={"message": "hi"}).json()["kind"] for _ in range(5)]
    assert kinds.count("ok") <= 3 and "error" in kinds

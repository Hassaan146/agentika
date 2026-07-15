"""Agent ReAct-loop tests with a scripted fake Groq client.

The loop (planner -> executor -> memory), the forced-answer path, memory writes,
the untrusted-data framing of observations, and the history-window guards are
the most complex and regression-prone code, and previously had no coverage.
A fake client returning canned tool_calls / content lets us exercise all of it
with no network and no API key.
"""

import json

from pydantic import BaseModel, Field

from agent import Agent
from config import settings
from hooks import HookManager
from memory import MemoryStore
from models import ToolResult
from registry import ToolRegistry

# ---- scripted fake Groq client ---------------------------------------------


class _Fn:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.type = "function"
        self.function = _Fn(name, arguments)


class _Message:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Resp:
    def __init__(self, message):
        self.choices = [type("C", (), {"message": message})()]


class _Completions:
    def __init__(self, planner_script, facts):
        self._planner = list(planner_script)
        self._facts = facts

    def create(self, **kwargs):
        if "response_format" in kwargs:  # memory-extraction call
            return _Resp(_Message(content=json.dumps({"facts": self._facts})))
        return _Resp(self._planner.pop(0))  # planner call


class FakeGroq:
    def __init__(self, planner_script, facts=None):
        self.chat = type("Chat", (), {"completions": _Completions(planner_script, facts or [])})()


def tool_call_msg(name="ping", args=None):
    return _Message(tool_calls=[_ToolCall("call_1", name, json.dumps(args or {"q": "x"}))])


def make_registry(calls):
    registry = ToolRegistry(HookManager())

    class PingInput(BaseModel):
        q: str = Field(..., description="a query")

    @registry.register(PingInput, "returns a canned fact")
    def ping(args: PingInput) -> ToolResult:
        calls.append(args.q)
        return ToolResult(ok=True, data="the sky is blue")

    return registry


# ---- tests -----------------------------------------------------------------


def test_loop_dispatches_tool_then_answers():
    calls = []
    script = [tool_call_msg(args={"q": "sky"}), _Message(content="The sky is blue.")]
    agent = Agent(make_registry(calls), MemoryStore(), client=FakeGroq(script))

    answer = agent.run_turn("what color is the sky?")

    assert answer == "The sky is blue."
    assert calls == ["sky"]  # the tool actually ran with the model's args
    tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "the sky is blue" in tool_msgs[0]["content"]


def test_observation_is_framed_as_untrusted_data():
    calls = []
    script = [tool_call_msg(), _Message(content="done")]
    agent = Agent(make_registry(calls), MemoryStore(), client=FakeGroq(script))
    agent.run_turn("go")
    tool_msg = next(m for m in agent.history if m.get("role") == "tool")
    # prompt-injection defence: the observation is delimited, not inlined raw
    assert tool_msg["content"].startswith('<tool_output tool="ping">')
    assert tool_msg["content"].endswith("</tool_output>")


def test_max_steps_forces_final_answer(monkeypatch):
    monkeypatch.setattr(settings, "max_steps", 2)
    calls = []
    script = [tool_call_msg(), tool_call_msg(), _Message(content="Best-effort answer.")]
    agent = Agent(make_registry(calls), MemoryStore(), client=FakeGroq(script))

    answer = agent.run_turn("loop forever")

    assert answer == "Best-effort answer."
    assert len(calls) == 2  # exactly max_steps tool calls, then a forced answer


def test_memory_written_from_turn():
    script = [_Message(content="Anthropic builds Claude.")]
    facts = [{"key": "builder_of_claude", "value": "Anthropic"}]
    agent = Agent(make_registry([]), MemoryStore(), client=FakeGroq(script, facts=facts))

    agent.run_turn("who builds claude?")

    assert any(f.key == "builder_of_claude" and f.value == "Anthropic" for f in agent.memory.facts)


def test_request_history_guard_never_returns_empty(monkeypatch):
    """If a single oversized turn makes the user-boundary trim drop everything,
    the window must still not be empty (never send [system] alone)."""
    monkeypatch.setattr(settings, "history_max_messages", 2)
    agent = Agent(make_registry([]), MemoryStore(), client=FakeGroq([]))
    agent.history = [
        {"role": "assistant", "content": "a"},
        {"role": "tool", "tool_call_id": "t1", "content": "o1"},
        {"role": "tool", "tool_call_id": "t2", "content": "o2"},
    ]
    window = agent._request_history()
    assert window == [agent.history[-1]]  # falls back to the most recent message


def test_history_hard_cap_trims_after_turn(monkeypatch):
    monkeypatch.setattr(settings, "history_hard_cap", 4)
    script = [_Message(content="done")]
    agent = Agent(make_registry([]), MemoryStore(), client=FakeGroq(script))
    for i in range(10):
        agent.history.append({"role": "user", "content": f"q{i}"})
        agent.history.append({"role": "assistant", "content": f"a{i}"})

    agent.run_turn("final")

    assert len(agent.history) <= 4
    assert agent.history[0]["role"] == "user"  # cut at a user-message boundary

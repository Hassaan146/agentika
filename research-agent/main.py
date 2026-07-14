"""CLI entry point: interactive chat, or a scripted multi-hop demo (--demo)."""

import sys

from agent import Agent
from config import settings
from hooks import default_hook_manager
from memory import MemoryStore
from registry import ToolRegistry
from tools import register_all

DEMO_TURNS = [
    "Read company_brief.txt from the docs folder and remember the key facts from it.",
    "Now read research_notes.pdf and tell me what it adds beyond the brief.",
    "Who is the current CEO of the company described in that brief, and what did they do before founding it?",
    "Without using any tools, summarize everything we have learned this session.",
]


def build():
    hooks, metrics = default_hook_manager()
    registry = ToolRegistry(hooks)
    register_all(registry)
    agent = Agent(registry, MemoryStore())
    return agent, metrics


def run_demo(agent: Agent, metrics) -> None:
    print("=" * 70)
    print("DEMO: multi-hop research using file reading + memory + web search")
    print("=" * 70)
    for i, question in enumerate(DEMO_TURNS, 1):
        print(f"\n--- Turn {i} ---")
        print(f"USER: {question}")
        answer = agent.run_turn(question)
        print(f"AGENT: {answer}")

    print("\n" + "=" * 70)
    print(metrics.summary())
    print(f"\nFacts in memory ({len(agent.memory.facts)}):")
    for fact in agent.memory.facts:
        print(f"  {fact.key} = {fact.value[:100]}")
    print(f"\nFull structured log: {settings.log_path}")


def run_chat(agent: Agent, metrics) -> None:
    print("Research agent ready. Type a question ('exit' to quit).")
    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in {"exit", "quit"}:
            break
        print(f"agent> {agent.run_turn(user_input)}")
    print("\n" + metrics.summary())


def main() -> None:
    settings.require_keys()
    agent, metrics = build()
    if "--demo" in sys.argv:
        run_demo(agent, metrics)
    else:
        run_chat(agent, metrics)


if __name__ == "__main__":
    main()

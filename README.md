# Agentika

[![CI](https://github.com/Hassaan146/agentika/actions/workflows/ci.yml/badge.svg)](https://github.com/Hassaan146/agentika/actions/workflows/ci.yml)

An AI research agent (originally built for Week 4 of the Arbisoft internship). A
single agent answers multi-hop questions using **web search**, **page
fetching**, **local file reading (.txt/.pdf)**, and **automatic session
memory** — every tool call intercepted by **hooks** (validation, structured
logging, metrics). Hand-rolled ReAct loop on Groq's OpenAI-compatible
function-calling API; no agent framework. Ships with a single-page glassmorphism
web UI.

## Contents

| Path | What |
|------|------|
| [`research-agent/`](research-agent) | The agent: CLI, FastAPI web app, tools, memory, hooks, tests |
| [`research-agent/README.md`](research-agent/README.md) | **Full setup, architecture, and design decisions** |
| [`ai-agents-concepts.md`](ai-agents-concepts.md) | Conceptual guide to the Week 4 topics (agents, tools, memory, ReAct, …) |
| [`plan.md`](plan.md) | The design plan the agent was built from |
| [`progress.md`](progress.md) | Task tracker and verification log |
| [`prompts.md`](prompts.md) | Log of the prompts that produced this project |

## Quick start

```bash
cd research-agent
pip install -r requirements.txt
cp .env.example .env          # add GROQ_API_KEY and SERPAPI_API_KEY

python main.py                # interactive chat (terminal)
python main.py --demo         # scripted multi-hop demo
uvicorn server:app --port 8010   # web UI -> http://localhost:8010
pytest tests/ -q              # unit tests (no API keys needed)
```

Free keys: [console.groq.com](https://console.groq.com) and [serpapi.com](https://serpapi.com).
See [`research-agent/README.md`](research-agent/README.md) for everything else.

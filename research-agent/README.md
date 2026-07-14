# Research Agent (Week 4)

A single AI research agent that answers multi-hop questions using **web search**, **page fetching**, **local file reading (.txt/.pdf)**, and **automatic session memory** — with every tool call intercepted by **hooks** (validation, structured logging, metrics). Hand-rolled ReAct loop on Groq's OpenAI-compatible function-calling API; no agent framework.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env    # add your GROQ_API_KEY and SERPAPI_API_KEY
```

Free keys: [console.groq.com](https://console.groq.com) and [serpapi.com](https://serpapi.com).
(SerpAPI is used instead of the originally planned Brave Search API because Brave's signup site was down at build time; the provider is isolated in `tools/search.py`.)

## Run

```bash
python main.py            # interactive chat (terminal)
python main.py --demo     # scripted multi-hop demo (file -> memory -> 2-hop search -> memory-only recall)
uvicorn server:app --port 8010   # Agentika web UI -> open http://localhost:8010
pytest tests/ -q          # 27 unit tests, no API keys needed (APIs mocked / not called)
ruff check . && ruff format --check .   # lint + formatting (config in pyproject.toml)
```

## Web frontend (Agentika)

Single-page glassmorphism chat UI (`web/index.html`, served by `server.py`):
looping mountain-video background with a custom requestAnimationFrame fade
system (250ms fade in/out around each loop, no CSS transitions on the video),
hero that collapses into a ChatGPT-style thread on first message, typewriter
reply animation with a 3-dot thinking indicator, green/white palette, Space
Grotesk + DM Sans (ui-ux-pro-max pairing). One route only; the page and the
CLI share the same agent internals — one server = one session memory.

## Architecture

```
                        ┌────────────────────────────────────────────┐
                        │                 main.py (CLI)              │
                        │        interactive chat  /  --demo         │
                        └───────────────────┬────────────────────────┘
                                            ▼
      ┌───────────────────────────  agent.py (ReAct loop)  ─────────────────────────┐
      │                                                                             │
      │   ┌──────────────┐    tool_calls    ┌──────────────┐     result             │
      │   │   PLANNER    │ ───────────────► │   EXECUTOR   │ ──────────────┐        │
      │   │  (Groq LLM)  │                  │ registry.py  │               │        │
      │   └──────▲───────┘                  └──────┬───────┘               │        │
      │          │                                 │                       │        │
      │          │ relevant facts       pre_tool_use / post_tool_use       │        │
      │          │ injected into        / on_tool_error (hooks.py)         │        │
      │          │ system prompt                   │                       │        │
      │   ┌──────┴───────┐                         ▼                       │        │
      │   │  memory.py   │◄── fact extraction   tool_calls.jsonl           │        │
      │   │ MemoryStore  │    after each turn   (structured log)           │        │
      │   └──────────────┘                                                 │        │
      │          ▲                                                         │        │
      │          └──────────────── observation appended to history ◄───────┘        │
      └─────────────────────────────────────────────────────────────────────────────┘
                       tools/: web_search, fetch_page, read_file
                       config.py: validated env + defaults    models.py: Pydantic schemas
```

**Flow per turn:** user input → memory injects top-k relevant facts into the system prompt → LLM plans → registry validates args (Pydantic), runs pre-hooks (may block), executes the tool, runs post-hooks (log + metrics) → observation appended → loop (≤ `MAX_STEPS`, then a forced no-tools best-effort answer) → final answer → extraction LLM call stores durable facts into memory.

## Design decisions

### Memory is architecture, not a tool
The agent never "decides" to remember. After every turn, a separate extraction call pulls durable facts (`{"key", "value"}` JSON) into `MemoryStore`. Same key → newest value overwrites, old value kept in `Fact.history`. Before every turn, facts are ranked by keyword overlap with the user message (recency breaks ties; zero-overlap facts fill remaining slots so "summarize the session" works) and the top-k are injected into the system prompt. Token-overlap scoring instead of embeddings is deliberate: transparent, dependency-free, sufficient for one session.

### Hooks are deterministic control around a probabilistic model
The registry always runs `pre_tool_use` (sandbox validation — can block a call), `post_tool_use` and `on_tool_error` (JSONL logging with `ts / tool / args / duration_ms / status / error / result_preview`, plus metrics counters). Adding a hook is appending a function to a list.

### Errors are observations
`dispatch()` never raises. Validation failures, policy blocks, and exceptions all return `ToolResult{ok, data, error}` — the error text goes back to the model, which adapts (the system prompt forbids repeating an identical failing call). Transient HTTP failures (timeout/429/5xx) are retried with exponential backoff (`utils.retry_http`); auth/bad-input errors fail fast. Missing API keys exit with a one-line fix instruction at startup.

### File reading is sandboxed
`read_file` resolves the path and requires it inside `docs/` (blocks `../` and absolute paths — checked both in the tool and in a pre-hook, defense in depth), allows only `.txt`/`.pdf`, caps size (5 MB) and output length (8k chars).

### Search behavior
`web_search` returns Google results via SerpAPI (answer-box included when present). The system prompt instructs: search first, `fetch_page` a specific URL only when snippets aren't enough.

### Why no LangChain?
The course goal is conceptual clarity: this loop is ~400 lines with every moving part visible. Mapping to framework equivalents: `registry.py` ≈ LangChain `@tool` + `bind_tools`, `memory.py` ≈ checkpointer/store, `hooks.py` ≈ callbacks, `agent.py` ≈ `create_react_agent`. Trade-off: frameworks give integrations and tracing for free; here you see and own everything.

### Prompts
Both prompts live as constants in `agent.py`:
- **`SYSTEM_PROMPT`** — role, ReAct guidance, tool policy (search→fetch escalation, cite URLs, adapt to tool errors, admit uncertainty), plus the injected "Known facts" block.
- **`EXTRACTION_PROMPT`** — strict-JSON fact extraction, instructed to reuse existing keys so updates overwrite instead of duplicating.

### Config
Everything tunable lives in `config.py` (overridable via `.env`): `MODEL`, `MAX_STEPS` (default 8 — a hard cost/latency ceiling per turn on a free-tier key; demo tasks need ≤5; on hitting it the agent gives a best-effort answer and says what's unverified), `MEMORY_TOP_K`, `SEARCH_COUNT`, size/truncation limits, log path. Keys are validated at startup, not import, so tests run keyless.

## Verified behavior (2026-07-13)

- `pytest tests/ -q` → **27 passed** (registry schema/dispatch/validation, memory conflict+ranking, file sandbox/size/truncation/corrupt-PDF, hook logging/metrics/blocking).
- `python main.py --demo` → full run: reads txt + pdf, extracts 6 facts, resolves "the company" from memory, 2-hop web search for the CEO, final turn answered from memory with zero tool calls; metrics + `tool_calls.jsonl` produced.
- Negative paths: missing `.env` → clean startup message; `../` traversal → blocked by policy hook; `.exe` → rejected; wrong tool args → readable validation error back to the model; live `fetch_page` → 4k chars of page text.

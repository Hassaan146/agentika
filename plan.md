# Research Agent: Plan (rev 3)

> **Provenance:** this is the original build plan, written when the project
> lived in an internal `Week4/` internship repo. It is kept here as a design
> record; paths below refer to this standalone repo's layout (`research-agent/`,
> `ai-agents-concepts.md`, …). See [`correction-plan.md`](correction-plan.md) for
> the follow-up remediation roadmap.

## Context

Build a research agent demonstrating the concepts from [`ai-agents-concepts.md`](ai-agents-concepts.md) — web-search skill, session memory, tool-call hooks, file-read plugin, multi-hop demo. Simple but complete, with production-minded structure.

**Decisions:** LLM = **Groq free tier** (`llama-3.3-70b-versatile`, OpenAI-compatible function calling). Search = **SerpAPI** (Google results, free tier 100 searches/mo).

> **Rev 3 change — Brave → SerpAPI:** the plan originally chose Brave Search API, but the Brave API signup website was down when we tried to create a key (2026-07-13), so we switched to SerpAPI. The search tool is isolated in `tools/search.py` behind the same `SearchResult` schema, so swapping back to Brave later is a one-file change.

**Rev 2** incorporates the user's review: proper memory subsystem (internal, not tools), tool registry, richer hooks + structured logging, error handling & retries, page-fetch fallback, file-reader hardening, Pydantic schemas, central config, unit tests, documented prompts, architecture diagram, and a written justification for not using LangChain.

**This turn's deliverable is documentation only:** write `plan.md` + `progress.md`, append prompt to `prompts.md`, push. Implementation starts after user approves the pushed plan.

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

**Execution flow:** user input → memory injects top-k relevant facts into system prompt → LLM plans → registry executes tool calls (wrapped by hooks) → observations appended → loop (≤ `MAX_STEPS`) → final answer → memory extracts/updates facts from the turn.

## File layout

```
research-agent/
├── main.py            # CLI chat + --demo mode
├── agent.py           # ReAct loop only (~80 lines)
├── config.py          # central config: env validation, defaults
├── registry.py        # ToolRegistry: register/dispatch/schemas
├── memory.py          # MemoryStore: internal session memory
├── hooks.py           # HookManager: logging, timing, validation, metrics
├── models.py          # Pydantic: tool inputs/outputs, ToolResult, Fact
├── tools/
│   ├── search.py      # web_search + fetch_page (SerpAPI + page retrieval)
│   └── files.py       # read_file (.txt/.pdf, hardened)
├── tests/             # pytest: registry, memory, files, hooks (APIs mocked)
├── docs/              # sample .txt/.pdf used by the demo
├── requirements.txt   # groq, pydantic, pypdf, httpx, beautifulsoup4, python-dotenv, pytest
├── .env.example       # GROQ_API_KEY, SERPAPI_API_KEY
└── README.md          # setup, usage, architecture, design decisions
```

## Component design (addressing each review point)

### 1. Memory — internal subsystem, not tools (`memory.py`)

- `MemoryStore` holds `Fact` records: `{key, value, source_turn, updated_at}` (Pydantic).
- **Write path (automatic):** after each completed turn, a lightweight extraction LLM call pulls durable facts from the turn ("user's name is X", "found: CEO of Y is Z") as key-value pairs. The agent never calls memory as a tool.
- **Update/conflict policy:** facts are keyed on a normalized key; same key → newest value overwrites, previous value kept in a `history` list on the fact (auditable). Extraction prompt instructs the model to reuse existing keys when the subject matches.
- **Read path (automatic):** before each planner call, `search(query, k=5)` scores facts by keyword overlap with the current user message (simple token-overlap scoring — deliberate choice over embeddings, documented) and injects them into the system prompt as a "Known facts" block.
- **Prioritization:** recency wins ties; injected facts capped at k to bound context.

### 2. Tool Registry (`registry.py`)

- `ToolRegistry` class: `@registry.register` decorator on functions whose parameters are a Pydantic model → auto-generates the OpenAI-compatible JSON schema from the model, stores `name → (fn, schema)`.
- `dispatch(name, raw_args) -> ToolResult`: validates args with Pydantic (validation errors returned to the model as readable text), runs pre/post/error hooks, never raises — always returns a `ToolResult`.
- Adding a tool = one new file in `tools/` + one decorator. No agent-loop changes (extensibility).

### 3–5. Hooks & logging (`hooks.py`)

- `HookManager` with three hook points the registry calls: `pre_tool_use`, `post_tool_use`, `on_tool_error`.
- Built-in hooks:
  - **Validation hook (pre):** args already Pydantic-validated; additionally blocks `read_file` outside the sandbox (defense in depth).
  - **Logging hook (pre+post):** appends one JSON line per call to `tool_calls.jsonl`: `{ts, tool, args, duration_ms, status: ok|error, error?, result_preview}` — and echoes a short colored line to console.
  - **Metrics hook (post):** in-memory counters (calls per tool, error count, total tool time) printed on exit.
- New hooks are appended to a list — no core changes needed.

### 6–7. Error handling & retries

- **Config errors:** `config.py` validates required env vars at startup; missing key → clear one-line exit message ("GROQ_API_KEY missing — copy .env.example to .env").
- **Tool errors:** every tool returns `ToolResult{ok, data, error}`; exceptions are caught in `dispatch`, logged via `on_tool_error`, and the error text is fed back to the model so it can adapt (retry, rephrase, different tool).
- **Retries:** HTTP calls (SerpAPI, page fetch, Groq) wrapped in a small `retry(fn, attempts=3, backoff=1s→2s→4s)` helper for timeouts/429/5xx only; non-retryable errors (401, bad input) fail immediately with a readable message.

### 8. Web search behavior (`tools/search.py`)

- `web_search(query, count=5)` → SerpAPI (Google engine) → structured `SearchResult[]` (title, url, snippet); Google answer-box included when present.
- `fetch_page(url)` → retrieves full page when snippets are insufficient (httpx + BeautifulSoup text extraction, truncated to ~4,000 chars). The system prompt tells the model: *search first; fetch a page only if snippets don't answer the question.*

### 9. File reader hardening (`tools/files.py`)

- `read_file(path)`: resolves to absolute path and requires it to be inside `docs/` (`Path.resolve()` + `is_relative_to` → blocks `../` traversal); extension allowlist `.txt`/`.pdf` (others → readable error); size cap 5 MB; extracted text truncated to ~8,000 chars with a "[truncated]" marker; PDF parse failures → `ToolResult.error`.

### 10. Multi-hop demo (`main.py --demo`)

Scripted demo showing all subsystems in one narrative, e.g.:
1. Turn 1: "Read docs/company_brief.txt and remember the key facts." → `read_file` → memory extraction stores facts.
2. Turn 2: "Who currently leads the company mentioned in that brief, and what did they do before?" → memory injects the company name → `web_search` (hop 1: leader) → `web_search`/`fetch_page` (hop 2: background).
3. Turn 3: "Summarize everything we've learned this session." → answered mostly from memory, no tools.
Demo prints the tool-call log tail + metrics at the end as proof.

### 11. Prompt design (documented in README + `agent.py`)

- **System prompt:** role ("research agent"), tool-use policy (search-then-fetch, cite URLs, admit uncertainty), ReAct guidance ("work step by step; call one or more tools when facts are needed; stop when you can answer"), and the injected "Known facts" block.
- **Memory-extraction prompt:** separate, small, returns strict JSON (`[{key, value}]`).
- Both prompts live as named constants and are reproduced in the README.

### 12. Structured outputs (`models.py`)

Pydantic models throughout: `SearchQuery`, `SearchResult`, `FetchPageInput`, `ReadFileInput`, `ToolResult`, `Fact`. Tool schemas are generated from these (single source of truth); extraction output parsed/validated with Pydantic.

### 13. Central config (`config.py`)

Dataclass/pydantic-settings loading `.env`: API keys (required), `MODEL` (default `llama-3.3-70b-versatile`), `MAX_STEPS` (default 8), `MEMORY_TOP_K` (5), `SEARCH_COUNT` (5), `FETCH_MAX_CHARS`, `FILE_MAX_MB`, `LOG_PATH`. Validated at import; one place to tune everything.

### 14. Testing (`tests/`, pytest)

- `test_registry.py` — schema generation, dispatch, arg-validation error path, unknown tool.
- `test_memory.py` — store/overwrite-on-conflict (history kept), keyword retrieval ranking, top-k cap.
- `test_files.py` — reads txt, blocks `../` traversal, rejects `.exe`, size cap, truncation.
- `test_hooks.py` — log line written with duration/status, error hook fires, metrics counted.
- All external APIs mocked; no keys needed to run tests. Run: `pytest tests/ -q`.

### 15. Step limit

`MAX_STEPS=8` in config, not hardcoded. Rationale documented: hard cost/latency ceiling for a free-tier key; demo tasks need ≤5 steps; on hitting the cap the agent returns its best partial answer and says the limit was reached.

### 16–17. Why custom instead of LangChain (README section)

Course goal is *conceptual clarity*: a hand-rolled loop makes planner/executor/memory/hooks visible in ~400 lines with zero framework magic, no breaking-change churn, and easier debugging. The README section will note the trade-off (LangChain gives integrations/tracing for free) and map each module to its LangChain equivalent (registry ≈ `@tool` + `bind_tools`, memory ≈ checkpointer/store, hooks ≈ callbacks) so the transfer to frameworks is explicit.

### 18. Diagram

The architecture + flow diagram above goes into `plan.md` and the README.

## Execution steps (after plan approval)

1. Write `plan.md` (this design incl. diagram) and `progress.md` (checklist: 6 tasks × status, updated as work lands).
2. Append today's prompt to `prompts.md`.
3. Commit + push.
4. **Stop and wait** for user approval of the pushed plan before implementing `research-agent/`.

## Verification (implementation phase, later)

- `pytest tests/ -q` — all green with no API keys.
- `python main.py` — chat; a fact question triggers `web_search`; `tool_calls.jsonl` shows args/duration/status.
- `python main.py --demo` — full multi-hop narrative (file → memory → 2-hop search → memory-only summary) completes; metrics printed.
- Negative paths: run without `.env` (clean error), ask it to read `../secret.txt` (blocked), kill network (retries then readable error).
- User creates free keys: console.groq.com + serpapi.com (keys live only in `.env`, which is gitignored; user will rotate the keys shared during setup).

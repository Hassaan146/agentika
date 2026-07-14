# Agentika — Backend, Fully Explained

A complete walkthrough of the Python backend: every file, every important
mechanism, with **What / How / Why** for each — plus the wire-level details
(function-calling format, decorator mechanics, request lifecycle) that a
conceptual overview leaves out. Read top to bottom and you should never be
blank on any part of this code.

> Scope: the backend (the Python agent + FastAPI server). The frontend
> (`web/index.html`) is covered separately in `README.md`.

---

## 0. The one-paragraph mental model

> **An agent = an LLM + tools + a loop.**

A plain LLM call is text-in, text-out — it can't check a fact or read a file.
Agentika wraps the LLM (Groq's Llama) in a loop and gives it **tools**. Each
turn: the model looks at the conversation, optionally **requests a tool call**
(as structured JSON), our code **runs** that tool and feeds the result back, and
the loop repeats until the model produces a final answer. Memory, hooks, and the
registry are the supporting cast around that loop.

---

## 1. Architecture at a glance

```
                        ┌────────────────────────────────────────────┐
                        │        main.py (CLI)  /  server.py (web)    │
                        └───────────────────┬────────────────────────┘
                                            ▼
      ┌───────────────────────────  agent.py (ReAct loop)  ─────────────────────────┐
      │                                                                             │
      │   ┌──────────────┐   tool_calls    ┌──────────────┐    ToolResult           │
      │   │   PLANNER    │ ──────────────► │   EXECUTOR   │ ───────────────┐        │
      │   │  (Groq LLM)  │                 │ registry.py  │                │        │
      │   └──────▲───────┘                 └──────┬───────┘                │        │
      │          │                                │  pre/post/error hooks  │        │
      │          │ inject known facts             ▼        (hooks.py)      │        │
      │   ┌──────┴───────┐                 tools/ (search, files)          │        │
      │   │  memory.py   │◄── extract facts after each turn                │        │
      │   └──────────────┘                                                 │        │
      │          ▲                                                         │        │
      │          └──────────── observation appended to history ◄──────────┘        │
      └─────────────────────────────────────────────────────────────────────────────┘
         config.py = settings/secrets     models.py = schemas     utils.py = retry
```

**The three roles (from the Week 4 concepts):**

- **Planner** — the LLM. Given the goal + memory, it decides the next step (call a tool, or answer).
- **Executor** — `registry.py`. Plain code that actually runs the chosen tool. The only part that touches the outside world.
- **Memory** — `memory.py`. What the planner sees on the next turn beyond the raw transcript.

---

## 2. The single most important mechanic: function calling on the wire

Everything hinges on how the LLM "calls" a tool. It does **not** run code and it
does **not** return a Python dict. It returns a **structured request**, and our
code does the rest. The exchange is always four steps:

1. **We send** the user message + the list of tool schemas.
2. **The model replies** with `stop_reason = tool_calls` and a block like:
   ```json
   { "id": "call_abc", "type": "function",
     "function": { "name": "web_search", "arguments": "{\"query\": \"CEO of Anthropic\"}" } }
   ```
   Note `arguments` is a **JSON string**, not a parsed object.
3. **We execute** the real function and send the result back as a new message:
   ```json
   { "role": "tool", "tool_call_id": "call_abc", "content": "{...ToolResult json...}" }
   ```
4. **The model** reads that observation and either answers or requests another call → loop.

Three rules that are load-bearing (and easy to get wrong):

- `arguments` is a **string** → the registry parses it with Pydantic's `model_validate_json`.
- The tool result must carry the **same `tool_call_id`** the model issued, so the model knows which call it answers. The model can request several at once.
- The assistant message that contains `tool_calls` must be appended to the history **before** the tool-result messages, or the API rejects the sequence.

**Why this design:** the model only ever emits text; our code performs every real
action. That separation is exactly what makes an agent safe and controllable —
we can validate, block, log, and time every action in one place.

---

## 3. `config.py` — one place for every setting

**What:** a single `settings` object holding secrets (API keys) and every tunable
number (`max_steps`, `memory_top_k`, size caps, `history_max_messages`…).

**How:** a `@dataclass` whose fields use `field(default_factory=lambda: os.getenv(...))`
so each value is read from the environment (loaded from `.env` by `load_dotenv`)
with a sensible default. `settings = Config()` at the bottom makes it a module
singleton imported everywhere. `require_keys()` collects any missing keys and
exits with a one-line fix message.

**Why:**
- Secrets come from `.env` (gitignored) → **keys never touch code or git**.
- Keys are validated **at startup** (`main.py`/`server.py` call `require_keys()`),
  not at import — that's the deliberate trick that lets the **27 tests run with no keys**.
- Every magic number lives here, so tuning = editing one file.

Key knobs and why they exist:

| Setting | Default | Why |
|---|---|---|
| `max_steps` | 8 | Hard cost/latency ceiling per turn on a free key; demo needs ≤5 |
| `memory_top_k` | 5 | How many remembered facts to inject per turn (bounds prompt size) |
| `history_max_messages` | 30 | Cap the transcript sent per request so long chats don't exceed context |
| `fetch_max_chars` / `file_max_chars` | 4000 / 8000 | Truncate tool output so one page/file can't blow the context |
| `file_max_mb` | 5 | Reject oversized files before reading them |

---

## 4. `models.py` — the data shapes (Pydantic)

**What:** typed schemas for tool **inputs** (`SearchQuery`, `FetchPageInput`,
`ReadFileInput`), the universal tool **output** (`ToolResult`), and a memory `Fact`.

**How:** each is a `pydantic.BaseModel`. `Field(..., description=...)` attaches a
human description to every input field. `ToolResult` has `ok: bool`, `data: Any`,
`error: str | None`, and `to_model_text()` which serializes to JSON (dropping
`None`s) for feeding back to the LLM.

**Why:**
- These input models are the **single source of truth**. The registry calls
  `Model.model_json_schema()` to generate the exact JSON Schema the LLM sees, and
  the same model validates incoming arguments. **Schema and validation can never drift.**
- The `description=` text is literally what the model reads to decide *how* to
  fill a tool's arguments — documentation and contract in one object.
- `ToolResult` being a uniform shape is what lets `dispatch` **never raise** —
  success and every kind of failure are the same type.

---

## 5. `utils.py` — `retry_http`

**What:** retries a network call on *transient* failures only.

**How:** runs `fn()`; on `httpx.TimeoutException` or a retryable status
(`408/429/500/502/503/504`) it waits with exponential backoff (1s → 2s → 4s) and
retries up to 3 times. A non-retryable error (e.g. 401 bad key) is re-raised immediately.

**Why:** rate limits and blips are temporary and worth retrying; a bad API key is
permanent and retrying just wastes time and money. Separating the two is the
difference between a robust client and a naive `try/except: retry`.

---

## 6. `tools/` — the agent's actual capabilities

Tools are the **action space**: the model can only do what's registered here.
Every tool takes a Pydantic model and returns a `ToolResult` — and **never crashes**.

### `tools/search.py`

- **`web_search(SearchQuery)`** → SerpAPI (Google engine). Returns the top ~5
  results as `{title, url, snippet}`, and prepends Google's **answer box** when
  present (often the direct answer). The HTTP call is wrapped in `retry_http`.
- **`fetch_page(FetchPageInput)`** → downloads a page, strips
  `script/style/nav/footer/header` with BeautifulSoup, collapses whitespace, and
  truncates to `fetch_max_chars`.

**Why two tools:** search is cheap and usually enough; fetching a full page is a
fallback for when snippets don't answer. The tool descriptions tell the model
exactly that ("use fetch ONLY when snippets aren't enough"), which keeps the
agent fast and within the free tier.

### `tools/files.py`

**`read_file(ReadFileInput)`** reads a `.txt`/`.pdf` from `docs/` — but only after
four guards, in order:

1. **Path containment:** `(docs / path).resolve()` must be `is_relative_to(docs)`
   → blocks `../` traversal and absolute paths.
2. **Extension allowlist:** only `.txt` / `.pdf`.
3. **Size cap:** reject over `file_max_mb`.
4. **Truncation:** cap output at `file_max_chars` with a `[truncated]` marker.

PDFs go through `pypdf`; a parse failure or an image-only PDF returns a readable
error, not an exception.

**Why so defensive:** a file tool the model controls is a **security surface**.
Path traversal could leak `.env` or source; a giant or binary file could crash
the process or poison the context. Each guard closes one of those holes.

### `tools/__init__.py` — where tools become available

`register_all(registry)` wires each function to the registry with a description.
The description is the **only thing the model uses to choose a tool**, so it's
written like API docs ("Search the web… use whenever you need current facts").

---

## 7. `registry.py` — the tool registry (the Executor)

**What:** holds all tools, exposes their schemas to the LLM, and runs the right
one on request.

**How, `register(InputModel, description)`:** returns a decorator that:
- builds the OpenAI-style schema:
  `{"type":"function","function":{name, description, parameters: Model.model_json_schema()}}`
- stores `name → (function, model, schema)`.

  Note the call site style: `registry.register(SearchQuery, "…")(web_search)`.
  `register(...)` **returns** a decorator; the trailing `(web_search)` calls it
  immediately. It's a decorator applied by hand instead of with `@` — handy for
  registering functions defined in another module.

**How, `dispatch(name, raw_args) -> ToolResult`:** the heart of the Executor:
1. unknown tool → `ToolResult(ok=False, …)` listing valid tools.
2. **validate** args with Pydantic (`model_validate_json` for the JSON string).
   Bad args → readable error, no crash.
3. run **pre-hooks** — any hook returning a reason **blocks** the call.
4. **execute** the tool inside `try/except`; an exception becomes an error
   `ToolResult` and fires the error-hooks.
5. run **post-hooks** with the result and the measured duration.

It **never raises** — always returns a `ToolResult`.

**Why:**
- **Extensibility:** adding a capability = one function + one `register` line.
  Zero changes to the agent loop.
- **One choke point:** validation, safety, timing, and logging all happen here
  instead of being copy-pasted into every tool.
- **Errors are data, not crashes:** because failures come back as `ToolResult`,
  the model can read them and adapt (retry, rephrase, pick another tool).

---

## 8. `hooks.py` — deterministic control around every call

**What:** interceptors that fire automatically on every tool execution —
validation, structured logging, metrics.

**How:** `HookManager` holds three lists — `pre_hooks`, `post_hooks`,
`error_hooks` — and the registry invokes them around `dispatch`. Signatures:

```
pre_tool_use(tool, args)            -> str | None   # a reason string BLOCKS the call
post_tool_use(tool, args, result, duration_ms)
on_tool_error(tool, args, exc, duration_ms)
```

Built-in hooks (wired by `default_hook_manager`):
- **`sandbox_pre_hook`** — a *second* `../`-escape check for `read_file` (defense
  in depth; `files.py` also checks).
- **`logging_post_hook` / `logging_error_hook`** — append one JSON line per call
  to `tool_calls.jsonl` (`ts, tool, args, duration_ms, status, error, result_preview`)
  and echo a short line to the console.
- **`Metrics`** — in-memory counters (calls / errors / total ms per tool), printed
  on exit via `summary()`.

**Why:**
- **Tools are what the agent *may* do; hooks are what the system *always* does.**
  Tool choice is probabilistic (the model decides); hooks are deterministic (they
  run every time). That's how you layer hard guarantees on top of an unpredictable
  model — e.g. "no file access can ever escape `docs/`."
- Same extensibility rule as the registry: a new hook is just a function appended
  to a list. No core edits.
- This is the concrete answer to the Week-4 "hooks: pre/post-action interceptors"
  concept.

---

## 9. `memory.py` — session memory (internal, NOT a tool)

**What:** lets the agent recall earlier facts ("who is *that* company's CEO?")
across turns.

**How:** a `MemoryStore` mapping `normalized_key → Fact`.

- **Write path (`remember` / `update_from_turn`):** after each turn, an LLM
  extraction call returns `[{key, value}]`; each is stored. On a **key collision**,
  the newest value wins and the previous value is pushed onto `Fact.history`
  (auditable). Keys are normalized (`Company Name!` → `company_name`).
  `update_from_turn` wraps the extractor in `try/except` so a memory failure can
  **never break the turn**.
- **Read path (`search` / `known_facts_block`):** before each turn, `search`
  scores every fact by **keyword overlap** with the user message
  (`len(query_tokens & fact_tokens)`), sorts by `(score, recency)`, and returns
  the top-k. `known_facts_block` formats them into a "Known facts…" block that the
  agent prepends to the system prompt. Zero-overlap facts still fill leftover
  slots (most-recent first), so broad prompts like "summarize the session" still
  see memory.

**Why:**
- Memory is **part of the architecture, not a tool** — the model shouldn't have to
  *decide* to remember; recall/extraction happen automatically around the loop.
  That's how real assistants behave.
- **Keyword overlap instead of vector embeddings** is a deliberate simplicity
  choice: transparent, dependency-free, and plenty for one session's worth of
  facts. (The concepts doc's "vector memory / ChromaDB" is the upgrade path.)
- The conflict-`history` keeps memory honest when a fact changes rather than
  silently overwriting.

---

## 10. `agent.py` — the ReAct loop (the heart)

**What:** ties Planner + Executor + Memory into one turn.

**Two prompts live here as constants:**
- **`SYSTEM_PROMPT`** — role, ReAct guidance (call a tool when you need facts,
  read the observation, then decide), tool policy (search→fetch, cite URLs, adapt
  to tool errors, don't repeat a failing call, admit uncertainty).
- **`EXTRACTION_PROMPT`** — instructs a *separate* small call to return strict
  JSON facts, reusing existing keys so updates overwrite.

**How, `run_turn(user_input)`:**
1. Build the system prompt = base rules **+ injected known facts** (`known_facts_block`).
2. Append the user message to `self.history`; form `messages = [system] + _request_history()`.
3. Loop up to `max_steps`:
   - Call the LLM (`_chat`). **No `tool_calls`** → that's the answer → `_finish`.
   - Otherwise rebuild the assistant message (with its `tool_calls`), append it to
     **both** `self.history` and `messages`, then for each call run
     `registry.dispatch(...)` and append a `role:"tool"` result (carrying
     `tool_call_id`) to both lists.
4. If the step budget is exhausted, send one **no-tools** nudge to force a
   best-effort answer.
5. `_finish` appends the answer to history and triggers `memory.update_from_turn`.

**Two subtle but important details:**

- **`self.history` vs `messages`.** `self.history` is the durable transcript
  (grows across turns). `messages` is a fresh per-turn buffer = system prompt +
  a *trimmed slice* of history. Because `[system] + slice` builds a **new list**,
  appending to `messages` doesn't touch `self.history` — so the loop appends to
  **both** deliberately, keeping the permanent record and the in-flight request in
  sync.
- **`_request_history` trimming.** When history exceeds `history_max_messages`, it
  sends only the last N — and slides the cut forward until it starts on a `user`
  message, so it never sends a dangling assistant/tool exchange (which the API
  rejects). Older turns aren't lost: they survive as memory facts.

**How, `_chat`:** wraps `client.chat.completions.create` with `temperature=0.2`,
`max_tokens=1024`; when tools are allowed it passes `tools=registry.schemas()` and
`tool_choice="auto"` (model decides whether to call). The Groq SDK retries
transient network errors itself.

**Why:**
- This **is** ReAct: Thought (LLM) → Action (tool) → Observation (result) → repeat.
- `max_steps` is a hard ceiling so a confused model can't loop forever or run up
  cost; the forced final answer means the user always gets *something* useful.
- The separate extraction call keeps "answering" and "remembering" cleanly apart.

---

## 11. `main.py` — CLI and the assembly point

**What:** the entry point. `build()` assembles the whole agent; two run modes:
interactive chat, or `--demo`.

**How:** `build()` wires `hooks → registry → register_all(tools) → Agent(registry,
MemoryStore())` and returns `(agent, metrics)`. `run_chat` is a read-eval-print
loop; `run_demo` runs four scripted turns (file → memory → 2-hop search →
memory-only summary) then prints metrics and the fact store. `main()` calls
`settings.require_keys()` first, then dispatches on `--demo`.

**Why:** `build()` is the **single assembly point reused by both the CLI and the
web server**, so the terminal and the website run the *identical* agent. The demo
is a repeatable proof that all six Week-4 features work together.

---

## 12. `server.py` — the web wrapper

**What:** a small FastAPI app serving the single-page UI and one chat endpoint.

**How:**
- Calls `settings.require_keys()`, then `build()` once → a module-level `agent`.
- `GET /` serves `web/index.html`; `GET /icon.svg` serves the favicon.
- `POST /api/chat` runs `agent.run_turn(message)` and returns a typed envelope:
  `_ok(reply)` → `{kind:"ok", reply}` or `_err(title, reply)` →
  `{kind:"error", title, reply}`.
- Errors are caught **by class**: `RateLimitError`, `APIStatusError` (with a
  400/413 + "token/context/length" branch = session-too-large), `APIConnectionError`,
  and a catch-all. Each logs the **real traceback server-side** and returns a
  friendly message.

**Why:**
- The browser must **never** see raw exception names like `BadRequestError` —
  that's not actionable and looks broken. The server translates failures into
  clear, styled messages while keeping the real detail in the logs.
- The typed `{kind, title, reply}` envelope lets the frontend render errors
  distinctly (amber bubbles) without guessing.

**Known limitation (be honest about it):** there is **one global `agent`**, so all
browser visitors currently share one memory and one history. That's fine for a
single-user demo; a multi-user version would create an `Agent` per session
(keyed by a cookie) instead.

---

## 13. A full request trace — "Who is the CEO of that company?"

Assume the user already asked Agentika to read `company_brief.txt` (so memory
holds `company_name = Anthropic`). Now they ask the CEO question. Follow it
through every file:

1. **`server.py`** `POST /api/chat` → `agent.run_turn("Who is the CEO of that company?")`.
2. **`agent.py`** → `memory.known_facts_block(...)` (**`memory.py`**) scores facts
   by keyword overlap, injects `company_name: Anthropic` into the system prompt.
   Now the model knows "that company" = Anthropic.
3. **`agent.py`** `_chat` → Groq with the tool schemas. Model returns a
   `tool_calls` request: `web_search({"query": "CEO of Anthropic"})`.
4. **`registry.dispatch("web_search", '{"query":"CEO of Anthropic"}')`**:
   validate args (**`models.py`** `SearchQuery`) → `sandbox_pre_hook` allows it
   (**`hooks.py`**) → run `web_search` (**`tools/search.py`**) → SerpAPI via
   `retry_http` (**`utils.py`**) → `ToolResult(ok=True, data=[…])`.
5. **`hooks.py`** `logging_post_hook` writes a line to `tool_calls.jsonl`; `Metrics`
   increments. Back in **`agent.py`**, the result is appended as a `role:"tool"`
   message.
6. **Loop again.** Model reads the observation and answers (or does one more
   `fetch_page` hop for the CEO's background). No `tool_calls` this time → answer.
7. **`agent.py`** `_finish` → `memory.update_from_turn` runs the extraction call →
   stores `current_ceo = Dario Amodei` (**`memory.py`**).
8. **`server.py`** wraps it as `{kind:"ok", reply:"…Dario Amodei… <source url>"}`.

Every concept — memory injection, function calling, validation, hooks, retry,
extraction — appears exactly once in that path.

---

## 14. Cross-cutting patterns (the two ideas that repeat everywhere)

1. **Extend by adding, not editing.** The registry and the hook manager are both
   just lists. A new tool or a new hook is one append/decorator — the agent loop
   never changes. This is the Open/Closed Principle in practice.
2. **Never crash; always return a readable result.** Tools return `ToolResult`;
   `dispatch` catches everything; the server maps exceptions to friendly text;
   memory extraction is wrapped so it can't break a turn. Failures become
   *observations the model can act on*, not stack traces the user sees.

Supporting patterns: **single source of truth** (Pydantic model → schema +
validation), **config centralization** (`settings`), **separation of concerns**
(each file = one job in the loop), and **defense in depth** (path checks in both
the tool and a hook).

---

## 15. Glossary (quick recall)

| Term | In this codebase |
|---|---|
| **Agent** | LLM + tools + the loop in `agent.py` |
| **Tool / skill** | A registered function (`web_search`, `read_file`, …) the model may call |
| **Function calling** | The model returns a structured tool *request*; our code runs it |
| **Registry** | `registry.py` — registers tools, generates schemas, dispatches safely |
| **Hook** | Deterministic interceptor around every tool call (`hooks.py`) |
| **Memory** | `memory.py` — auto-extracted facts, injected each turn |
| **ReAct** | Reason → Act → Observe loop; the shape of `run_turn` |
| **ToolResult** | Uniform `{ok, data, error}` every tool returns |
| **Planner / Executor** | The LLM / the registry |

---

**If you can explain section 2 (function calling on the wire), section 10 (the
loop, and `history` vs `messages`), and section 13 (the trace), you understand the
backend end to end.**

# Week 4 — AI Agents: Conceptual Guide

A concept-first walkthrough of everything in the Week 4 syllabus. Each section explains the *idea*, why it exists, and shows a small example. Code samples are Python unless noted.

---

## Table of Contents

1. [What are AI Agents? Agents vs Chatbots vs Copilots](#1-what-are-ai-agents)
2. [Agent Architecture: Planner → Executor → Memory Loop](#2-agent-architecture)
3. [Skills (Tools/Functions): Defining and Registering Callable Skills](#3-skills-tools-functions)
4. [Function Calling with Claude API and OpenAI-Compatible APIs](#4-function-calling)
5. [Hooks: Pre/Post-Action Interceptors](#5-hooks)
6. [Memory Types: In-Context, Vector (ChromaDB), Key-Value](#6-memory-types)
7. [Plugins: Search, Code Execution, File I/O](#7-plugins)
8. [Multi-Step Reasoning: Chain-of-Thought and ReAct](#8-multi-step-reasoning)
9. [Intro to LangChain & LlamaIndex](#9-langchain--llamaindex)
10. [Agentic Coding Tools: Cursor, Windsurf, Claude Code](#10-agentic-coding-tools)

---

## 1. What are AI Agents?

### The core idea

An **AI agent** is an LLM placed inside a loop where it can **take actions, observe the results, and decide what to do next** — repeatedly — until a goal is reached.

The one-line mental model:

> **Agent = LLM + tools + a loop.**

A plain LLM call is a pure function: text in, text out. It cannot check a database, run code, or retry after a failure. An agent wraps that same LLM in a control loop and gives it tools, so instead of *answering* a request it can *accomplish* it.

### Agents vs Chatbots vs Copilots

| | **Chatbot** | **Copilot** | **Agent** |
|---|---|---|---|
| **Interaction** | Turn-by-turn conversation | Assists a human inside a workflow | Works toward a goal, often unattended |
| **Who drives?** | The user (asks, reads answer) | The human (AI suggests, human accepts) | The AI (plans and acts, human supervises) |
| **Actions** | None — just text | Small, human-approved (e.g., autocomplete) | Real actions: run code, call APIs, edit files |
| **Loop** | One model call per user message | One suggestion per context | Many model calls per task, self-directed |
| **Failure mode** | Wrong answer | Bad suggestion (human rejects it) | Wrong action (needs guardrails) |
| **Example** | Customer-support FAQ bot | GitHub Copilot autocomplete | Claude Code fixing a failing test suite |

The boundary is **autonomy**, not intelligence. The same model (e.g., Claude) can power all three; what changes is how much of the decide-act-observe loop is delegated to it.

- A **chatbot** *answers*: "Here's how you'd write that migration."
- A **copilot** *suggests*: it drafts the migration inline; you press Tab to accept.
- An **agent** *does*: it writes the migration, runs it against a test DB, sees the error, fixes it, and reports back.

### When do you actually need an agent?

Agents cost more (many LLM calls) and are harder to make reliable. Use the simplest thing that works:

- Fixed, known steps → a **workflow/pipeline** (no agent needed).
- Steps unknown in advance, depend on intermediate results → an **agent**.

Anthropic's own guidance ("Building Effective Agents") makes this distinction: **workflows** orchestrate LLMs through predefined code paths; **agents** let the LLM dynamically direct its own process.

---

## 2. Agent Architecture

### The Planner → Executor → Memory loop

Almost every agent, regardless of framework, is a variation of this loop:

```
            ┌─────────────────────────────────────┐
            │                GOAL                 │
            └──────────────────┬──────────────────┘
                               ▼
   ┌──────────► ┌─────────────────────────┐
   │            │        PLANNER          │  "What should I do next?"
   │            │  (LLM decides next step)│
   │            └───────────┬─────────────┘
   │                        ▼
   │            ┌─────────────────────────┐
   │            │        EXECUTOR         │  "Do it."
   │            │  (run tool / API / code)│
   │            └───────────┬─────────────┘
   │                        ▼
   │            ┌─────────────────────────┐
   │            │         MEMORY          │  "Remember what happened."
   │            │ (observations, history) │
   │            └───────────┬─────────────┘
   │                        │
   └──── not done ──────────┤
                            ▼ done
                     FINAL ANSWER
```

**Planner** — the LLM itself. Given the goal + everything remembered so far, it emits the next step: either a tool call or "I'm finished, here's the answer." Planning can be *incremental* (decide one step at a time — ReAct style, see §8) or *upfront* (write a full plan first, then execute it — "plan-and-execute" style).

**Executor** — plain code, not the model. It receives the planner's chosen action ("call `search_flights(karachi, istanbul)`"), actually runs it, and captures the result *or the error*. This is the only part of the system that touches the real world, which makes it the right place for permissions and safety checks.

**Memory** — what the planner sees on the next iteration. At minimum it is the conversation history (every action + observation appended to the message list). Richer agents add long-term memory (see §6).

### A minimal agent loop in code

This ~30-line skeleton *is* the architecture — everything else in this course is elaboration of it:

```python
def run_agent(goal: str, tools: dict, max_steps: int = 10):
    messages = [{"role": "user", "content": goal}]   # memory (in-context)

    for _ in range(max_steps):
        response = llm(messages, tools=tool_schemas(tools))   # PLANNER

        if response.wants_tool_call:
            result = tools[response.tool_name](**response.tool_args)  # EXECUTOR
            messages.append(assistant_tool_call(response))            # MEMORY
            messages.append(tool_result(result))                      # MEMORY
        else:
            return response.text    # planner says: done

    return "Step limit reached"
```

Key properties to notice:

- **The LLM never executes anything.** It only *requests* actions as structured data; your code executes them. This separation is what makes agents controllable.
- **Errors are observations too.** If a tool throws, you feed the error message back as the tool result — the planner reads it and adapts (retry, different tool, ask the user). Self-correction falls out of the loop for free.
- **`max_steps` is a guardrail.** Agents can loop forever; production agents always have step/cost budgets.

---

## 3. Skills (Tools / Functions)

### Concept

A **skill** (also called a *tool* or *function*) is a capability you hand to the agent: a named, described, typed operation the model may invoke. The model can't do anything you didn't register — the tool list *is* the agent's action space.

A skill has three parts:

1. **Name** — `get_weather`
2. **Description** — *the most important part.* The model chooses tools by reading descriptions, exactly like a developer reading API docs. A vague description ("gets data") produces a confused agent; a precise one ("Returns current weather for a city. Use only when the user asks about weather.") produces reliable tool selection.
3. **Input schema** — JSON Schema describing parameters, so the model produces valid, typed arguments.

### Defining and registering skills

Most frameworks let you turn a plain function into a skill with a decorator. The docstring becomes the description, the type hints become the schema:

```python
# LangChain-style
from langchain_core.tools import tool

@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. "Lahore"
        unit: "celsius" or "fahrenheit"
    """
    return weather_api.fetch(city, unit)

# Registration = putting it in the list the LLM is allowed to use
agent = create_agent(model, tools=[get_weather, search_web, send_email])
```

Under the hood, registration converts each function into a JSON schema and injects it into the model's context. When the model "calls" a tool, it just emits JSON (`{"name": "get_weather", "input": {"city": "Lahore"}}`); a **registry** (often literally a dict of `name → function`) dispatches it.

### Design principles for good skills

- **Few, well-described tools beat many overlapping ones.** If two tools could plausibly handle the same request, the model will sometimes pick the wrong one.
- **Return errors as readable text**, not stack traces — the model must be able to *understand* the failure to recover from it.
- **Make tools coarse enough to be useful.** `search_and_summarize_docs(query)` is often better than making the agent chain `list_files` → `read_file` → `read_file` → …
- **Note:** "Skills" in Claude Code specifically also refers to *folders of instructions/scripts* (Agent Skills) that get loaded into context — same spirit (extending the agent's capabilities), different mechanism.

---

## 4. Function Calling

### What it actually is

**Function calling (tool use)** is the API-level mechanism behind skills. Crucial mental model:

> The model never runs your function. It returns a structured *request* to call it; **your code** runs the function and sends the result back.

The dance is always the same 4 steps:

1. You send the user message **plus tool definitions**.
2. Model replies: "I want to call `get_weather` with `{"city": "Multan"}`" (a structured block, not prose).
3. You execute the real function and send the result back as a new message.
4. Model produces the final natural-language answer (or requests another tool call → loop).

### Claude API version

```python
import anthropic
client = anthropic.Anthropic()

tools = [{
    "name": "get_weather",
    "description": "Get current weather for a given city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
}]

messages = [{"role": "user", "content": "What's the weather in Multan?"}]

resp = client.messages.create(
    model="claude-sonnet-5", max_tokens=1024,
    tools=tools, messages=messages,
)

# Step 2: model responds with stop_reason == "tool_use"
tool_use = next(b for b in resp.content if b.type == "tool_use")
# tool_use.name == "get_weather", tool_use.input == {"city": "Multan"}

# Step 3: WE run it and return the result, keyed by tool_use.id
result = get_weather(**tool_use.input)
messages += [
    {"role": "assistant", "content": resp.content},
    {"role": "user", "content": [{
        "type": "tool_result",
        "tool_use_id": tool_use.id,
        "content": result,
    }]},
]

# Step 4: final answer
final = client.messages.create(model="claude-sonnet-5", max_tokens=1024,
                               tools=tools, messages=messages)
print(final.content[0].text)   # "It's 41°C and sunny in Multan..."
```

### OpenAI-compatible version

Same concept, different wire format. ("OpenAI-compatible" matters because many providers — Groq, Ollama, vLLM, OpenRouter — expose this exact shape.)

```python
from openai import OpenAI
client = OpenAI()

tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a given city.",
        "parameters": {   # note: "parameters", not "input_schema"
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]

resp = client.chat.completions.create(
    model="gpt-4o", tools=tools,
    messages=[{"role": "user", "content": "What's the weather in Multan?"}],
)

call = resp.choices[0].message.tool_calls[0]
# call.function.name, call.function.arguments (a JSON *string* — must json.loads it)

messages += [
    resp.choices[0].message,
    {"role": "tool", "tool_call_id": call.id, "content": get_weather(**json.loads(call.function.arguments))},
]
```

### Key differences to remember

| | Claude | OpenAI-compatible |
|---|---|---|
| Schema key | `input_schema` | `parameters` (nested under `function`) |
| Tool call appears as | `tool_use` content block | `message.tool_calls[]` |
| Arguments | already-parsed dict | JSON **string** (parse it yourself) |
| Result goes back as | `tool_result` block in a `user` message | message with `role: "tool"` |
| Signal | `stop_reason == "tool_use"` | `finish_reason == "tool_calls"` |

Both support **parallel tool calls** (model requests several tools at once) and **forcing** a tool (`tool_choice`).

---

## 5. Hooks

### Concept

A **hook** is a function that the agent framework calls automatically **at a fixed point in the pipeline** — before or after an action — without the model deciding to call it. Tools are chosen *by the model*; hooks fire *deterministically*, every time.

> Tools = what the agent *may* do. Hooks = what the system *always* does around it.

This mirrors middleware in web frameworks (Express/Django) and pre-commit hooks in Git.

### Common hook points in an agent pipeline

```
user input
   │
   ├── on_user_prompt      (validate / enrich the prompt)
   ▼
planner (LLM call)
   │
   ├── pre_tool_use   ◄─── gatekeeper: can BLOCK the action
   ▼
tool execution
   │
   ├── post_tool_use  ◄─── observer: log, transform result
   ▼
... loop ...
   │
   └── on_stop / on_finish  (cleanup, notify, verify)
```

### What hooks are used for

- **Safety / policy** — `pre_tool_use`: block `rm -rf`, deny writes outside the project dir, require human approval for emails. The hook can *reject* the action before it happens — a guarantee the model's judgment alone can't give you.
- **Logging & audit** — `post_tool_use`: record every action + result for debugging and compliance.
- **Transformation** — redact secrets from tool output before the model sees it; auto-format code after every file edit.
- **Automation** — "after every file write, run the linter"; "when the agent finishes, send a Slack notification."

### Example: a guardrail hook

```python
def pre_tool_use(tool_name: str, tool_input: dict) -> Decision:
    if tool_name == "bash" and "rm -rf" in tool_input["command"]:
        return Decision.BLOCK("Destructive command denied by policy.")
    if tool_name == "send_email":
        return Decision.ASK_USER   # human-in-the-loop for side effects
    return Decision.ALLOW
```

Real-world instance: **Claude Code hooks** — shell commands configured in `settings.json` that run on events like `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`. A `PreToolUse` hook exiting with a blocking status actually prevents the tool call. This is *deterministic* control layered on top of a *probabilistic* model — the central reason hooks exist.

---

## 6. Memory Types

LLMs are **stateless**: every API call starts from zero, and the context window is finite. "Memory" is the set of engineering strategies for working around that.

### 6.1 In-context memory (short-term)

The simplest memory: **keep everything in the message list.** Every user turn, tool call, and result is appended, and the whole history is resent on each call.

- ✅ Perfect fidelity, zero infrastructure — the model literally sees everything.
- ❌ Limited by the context window; cost grows with every turn; gone when the session ends.

When the history gets long, agents **compact** it: summarize older turns into a paragraph and keep only recent messages verbatim (this is what Claude Code does when a session grows long).

### 6.2 Vector memory (semantic long-term) — e.g. ChromaDB

Store past information as **embeddings** — vectors that capture *meaning* — and retrieve by **similarity** rather than exact match.

The write path: `text → embedding model → vector → store`.
The read path: `query → embedding → nearest-neighbor search → top-k similar texts → inject into context`.

```python
import chromadb
client = chromadb.Client()
memory = client.create_collection("agent_memory")

# Write: remember facts from past sessions
memory.add(
    documents=["User prefers concise replies without over-engineering",
               "Project deploys to Railway on push to main"],
    ids=["pref-1", "proj-1"],
)

# Read: recall by MEANING, not keywords
memory.query(query_texts=["how should I write responses?"], n_results=1)
# → matches "User prefers concise replies..." even though no words overlap
```

- ✅ Scales to millions of memories; survives sessions; finds *semantically* related info ("car" matches "automobile").
- ❌ Retrieval is fuzzy — you get "probably relevant" chunks, and can miss or mis-rank. This is also the foundation of **RAG** (retrieval-augmented generation): same mechanism, pointed at documents instead of memories.

### 6.3 Key-value stores (exact long-term)

A plain lookup table (Redis, SQLite, JSON file) for **structured facts you can name**:

```python
kv.set("user:name", "Hassaan")
kv.set("user:timezone", "Asia/Karachi")
kv.set("task:current_branch", "week-4")

kv.get("user:timezone")   # exact, instant, deterministic
```

- ✅ Exact, fast, cheap, auditable. Right choice for preferences, settings, counters, task state.
- ❌ You must know the key — no "find things related to X."

### Choosing between them

| Question the agent asks | Right memory |
|---|---|
| "What did we just say?" | In-context (message history) |
| "Have I seen something *like* this before?" | Vector (ChromaDB) |
| "What is the user's timezone?" | Key-value |

Real agents layer all three: in-context for the working session, KV for profile/state, vector for experience and documents. (A fourth pattern worth knowing: **file-based memory** — the agent reads/writes plain markdown notes, e.g. `MEMORY.md` in Claude Code — which is human-inspectable and editable.)

---

## 7. Plugins

### Concept

A **plugin** is a *packaged bundle of capabilities* that extends an agent — typically one or more tools plus their config, auth, and docs, installable as a unit. If a *tool* is a function, a *plugin* is a module: "add web search to my agent" rather than "register these 4 functions."

The three classic plugin categories:

**Search** — lets the agent escape its training cutoff. A `web_search(query)` tool backed by a search API (Brave, Tavily, Google). Suddenly the agent can answer "what changed in Python 3.13?" with current facts, citing sources.

**Code execution** — the most powerful and most dangerous plugin. The agent writes code, a **sandbox** executes it, output comes back as an observation. This turns the LLM from "text predictor" into "thing that can compute": exact math, data analysis over a CSV, plotting. Safety is everything — always sandboxed (Docker, restricted interpreter, no network), never `exec()` on the host.

```python
# The agent handles "average revenue in sales.csv?" by WRITING code:
tool_call: run_python(code="""
import pandas as pd
print(pd.read_csv('sales.csv')['revenue'].mean())
""")
# observation: "48231.55"  → model states the answer with confidence
```

**File I/O** — `read_file`, `write_file`, `list_dir`. This is what makes coding agents possible: the workspace becomes both the agent's subject and its scratchpad. Guardrail: confine paths to a project root.

### The modern standard: MCP

**Model Context Protocol (MCP)**, an open standard from Anthropic, is the plugin system winning in practice. An **MCP server** exposes tools/resources over a standard protocol; any MCP client (Claude Code, Claude Desktop, many IDEs) can use it without custom integration code. Write one Slack MCP server → every MCP-capable agent gets Slack skills. Think "USB-C port for agent capabilities."

---

## 8. Multi-Step Reasoning

### Chain-of-Thought (CoT)

**Idea:** LLMs are dramatically more accurate on multi-step problems when they generate intermediate reasoning steps *before* the answer, instead of jumping to it.

Why it works: each generated token is conditioned on everything before it. Writing out step 2 gives the model something concrete to build step 3 on — the reasoning text is *working memory*. Asking for the answer directly forces the model to do all the work in one leap.

```
Q: A shop sells pens at Rs.30. Bulk orders over 10 get 20% off. Cost of 15 pens?

Direct answer:  "Rs.450" ❌ (forgot the discount)

Chain-of-thought:
  15 pens × Rs.30 = Rs.450
  15 > 10, so 20% discount applies
  Rs.450 × 0.80 = Rs.360 ✅
```

Classic trigger: *"Let's think step by step."* Modern reasoning models (Claude with extended thinking, OpenAI o-series) build this in — they emit internal reasoning tokens before answering. CoT is **thinking only**: no contact with the world, so a factual error in step 1 flows uncorrected into the conclusion.

### ReAct (Reason + Act)

**Idea:** interleave reasoning with tool use, so every few thoughts get grounded by a real observation:

```
Thought → Action → Observation → Thought → Action → Observation → ... → Answer
```

Example — "Which is taller, the Eiffel Tower or Burj Khalifa, and by how much?":

```
Thought: I need both heights. Search for Eiffel Tower first.
Action:  search("Eiffel Tower height")
Observation: 330 m (with antennas)

Thought: Now Burj Khalifa.
Action:  search("Burj Khalifa height")
Observation: 828 m

Thought: 828 − 330 = 498. I can answer now.
Answer:  Burj Khalifa, by ~498 m.
```

Why this beats pure CoT for tasks needing facts or actions: **observations correct the model mid-flight.** A wrong assumption dies at the next Observation instead of propagating; hallucinated "facts" get replaced by retrieved ones.

**ReAct is the agent loop from §2, seen from the model's perspective** — Thought = planner, Action = executor call, Observation = memory update. Modern function-calling APIs implement ReAct natively: the "Thought" is the model's (possibly hidden) reasoning, the "Action" is a structured `tool_use` block instead of parsed text.

Other patterns in the same family, worth recognizing by name: **plan-and-execute** (write the whole plan first, then do it), **reflection** (a critique pass over one's own output), **tree-of-thoughts** (explore several reasoning branches, keep the best).

---

## 9. LangChain & LlamaIndex

Two open-source Python/JS frameworks that package everything above so you don't hand-roll it. They overlap, but their centers of gravity differ:

> **LangChain** is *agent-first* (orchestration, tools, multi-step workflows).
> **LlamaIndex** is *data-first* (ingestion, indexing, retrieval — RAG).

### LangChain (+ LangGraph)

Building blocks: model wrappers (swap Claude/GPT/Llama behind one interface), prompt templates, output parsers, tools, memory, and **chains** — sequences composed with the pipe operator (LCEL):

```python
chain = prompt | model | output_parser        # a chain: fixed pipeline
result = chain.invoke({"topic": "AI agents"})
```

For agents, the modern path is **LangGraph**: you model the agent as a *graph* of nodes (LLM call, tool execution, human approval) with edges and loops — which is exactly the planner→executor→memory loop made explicit and controllable. The high-level API is one call:

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model="anthropic:claude-sonnet-5",
    tools=[get_weather, search_web],
)
agent.invoke({"messages": [{"role": "user", "content": "Weather in Lahore?"}]})
```

Ecosystem: hundreds of pre-built integrations, plus **LangSmith** for tracing/debugging agent runs.

### LlamaIndex

Optimized for the **RAG pipeline**: *load → chunk → embed → index → retrieve → synthesize*. Its five-line canonical example indexes a folder of documents and answers questions over them:

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

docs = SimpleDirectoryReader("./my_docs").load_data()   # load (PDF, md, ...)
index = VectorStoreIndex.from_documents(docs)           # chunk + embed + index
engine = index.as_query_engine()                        # retriever + LLM
print(engine.query("What does the contract say about termination?"))
```

It also has agents (function-calling agents, and workflow orchestration), but its differentiators are data connectors (LlamaHub: PDFs, Notion, SQL, Slack…) and sophisticated retrieval strategies (hybrid search, re-ranking, sub-question decomposition).

### Choosing

- Complex multi-step agent, many tools, branching control flow → **LangChain/LangGraph**.
- "Chat with my documents / knowledge base" → **LlamaIndex**.
- Big real systems often use both: LlamaIndex retrieval wrapped as a *tool* inside a LangGraph agent.
- Also know that **frameworks are optional** — everything they do can be written against the raw APIs (§4), and understanding the loop in §2 means you're never locked in.

---

## 10. Agentic Coding Tools

The most commercially successful agents so far are coding agents. Three representative tools, three philosophies:

### Cursor — the AI-native IDE

A VS Code *fork* rebuilt around AI. Spans the whole autonomy spectrum in one app: **Tab** (autocomplete/copilot mode), **Inline edit** (Cmd+K on a selection), and **Agent mode** (multi-file tasks with terminal access). Codebase-aware via embeddings of your repo; supports rules files (`.cursor/rules`) to encode team conventions. Philosophy: *bring the agent into the editor you live in* — human stays in the driver's seat with fast accept/reject UX.

### Windsurf — the "flows" IDE

Also a VS Code-lineage IDE; its agent is called **Cascade**. Signature idea: **flows** — the agent continuously tracks your recent edits and state, so human and AI feel like they're co-editing one session ("you edit, it picks up where you left off"). Generally positioned as the most beginner-friendly of the three. Philosophy: *keep human and agent in one shared flow state*.

### Claude Code — the terminal agent

No IDE at all: an agent in the **terminal** (plus IDE/desktop/web frontends) that reads files, edits, runs commands, and commits — driven by conversation. Most autonomous of the three by default; designed for *delegation* ("fix these failing tests, then open a PR") rather than keystroke-level assistance. Deeply extensible — the concepts from this doc appear as literal features:

| Concept (this doc) | Claude Code feature |
|---|---|
| Skills (§3) | Skills & slash commands (`.claude/skills/`) |
| Hooks (§5) | `PreToolUse` / `PostToolUse` / `Stop` hooks in settings |
| Memory (§6) | `CLAUDE.md` project memory + auto memory dir |
| Plugins (§7) | MCP servers |
| Agent loop (§2) | The whole product; also the **Agent SDK** to build your own |

### The spectrum, summarized

```
 copilot ◄──────────────────────────────────────► autonomous agent
 (you type, it suggests)                    (you delegate, it works)

   Tab-complete   Inline edits   IDE agent panes      Terminal/CI agents
   (Cursor Tab)   (Cmd+K)        (Cursor/Windsurf)    (Claude Code)
```

Convergence trend: everyone is adding everything (CLIs get IDE plugins, IDEs get background agents, all adopt MCP). The durable skill isn't any one tool — it's understanding the loop, tools, hooks, and memory underneath, because those concepts transfer.

---

## How it all fits together

One paragraph to bind the week:

> An **agent** (§1) is an LLM in a **planner→executor→memory loop** (§2). You give it capabilities as **skills/tools** (§3), which the model invokes via **function calling** (§4). **Hooks** (§5) wrap the loop with deterministic control — logging, guardrails, automation. **Memory systems** (§6) let it remember beyond the context window; **plugins** (§7) package capabilities like search, code execution, and file I/O (with **MCP** as the standard). The model drives the loop well because of **multi-step reasoning** patterns — CoT for thinking, **ReAct** for thinking-while-acting (§8). Frameworks like **LangChain and LlamaIndex** (§9) give you these pieces pre-built, and tools like **Cursor, Windsurf, and Claude Code** (§10) are this exact architecture productized for software engineering.

### Suggested further reading

- Anthropic — *Building Effective Agents* (workflows vs agents, when to use which)
- Claude API docs — Tool use / function calling
- ReAct paper — Yao et al., 2022 (*ReAct: Synergizing Reasoning and Acting in Language Models*)
- Chain-of-Thought paper — Wei et al., 2022
- LangGraph docs (agent graphs), LlamaIndex docs (RAG pipeline)
- Model Context Protocol — modelcontextprotocol.io

# Week 4 — Progress

Status legend: ⬜ not started · 🔄 in progress · ✅ done

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Research agent with web-search skill | ✅ | `tools/search.py`: web_search (SerpAPI — Brave signup site was down) + fetch_page fallback |
| 2 | Memory: recall facts from earlier in session | ✅ | `memory.py`: automatic LLM fact extraction, keyed conflict handling with history, top-k injection |
| 3 | Hook logging every tool call with timestamps | ✅ | `hooks.py`: JSONL log (ts, args, duration_ms, status, error) + console echo + metrics + sandbox pre-hook |
| 4 | File-read plugin (.txt / .pdf) | ✅ | `tools/files.py`: sandboxed to docs/, traversal blocked, extension allowlist, size cap, truncation |
| 5 | Demo: multi-hop questions using all of the above | ✅ | `python main.py --demo`: txt → pdf → memory-resolved 2-hop search → memory-only summary |
| 6 | Update prompts.md | ✅ | Updated on every push (standing rule) |

## Verification

- **Unit tests:** `pytest tests/ -q` → 27 passed (no API keys needed).
- **Live demo (2026-07-13):** full 4-turn run succeeded — 6 facts auto-extracted into memory, turn 3 resolved "the company" from memory and did a 2-hop search (CEO → background), turn 4 summarized the session with zero tool calls. Metrics: read_file ×2, web_search ×2, 0 errors.
- **Negative paths:** missing .env → clean one-line error; `../` traversal → blocked by policy hook; `.exe` → rejected; invalid tool args → readable validation error returned to the model; live fetch_page → ok.

## Frontend (bonus)

- **Agentika web UI** — single-page glassmorphism chat over a looping mountain-video background (custom rAF fade system per spec). FastAPI wrapper (`server.py`, `/api/chat`) + `web/index.html` (Space Grotesk/DM Sans from ui-ux-pro-max skill, green/white palette, typewriter replies, 3-dot typing indicator, ChatGPT-style hero→chat transition). One route, no nav/credits/attach clutter. Prettier-formatted, ruff clean.
- Verified in browser: file-read turn, memory-resolved 2-hop web search turn ("that company" → Anthropic → CEO with source link), memory recall after page reload.
- **Favicon** (`web/icon.svg`) + fix for white flash at video loop end (deep-green body backdrop behind the fading video).
- **Focus-ring fix** — moved the input focus ring to the whole pill (`:focus-within`) instead of the inner input, which drew a floating green box.
- **Hero/composer overlap fix** — hero text lifted above the composer (bottom padding + tightened mobile type scale); verified clearance at 1280×720 (77px) and 375×812 (108px).
- **Resilient error handling** — request history capped (`HISTORY_MAX_MESSAGES`, default 30) so long sessions no longer hit the provider's context limit; server maps failures to friendly `{kind, title, reply}` messages (rate limit / session limit / connection / generic) and logs the real traceback server-side only; UI renders errors as amber-accented glass bubbles with a warning icon. No raw exception names reach the user.

## Log

- **2026-07-13** — Concepts doc (`ai-agents-concepts.md`) written; plan reviewed (18 feedback points) and revised to rev 2; plan.md + progress.md pushed.
- **2026-07-13** — Plan rev 3: Brave → SerpAPI (Brave signup site down). Full implementation of `research-agent/` (config, models, registry, hooks, memory, tools, agent, CLI, 27 tests, docs samples incl. generated PDF). Unit + live end-to-end testing passed. All 6 tasks complete.
- **2026-07-13** — Agentika web frontend + ruff/prettier tooling. Polish pass: favicon, video loop-flash fix, focus-ring fix, hero/composer overlap fix, resilient error handling (history cap + friendly styled error bubbles). Switched to Conventional Commits for all commits (saved to memory).

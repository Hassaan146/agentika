"""Hooks - deterministic interceptors around every tool execution.

Tools are what the agent MAY do; hooks are what the system ALWAYS does around
them. The registry calls three hook points on every dispatch:

    pre_tool_use(tool, args)            -> may return a block reason (str)
    post_tool_use(tool, args, result, duration_ms)
    on_tool_error(tool, args, exc, duration_ms)

Built-in hooks: sandbox validation (pre), JSONL logging (post/error), metrics
(post/error). New hooks are just functions appended to a list - no core changes.
"""

import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from config import settings
from models import ToolResult


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class HookManager:
    def __init__(self) -> None:
        self.pre_hooks: list[Callable] = []
        self.post_hooks: list[Callable] = []
        self.error_hooks: list[Callable] = []

    def pre_tool_use(self, tool: str, args: dict[str, Any]) -> str | None:
        """Runs all pre-hooks; the first one returning a reason blocks the call."""
        for hook in self.pre_hooks:
            reason = hook(tool, args)
            if reason:
                return reason
        return None

    def post_tool_use(self, tool: str, args: dict[str, Any], result: ToolResult, duration_ms: float) -> None:
        for hook in self.post_hooks:
            hook(tool, args, result, duration_ms)

    def on_tool_error(self, tool: str, args: dict[str, Any], exc: Exception, duration_ms: float) -> None:
        for hook in self.error_hooks:
            hook(tool, args, exc, duration_ms)


# ---- Built-in hook: sandbox validation (defense in depth; files.py also checks)


def sandbox_pre_hook(tool: str, args: dict[str, Any]) -> str | None:
    if tool == "read_file":
        docs = settings.docs_dir.resolve()
        target = (docs / str(args.get("path", ""))).resolve()
        if not target.is_relative_to(docs):
            return f"read_file path '{args.get('path')}' escapes the docs/ sandbox"
    return None


# ---- Built-in hook: structured logging (JSONL + console echo) ---------------


def _write_log(record: dict[str, Any]) -> None:
    with open(settings.log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def logging_post_hook(tool: str, args: dict[str, Any], result: ToolResult, duration_ms: float) -> None:
    record = {
        "ts": _now_iso(),
        "tool": tool,
        "args": args,
        "duration_ms": round(duration_ms, 1),
        "status": "ok" if result.ok else "error",
    }
    if result.ok and result.data is not None:
        record["result_preview"] = json.dumps(result.data, ensure_ascii=False, default=str)[:200]
    if not result.ok:
        record["error"] = result.error
    _write_log(record)
    arg_str = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in args.items())
    print(f"  [hook] {record['ts']} {tool}({arg_str}) -> {record['status']} in {record['duration_ms']}ms")


def logging_error_hook(tool: str, args: dict[str, Any], exc: Exception, duration_ms: float) -> None:
    record = {
        "ts": _now_iso(),
        "tool": tool,
        "args": args,
        "duration_ms": round(duration_ms, 1),
        "status": "exception",
        "error": f"{type(exc).__name__}: {exc}",
    }
    _write_log(record)
    print(f"  [hook] {record['ts']} {tool} -> EXCEPTION {record['error']} in {record['duration_ms']}ms")


# ---- Built-in hook: metrics --------------------------------------------------


class Metrics:
    def __init__(self) -> None:
        self.calls: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.total_ms: dict[str, float] = defaultdict(float)

    def post_hook(self, tool: str, args: dict[str, Any], result: ToolResult, duration_ms: float) -> None:
        self.calls[tool] += 1
        self.total_ms[tool] += duration_ms
        if not result.ok:
            self.errors[tool] += 1

    def error_hook(self, tool: str, args: dict[str, Any], exc: Exception, duration_ms: float) -> None:
        self.calls[tool] += 1
        self.errors[tool] += 1
        self.total_ms[tool] += duration_ms

    def summary(self) -> str:
        if not self.calls:
            return "No tool calls made."
        lines = ["Tool metrics:"]
        for tool in sorted(self.calls):
            lines.append(
                f"  {tool}: {self.calls[tool]} call(s), "
                f"{self.errors[tool]} error(s), {self.total_ms[tool]:.0f}ms total"
            )
        return "\n".join(lines)


def default_hook_manager() -> "tuple[HookManager, Metrics]":
    """Wire up the standard hook set used by main.py."""
    hooks = HookManager()
    metrics = Metrics()
    hooks.pre_hooks.append(sandbox_pre_hook)
    hooks.post_hooks.append(logging_post_hook)
    hooks.post_hooks.append(metrics.post_hook)
    hooks.error_hooks.append(logging_error_hook)
    hooks.error_hooks.append(metrics.error_hook)
    return hooks, metrics

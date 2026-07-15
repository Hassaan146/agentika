"""ToolRegistry - registration, schema generation, and safe dispatch.

Adding a tool = write a function taking a Pydantic input model, register it
with a description. The OpenAI-compatible JSON schema is generated from the
model, so the schema and the validation can never drift apart.

dispatch() never raises: validation errors, policy blocks, and exceptions all
come back as ToolResult with readable error text the LLM can act on.
"""

import time
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from hooks import HookManager
from models import ToolResult


class ToolRegistry:
    def __init__(self, hooks: HookManager) -> None:
        self.hooks = hooks
        self._tools: dict[str, tuple[Callable, type[BaseModel], dict]] = {}

    def register(self, input_model: type[BaseModel], description: str, name: str | None = None):
        def decorator(fn: Callable) -> Callable:
            tool_name = name or fn.__name__
            schema = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": input_model.model_json_schema(),
                },
            }
            self._tools[tool_name] = (fn, input_model, schema)
            return fn

        return decorator

    def schemas(self) -> list[dict]:
        return [schema for _, _, schema in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def dispatch(self, name: str, raw_args) -> ToolResult:
        if name not in self._tools:
            return ToolResult(ok=False, error=f"Unknown tool '{name}'. Available tools: {self.names()}")

        fn, input_model, _ = self._tools[name]

        # 1. Validate arguments (Pydantic = structured input schema)
        try:
            if isinstance(raw_args, str):
                args = input_model.model_validate_json(raw_args)
            else:
                args = input_model.model_validate(raw_args)
        except ValidationError as e:
            issues = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            return ToolResult(ok=False, error=f"Invalid arguments for {name}: {issues}")

        args_dict = args.model_dump()

        # 2. Pre-hooks may block the call (policy / sandbox)
        block_reason = self.hooks.pre_tool_use(name, args_dict)
        if block_reason:
            result = ToolResult(ok=False, error=f"Blocked by policy: {block_reason}")
            self.hooks.post_tool_use(name, args_dict, result, 0.0)
            return result

        # 3. Execute; exceptions become readable errors, never crashes
        start = time.perf_counter()
        try:
            result = fn(args)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self.hooks.on_tool_error(name, args_dict, exc, duration_ms)
            return ToolResult(ok=False, error=f"{name} failed: {type(exc).__name__}: {exc}")

        duration_ms = (time.perf_counter() - start) * 1000
        self.hooks.post_tool_use(name, args_dict, result, duration_ms)
        return result

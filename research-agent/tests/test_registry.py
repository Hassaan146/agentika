from pydantic import BaseModel, Field

from hooks import HookManager
from models import ToolResult
from registry import ToolRegistry


class EchoInput(BaseModel):
    text: str = Field(..., description="text to echo")


def make_registry():
    registry = ToolRegistry(HookManager())

    @registry.register(EchoInput, "Echo the text back")
    def echo(args: EchoInput) -> ToolResult:
        return ToolResult(ok=True, data=args.text)

    @registry.register(EchoInput, "Always raises")
    def boom(args: EchoInput) -> ToolResult:
        raise RuntimeError("kaboom")

    return registry


def test_schema_generation():
    registry = make_registry()
    schema = registry.schemas()[0]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert schema["function"]["description"] == "Echo the text back"
    assert "text" in schema["function"]["parameters"]["properties"]


def test_dispatch_valid_json_args():
    result = make_registry().dispatch("echo", '{"text": "hello"}')
    assert result.ok and result.data == "hello"


def test_dispatch_invalid_args_returns_readable_error():
    result = make_registry().dispatch("echo", '{"wrong_field": 1}')
    assert not result.ok
    assert "Invalid arguments for echo" in result.error
    assert "text" in result.error


def test_dispatch_unknown_tool():
    result = make_registry().dispatch("nope", "{}")
    assert not result.ok
    assert "Unknown tool" in result.error
    assert "echo" in result.error  # lists available tools


def test_exception_becomes_tool_result_not_crash():
    result = make_registry().dispatch("boom", '{"text": "x"}')
    assert not result.ok
    assert "RuntimeError" in result.error and "kaboom" in result.error


def test_pre_hook_blocks_call():
    registry = make_registry()
    registry.hooks.pre_hooks.append(lambda tool, args: "denied by test" if tool == "echo" else None)
    result = registry.dispatch("echo", '{"text": "hello"}')
    assert not result.ok
    assert "Blocked by policy: denied by test" in result.error

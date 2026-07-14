import json

from config import settings
from hooks import HookManager, Metrics, logging_error_hook, logging_post_hook, sandbox_pre_hook
from models import ToolResult


def test_logging_post_hook_writes_structured_line(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(settings, "log_path", log)
    logging_post_hook("web_search", {"query": "test"}, ToolResult(ok=True, data=[{"t": 1}]), 123.456)
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert record["tool"] == "web_search"
    assert record["args"] == {"query": "test"}
    assert record["status"] == "ok"
    assert record["duration_ms"] == 123.5
    assert "ts" in record and "result_preview" in record


def test_logging_post_hook_records_tool_errors(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(settings, "log_path", log)
    logging_post_hook("read_file", {"path": "x"}, ToolResult(ok=False, error="not found"), 5)
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert record["status"] == "error" and record["error"] == "not found"


def test_logging_error_hook_records_exception(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(settings, "log_path", log)
    logging_error_hook("web_search", {"query": "q"}, RuntimeError("net down"), 10)
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert record["status"] == "exception" and "net down" in record["error"]


def test_metrics_counts_calls_errors_and_time():
    metrics = Metrics()
    metrics.post_hook("t", {}, ToolResult(ok=True), 100)
    metrics.post_hook("t", {}, ToolResult(ok=False, error="e"), 50)
    metrics.error_hook("t", {}, RuntimeError("x"), 25)
    assert metrics.calls["t"] == 3
    assert metrics.errors["t"] == 2
    assert metrics.total_ms["t"] == 175
    assert "3 call(s)" in metrics.summary()


def test_hook_manager_first_block_wins():
    manager = HookManager()
    manager.pre_hooks.append(lambda t, a: None)
    manager.pre_hooks.append(lambda t, a: "blocked!")
    assert manager.pre_tool_use("any", {}) == "blocked!"


def test_sandbox_pre_hook_blocks_escape():
    assert sandbox_pre_hook("read_file", {"path": "../../etc/passwd"}) is not None
    assert sandbox_pre_hook("read_file", {"path": "company_brief.txt"}) is None
    assert sandbox_pre_hook("web_search", {"query": "x"}) is None

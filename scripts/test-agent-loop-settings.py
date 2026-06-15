"""Verification script for the AgentLoopSettings feature.

Covers every test case in docs/design/agent-loop-settings.md Section 10.
Run with: python scripts/test-agent-loop-settings.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from vidbyte.agents import AgentLoopSettings, BaseAgent
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.errors import ConfigurationError


# ── helpers ───────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def _ok(name: str) -> None:
    global _passed
    _passed += 1
    print(f"  PASS  {name}")


def _fail(name: str, reason: str) -> None:
    global _failed
    _failed += 1
    print(f"  FAIL  {name}")
    print(f"        {reason}")


def run(name: str, fn):
    """Execute a single test case and record its result."""
    try:
        fn()
        _ok(name)
    except AssertionError as exc:
        _fail(name, str(exc) or "assertion failed")
    except Exception as exc:
        _fail(name, f"{type(exc).__name__}: {exc}")


def raises(exc_type, fn):
    """Assert that fn() raises exc_type; return the exception."""
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(f"Expected {exc_type.__name__} to be raised, but nothing was raised.")


class EchoRunner:
    """Minimal runner that responds with isDone immediately."""

    def __init__(self, tool_calls: list[dict] | None = None) -> None:
        self._tool_calls = tool_calls or []
        self._call_count = 0

    def run(self, prompt: str, *, system: str | None = None, **_):
        self._call_count += 1
        if self._tool_calls and self._call_count <= len(self._tool_calls):
            call = self._tool_calls[self._call_count - 1]
            return _FakeResponse("", {"output": [call]})
        return _FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
        )


class _FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


def _tool_call(name: str = "fake_tool") -> dict:
    return {"type": "function_call", "name": name, "arguments": "{}"}


# ── AgentLoopSettings validation ──────────────────────────────────────────────

print("\n-- AgentLoopSettings validation --")

run("constructs successfully with all None defaults", lambda: AgentLoopSettings())

run("constructs successfully with only max_iterations set", lambda: AgentLoopSettings(max_iterations=5))

run("raises ConfigurationError when max_iterations is 0", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(max_iterations=0))
))

run("raises ConfigurationError when max_iterations is negative", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(max_iterations=-1))
))

run("raises ConfigurationError when max_tokens is 0", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(max_tokens=0))
))

run("raises ConfigurationError when max_tool_calls is 0", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(max_tool_calls=0))
))

run("raises ConfigurationError when timeout_seconds is 0.0", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(timeout_seconds=0.0))
))

run("raises ConfigurationError when timeout_seconds is negative", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(timeout_seconds=-5.0))
))

run("raises ConfigurationError when memory_strategy is unrecognized", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(memory_strategy="magic"))
))


def _test_valid_memory_strategies():
    for strategy in ("sliding_window", "summarize", "trim"):
        s = AgentLoopSettings(memory_strategy=strategy)
        assert s.memory_strategy == strategy, f"expected {strategy!r}, got {s.memory_strategy!r}"


run("accepts all three valid memory_strategy values", _test_valid_memory_strategies)

run(
    "raises ConfigurationError when compaction_target_tokens >= compaction_trigger_tokens",
    lambda: raises(ConfigurationError, lambda: AgentLoopSettings(
        compaction_trigger_tokens=1000,
        compaction_target_tokens=1000,
    )),
)

run("accepts allowed_tools as empty tuple", lambda: AgentLoopSettings(allowed_tools=()))

run("raises ConfigurationError when context_window_budget is 0", lambda: (
    raises(ConfigurationError, lambda: AgentLoopSettings(context_window_budget=0))
))

# ── AgentLoopSettings.to_runtime_config() ────────────────────────────────────

print("\n-- AgentLoopSettings.to_runtime_config() --")


def _test_to_runtime_config_empty():
    cfg = AgentLoopSettings().to_runtime_config()
    assert isinstance(cfg, AgentRuntimeConfig)
    assert cfg.max_iterations is None
    assert cfg.max_tokens is None
    assert cfg.max_tool_calls is None


run("produces AgentRuntimeConfig with None fields when settings are all None", _test_to_runtime_config_empty)


def _test_to_runtime_config_max_iterations():
    cfg = AgentLoopSettings(max_iterations=7).to_runtime_config()
    assert cfg.max_iterations == 7, f"expected 7, got {cfg.max_iterations}"


run("correctly maps max_iterations to AgentRuntimeConfig", _test_to_runtime_config_max_iterations)


def _test_to_runtime_config_max_tool_calls():
    cfg = AgentLoopSettings(max_tool_calls=3).to_runtime_config()
    assert cfg.max_tool_calls == 3, f"expected 3, got {cfg.max_tool_calls}"


run("correctly maps max_tool_calls to AgentRuntimeConfig", _test_to_runtime_config_max_tool_calls)


def _test_to_runtime_config_compaction():
    cfg = AgentLoopSettings(
        compaction_trigger_tokens=5000,
        compaction_target_tokens=2000,
    ).to_runtime_config()
    assert cfg.compaction_trigger_tokens == 5000
    assert cfg.compaction_target_tokens == 2000


run("correctly maps compaction fields to AgentRuntimeConfig", _test_to_runtime_config_compaction)

# ── BaseAgent integration ─────────────────────────────────────────────────────

print("\n-- BaseAgent integration --")


def _make_agent(**kwargs) -> BaseAgent:
    return BaseAgent(name="test", system_prompt="test", runner=EchoRunner(), **kwargs)


def _test_agent_stores_loop_settings():
    settings = AgentLoopSettings(max_iterations=3)
    agent = _make_agent(agent_loop_settings=settings)
    assert agent.agent_loop_settings is settings


run("stores self.agent_loop_settings when agent_loop_settings is provided", _test_agent_stores_loop_settings)


def _test_agent_builds_from_flat_params():
    agent = _make_agent(max_iterations=5)
    assert agent.agent_loop_settings.max_iterations == 5


run("constructs AgentLoopSettings from flat params when agent_loop_settings is not provided", _test_agent_builds_from_flat_params)


def _test_agent_default_empty_settings():
    agent = _make_agent()
    assert agent.agent_loop_settings.max_iterations is None
    assert agent.agent_loop_settings.max_tokens is None


run("defaults self.agent_loop_settings to all-None instance when no params provided", _test_agent_default_empty_settings)


def _test_agent_raises_on_double_config():
    raises(ConfigurationError, lambda: _make_agent(
        agent_loop_settings=AgentLoopSettings(max_iterations=5),
        max_iterations=10,
    ))


run("raises ConfigurationError when agent_loop_settings AND max_iterations are both provided", _test_agent_raises_on_double_config)


def _test_agent_raises_on_double_config_tokens():
    raises(ConfigurationError, lambda: _make_agent(
        agent_loop_settings=AgentLoopSettings(max_tokens=5000),
        max_tokens=1000,
    ))


run("raises ConfigurationError when agent_loop_settings AND max_tokens are both provided", _test_agent_raises_on_double_config_tokens)


def _test_agent_max_tool_rounds_alias():
    agent = _make_agent(max_tool_rounds=4)
    assert agent.agent_loop_settings.max_iterations == 4


run("accepts max_tool_rounds as alias for max_iterations via flat params path", _test_agent_max_tool_rounds_alias)

# ── Fork inheritance ──────────────────────────────────────────────────────────

print("\n-- Fork inheritance --")


def _test_fork_inherits_loop_settings():
    settings = AgentLoopSettings(max_iterations=8, max_tool_calls=15)
    parent = _make_agent(agent_loop_settings=settings)
    child = parent.fork(name="child")
    assert child.agent_loop_settings is settings


run("fork inherits parent agent_loop_settings unchanged", _test_fork_inherits_loop_settings)

# ── AgentRuntime max_tool_calls enforcement ───────────────────────────────────

print("\n-- AgentRuntime max_tool_calls enforcement --")


async def _run_agent_with_tool_calls(max_tool_calls: int, num_tool_calls: int) -> dict:
    """Run an agent that issues num_tool_calls tool calls, bounded by max_tool_calls."""
    tool_calls = [_tool_call() for _ in range(num_tool_calls)]
    from vidbyte.tools.base import BaseTool
    from vidbyte.tools.types import ToolResult, ToolSpec

    class FakeTool(BaseTool):
        def spec(self):
            return ToolSpec(name="fake_tool", description="fake")

        async def execute(self, call):
            return ToolResult.success("fake_tool", "ok")

    settings = AgentLoopSettings(max_tool_calls=max_tool_calls)
    agent = BaseAgent(
        name="test",
        system_prompt="test",
        runner=EchoRunner(tool_calls=tool_calls),
        tools=[FakeTool()],
        agent_loop_settings=settings,
    )
    reply = await agent.generate_reply("go")
    return dict(reply.metadata)


def _test_max_tool_calls_stops_loop():
    meta = asyncio.run(_run_agent_with_tool_calls(max_tool_calls=1, num_tool_calls=3))
    stop = meta.get("stop_reason")
    assert stop == AgentStopReason.MAX_TOOL_CALLS.value, f"expected max_tool_calls stop, got {stop!r}"


run("stops with MAX_TOOL_CALLS stop reason when tool call count reaches max_tool_calls", _test_max_tool_calls_stops_loop)


def _test_no_early_stop_below_limit():
    meta = asyncio.run(_run_agent_with_tool_calls(max_tool_calls=5, num_tool_calls=1))
    stop = meta.get("stop_reason")
    assert stop in (AgentStopReason.IS_DONE.value, AgentStopReason.FINAL_RESPONSE.value), \
        f"expected normal completion, got {stop!r}"


run("does not stop early when tool call count is below max_tool_calls", _test_no_early_stop_below_limit)


def _test_max_tool_calls_wins_over_max_iterations():
    meta = asyncio.run(_run_agent_with_tool_calls(max_tool_calls=1, num_tool_calls=5))
    stop = meta.get("stop_reason")
    assert stop == AgentStopReason.MAX_TOOL_CALLS.value, f"expected max_tool_calls stop, got {stop!r}"


run("stops on MAX_TOOL_CALLS even if max_iterations has not been reached", _test_max_tool_calls_wins_over_max_iterations)


def _test_no_max_tool_calls_no_enforcement():
    meta = asyncio.run(_run_agent_with_tool_calls(max_tool_calls=999, num_tool_calls=2))
    stop = meta.get("stop_reason")
    assert stop != AgentStopReason.MAX_TOOL_CALLS.value, f"expected no max_tool_calls stop, got {stop!r}"


run("does not enforce max_tool_calls when far above the call count", _test_no_max_tool_calls_no_enforcement)

# ── AgentStopReason enum ──────────────────────────────────────────────────────

print("\n-- AgentStopReason enum --")


def _test_stop_reason_enum_has_max_tool_calls():
    assert hasattr(AgentStopReason, "MAX_TOOL_CALLS")
    assert AgentStopReason.MAX_TOOL_CALLS.value == "max_tool_calls"


run("AgentStopReason has MAX_TOOL_CALLS value", _test_stop_reason_enum_has_max_tool_calls)

# ── Summary ───────────────────────────────────────────────────────────────────

total = _passed + _failed
print(f"\n{_passed}/{total} tests passed")
if _failed:
    print(f"\n{_failed} test(s) FAILED")
    sys.exit(1)

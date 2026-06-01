# -*- coding: utf-8 -*-
"""Verification script for the typed-output-schema feature.

Runs every test case from the design doc Section 10 and prints PASS/FAIL per case.
Exits with code 1 if any test fails.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import traceback
from typing import Any

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def _run_test(name: str, fn: Any) -> None:
    """Execute one test case, record pass/fail, and print the result."""
    try:
        fn()
        _results.append((name, True, ""))
        print(f"  PASS  {name}")
    except Exception as exc:
        _results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def _run_async_test(name: str, coro: Any) -> None:
    """Execute one async test case synchronously."""
    try:
        asyncio.run(coro)
        _results.append((name, True, ""))
        print(f"  PASS  {name}")
    except Exception as exc:
        _results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from pydantic import BaseModel

from vidbyte.tools.output_schema import OutputSchemaValidator
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec, ToolStatus, ToolParameter
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.agents import AgentSpec
from vidbyte.tools.base import BaseTool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixture Pydantic model
# ---------------------------------------------------------------------------

class RowsResult(BaseModel):
    rows: list[str]
    count: int


# ---------------------------------------------------------------------------
# OutputSchemaValidator tests
# ---------------------------------------------------------------------------

print("\n=== OutputSchemaValidator ===")


def test_resolve_pydantic_type() -> None:
    schema = OutputSchemaValidator.resolve(RowsResult)
    assert "properties" in schema, f"Expected JSON Schema dict, got: {schema}"
    assert "rows" in schema["properties"]


def test_resolve_raw_dict() -> None:
    raw = {"type": "object", "properties": {"x": {"type": "integer"}}}
    resolved = OutputSchemaValidator.resolve(raw)
    assert resolved == raw


def test_validate_valid_json_pydantic() -> None:
    data = json.dumps({"rows": ["a", "b"], "count": 2})
    value, error = OutputSchemaValidator.validate(data, RowsResult)
    assert error is None, f"Expected no error, got: {error}"
    assert isinstance(value, RowsResult)
    assert value.count == 2


def test_validate_invalid_json() -> None:
    value, error = OutputSchemaValidator.validate("not json", RowsResult)
    assert value is None
    assert error is not None
    assert "not valid JSON" in error


def test_validate_empty_string() -> None:
    value, error = OutputSchemaValidator.validate("", RowsResult)
    assert value is None
    assert error is not None


def test_validate_wrong_pydantic_shape() -> None:
    data = json.dumps({"wrong_field": 42})
    value, error = OutputSchemaValidator.validate(data, RowsResult)
    assert value is None
    assert error is not None
    assert "schema" in error.lower() or "does not match" in error.lower()


def test_validate_raw_dict_schema() -> None:
    raw_schema = {"type": "object"}
    data = json.dumps({"anything": True})
    value, error = OutputSchemaValidator.validate(data, raw_schema)
    assert error is None
    assert value == {"anything": True}


def test_schema_prompt_hint_contains_schema() -> None:
    hint = OutputSchemaValidator.schema_prompt_hint(RowsResult)
    assert "rows" in hint
    assert "count" in hint
    assert "```json" in hint


_run_test("resolve() with Pydantic BaseModel returns JSON Schema", test_resolve_pydantic_type)
_run_test("resolve() with raw dict returns copy of dict", test_resolve_raw_dict)
_run_test("validate() valid JSON + Pydantic model returns(instance, None)", test_validate_valid_json_pydantic)
_run_test("validate() invalid JSON returns(None, error)", test_validate_invalid_json)
_run_test("validate() empty string returns(None, error)", test_validate_empty_string)
_run_test("validate() wrong Pydantic shape returns(None, error)", test_validate_wrong_pydantic_shape)
_run_test("validate() valid JSON + raw dict schema returns(dict, None)", test_validate_raw_dict_schema)
_run_test("schema_prompt_hint() contains schema fields", test_schema_prompt_hint_contains_schema)


# ---------------------------------------------------------------------------
# ToolSpec / ToolResult backward-compat tests
# ---------------------------------------------------------------------------

print("\n=== ToolSpec / ToolResult backward-compat ===")


def test_toolspec_no_output_schema() -> None:
    spec = ToolSpec(name="echo", description="Echo text.")
    assert spec.output_schema is None


def test_toolspec_with_pydantic_output_schema() -> None:
    spec = ToolSpec(name="echo", description="Echo text.", output_schema=RowsResult)
    assert spec.output_schema is RowsResult


def test_toolspec_with_dict_output_schema() -> None:
    schema = {"type": "object"}
    spec = ToolSpec(name="echo", description="Echo text.", output_schema=schema)
    assert spec.output_schema == schema


def test_toolresult_success_no_structured() -> None:
    result = ToolResult.success("echo", "hello")
    assert result.structured is None
    assert result.output == "hello"
    assert result.status is ToolStatus.SUCCESS


def test_toolresult_error_no_structured() -> None:
    result = ToolResult.error("echo", "something went wrong")
    assert result.structured is None
    assert result.status is ToolStatus.ERROR


def test_toolresult_replace_structured() -> None:
    result = ToolResult.success("echo", '{"rows": [], "count": 0}')
    updated = dataclasses.replace(result, structured={"rows": [], "count": 0})
    assert updated.structured == {"rows": [], "count": 0}
    assert result.structured is None


_run_test("ToolSpec without output_schema defaults to None", test_toolspec_no_output_schema)
_run_test("ToolSpec with Pydantic output_schema stores it", test_toolspec_with_pydantic_output_schema)
_run_test("ToolSpec with dict output_schema stores it", test_toolspec_with_dict_output_schema)
_run_test("ToolResult.success() without structured returnsstructured=None", test_toolresult_success_no_structured)
_run_test("ToolResult.error() without structured returnsstructured=None", test_toolresult_error_no_structured)
_run_test("dataclasses.replace() on frozen ToolResult works", test_toolresult_replace_structured)


# ---------------------------------------------------------------------------
# AgentResult / AgentSpec backward-compat tests
# ---------------------------------------------------------------------------

print("\n=== AgentResult / AgentSpec backward-compat ===")


def test_agentresult_no_structured() -> None:
    result = AgentResult(output="hello", strategy_name="direct_runner")
    assert result.structured is None


def test_agentspec_no_output_schema() -> None:
    spec = AgentSpec(name="agent", system_prompt="You are helpful.")
    assert spec.output_schema is None


def test_agentspec_with_output_schema() -> None:
    spec = AgentSpec(name="agent", system_prompt="You are helpful.", output_schema=RowsResult)
    assert spec.output_schema is RowsResult


_run_test("AgentResult without structured returnsstructured=None", test_agentresult_no_structured)
_run_test("AgentSpec without output_schema returnsNone", test_agentspec_no_output_schema)
_run_test("AgentSpec with output_schema stores it", test_agentspec_with_output_schema)


# ---------------------------------------------------------------------------
# ToolExecutor output schema validation tests
# ---------------------------------------------------------------------------

print("\n=== ToolExecutor output schema validation ===")


class SchemaToolValid(BaseTool):
    """Returns valid JSON conforming to RowsResult."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="schema_valid",
            description="Returns structured rows.",
            output_schema=RowsResult,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self.name, json.dumps({"rows": ["x"], "count": 1}))


class SchemaToolInvalidJson(BaseTool):
    """Returns non-JSON output despite declaring a schema."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="schema_invalid_json",
            description="Returns bad output.",
            output_schema=RowsResult,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self.name, "this is not json")


class SchemaToolWrongShape(BaseTool):
    """Returns JSON that doesn't match the Pydantic model."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="schema_wrong_shape",
            description="Returns wrong shape.",
            output_schema=RowsResult,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self.name, json.dumps({"unexpected": True}))


class SchemaToolNone(BaseTool):
    """No output schema — any output is fine."""

    def spec(self) -> ToolSpec:
        return ToolSpec(name="no_schema", description="No schema.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self.name, "raw text")


class SchemaToolError(BaseTool):
    """Returns an error result — schema must not be validated."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="schema_error_result",
            description="Returns an error.",
            output_schema=RowsResult,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.error(self.name, "something failed")


def _make_executor(*tools: BaseTool) -> ToolExecutor:
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    return ToolExecutor(registry)


async def test_executor_valid_schema_populates_structured() -> None:
    executor = _make_executor(SchemaToolValid())
    result = await executor.execute_call(ToolCall("schema_valid", {}))
    assert result.status is ToolStatus.SUCCESS, f"Expected SUCCESS, got {result.status}"
    assert result.structured is not None, "structured should be populated"
    assert isinstance(result.structured, RowsResult)
    assert result.structured.count == 1


async def test_executor_invalid_json_returns_error() -> None:
    executor = _make_executor(SchemaToolInvalidJson())
    result = await executor.execute_call(ToolCall("schema_invalid_json", {}))
    assert result.status is ToolStatus.ERROR, f"Expected ERROR, got {result.status}"
    assert result.metadata.get("error") == "output_schema_violation"


async def test_executor_wrong_pydantic_shape_returns_error() -> None:
    executor = _make_executor(SchemaToolWrongShape())
    result = await executor.execute_call(ToolCall("schema_wrong_shape", {}))
    assert result.status is ToolStatus.ERROR, f"Expected ERROR, got {result.status}"
    assert result.metadata.get("error") == "output_schema_violation"


async def test_executor_no_schema_passes_through() -> None:
    executor = _make_executor(SchemaToolNone())
    result = await executor.execute_call(ToolCall("no_schema", {}))
    assert result.status is ToolStatus.SUCCESS
    assert result.structured is None
    assert result.output == "raw text"


async def test_executor_error_result_no_validation() -> None:
    executor = _make_executor(SchemaToolError())
    result = await executor.execute_call(ToolCall("schema_error_result", {}))
    assert result.status is ToolStatus.ERROR
    assert result.metadata.get("error") != "output_schema_violation", \
        "Error results should not be schema-validated"


_run_async_test("Executor: valid schema returnsstructured populated", test_executor_valid_schema_populates_structured())
_run_async_test("Executor: non-JSON output returnsToolResult.error with output_schema_violation", test_executor_invalid_json_returns_error())
_run_async_test("Executor: wrong Pydantic shape returnsToolResult.error", test_executor_wrong_pydantic_shape_returns_error())
_run_async_test("Executor: no schema returnsstructured=None, no error", test_executor_no_schema_passes_through())
_run_async_test("Executor: error result returnsno schema validation attempted", test_executor_error_result_no_validation())


# ---------------------------------------------------------------------------
# AgentRuntime output schema tests (unit — no live model)
# ---------------------------------------------------------------------------

print("\n=== AgentRuntime output schema (unit) ===")

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy


def _make_runtime(output_schema: Any = None) -> AgentRuntime:
    return AgentRuntime(
        agent_name="test-agent",
        system_prompt="You are helpful.",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        output_schema=output_schema,
    )


def test_runtime_system_string_has_hint() -> None:
    from vidbyte.lib.dataclasses.context import BaseAgentContext
    runtime = _make_runtime(output_schema=RowsResult)
    ctx = BaseAgentContext(system_prompt="You are helpful.")
    system = runtime._build_system_string(ctx)
    assert "```json" in system, "Schema hint should appear in system string"
    assert "rows" in system


def test_runtime_system_string_no_hint_when_no_schema() -> None:
    from vidbyte.lib.dataclasses.context import BaseAgentContext
    runtime = _make_runtime(output_schema=None)
    ctx = BaseAgentContext(system_prompt="You are helpful.")
    system = runtime._build_system_string(ctx)
    assert "```json" not in system, "No hint when output_schema is None"


def test_runtime_final_result_valid_schema() -> None:
    runtime = _make_runtime(output_schema=RowsResult)
    result = runtime._final_result(
        json.dumps({"rows": ["a"], "count": 1}),
        runner_metadata={},
        contexts=[],
        iteration_count=1,
        tokens_used=None,
        stop_reason=__import__("vidbyte.lib.dataclasses.agents", fromlist=["AgentStopReason"]).AgentStopReason.IS_DONE,
    )
    assert result.structured is not None
    assert isinstance(result.structured, RowsResult)
    assert "output_schema_error" not in result.metadata


def test_runtime_final_result_invalid_schema() -> None:
    from vidbyte.lib.dataclasses.agents import AgentStopReason
    runtime = _make_runtime(output_schema=RowsResult)
    result = runtime._final_result(
        "this is not json",
        runner_metadata={},
        contexts=[],
        iteration_count=1,
        tokens_used=None,
        stop_reason=AgentStopReason.FINAL_RESPONSE,
    )
    assert result.structured is None
    assert "output_schema_error" in result.metadata


def test_runtime_final_result_no_schema() -> None:
    from vidbyte.lib.dataclasses.agents import AgentStopReason
    runtime = _make_runtime(output_schema=None)
    result = runtime._final_result(
        "plain text output",
        runner_metadata={},
        contexts=[],
        iteration_count=1,
        tokens_used=None,
        stop_reason=AgentStopReason.FINAL_RESPONSE,
    )
    assert result.structured is None
    assert "output_schema_error" not in result.metadata


def test_runtime_middleware_metadata_preserves_structured() -> None:
    from vidbyte.lib.dataclasses.agents import AgentStopReason
    runtime = _make_runtime(output_schema=RowsResult)
    result_with_structured = AgentResult(
        output=json.dumps({"rows": [], "count": 0}),
        strategy_name="direct_runner",
        structured=RowsResult(rows=[], count=0),
    )
    rebuilt = runtime._with_middleware_metadata(result_with_structured)
    assert rebuilt.structured is not None
    assert isinstance(rebuilt.structured, RowsResult)


_run_test("Runtime: system string includes schema hint when output_schema set", test_runtime_system_string_has_hint)
_run_test("Runtime: system string has no hint when output_schema=None", test_runtime_system_string_no_hint_when_no_schema)
_run_test("Runtime: _final_result valid schema returnsstructured populated", test_runtime_final_result_valid_schema)
_run_test("Runtime: _final_result invalid schema returnsstructured=None + metadata error key", test_runtime_final_result_invalid_schema)
_run_test("Runtime: _final_result no schema returnsstructured=None no error", test_runtime_final_result_no_schema)
_run_test("Runtime: _with_middleware_metadata preserves structured", test_runtime_middleware_metadata_preserves_structured)


# ---------------------------------------------------------------------------
# BaseAgent output_schema wiring tests
# ---------------------------------------------------------------------------

print("\n=== BaseAgent output_schema wiring ===")

from vidbyte.agents.base import BaseAgent


def test_base_agent_default_no_schema() -> None:
    agent = BaseAgent(name="test", system_prompt="Hello.")
    assert agent.output_schema is None


def test_base_agent_stores_schema() -> None:
    agent = BaseAgent(name="test", system_prompt="Hello.", output_schema=RowsResult)
    assert agent.output_schema is RowsResult


def test_base_agent_fork_inherits_schema() -> None:
    parent = BaseAgent(name="parent", system_prompt="Hello.", output_schema=RowsResult)
    child = parent.fork(name="child")
    assert child.output_schema is RowsResult


def test_base_agent_runtime_receives_schema() -> None:
    agent = BaseAgent(name="test", system_prompt="Hello.", output_schema=RowsResult)
    runtime = agent._runtime()
    assert runtime.output_schema is RowsResult


def test_base_agent_runtime_no_schema() -> None:
    agent = BaseAgent(name="test", system_prompt="Hello.")
    runtime = agent._runtime()
    assert runtime.output_schema is None


_run_test("BaseAgent without output_schema defaults to None", test_base_agent_default_no_schema)
_run_test("BaseAgent stores output_schema", test_base_agent_stores_schema)
_run_test("BaseAgent.fork() inherits output_schema from parent", test_base_agent_fork_inherits_schema)
_run_test("BaseAgent._runtime() receives output_schema", test_base_agent_runtime_receives_schema)
_run_test("BaseAgent._runtime() gets None when no schema", test_base_agent_runtime_no_schema)


# ---------------------------------------------------------------------------
# AgentRuntime tool schema validation (via execute_tool_call)
# ---------------------------------------------------------------------------

print("\n=== AgentRuntime tool output schema validation ===")


async def test_runtime_tool_valid_schema() -> None:
    tools = Tools().add(SchemaToolValid())
    runtime = AgentRuntime(
        agent_name="test",
        system_prompt=".",
        tools=tools,
        permission_policy=PermissionPolicy(),
    )
    ctx_record, result = await runtime.execute_tool_call(
        ToolCall("schema_valid", {}), provider="anthropic"
    )
    assert result.status is ToolStatus.SUCCESS
    assert result.structured is not None
    assert isinstance(result.structured, RowsResult)


async def test_runtime_tool_invalid_json_returns_error() -> None:
    tools = Tools().add(SchemaToolInvalidJson())
    runtime = AgentRuntime(
        agent_name="test",
        system_prompt=".",
        tools=tools,
        permission_policy=PermissionPolicy(),
    )
    ctx_record, result = await runtime.execute_tool_call(
        ToolCall("schema_invalid_json", {}), provider="anthropic"
    )
    assert result.status is ToolStatus.ERROR
    assert result.metadata.get("error") == "output_schema_violation"


_run_async_test("Runtime.execute_tool_call: valid schema returnsstructured populated", test_runtime_tool_valid_schema())
_run_async_test("Runtime.execute_tool_call: invalid JSON returnserror with output_schema_violation", test_runtime_tool_invalid_json_returns_error())


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

total = len(_results)
passed = sum(1 for _, ok, _ in _results if ok)
failed = total - passed

print(f"\n{'='*60}")
print(f"{passed}/{total} tests passed")

if failed:
    print(f"\nFailed tests:")
    for name, ok, err in _results:
        if not ok:
            print(f"  - {name}: {err}")
    sys.exit(1)
else:
    print("All tests passed.")
    sys.exit(0)

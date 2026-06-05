"""Context Protocol Header

Description:
    Standalone verification script for the continual trace agent feature.
Purpose:
    Exercises every Section 10 test case (schema/option validation, tool merge
    semantics, middleware cadence, fail-open, BaseAgent wiring, and an end-to-end
    run) and prints PASS/FAIL per case with a final summary, exiting non-zero on
    any failure.
Architecture:
    - Checks: ordered list of named async/sync verification callables.
Relations:
    Mirrors tests/test_continual_trace.py against the public vidbyte surface.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel, Field

from vidbyte import Agent, TraceOption, TraceSchema
from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec
from vidbyte.trace.continual import ActionTrace, ContinualTraceMiddleware
from vidbyte.trace.continual.middleware import RESULT_METADATA_KEY
from vidbyte.trace.continual.tools import UPDATE_TRACE_TOOL_NAME, UpdateTraceTool


class ProgressModel(BaseModel):
    """Progress."""

    goal: str = Field(description="The goal.")
    steps: list[str] = Field(default_factory=list, description="Ordered steps.")
    done: bool = Field(default=False, description="Completed flag.")


def schema() -> TraceSchema:
    return TraceSchema.from_model(ProgressModel, name="progress")


def call(trace: object) -> ToolCall:
    return ToolCall(tool_name=UPDATE_TRACE_TOOL_NAME, arguments={"trace": trace})


def fc(name: str, arguments: str, call_id: str) -> dict:
    return {"output": [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}]}


class Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class Lookup(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Look something up.")

    async def execute(self, c: ToolCall) -> ToolResult:
        return ToolResult.success("lookup", "found")


class ScriptedRunner:
    def __init__(self, *, trace_raises: bool = False) -> None:
        self.trace_raises = trace_raises
        self.main_payloads: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> Resp:
        is_trace = "<trace_schema>" in prompt
        has_messages = "messages" in kwargs
        if is_trace:
            if self.trace_raises:
                raise RuntimeError("trace model failure")
            if not has_messages:
                match = re.search(r'"iteration_count":\s*(\d+)', prompt)
                iteration = int(match.group(1)) if match else 0
                return Resp(fc("updateTrace", '{"trace": {"steps": ["step-%d"]}}' % iteration, "t1"))
            return Resp(fc("isDone", '{"final_answer": "traced"}', "t2"))
        self.main_payloads.append(prompt + str(kwargs.get("messages", "")))
        if not has_messages:
            return Resp(fc("lookup", "{}", "m1"))
        return Resp(fc("isDone", '{"final_answer": "done"}', "m2"))


# --- Verification cases -----------------------------------------------------
async def case_option_from_model() -> None:
    option = TraceOption.continual(ProgressModel)
    assert option.schema.fields["steps"].type is TraceFieldType.ARRAY
    assert option.schema.fields["done"].type is TraceFieldType.BOOLEAN


async def case_option_from_mapping() -> None:
    option = TraceOption.continual({"summary": "running summary"})
    assert option.schema.fields["summary"].type is TraceFieldType.STRING


async def case_rejects_empty_schema() -> None:
    _assert_raises(ValueError, lambda: TraceOption.continual({}))


async def case_rejects_bad_interval() -> None:
    _assert_raises(ValueError, lambda: TraceOption.continual(ProgressModel, every_n_iterations=0))


async def case_rejects_bad_max_iters() -> None:
    _assert_raises(ValueError, lambda: TraceOption.continual(ProgressModel, max_trace_iterations=4))


async def case_from_model_requires_description() -> None:
    class NoDesc(BaseModel):
        a: str

    _assert_raises(ValueError, lambda: TraceSchema.from_model(NoDesc))


async def case_initial_artifact() -> None:
    assert schema().initial_artifact() == {"goal": None, "steps": None, "done": None}


async def case_tool_appends_array() -> None:
    tool = UpdateTraceTool(schema())
    await tool.execute(call({"steps": ["a"]}))
    await tool.execute(call({"steps": ["b"]}))
    assert tool.current_trace()["steps"] == ["a", "b"]


async def case_tool_dedupes() -> None:
    tool = UpdateTraceTool(schema())
    await tool.execute(call({"steps": ["a"]}))
    await tool.execute(call({"steps": ["a", "c"]}))
    assert tool.current_trace()["steps"] == ["a", "c"]


async def case_tool_deep_merges_object() -> None:
    obj_schema = TraceSchema(name="o", fields={"meta": TraceField(description="d", type=TraceFieldType.OBJECT)})
    tool = UpdateTraceTool(obj_schema)
    await tool.execute(call({"meta": {"x": 1}}))
    await tool.execute(call({"meta": {"y": 2}}))
    assert tool.current_trace()["meta"] == {"x": 1, "y": 2}


async def case_tool_replaces_scalar_preserves_omitted() -> None:
    tool = UpdateTraceTool(schema())
    await tool.execute(call({"goal": "first", "steps": ["a"]}))
    await tool.execute(call({"goal": "second"}))
    trace = tool.current_trace()
    assert trace["goal"] == "second" and trace["steps"] == ["a"]


async def case_tool_drops_unknown_keys() -> None:
    tool = UpdateTraceTool(schema())
    await tool.execute(call({"goal": "g", "unknown": "x"}))
    assert "unknown" not in tool.current_trace()


async def case_tool_type_mismatch_errors() -> None:
    tool = UpdateTraceTool(schema())
    result = await tool.execute(call({"steps": "not-a-list"}))
    assert result.status.value == "error" and "output shape mismatch" in result.output


async def case_tool_non_object_errors() -> None:
    result = await UpdateTraceTool(schema()).execute(call("nope"))
    assert result.status.value == "error"


async def case_integration_accumulates() -> None:
    runner = ScriptedRunner()
    agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[Lookup()], trace_option=TraceOption.continual(ProgressModel, every_n_iterations=1))
    reply = await agent.arun("task")
    trace = reply.metadata["trace"]
    assert reply.content == "done"
    assert "step-1" in trace["steps"] and "step-2" in trace["steps"]
    assert agent.last_trace == trace


async def case_integration_no_leak() -> None:
    runner = ScriptedRunner()
    agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[Lookup()], trace_option=TraceOption.continual(ProgressModel, every_n_iterations=1))
    await agent.arun("task")
    for payload in runner.main_payloads:
        assert "step-1" not in payload and "trace_so_far" not in payload


async def case_integration_fail_open() -> None:
    runner = ScriptedRunner(trace_raises=True)
    agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[Lookup()], trace_option=TraceOption.continual(ProgressModel, every_n_iterations=1))
    reply = await agent.arun("task")
    assert reply.content == "done"
    assert reply.metadata["trace_metadata"]["error_count"] >= 1


async def case_non_linear_guard() -> None:
    _assert_raises(ConfigurationError, lambda: Agent(name="a", system_prompt="s", runtime="mcts_search", trace_option=TraceOption.continual(ProgressModel)))


async def case_fork_preserves_option() -> None:
    agent = Agent(name="a", system_prompt="s", trace_option=TraceOption.continual(ProgressModel))
    assert agent.fork(name="b")._trace_option.enabled


async def case_prebuilt_action_trace() -> None:
    assert set(ActionTrace.fields) == {"goal", "actions_taken", "mistakes", "current_status"}
    assert ActionTrace.fields["actions_taken"].type is TraceFieldType.ARRAY


async def case_middleware_fail_open_flag() -> None:
    assert ContinualTraceMiddleware.fail_closed is False
    assert RESULT_METADATA_KEY == "__result_metadata__"


def _assert_raises(exc_type: type[BaseException], fn) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


CHECKS = [
    ("option_from_pydantic_model", case_option_from_model),
    ("option_from_mapping_defaults_string", case_option_from_mapping),
    ("rejects_empty_schema", case_rejects_empty_schema),
    ("rejects_non_positive_interval", case_rejects_bad_interval),
    ("rejects_out_of_range_max_iterations", case_rejects_bad_max_iters),
    ("from_model_requires_description", case_from_model_requires_description),
    ("initial_artifact_all_none", case_initial_artifact),
    ("tool_appends_array", case_tool_appends_array),
    ("tool_dedupes_duplicates", case_tool_dedupes),
    ("tool_deep_merges_object", case_tool_deep_merges_object),
    ("tool_replaces_scalar_preserves_omitted", case_tool_replaces_scalar_preserves_omitted),
    ("tool_drops_unknown_keys", case_tool_drops_unknown_keys),
    ("tool_type_mismatch_errors", case_tool_type_mismatch_errors),
    ("tool_non_object_errors", case_tool_non_object_errors),
    ("integration_accumulates_and_surfaces", case_integration_accumulates),
    ("integration_no_context_leak", case_integration_no_leak),
    ("integration_fail_open", case_integration_fail_open),
    ("non_linear_runtime_guard", case_non_linear_guard),
    ("fork_preserves_trace_option", case_fork_preserves_option),
    ("prebuilt_action_trace", case_prebuilt_action_trace),
    ("middleware_fail_open_flag", case_middleware_fail_open_flag),
]


async def main() -> int:
    passed = 0
    for name, check in CHECKS:
        try:
            await check()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
    total = len(CHECKS)
    print(f"\n{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

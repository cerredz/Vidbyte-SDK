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

from pydantic import BaseModel, Field, ValidationError

from tests.agent_test_support import build_test_agent
from vidbyte import Agent, AgentForkSettings, TraceOption, TraceSchema
from vidbyte.lib.constants.trace import MAX_TRACE_FIELD_NESTING_DEPTH
from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec
from vidbyte.trace.continual import (
    ActionTrace,
    CalibrationTrace,
    ContinualTraceMiddleware,
    CounterfactualAlternativesTrace,
    ErrorTaxonomyTrace,
    HierarchicalTaskTreeTrace,
    SelfConsistencyEnsembleTrace,
)
from vidbyte.trace.continual.middleware import RESULT_METADATA_KEY
from vidbyte.trace.continual.tools import UPDATE_TRACE_TOOL_NAME, UpdateTraceTool


class ProgressModel(BaseModel):
    """Progress."""

    goal: str = Field(description="The goal.")
    steps: list[str] = Field(default_factory=list, description="Ordered steps.")
    done: bool = Field(default=False, description="Completed flag.")


def schema() -> TraceSchema:
    return TraceSchema.from_model(ProgressModel, name="progress")


class SubRecordModel(BaseModel):
    """One nested record used to exercise TraceField.fields/.items."""

    label: str = Field(description="A label.")
    count: int = Field(description="A count.")


class SnapshotWithTagsModel(BaseModel):
    """A nested record with an array-shaped subfield, used to test that OBJECT merges do not make it accumulate."""

    label: str = Field(description="A label.")
    tags: list[str] = Field(default_factory=list, description="A nested list.")


class NestedModel(BaseModel):
    """Nested."""

    items: list[SubRecordModel] = Field(default_factory=list, description="A list of records.")
    snapshot: SubRecordModel = Field(description="A single nested record.")
    tagged_snapshot: SnapshotWithTagsModel = Field(description="A nested record containing an array-shaped subfield.")
    plain: dict = Field(default_factory=dict, description="An opaque object.")
    plain_list: list[dict] = Field(default_factory=list, description="An opaque list of objects.")


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
    agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[Lookup()], trace_option=TraceOption.continual(ProgressModel, every_n_iterations=1))
    reply = await agent.arun("task")
    trace = reply.metadata["trace"]
    assert reply.content == "done"
    assert "step-1" in trace["steps"] and "step-2" in trace["steps"]
    assert agent.last_trace == trace


async def case_integration_no_leak() -> None:
    runner = ScriptedRunner()
    agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[Lookup()], trace_option=TraceOption.continual(ProgressModel, every_n_iterations=1))
    await agent.arun("task")
    for payload in runner.main_payloads:
        assert "step-1" not in payload and "trace_so_far" not in payload


async def case_integration_fail_open() -> None:
    runner = ScriptedRunner(trace_raises=True)
    agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[Lookup()], trace_option=TraceOption.continual(ProgressModel, every_n_iterations=1))
    reply = await agent.arun("task")
    assert reply.content == "done"
    assert reply.metadata["trace_metadata"]["error_count"] >= 1


async def case_non_linear_guard() -> None:
    _assert_raises(ConfigurationError, lambda: Agent(name="a", system_prompt="s", runtime="mcts_search", trace_option=TraceOption.continual(ProgressModel)))


async def case_fork_preserves_option() -> None:
    agent = Agent(name="a", system_prompt="s", trace_option=TraceOption.continual(ProgressModel))
    assert agent.fork(AgentForkSettings(name="b"))._trace_option.enabled


async def case_prebuilt_action_trace() -> None:
    assert set(ActionTrace.fields) == {"goal", "actions_taken", "mistakes", "current_status"}
    assert ActionTrace.fields["actions_taken"].type is TraceFieldType.ARRAY


async def case_middleware_fail_open_flag() -> None:
    assert ContinualTraceMiddleware.fail_closed is False
    assert RESULT_METADATA_KEY == "__result_metadata__"


# --- Nested subfield/item shape (fields/items) -------------------------------
async def case_nested_object_builds_fields() -> None:
    nested = TraceSchema.from_model(NestedModel, name="nested")
    snapshot = nested.fields["snapshot"]
    assert snapshot.type is TraceFieldType.OBJECT
    assert set(snapshot.fields) == {"label", "count"}
    assert snapshot.fields["count"].type is TraceFieldType.INTEGER


async def case_nested_array_builds_items() -> None:
    nested = TraceSchema.from_model(NestedModel, name="nested")
    items_field = nested.fields["items"]
    assert items_field.type is TraceFieldType.ARRAY
    assert items_field.items is not None
    assert items_field.items.type is TraceFieldType.OBJECT
    assert set(items_field.items.fields) == {"label", "count"}


async def case_plain_dict_stays_opaque() -> None:
    nested = TraceSchema.from_model(NestedModel, name="nested")
    assert nested.fields["plain"].type is TraceFieldType.OBJECT
    assert nested.fields["plain"].fields is None
    assert nested.fields["plain_list"].type is TraceFieldType.ARRAY
    assert nested.fields["plain_list"].items is None


async def case_trace_field_rejects_empty_description() -> None:
    _assert_raises(ValidationError, lambda: TraceField(description="   "))


async def case_trace_field_rejects_fields_on_non_object() -> None:
    _assert_raises(ValidationError, lambda: TraceField(description="x", type=TraceFieldType.STRING, fields={"a": TraceField(description="a")}))


async def case_trace_field_rejects_items_on_non_array() -> None:
    _assert_raises(ValidationError, lambda: TraceField(description="x", type=TraceFieldType.STRING, items=TraceField(description="a")))


async def case_trace_field_rejects_excess_depth() -> None:
    built = TraceField(description="leaf")
    for level in range(MAX_TRACE_FIELD_NESTING_DEPTH - 1):
        built = TraceField(description=f"level-{level}", type=TraceFieldType.OBJECT, fields={"child": built})
    assert built._nesting_depth() == MAX_TRACE_FIELD_NESTING_DEPTH
    _assert_raises(ValidationError, lambda: TraceField(description="root", type=TraceFieldType.OBJECT, fields={"child": built}))


async def case_input_schema_renders_nested_properties() -> None:
    tool = UpdateTraceTool(TraceSchema.from_model(NestedModel, name="nested"))
    properties = tool.spec().input_schema["properties"]["trace"]["properties"]
    assert "properties" in properties["snapshot"]
    assert set(properties["snapshot"]["properties"]) == {"label", "count"}
    assert "items" in properties["items"]
    assert "properties" in properties["items"]["items"]


async def case_nested_update_validates_leaf_type() -> None:
    tool = UpdateTraceTool(TraceSchema.from_model(NestedModel, name="nested"))
    result = await tool.execute(call({"snapshot": {"label": "ok", "count": "not-an-int"}}))
    assert result.status.value == "error"
    assert "snapshot.count expected integer" in result.output


async def case_nested_array_element_validates() -> None:
    tool = UpdateTraceTool(TraceSchema.from_model(NestedModel, name="nested"))
    result = await tool.execute(call({"items": [{"label": "a", "count": 1}, {"label": "b", "count": "bad"}]}))
    assert result.status.value == "error"
    assert "items[1].count expected integer" in result.output


async def case_nested_valid_update_accumulates_array() -> None:
    tool = UpdateTraceTool(TraceSchema.from_model(NestedModel, name="nested"))
    await tool.execute(call({"items": [{"label": "a", "count": 1}]}))
    await tool.execute(call({"items": [{"label": "b", "count": 2}]}))
    trace = tool.current_trace()
    assert trace["items"] == [{"label": "a", "count": 1}, {"label": "b", "count": 2}]


async def case_nested_array_subfield_does_not_accumulate() -> None:
    # Documents the merge-semantics invariant: an OBJECT field's own merge preserves
    # sibling keys not present in a given update (shallow key-union), but any key that
    # IS present -- including an array-shaped one -- is replaced with its new value
    # whole, never element-wise appended the way a top-level ARRAY field would be.
    tool = UpdateTraceTool(TraceSchema.from_model(NestedModel, name="nested"))
    await tool.execute(call({"tagged_snapshot": {"label": "first", "tags": ["a"]}}))
    await tool.execute(call({"tagged_snapshot": {"tags": ["b"]}}))
    trace = tool.current_trace()
    assert trace["tagged_snapshot"]["tags"] == ["b"]
    assert trace["tagged_snapshot"]["label"] == "first"


async def case_prebuilt_hierarchical_task_tree_trace() -> None:
    assert len(HierarchicalTaskTreeTrace.fields) == 14
    nodes = HierarchicalTaskTreeTrace.fields["task_nodes"]
    assert nodes.type is TraceFieldType.ARRAY and nodes.items is not None
    assert "goal_success_verdict" in nodes.items.fields


async def case_prebuilt_calibration_trace() -> None:
    assert len(CalibrationTrace.fields) == 13
    assert CalibrationTrace.fields["best_calibrated_axis"].type is TraceFieldType.STRING


async def case_prebuilt_error_taxonomy_trace() -> None:
    assert len(ErrorTaxonomyTrace.fields) == 12
    events = ErrorTaxonomyTrace.fields["goal_success_error_events"]
    assert events.items is not None and "error_type" in events.items.fields


async def case_prebuilt_self_consistency_ensemble_trace() -> None:
    assert len(SelfConsistencyEnsembleTrace.fields) == 12


async def case_prebuilt_counterfactual_alternatives_trace() -> None:
    assert len(CounterfactualAlternativesTrace.fields) == 12


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
    ("nested_object_builds_fields", case_nested_object_builds_fields),
    ("nested_array_builds_items", case_nested_array_builds_items),
    ("plain_dict_stays_opaque", case_plain_dict_stays_opaque),
    ("trace_field_rejects_empty_description", case_trace_field_rejects_empty_description),
    ("trace_field_rejects_fields_on_non_object", case_trace_field_rejects_fields_on_non_object),
    ("trace_field_rejects_items_on_non_array", case_trace_field_rejects_items_on_non_array),
    ("trace_field_rejects_excess_depth", case_trace_field_rejects_excess_depth),
    ("input_schema_renders_nested_properties", case_input_schema_renders_nested_properties),
    ("nested_update_validates_leaf_type", case_nested_update_validates_leaf_type),
    ("nested_array_element_validates", case_nested_array_element_validates),
    ("nested_valid_update_accumulates_array", case_nested_valid_update_accumulates_array),
    ("nested_array_subfield_does_not_accumulate", case_nested_array_subfield_does_not_accumulate),
    ("prebuilt_hierarchical_task_tree_trace", case_prebuilt_hierarchical_task_tree_trace),
    ("prebuilt_calibration_trace", case_prebuilt_calibration_trace),
    ("prebuilt_error_taxonomy_trace", case_prebuilt_error_taxonomy_trace),
    ("prebuilt_self_consistency_ensemble_trace", case_prebuilt_self_consistency_ensemble_trace),
    ("prebuilt_counterfactual_alternatives_trace", case_prebuilt_counterfactual_alternatives_trace),
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

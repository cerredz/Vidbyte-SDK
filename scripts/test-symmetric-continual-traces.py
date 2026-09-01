"""Context Protocol Header

PURPOSE: Standalone, dependency-free verification of the six symmetric continual trace schemas against the public vidbyte import surface.
ROLE IN CODEBASE: Runnable companion to tests/test_symmetric_continual_traces.py; exercises schema shape, merge behavior, and one end-to-end agent run without pytest.
ARCHITECTURE NOTE: CHECKS is an ordered list of named async callables; main() runs each, prints PASS/FAIL, and exits non-zero on any failure, mirroring scripts/test-continual-trace.py's structure.
COMMON MODIFICATION PATTERNS: Add a new (name, case_fn) tuple to CHECKS when a new symmetric schema or merge behavior needs coverage; keep each case_fn a single focused assertion.
KNOWN EDGE CASES: Integration cases must use tests.agent_test_support.build_test_agent, not Agent(runner=...) directly, since the public Agent constructor no longer accepts a runner kwarg.
RELATED DOCS: docs/design/symmetric-continual-trace-schemas.md and skills/vidbyte-sdk/continual-tracing.md.
TESTS: Run directly via `python scripts/test-symmetric-continual-traces.py`; mirrored by tests/test_symmetric_continual_traces.py.

Description:
    Standalone verification script for the six symmetric continual trace schemas.
Purpose:
    Exercises every Section 10 test case from docs/design/symmetric-continual-trace-schemas.md
    (schema shape assertions, merge behavior per field type, and an end-to-end run) and prints
    PASS/FAIL per case with a final summary, exiting non-zero on any failure.
Architecture:
    - CHECKS: ordered list of named async verification callables.
Relations:
    Mirrors tests/test_symmetric_continual_traces.py against the public vidbyte surface.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.agent_test_support import build_test_agent
from vidbyte import (
    SymmetricChecklistTrace,
    SymmetricEventLedgerTrace,
    SymmetricEvidenceTrace,
    SymmetricFlatTrace,
    SymmetricSubScoreTrace,
    SymmetricTimelineTrace,
    TraceOption,
)
from vidbyte.lib.dataclasses.trace import TraceFieldType
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec
from vidbyte.trace.continual.tools import UPDATE_TRACE_TOOL_NAME, UpdateTraceTool

ALL_SCHEMAS = {
    "SymmetricFlatTrace": SymmetricFlatTrace,
    "SymmetricChecklistTrace": SymmetricChecklistTrace,
    "SymmetricSubScoreTrace": SymmetricSubScoreTrace,
    "SymmetricEventLedgerTrace": SymmetricEventLedgerTrace,
    "SymmetricTimelineTrace": SymmetricTimelineTrace,
    "SymmetricEvidenceTrace": SymmetricEvidenceTrace,
}
AXES = ("goal_success", "path_quality", "answer_correctness")


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


class EventLedgerScriptedRunner:
    def __init__(self) -> None:
        self.main_payloads: list[str] = []
        self._trace_call = 0

    def run(self, prompt: str, **kwargs: object) -> Resp:
        is_trace = "<trace_schema>" in prompt
        has_messages = "messages" in kwargs
        if is_trace:
            if not has_messages:
                self._trace_call += 1
                event = {"iteration": self._trace_call, "subgoal_id": "s1", "status": "in_progress", "description": "pass-%d" % self._trace_call}
                return Resp(fc("updateTrace", '{"trace": {"goal_success_events": [%s]}}' % json.dumps(event), "t1"))
            return Resp(fc("isDone", '{"final_answer": "traced"}', "t2"))
        self.main_payloads.append(prompt + str(kwargs.get("messages", "")))
        if not has_messages:
            return Resp(fc("lookup", "{}", "m1"))
        return Resp(fc("isDone", '{"final_answer": "done"}', "m2"))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# --- Schema shape checks -----------------------------------------------------
async def case_flat_twelve_fields_four_per_axis() -> None:
    assert_true(len(SymmetricFlatTrace.fields) == 12, "expected 12 fields")
    for axis in AXES:
        axis_fields = [n for n in SymmetricFlatTrace.fields if n.startswith(axis)]
        assert_true(len(axis_fields) == 4, f"expected 4 fields for axis {axis}")


async def case_flat_types_correct() -> None:
    for axis in AXES:
        assert_true(SymmetricFlatTrace.fields[f"{axis}_confidence"].type is TraceFieldType.NUMBER, "confidence should be NUMBER")
        assert_true(SymmetricFlatTrace.fields[f"{axis}_evidence"].type is TraceFieldType.ARRAY, "evidence should be ARRAY")
        assert_true(SymmetricFlatTrace.fields[f"{axis}_status"].type is TraceFieldType.STRING, "status should be STRING")


async def case_checklist_all_array() -> None:
    assert_true(len(SymmetricChecklistTrace.fields) == 3, "expected 3 fields")
    for axis in AXES:
        assert_true(SymmetricChecklistTrace.fields[f"{axis}_checks"].type is TraceFieldType.ARRAY, "checks should be ARRAY")


async def case_subscore_nine_fields_all_number() -> None:
    assert_true(len(SymmetricSubScoreTrace.fields) == 9, "expected 9 fields")
    assert_true(all(spec.type is TraceFieldType.NUMBER for spec in SymmetricSubScoreTrace.fields.values()), "all metrics should be NUMBER")


async def case_event_ledger_three_array_fields() -> None:
    assert_true(len(SymmetricEventLedgerTrace.fields) == 3, "expected 3 fields")
    assert_true(all(spec.type is TraceFieldType.ARRAY for spec in SymmetricEventLedgerTrace.fields.values()), "all should be ARRAY")


async def case_timeline_three_array_fields() -> None:
    assert_true(len(SymmetricTimelineTrace.fields) == 3, "expected 3 fields")
    assert_true(all(spec.type is TraceFieldType.ARRAY for spec in SymmetricTimelineTrace.fields.values()), "all should be ARRAY")


async def case_evidence_nine_fields_shape() -> None:
    assert_true(len(SymmetricEvidenceTrace.fields) == 9, "expected 9 fields")
    for axis in AXES:
        assert_true(SymmetricEvidenceTrace.fields[f"{axis}_supporting"].type is TraceFieldType.ARRAY, "supporting should be ARRAY")
        assert_true(SymmetricEvidenceTrace.fields[f"{axis}_contradicting"].type is TraceFieldType.ARRAY, "contradicting should be ARRAY")
        assert_true(SymmetricEvidenceTrace.fields[f"{axis}_verdict"].type is TraceFieldType.STRING, "verdict should be STRING")


async def case_all_schemas_construct() -> None:
    for name, schema in ALL_SCHEMAS.items():
        assert_true(bool(schema.fields), f"{name} has no fields")


async def case_all_schemas_initial_artifact_all_none() -> None:
    for schema in ALL_SCHEMAS.values():
        artifact = schema.initial_artifact()
        assert_true(set(artifact) == set(schema.fields), "artifact keys mismatch")
        assert_true(all(v is None for v in artifact.values()), "artifact values should all be None")


async def case_no_duplicate_field_names() -> None:
    seen: set[str] = set()
    for schema_name, schema in ALL_SCHEMAS.items():
        for field_name in schema.fields:
            key = f"{schema_name}.{field_name}"
            assert_true(key not in seen, f"duplicate key {key}")
            seen.add(key)


async def case_trace_option_accepts_each_schema() -> None:
    for schema in ALL_SCHEMAS.values():
        option = TraceOption.continual(schema)
        assert_true(option.enabled, "option should be enabled")


# --- Merge behavior checks ---------------------------------------------------
async def case_event_ledger_accumulates() -> None:
    tool = UpdateTraceTool(SymmetricEventLedgerTrace)
    await tool.execute(call({"goal_success_events": [{"iteration": 1, "subgoal_id": "s1", "status": "pending", "description": "started"}]}))
    await tool.execute(call({"goal_success_events": [{"iteration": 2, "subgoal_id": "s1", "status": "done", "description": "finished"}]}))
    events = tool.current_trace()["goal_success_events"]
    assert_true(len(events) == 2, "events should accumulate across calls")


async def case_checklist_appends_distinct_entries() -> None:
    tool = UpdateTraceTool(SymmetricChecklistTrace)
    await tool.execute(call({"path_quality_checks": [{"criterion": "no redundant calls", "met": True, "evidence": "e1", "iteration": 1}]}))
    await tool.execute(call({"path_quality_checks": [{"criterion": "no risky actions", "met": False, "evidence": "e2", "iteration": 2}]}))
    checks = tool.current_trace()["path_quality_checks"]
    assert_true(len(checks) == 2, "checks should accumulate")


async def case_flat_status_replaces() -> None:
    tool = UpdateTraceTool(SymmetricFlatTrace)
    await tool.execute(call({"goal_success_status": "in_progress"}))
    await tool.execute(call({"goal_success_status": "achieved"}))
    assert_true(tool.current_trace()["goal_success_status"] == "achieved", "status should replace, not accumulate")


async def case_flat_evidence_appends_and_dedupes() -> None:
    tool = UpdateTraceTool(SymmetricFlatTrace)
    await tool.execute(call({"goal_success_evidence": ["fact a"]}))
    await tool.execute(call({"goal_success_evidence": ["fact a", "fact b"]}))
    assert_true(tool.current_trace()["goal_success_evidence"] == ["fact a", "fact b"], "evidence should append+dedupe")


async def case_subscore_replaces_and_preserves_omitted() -> None:
    tool = UpdateTraceTool(SymmetricSubScoreTrace)
    await tool.execute(call({"path_efficiency": 0.4, "path_safety": 0.9}))
    await tool.execute(call({"path_efficiency": 0.8}))
    trace = tool.current_trace()
    assert_true(trace["path_efficiency"] == 0.8, "path_efficiency should replace")
    assert_true(trace["path_safety"] == 0.9, "path_safety should be preserved when omitted")


async def case_evidence_lists_track_independently() -> None:
    tool = UpdateTraceTool(SymmetricEvidenceTrace)
    await tool.execute(call({"answer_correctness_supporting": ["claim verified"], "answer_correctness_verdict": "unverified"}))
    await tool.execute(call({"answer_correctness_contradicting": ["claim disputed"], "answer_correctness_verdict": "contradicted"}))
    trace = tool.current_trace()
    assert_true(trace["answer_correctness_supporting"] == ["claim verified"], "supporting should be untouched")
    assert_true(trace["answer_correctness_contradicting"] == ["claim disputed"], "contradicting should be set")
    assert_true(trace["answer_correctness_verdict"] == "contradicted", "verdict should be latest")


# --- Integration checks -------------------------------------------------------
async def case_integration_event_ledger_accumulates() -> None:
    runner = EventLedgerScriptedRunner()
    agent = build_test_agent(
        name="worker",
        system_prompt="Work.",
        runner=runner,
        tools=[Lookup()],
        trace_option=TraceOption.continual(SymmetricEventLedgerTrace, every_n_iterations=1),
    )
    reply = await agent.arun("task")
    assert_true(reply.content == "done", "main run should complete normally")
    trace = reply.metadata["trace"]
    assert_true(len(trace["goal_success_events"]) >= 2, "events should accumulate across multiple passes")
    assert_true(reply.metadata["trace_metadata"]["update_count"] >= 2, "update_count should reflect multiple passes")


async def case_integration_no_context_leak() -> None:
    runner = EventLedgerScriptedRunner()
    agent = build_test_agent(
        name="worker",
        system_prompt="Work.",
        runner=runner,
        tools=[Lookup()],
        trace_option=TraceOption.continual(SymmetricEventLedgerTrace, every_n_iterations=1),
    )
    await agent.arun("task")
    for payload in runner.main_payloads:
        assert_true("subgoal_id" not in payload, "trace content must never leak into the main agent context")


CHECKS = [
    ("flat_twelve_fields_four_per_axis", case_flat_twelve_fields_four_per_axis),
    ("flat_types_correct", case_flat_types_correct),
    ("checklist_all_array", case_checklist_all_array),
    ("subscore_nine_fields_all_number", case_subscore_nine_fields_all_number),
    ("event_ledger_three_array_fields", case_event_ledger_three_array_fields),
    ("timeline_three_array_fields", case_timeline_three_array_fields),
    ("evidence_nine_fields_shape", case_evidence_nine_fields_shape),
    ("all_schemas_construct", case_all_schemas_construct),
    ("all_schemas_initial_artifact_all_none", case_all_schemas_initial_artifact_all_none),
    ("no_duplicate_field_names", case_no_duplicate_field_names),
    ("trace_option_accepts_each_schema", case_trace_option_accepts_each_schema),
    ("event_ledger_accumulates", case_event_ledger_accumulates),
    ("checklist_appends_distinct_entries", case_checklist_appends_distinct_entries),
    ("flat_status_replaces", case_flat_status_replaces),
    ("flat_evidence_appends_and_dedupes", case_flat_evidence_appends_and_dedupes),
    ("subscore_replaces_and_preserves_omitted", case_subscore_replaces_and_preserves_omitted),
    ("evidence_lists_track_independently", case_evidence_lists_track_independently),
    ("integration_event_ledger_accumulates", case_integration_event_ledger_accumulates),
    ("integration_no_context_leak", case_integration_no_context_leak),
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

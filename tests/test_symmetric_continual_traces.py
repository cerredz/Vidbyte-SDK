from __future__ import annotations

import unittest

from tests.agent_test_support import build_test_agent
from vidbyte import (
    Agent,
    SymmetricChecklistTrace,
    SymmetricEventLedgerTrace,
    SymmetricEvidenceTrace,
    SymmetricFlatTrace,
    SymmetricSubScoreTrace,
    SymmetricTimelineTrace,
    TraceOption,
)
from vidbyte.lib.dataclasses.trace import TraceFieldType, TraceSchema
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec
from vidbyte.trace.continual.tools import UPDATE_TRACE_TOOL_NAME, UpdateTraceTool

ALL_SYMMETRIC_SCHEMAS: dict[str, TraceSchema] = {
    "SymmetricFlatTrace": SymmetricFlatTrace,
    "SymmetricChecklistTrace": SymmetricChecklistTrace,
    "SymmetricSubScoreTrace": SymmetricSubScoreTrace,
    "SymmetricEventLedgerTrace": SymmetricEventLedgerTrace,
    "SymmetricTimelineTrace": SymmetricTimelineTrace,
    "SymmetricEvidenceTrace": SymmetricEvidenceTrace,
}

_AXES = ("goal_success", "path_quality", "answer_correctness")


def _call(trace: object) -> ToolCall:
    return ToolCall(tool_name=UPDATE_TRACE_TOOL_NAME, arguments={"trace": trace})


# ---------------------------------------------------------------------------
# Schema shape assertions
# ---------------------------------------------------------------------------
class SchemaShapeTests(unittest.TestCase):
    def test_symmetric_flat_trace_has_twelve_fields_four_per_axis(self) -> None:  # [Hidden Assumption]
        self.assertEqual(len(SymmetricFlatTrace.fields), 12)
        for axis in _AXES:
            axis_fields = [name for name in SymmetricFlatTrace.fields if name.startswith(axis)]
            self.assertEqual(len(axis_fields), 4)

    def test_symmetric_flat_trace_types_confidence_number_and_evidence_array(self) -> None:  # [Silent Failure]
        for axis in _AXES:
            self.assertEqual(SymmetricFlatTrace.fields[f"{axis}_confidence"].type, TraceFieldType.NUMBER)
            self.assertEqual(SymmetricFlatTrace.fields[f"{axis}_evidence"].type, TraceFieldType.ARRAY)
            self.assertEqual(SymmetricFlatTrace.fields[f"{axis}_status"].type, TraceFieldType.STRING)
            self.assertEqual(SymmetricFlatTrace.fields[f"{axis}_rationale"].type, TraceFieldType.STRING)

    def test_symmetric_checklist_trace_all_three_checks_are_array(self) -> None:  # [Silent Failure]
        self.assertEqual(len(SymmetricChecklistTrace.fields), 3)
        for axis in _AXES:
            self.assertEqual(SymmetricChecklistTrace.fields[f"{axis}_checks"].type, TraceFieldType.ARRAY)

    def test_symmetric_subscore_trace_has_nine_fields_three_per_axis_all_number(self) -> None:  # [Hidden Assumption]
        self.assertEqual(len(SymmetricSubScoreTrace.fields), 9)
        for spec in SymmetricSubScoreTrace.fields.values():
            self.assertEqual(spec.type, TraceFieldType.NUMBER)

    def test_symmetric_event_ledger_trace_has_three_array_fields(self) -> None:  # [Edge Case]
        self.assertEqual(len(SymmetricEventLedgerTrace.fields), 3)
        for spec in SymmetricEventLedgerTrace.fields.values():
            self.assertEqual(spec.type, TraceFieldType.ARRAY)

    def test_symmetric_timeline_trace_has_three_array_fields(self) -> None:  # [Edge Case]
        self.assertEqual(len(SymmetricTimelineTrace.fields), 3)
        for spec in SymmetricTimelineTrace.fields.values():
            self.assertEqual(spec.type, TraceFieldType.ARRAY)

    def test_symmetric_evidence_trace_has_nine_fields_two_array_one_string_per_axis(self) -> None:  # [Hidden Assumption]
        self.assertEqual(len(SymmetricEvidenceTrace.fields), 9)
        for axis in _AXES:
            self.assertEqual(SymmetricEvidenceTrace.fields[f"{axis}_supporting"].type, TraceFieldType.ARRAY)
            self.assertEqual(SymmetricEvidenceTrace.fields[f"{axis}_contradicting"].type, TraceFieldType.ARRAY)
            self.assertEqual(SymmetricEvidenceTrace.fields[f"{axis}_verdict"].type, TraceFieldType.STRING)

    def test_all_schemas_construct_without_raising(self) -> None:  # [Hidden Failure]
        # A missing Field(description=...) raises ValueError at TraceSchema.from_model call
        # time (module import), so successful import of this module already proves this, but
        # assert explicitly so a future refactor that re-derives a schema lazily stays covered.
        for name, schema in ALL_SYMMETRIC_SCHEMAS.items():
            self.assertTrue(schema.fields, msg=f"{name} has no fields")

    def test_all_schemas_initial_artifact_is_all_none(self) -> None:  # [Edge Case]
        for schema in ALL_SYMMETRIC_SCHEMAS.values():
            artifact = schema.initial_artifact()
            self.assertEqual(set(artifact), set(schema.fields))
            self.assertTrue(all(value is None for value in artifact.values()))

    def test_no_duplicate_field_names_across_all_six_schemas(self) -> None:  # [Hidden Failure]
        seen: dict[str, str] = {}
        for schema_name, schema in ALL_SYMMETRIC_SCHEMAS.items():
            for field_name in schema.fields:
                key = f"{schema_name}.{field_name}"
                self.assertNotIn(key, seen)
                seen[key] = schema_name

    def test_trace_option_continual_accepts_each_schema(self) -> None:  # [Edge Case]
        for schema in ALL_SYMMETRIC_SCHEMAS.values():
            option = TraceOption.continual(schema)
            self.assertTrue(option.enabled)


# ---------------------------------------------------------------------------
# Merge behavior: accumulation vs. replacement per field type
# ---------------------------------------------------------------------------
class MergeBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_ledger_array_field_accumulates_across_calls(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricEventLedgerTrace)
        await tool.execute(_call({"goal_success_events": [{"iteration": 1, "subgoal_id": "s1", "status": "pending", "description": "started"}]}))
        await tool.execute(_call({"goal_success_events": [{"iteration": 2, "subgoal_id": "s1", "status": "done", "description": "finished"}]}))
        events = tool.current_trace()["goal_success_events"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["status"], "pending")
        self.assertEqual(events[1]["status"], "done")

    async def test_checklist_array_field_appends_distinct_entries(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricChecklistTrace)
        await tool.execute(_call({"path_quality_checks": [{"criterion": "no redundant calls", "met": True, "evidence": "e1", "iteration": 1}]}))
        await tool.execute(_call({"path_quality_checks": [{"criterion": "no risky actions", "met": False, "evidence": "e2", "iteration": 2}]}))
        checks = tool.current_trace()["path_quality_checks"]
        self.assertEqual(len(checks), 2)

    async def test_flat_scalar_status_replaces_rather_than_accumulates(self) -> None:  # [Hidden Assumption]
        tool = UpdateTraceTool(SymmetricFlatTrace)
        await tool.execute(_call({"goal_success_status": "in_progress"}))
        await tool.execute(_call({"goal_success_status": "achieved"}))
        trace = tool.current_trace()
        self.assertEqual(trace["goal_success_status"], "achieved")

    async def test_flat_evidence_array_appends_and_dedupes(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricFlatTrace)
        await tool.execute(_call({"goal_success_evidence": ["fact a"]}))
        await tool.execute(_call({"goal_success_evidence": ["fact a", "fact b"]}))
        self.assertEqual(tool.current_trace()["goal_success_evidence"], ["fact a", "fact b"])

    async def test_subscore_field_replaces_and_omitted_fields_preserved(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricSubScoreTrace)
        await tool.execute(_call({"path_efficiency": 0.4, "path_safety": 0.9}))
        await tool.execute(_call({"path_efficiency": 0.8}))
        trace = tool.current_trace()
        self.assertEqual(trace["path_efficiency"], 0.8)
        self.assertEqual(trace["path_safety"], 0.9)

    async def test_evidence_supporting_and_contradicting_track_independently(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricEvidenceTrace)
        await tool.execute(_call({"answer_correctness_supporting": ["claim verified"], "answer_correctness_verdict": "unverified"}))
        await tool.execute(_call({"answer_correctness_contradicting": ["claim disputed"], "answer_correctness_verdict": "contradicted"}))
        trace = tool.current_trace()
        self.assertEqual(trace["answer_correctness_supporting"], ["claim verified"])
        self.assertEqual(trace["answer_correctness_contradicting"], ["claim disputed"])
        self.assertEqual(trace["answer_correctness_verdict"], "contradicted")


# ---------------------------------------------------------------------------
# Integration: main agent + trace sub-agent over a shared scripted runner
# ---------------------------------------------------------------------------
class _Lookup(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Look something up.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("lookup", "found")


def _fc(name: str, arguments: str, call_id: str) -> dict:
    return {"output": [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}]}


class _Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class _EventLedgerScriptedRunner:
    """Discriminates main-agent vs trace-agent calls and emits SymmetricEventLedgerTrace updates."""

    def __init__(self) -> None:
        self.main_payloads: list[str] = []
        self._trace_call = 0

    def run(self, prompt: str, **kwargs: object) -> _Resp:
        is_trace = "<trace_schema>" in prompt
        has_messages = "messages" in kwargs
        if is_trace:
            if not has_messages:
                self._trace_call += 1
                event = {"iteration": self._trace_call, "subgoal_id": "s1", "status": "in_progress", "description": "pass-%d" % self._trace_call}
                return _Resp(_fc("updateTrace", '{"trace": {"goal_success_events": [%s]}}' % _json_dict(event), "t1"))
            return _Resp(_fc("isDone", '{"final_answer": "traced"}', "t2"))
        self.main_payloads.append(prompt + str(kwargs.get("messages", "")))
        if not has_messages:
            return _Resp(_fc("lookup", "{}", "m1"))
        return _Resp(_fc("isDone", '{"final_answer": "done"}', "m2"))


def _json_dict(d: dict) -> str:
    import json

    return json.dumps(d)


class SymmetricTraceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_ledger_trace_accumulates_across_multiple_passes(self) -> None:  # [Silent Failure]
        runner = _EventLedgerScriptedRunner()
        agent = build_test_agent(
            name="worker",
            system_prompt="Work.",
            runner=runner,
            tools=[_Lookup()],
            trace_option=TraceOption.continual(SymmetricEventLedgerTrace, every_n_iterations=1),
        )
        reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")
        trace = reply.metadata["trace"]
        self.assertGreaterEqual(len(trace["goal_success_events"]), 2)
        self.assertGreaterEqual(reply.metadata["trace_metadata"]["update_count"], 2)

    async def test_symmetric_trace_never_leaks_into_main_context(self) -> None:  # [Silent Failure]
        runner = _EventLedgerScriptedRunner()
        agent = build_test_agent(
            name="worker",
            system_prompt="Work.",
            runner=runner,
            tools=[_Lookup()],
            trace_option=TraceOption.continual(SymmetricEventLedgerTrace, every_n_iterations=1),
        )
        await agent.arun("task")
        for payload in runner.main_payloads:
            self.assertNotIn("subgoal_id", payload)
            self.assertNotIn("pass-1", payload)


if __name__ == "__main__":
    unittest.main()

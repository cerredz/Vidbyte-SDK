"""Context Protocol Header

PURPOSE: Unit and integration coverage for the six symmetric continual trace schemas added to vidbyte/trace/continual/prebuilt.py, including the nested per-entry subschemas in vidbyte/trace/continual/prebuilt_events.py that back SymmetricChecklistTrace/SymmetricEventLedgerTrace/SymmetricTimelineTrace's list fields.
ROLE IN CODEBASE: Verifies schema shape (top-level field count/type per axis, plus nested item field count/type for the three list-of-record schemas), UpdateTraceTool merge behavior per field type, and one end-to-end agent run per schema family.
ARCHITECTURE NOTE: Mirrors tests/test_continual_trace.py's structure (SchemaShapeTests / MergeBehaviorTests / integration tests) scoped to the six symmetric schemas instead of ActionTrace. NestedItemShapeTests specifically covers the TraceField.fields/items capability (vidbyte/lib/dataclasses/trace.py) that lets these three schemas' list fields declare a typed per-entry shape instead of an opaque dict.
COMMON MODIFICATION PATTERNS: Add a new schema-shape test to SchemaShapeTests when a new symmetric schema is added; add a merge-behavior test whenever a field's accumulate-vs-replace semantics needs regression coverage; add a nested-item assertion to NestedItemShapeTests when a helper submodel in prebuilt_events.py gains or loses a field.
KNOWN EDGE CASES: Array fields nested inside OBJECT-typed fields would silently fail to accumulate across updates (UpdateTraceTool's object merge is a shallow dict.update()); every array field in these schemas is declared top-level specifically to avoid that, and MergeBehaviorTests asserts the accumulation directly. UpdateTraceTool's shape validation only checks keys actually present in an incoming nested-item dict — it does not enforce that every declared subfield of a helper submodel is present, so a partial nested-item dict still passes; test_event_ledger_accepts_partial_nested_item covers this explicitly rather than leaving it implicit.
RELATED DOCS: docs/design/symmetric-continual-trace-schemas.md, field-guide/vidbyte-sdk/tracing-shape-contracts.md, skills/vidbyte-sdk/continual-tracing.md.
TESTS: This file; run via `python -m pytest tests/test_symmetric_continual_traces.py` or `python -m unittest tests.test_symmetric_continual_traces`.
"""

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
_HELPER_ENTRY_FIELD_COUNT = 8


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
# Nested item shape: TraceField.fields/items on the three list-of-record schemas
# ---------------------------------------------------------------------------
class NestedItemShapeTests(unittest.TestCase):
    def test_checklist_entries_declare_eight_typed_fields_per_axis(self) -> None:  # [Silent Failure]
        for axis in _AXES:
            item = SymmetricChecklistTrace.fields[f"{axis}_checks"].items
            self.assertIsNotNone(item, msg=f"{axis}_checks has no declared item shape")
            self.assertEqual(item.type, TraceFieldType.OBJECT)
            self.assertEqual(len(item.fields), _HELPER_ENTRY_FIELD_COUNT)
            self.assertEqual(item.fields["met"].type, TraceFieldType.BOOLEAN)
            self.assertEqual(item.fields["confidence"].type, TraceFieldType.NUMBER)
            self.assertEqual(item.fields["iteration"].type, TraceFieldType.INTEGER)
            self.assertEqual(item.fields["blocking"].type, TraceFieldType.BOOLEAN)
            self.assertEqual(item.fields["verdict"].type, TraceFieldType.STRING)

    def test_event_ledger_entries_declare_eight_typed_fields_per_axis(self) -> None:  # [Silent Failure]
        for axis in _AXES:
            item = SymmetricEventLedgerTrace.fields[f"{axis}_events"].items
            self.assertIsNotNone(item, msg=f"{axis}_events has no declared item shape")
            self.assertEqual(item.type, TraceFieldType.OBJECT)
            self.assertEqual(len(item.fields), _HELPER_ENTRY_FIELD_COUNT)
            self.assertEqual(item.fields["iteration"].type, TraceFieldType.INTEGER)

    def test_timeline_entries_declare_eight_typed_fields_per_axis(self) -> None:  # [Silent Failure]
        for axis in _AXES:
            item = SymmetricTimelineTrace.fields[f"{axis}_timeline"].items
            self.assertIsNotNone(item, msg=f"{axis}_timeline has no declared item shape")
            self.assertEqual(item.type, TraceFieldType.OBJECT)
            self.assertEqual(len(item.fields), _HELPER_ENTRY_FIELD_COUNT)
            self.assertEqual(item.fields["iteration"].type, TraceFieldType.INTEGER)

    def test_flat_and_evidence_schemas_declare_no_nested_item_shape(self) -> None:  # [Edge Case]
        # SymmetricFlatTrace/SymmetricSubScoreTrace/SymmetricEvidenceTrace have no list-of-record
        # fields, so no ARRAY field on them should carry a declared item shape.
        for schema in (SymmetricFlatTrace, SymmetricEvidenceTrace):
            for spec in schema.fields.values():
                if spec.type is TraceFieldType.ARRAY:
                    self.assertIsNone(spec.items)


# ---------------------------------------------------------------------------
# Merge behavior: accumulation vs. replacement per field type
# ---------------------------------------------------------------------------
class MergeBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_ledger_array_field_accumulates_across_calls(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricEventLedgerTrace)
        await tool.execute(
            _call(
                {
                    "goal_success_events": [
                        {
                            "iteration": 1,
                            "subgoal_id": "s1",
                            "status": "in_progress",
                            "previous_status": None,
                            "description": "started",
                            "confidence": 0.4,
                            "triggered_by": "initial plan",
                            "blocking": True,
                        }
                    ]
                }
            )
        )
        await tool.execute(
            _call(
                {
                    "goal_success_events": [
                        {
                            "iteration": 2,
                            "subgoal_id": "s1",
                            "status": "achieved",
                            "previous_status": "in_progress",
                            "description": "finished",
                            "confidence": 0.9,
                            "triggered_by": "final verification",
                            "blocking": False,
                        }
                    ]
                }
            )
        )
        events = tool.current_trace()["goal_success_events"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["status"], "in_progress")
        self.assertEqual(events[1]["status"], "achieved")

    async def test_event_ledger_accepts_partial_nested_item(self) -> None:  # [Edge Case]
        # UpdateTraceTool's shape check only validates keys present in the incoming item, so a
        # nested item that omits some of GoalSuccessEvent's declared fields still passes.
        tool = UpdateTraceTool(SymmetricEventLedgerTrace)
        result = await tool.execute(_call({"goal_success_events": [{"iteration": 1, "subgoal_id": "s1", "status": "in_progress"}]}))
        self.assertIsNone(tool.last_error)
        self.assertEqual(len(tool.current_trace()["goal_success_events"]), 1)
        self.assertEqual(result.metadata["trace"]["goal_success_events"][0]["subgoal_id"], "s1")

    async def test_checklist_array_field_appends_distinct_entries(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(SymmetricChecklistTrace)
        await tool.execute(
            _call(
                {
                    "path_quality_checks": [
                        {
                            "criterion_id": "no-redundant-calls",
                            "criterion": "no redundant calls",
                            "met": True,
                            "verdict": "efficient",
                            "evidence": "e1",
                            "confidence": 0.8,
                            "blocking": False,
                            "iteration": 1,
                        }
                    ]
                }
            )
        )
        await tool.execute(
            _call(
                {
                    "path_quality_checks": [
                        {
                            "criterion_id": "no-risky-actions",
                            "criterion": "no risky actions",
                            "met": False,
                            "verdict": "risky",
                            "evidence": "e2",
                            "confidence": 0.6,
                            "blocking": True,
                            "iteration": 2,
                        }
                    ]
                }
            )
        )
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
                event = {
                    "iteration": self._trace_call,
                    "subgoal_id": "s1",
                    "status": "in_progress",
                    "previous_status": None,
                    "description": "pass-%d" % self._trace_call,
                    "confidence": 0.5,
                    "triggered_by": "scripted trace pass",
                    "blocking": True,
                }
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

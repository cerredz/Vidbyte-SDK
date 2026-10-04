"""FILE: tests/test_jev_required_sequence.py

PURPOSE: Check the required-sequence done check through JevAgent's shared run-state, handoff, and continuation APIs.
ROLE IN CODEBASE: Covers the feature's request recognition, event evidence, ordered judgment, and public settings contract.
ARCHITECTURE NOTE: These tests use the same typed records and shared pipeline as other Jev done checks.
COMMON MODIFICATION PATTERNS: Add cases beside the behavior they exercise and construct records through JevRunState helpers.
KNOWN EDGE CASES: This check depends on exact event citations; tests should distinguish missing work from out-of-order work.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md and skills/jev-agent/SKILL.md.
TESTS: This file.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from vidbyte import (
    JevAgent,
    JevAgentSettings,
    JevContinuationGateSettings,
    JevContinuationGate,
    JevRuntimeSettings,
)
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.context.primitives import ResponseContextItem, TextContextItem
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevContinuationEvidence,
    JevContinuationGateResult,
    JevHandoffRecord,
    JevRequiredSequenceEvidence,
    JevSequenceStageEvidence,
    JevSequenceWork,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult
from vidbyte.lib.jev.done import (
    MultiPartDeliveredQuestion,
    RequiredSequenceWorkShownQuestion,
)
from vidbyte.lib.jev.done.state import DONE_STATE
from vidbyte.lib.runners.types import DecisionModelResponse

REQUEST = "First research the topic, then write a draft from your research."
STAGES = [
    {"name": "Research", "source_text": "research the topic", "completion_criterion": "Sources on the topic were looked up.", "produces": "research notes", "depends_on_previous": False},
    {"name": "Draft", "source_text": "write a draft from your research", "completion_criterion": "A draft exists.", "produces": "the draft", "depends_on_previous": True},
]


def _agent(
    checks: tuple[JevContinuationGate, ...] = (JevContinuationGate.REQUIRED_SEQUENCE,),
) -> JevAgent:
    """Construct the public agent with the requested done checks enabled."""
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini")
    runtime = JevRuntimeSettings(continuation_gate=JevContinuationGateSettings(enabled=checks))
    return JevAgent(settings, runtime)


def _answer(name: str, probability: float) -> JevAnswer:
    """Build a normalized test answer for a required-sequence question."""
    return JevAnswer(
        question_name=name,
        question_type=JevQuestionType.NOUL,
        choice="true" if probability >= 0.5 else "false",
        probabilities={"true": probability, "false": 1 - probability},
        noul=probability,
    )


def _stage_evidence(stage_id: str, event_id: str, *, inputs: tuple[str, ...] = ()) -> JevSequenceStageEvidence:
    return JevSequenceStageEvidence(
        stage_id=stage_id,
        observed_work=(JevSequenceWork("The stage action completed.", (event_id,)),),
        outputs_produced=("research notes",),
        inputs_used=inputs,
        first_event_id=event_id,
        last_work_event_id=event_id,
        failures=(),
        missing_or_uncertain=(),
    )


class JevRequiredSequenceTests(unittest.IsolatedAsyncioTestCase):
    """Required sequence is represented by the shared run-state, handoff, and done records."""

    def setUp(self) -> None:
        self.agent = _agent()
        assert self.agent.run_state is not None
        self.run_state = self.agent.run_state
        self.run_state.request = REQUEST
        self.payload = self.run_state.payload(
            goal="Research the topic and produce a draft.",
            objective="A draft based on research.",
            mission="Complete the stages in order.",
            hard_part="Complete the ordered research and draft stages.",
            what_not_to_do=[],
            required_sequence={"stages": STAGES},
        )
        self.run_state.record = self.run_state._record(self.payload)

    def test_all_fixed_questions_share_the_full_canonical_state(self) -> None:
        from vidbyte.lib.jev.done.multi_part import DONE_STATE as multi_part_state

        self.assertIs(multi_part_state, DONE_STATE)
        self.assertIs(MultiPartDeliveredQuestion().instructions.state, DONE_STATE)
        self.assertIs(RequiredSequenceWorkShownQuestion().instructions.state, DONE_STATE)
        self.assertIn("first_event_id", DONE_STATE)
        self.assertIn("E1", DONE_STATE)

    def test_run_state_numbers_stages_and_checks_request_sources(self) -> None:
        sequence = self.run_state.record.required_sequence
        assert sequence is not None
        self.assertTrue(sequence.active)
        self.assertEqual(sequence.ids(), ("stage_1", "stage_2"))
        self.assertFalse(sequence.stages[0].depends_on_previous)
        self.assertTrue(sequence.stages[1].depends_on_previous)
        self.assertIn("Stage 2 (Draft)", self.run_state.agent_instructions())

    def test_unordered_request_does_not_activate_the_check(self) -> None:
        self.run_state.request = "Add tests and update the docs."
        payload = self.run_state.payload(
            goal="Add tests and update docs.",
            objective="Tests and docs are updated.",
            mission="Do the requested work.",
            hard_part="Update both requested outputs.",
            what_not_to_do=[],
            required_sequence={"stages": []},
        )
        self.run_state.record = self.run_state._record(payload)
        sequence = self.run_state.record.required_sequence
        assert sequence is not None
        self.assertFalse(sequence.active)
        self.assertEqual(sequence.reason, "request_has_no_required_order")
        self.assertEqual(self.run_state.agent_instructions(), "")

    def test_invented_stage_source_disables_the_check(self) -> None:
        payload = self.run_state.payload(
            goal="Research and draft.",
            objective="A draft.",
            mission="Follow the request.",
            hard_part="Use the research to write the draft.",
            what_not_to_do=[],
            required_sequence={"stages": [STAGES[0], {**STAGES[1], "source_text": "publish the draft"}]},
        )
        sequence = self.run_state._record(payload).required_sequence
        assert sequence is not None
        self.assertFalse(sequence.active)
        self.assertEqual(sequence.reason, "stage_source_not_in_request")

    def test_finish_review_checks_order_and_batches_the_two_recognition_answers(self) -> None:
        evidence = JevRequiredSequenceEvidence((
            _stage_evidence("stage_1", "E2"),
            _stage_evidence("stage_2", "E3", inputs=("research notes",)),
        ))
        handoff = JevHandoffRecord(required_sequence=evidence)
        work_name = "required_sequence.work_shown.stage_1"
        draft_name = "required_sequence.work_shown.stage_2"
        previous_name = "required_sequence.uses_previous_output.stage_2"
        request = self.run_state.combine(handoff)
        assert request is not None
        self.assertEqual([question.name for question in request.questions], [work_name, draft_name, previous_name])
        answers = {name: _answer(name, 0.95) for name in (work_name, draft_name, previous_name)}
        decision = DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-test", answers=answers, raw={}, usage={})
        result = self.run_state._required_sequence(handoff, decision)
        self.assertTrue(result.passed)
        self.assertEqual(result.incomplete, ())

    def test_out_of_order_events_fail_in_code_even_when_jev_is_unavailable(self) -> None:
        evidence = JevRequiredSequenceEvidence((
            _stage_evidence("stage_1", "E3"),
            _stage_evidence("stage_2", "E2", inputs=("research notes",)),
        ))
        result = self.run_state._required_sequence(JevHandoffRecord(required_sequence=evidence), None)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("stage_2",))

    def test_event_log_excludes_the_request_and_uses_one_based_tool_iterations(self) -> None:
        log = JevRunEventLog.from_run(
            REQUEST,
            ("I found the requested sources.",),
            (ToolCallContext(tool_name="lookup", iteration_count=1),),
        )
        self.assertTrue(log.lines[0].startswith("E1 USER:"))
        self.assertIn("E2 ASSISTANT iteration=1:", log.lines[1])
        self.assertIn("E3 TOOL lookup", log.lines[2])
        self.assertEqual(log.event_ids(), frozenset({"E2", "E3"}))

    def test_segmented_event_log_keeps_global_ids_and_local_source_chronology(self) -> None:
        response_with_user_text = "Resumed answer contains USER: as body text.\nSecond line remains one event."
        segments = (
            JevContinuationEvidence("main:1", ("Main step.",), (ToolCallContext(tool_name="main_lookup", iteration_count=1),)),
            JevContinuationEvidence("fresh:1", ("Fresh step.",), (ToolCallContext(tool_name="fresh_lookup", iteration_count=1),)),
            JevContinuationEvidence("main:2", (response_with_user_text,), (ToolCallContext(tool_name="resumed_lookup", iteration_count=1),)),
        )
        log = JevRunEventLog.from_segments(REQUEST, segments)

        self.assertTrue(log.lines[0].startswith("E1 USER:"))
        self.assertIn("source=main:1 ASSISTANT iteration=1:", log.lines[1])
        self.assertIn("source=main:1 TOOL main_lookup", log.lines[2])
        self.assertIn("source=fresh:1 ASSISTANT iteration=1:", log.lines[3])
        self.assertIn("source=fresh:1 TOOL fresh_lookup", log.lines[4])
        self.assertIn("source=main:2 ASSISTANT iteration=1:", log.lines[5])
        self.assertTrue(log.lines[5].endswith(response_with_user_text))
        self.assertIn("source=main:2 TOOL resumed_lookup", log.lines[6])
        self.assertEqual(log.event_ids(), frozenset(f"E{number}" for number in range(2, 8)))

    def test_main_fresh_main_evidence_uses_cursors_and_local_tool_iterations(self) -> None:
        main_first = ToolCallContext(tool_name="main_first", iteration_count=1)
        fresh = ToolCallContext(tool_name="fresh", iteration_count=1)
        main_resumed = ToolCallContext(tool_name="main_resumed", iteration_count=2)
        responses = ("Main first output.",)
        calls = (main_first,)

        self.run_state._capture_main_evidence(responses, calls)
        self.run_state.add_continuation_evidence(JevContinuationEvidence("fresh", ("Fresh output.",), (fresh,)))
        self.run_state._capture_main_evidence((*responses, "Main resumed output."), (*calls, main_resumed))
        self.run_state._capture_main_evidence((*responses, "Main resumed output."), (*calls, main_resumed))

        self.assertEqual([segment.source for segment in self.run_state._evidence_segments], ["main:1", "fresh:1", "main:2"])
        self.assertEqual(
            tuple(response for segment in self.run_state._evidence_segments for response in segment.responses),
            ("Main first output.", "Fresh output.", "Main resumed output."),
        )
        captured_calls = tuple(call for segment in self.run_state._evidence_segments for call in segment.tool_calls)
        self.assertEqual([call.iteration_count for call in captured_calls], [1, 1, 1])
        self.assertEqual(main_resumed.iteration_count, 2)

    async def test_begin_resets_continuation_evidence_segments_and_cursors(self) -> None:
        self.run_state._capture_main_evidence(
            ("Prior main output.",),
            (ToolCallContext(tool_name="prior", iteration_count=1),),
        )
        self.run_state.add_continuation_evidence(JevContinuationEvidence("fresh", ("Prior fresh output.",), ()))

        async def return_state(_agent_input: object) -> SimpleNamespace:
            self.assertEqual(self.run_state._evidence_segments, [])
            self.assertEqual(self.run_state._main_response_cursor, 0)
            self.assertEqual(self.run_state._main_call_cursor, 0)
            return SimpleNamespace(structured=self.payload)

        self.run_state.arun = return_state
        await self.run_state.begin(REQUEST)

        self.assertEqual(self.run_state._evidence_segments, [])
        self.assertEqual(self.run_state._main_segment_number, 0)
        self.assertEqual(self.run_state._fresh_segment_number, 0)

    async def test_check_forwards_fresh_evidence_through_every_enabled_handoff_helper(self) -> None:
        checks = (
            JevContinuationGate.CLAIMS,
            JevContinuationGate.REQUIRED_SEQUENCE,
            JevContinuationGate.REQUIRED_ACTIONS,
            JevContinuationGate.DISCOVERED_ITEM_COVERAGE,
        )
        agent = _agent(checks)
        assert agent.run_state is not None
        run_state = agent.run_state
        request = f"{REQUEST} Also run a lookup for the fresh item."
        run_state.request = request
        state_payload = run_state.payload(
            goal="Research and write a draft.",
            objective="A draft based on research.",
            mission="Complete the ordered work and lookup.",
            hard_part="Use the fresh lookup result in the ordered work.",
            what_not_to_do=[],
            required_sequence={"stages": STAGES},
            required_actions={
                "actions": [{
                    "id": "fresh_lookup",
                    "action": "Run a lookup for the fresh item.",
                    "completion_signal": "A successful lookup records the fresh item.",
                    "predecessors": [],
                }]
            },
        )
        run_state.record = run_state._record(state_payload)
        assert run_state.record is not None

        main_raw = "Research notes: sources were found."
        fresh_raw = "Fresh output includes doc_id=fresh-item."
        resumed_raw = "Draft material was written from the research notes."
        main_tool_output = "main-source: topic sources"
        fresh_tool_output = "doc_id=fresh-item\nstatus=ready"
        resumed_tool_output = "draft: first version"
        main_first = ToolCallContext(
            tool_name="main_research",
            state=ToolCallState.SUCCEEDED,
            result=ToolResult.success("main_research", main_tool_output),
            iteration_count=1,
        )
        fresh = ToolCallContext(
            tool_name="fresh_lookup",
            state=ToolCallState.SUCCEEDED,
            result=ToolResult.success("fresh_lookup", fresh_tool_output),
            iteration_count=1,
        )
        main_resumed = ToolCallContext(
            tool_name="main_write",
            state=ToolCallState.SUCCEEDED,
            result=ToolResult.success("main_write", resumed_tool_output),
            iteration_count=2,
        )
        run_state._capture_main_evidence((main_raw,), (main_first,))
        run_state.add_continuation_evidence(JevContinuationEvidence("fresh", (fresh_raw,), (fresh,)))

        sequence_section = {
            "stages": [
                {
                    "stage_id": "stage_1",
                    "observed_work": [{"description": "Research sources were found.", "event_ids": ["E2"]}],
                    "outputs_produced": ["research notes"],
                    "inputs_used": [],
                    "first_event_id": "E2",
                    "last_work_event_id": "E2",
                    "failures": [],
                    "missing_or_uncertain": [],
                },
                {
                    "stage_id": "stage_2",
                    "observed_work": [{"description": "The fresh response supplied draft material.", "event_ids": ["E4"]}],
                    "outputs_produced": ["draft material"],
                    "inputs_used": ["research notes"],
                    "first_event_id": "E4",
                    "last_work_event_id": "E4",
                    "failures": [],
                    "missing_or_uncertain": [],
                },
            ]
        }
        required_actions_section = {
            "actions": [{
                "id": "fresh_lookup",
                "evidence": "fresh_lookup succeeded at trace[1] and returned the requested item.",
                "trace_indices": [1],
                "completion_trace_index": 1,
                "missing": "Nothing is missing.",
                "output_source": "response[1]",
                "output_excerpt": fresh_raw,
            }]
        }
        claims_section = {
            "claims": [{
                "id": "fresh_item_seen",
                "claim": {
                    "identity": {"title": "Fresh item found", "description": "The fresh response reports a discovered item.", "intent": None},
                    "scope": {"scope": "The fresh response", "qualifications": []},
                    "kind": "run_activity",
                    "output": None,
                    "assertions": [{
                        "id": "item_reported",
                        "statement": "The fresh response reports doc_id=fresh-item.",
                        "completion_criteria": "The raw fresh response contains doc_id=fresh-item.",
                    }],
                },
                "evidence": "The fresh response and lookup call both show doc_id=fresh-item.",
                "missing": "Nothing is missing.",
            }]
        }
        discovered_section = {
            "batches": [
                {"source_id": "tool_call_0", "candidates": []},
                {"source_id": "tool_call_1", "candidates": [{
                    "id": "fresh_item",
                    "identity": "doc_id=fresh-item",
                    "requested_processing": "Use the fresh item in the draft.",
                    "completion_criteria": "The draft includes the fresh item.",
                    "processing_evidence": "The fresh response reports the item for the draft.",
                    "missing": "Nothing is missing.",
                }]},
                {"source_id": "tool_call_2", "candidates": []},
            ]
        }
        handoff_payload = run_state.handoff_writer.payload(
            **{
                JevContinuationGate.CLAIMS.value: claims_section,
                JevContinuationGate.REQUIRED_SEQUENCE.value: sequence_section,
                JevContinuationGate.REQUIRED_ACTIONS.value: required_actions_section,
                JevContinuationGate.DISCOVERED_ITEM_COVERAGE.value: discovered_section,
            }
        )

        class HandoffWriterSpy:
            rendered = "compiled"

            def __init__(self, writer: object) -> None:
                self.writer = writer
                self.snapshots: list[dict[str, object]] = []
                self.records: list[JevHandoffRecord | None] = []

            async def compile(
                self,
                _request: str,
                state: object,
                window: object,
                *,
                calls: object,
                responses: object,
                final_answer: object,
                review: object = None,
                event_ids: object,
            ) -> JevHandoffRecord | None:
                self.snapshots.append({
                    "window": window,
                    "calls": calls,
                    "responses": responses,
                    "event_ids": event_ids,
                })
                record = self.writer._record(  # type: ignore[attr-defined]
                    handoff_payload,
                    state,
                    calls,
                    responses,
                    final_answer,
                    review,
                    event_ids=event_ids,
                )
                self.records.append(record)
                return record

        handoff_writer = HandoffWriterSpy(run_state.handoff_writer)
        run_state.handoff_writer = handoff_writer

        async def no_decision(_handoff: JevHandoffRecord | None) -> None:
            return None

        run_state._ask = no_decision
        run_state._judge = lambda check, _handoff, _decision: JevContinuationGateResult(check=check, score=None)
        await run_state.check(
            "The draft uses the research and fresh item.",
            (main_raw, resumed_raw),
            (main_first, main_resumed),
        )
        await run_state.check(
            "The draft uses the research and fresh item.",
            (main_raw, resumed_raw),
            (main_first, main_resumed),
        )

        self.assertEqual(len(handoff_writer.snapshots), 2)
        expected_responses = (main_raw, fresh_raw, resumed_raw)
        expected_tool_outputs = (main_tool_output, fresh_tool_output, resumed_tool_output)
        for snapshot, record in zip(handoff_writer.snapshots, handoff_writer.records, strict=True):
            self.assertEqual(snapshot["responses"], expected_responses)
            calls = snapshot["calls"]
            self.assertEqual(tuple(call.output for call in calls), expected_tool_outputs)  # type: ignore[union-attr]
            self.assertEqual(tuple(call.iteration_count for call in calls), (1, 1, 1))  # type: ignore[union-attr]
            self.assertEqual(snapshot["event_ids"], frozenset(f"E{number}" for number in range(2, 8)))
            assert record is not None
            assert record.required_sequence is not None
            self.assertEqual(record.required_sequence.stages[1].observed_work[0].event_ids, ("E4",))
            assert record.required_actions is not None
            self.assertEqual(record.required_actions.actions[0].trace_indices, (1,))
            self.assertEqual(record.required_actions.actions[0].completion_trace_index, 1)
            assert record.discovered_item_coverage is not None
            self.assertEqual(record.discovered_item_coverage.batches[1].source_id, "tool_call_1")
            self.assertEqual(record.discovered_item_coverage.batches[1].source_output, fresh_tool_output)
            assert record.claims is not None
            self.assertEqual(record.claims.claims[0].evidence, "The fresh response and lookup call both show doc_id=fresh-item.")
            response_items = [item.content for item in snapshot["window"].items() if isinstance(item, ResponseContextItem)]  # type: ignore[union-attr]
            self.assertEqual(tuple(response_items), expected_responses)
            source_maps = [
                item.content
                for item in snapshot["window"].items()  # type: ignore[union-attr]
                if isinstance(item, TextContextItem) and item.title == "Continuation evidence source ranges"
            ]
            self.assertEqual(len(source_maps), 1)
            self.assertIn("main:1: responses[0:1], tool_calls[0:1]", source_maps[0])
            self.assertIn("fresh:1: responses[1:2], tool_calls[1:2]", source_maps[0])
            self.assertIn("main:2: responses[2:3], tool_calls[2:3]", source_maps[0])
        self.assertEqual([segment.source for segment in run_state._evidence_segments], ["main:1", "fresh:1", "main:2"])

    def test_handoff_rejects_request_event_citations(self) -> None:
        sequence_payload = {
            "stages": [
                {
                    "stage_id": "stage_1",
                    "observed_work": [{"description": "Research completed.", "event_ids": ["E1"]}],
                    "outputs_produced": ["research notes"],
                    "inputs_used": [],
                    "first_event_id": "E1",
                    "last_work_event_id": "E1",
                    "failures": [],
                    "missing_or_uncertain": [],
                },
                {
                    "stage_id": "stage_2",
                    "observed_work": [{"description": "Draft written from notes.", "event_ids": ["E3"]}],
                    "outputs_produced": ["the draft"],
                    "inputs_used": ["research notes"],
                    "first_event_id": "E3",
                    "last_work_event_id": "E3",
                    "failures": [],
                    "missing_or_uncertain": [],
                },
            ],
        }
        payload = self.run_state.handoff_writer.payload(required_sequence=sequence_payload)
        record = self.run_state.handoff_writer._record(
            payload,
            self.run_state.record,
            event_ids=frozenset({"E2", "E3"}),
        )
        self.assertIsNone(record)

    def test_handoff_rejects_duplicate_sequence_stage_ids(self) -> None:
        stage_1 = {
            "stage_id": "stage_1",
            "observed_work": [{"description": "Research completed.", "event_ids": ["E2"]}],
            "outputs_produced": ["research notes"],
            "inputs_used": [],
            "first_event_id": "E2",
            "last_work_event_id": "E2",
            "failures": [],
            "missing_or_uncertain": [],
        }
        stage_2 = {
            "stage_id": "stage_2",
            "observed_work": [{"description": "Draft written from notes.", "event_ids": ["E3"]}],
            "outputs_produced": ["the draft"],
            "inputs_used": ["research notes"],
            "first_event_id": "E3",
            "last_work_event_id": "E3",
            "failures": [],
            "missing_or_uncertain": [],
        }
        sequence_payload = {"stages": [stage_1, stage_2, stage_1]}
        payload = self.run_state.handoff_writer.payload(required_sequence=sequence_payload)
        record = self.run_state.handoff_writer._record(
            payload,
            self.run_state.record,
            event_ids=frozenset({"E2", "E3"}),
        )
        self.assertIsNone(record)


if __name__ == "__main__":
    unittest.main()

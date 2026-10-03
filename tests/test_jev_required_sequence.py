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

from vidbyte import (
    JevAgent,
    JevAgentSettings,
    JevContinualSettings,
    JevDoneCheck,
    JevRuntimeSettings,
)
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevHandoffRecord,
    JevRequiredSequenceEvidence,
    JevSequenceStageEvidence,
    JevSequenceWork,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.jev.done import (
    MultiPartDeliveredQuestion,
    RequiredSequenceWorkShownQuestion,
)
from vidbyte.lib.jev.done.state import DONE_STATE
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.types import ToolCallContext

REQUEST = "First research the topic, then write a draft from your research."
STAGES = [
    {"name": "Research", "source_text": "research the topic", "completion_criterion": "Sources on the topic were looked up.", "produces": "research notes", "depends_on_previous": False},
    {"name": "Draft", "source_text": "write a draft from your research", "completion_criterion": "A draft exists.", "produces": "the draft", "depends_on_previous": True},
]


def _agent() -> JevAgent:
    """Construct the public agent with only the sequence done check enabled."""
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini")
    runtime = JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.REQUIRED_SEQUENCE,)))
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


class JevRequiredSequenceTests(unittest.TestCase):
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

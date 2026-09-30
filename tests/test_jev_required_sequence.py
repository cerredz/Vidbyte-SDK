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

from vidbyte import JevAgent, JevAgentSettings, JevContinualSettings, JevDoneCheck, JevRuntimeSettings
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevHandoffRecord,
    JevRequiredSequenceEvidence,
    JevSequenceStageEvidence,
    JevSequenceWork,
)
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.lib.enums import ModelProvider


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
            what_not_to_do=[],
            required_sequence={"stages": STAGES},
        )
        self.run_state.record = self.run_state._record(self.payload)

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


if __name__ == "__main__":
    unittest.main()

"""FILE: tests/test_jev_required_sequence.py

PURPOSE: Verifies JevAgent's required-sequence done check end to end without network access.
ROLE IN CODEBASE: Covers docs/design/jev-required-sequence.md: stage derivation, the event log, handoff validation and rebuild, the code order checks, the Jev questions, and the AgentRuntime finish-attempt seam on both finish paths.
ARCHITECTURE NOTE: One scripted runner serves the run-state builder, the main loop, and the handoff builder in call order; a scripted decider replaces only the TypeSafe boundary.
COMMON MODIFICATION PATTERNS: Script a new scenario as [state, main-loop responses..., handoff, ...] and assert on the JevRunReport in the reply metadata.
KNOWN EDGE CASES: Event IDs in scripted handoffs must match the log the runtime builds (E1 is the request; empty assistant text adds no event).
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping, Sequence
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings
from vidbyte.agents.jev.required_sequence import (
    JevRequiredSequence,
    JevRequiredSequenceReview,
    JevRequiredSequenceState,
)
from vidbyte.agents.jev.run_state import JevRunReport
from vidbyte.lib.constants.jev import JEV_RUN_REPORT_METADATA_KEY
from vidbyte.lib.dataclasses.agents import FinishReviewAction
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.enums import (
    JevQuestionType,
    JevRunSectionKey,
    JevSectionStatus,
    JevStageFailure,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse

REQUEST = "First research the topic, then write a draft from your research."
RESEARCH = {"name": "Research", "source_text": "research the topic", "completion_criterion": "Sources on the topic were looked up.", "produces": "research notes", "depends_on_previous": False}
DRAFT = {"name": "Draft", "source_text": "write a draft from your research", "completion_criterion": "A draft exists.", "produces": "the draft", "depends_on_previous": True}


class ScriptedRunner:
    """Returns scripted model responses in call order and records every call."""

    def __init__(self, *responses: object) -> None:
        # Retains the responses and the prompts/options each call received.
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Pops the next response exactly as a production runner would return one.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


class RawResponse:
    """OpenAI-shaped raw response wrapper for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        # Exposes the two response attributes consumed by BaseAgent.
        self.text = ""
        self.raw = raw


class ScriptedDecider:
    """Answers every noul question with scripted P(true); one mapping per call, 0.9 by default."""

    def __init__(self, *rounds: Mapping[str, float]) -> None:
        # Retains per-call probability overrides and every request received.
        self.rounds = list(rounds)
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Returns a normalized noul answer for each question in the request.
        self.requests.append(request)
        overrides = self.rounds.pop(0) if self.rounds else {}
        answers = {question.name: _noul(question.name, overrides.get(question.name, 0.9)) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-test", answers=answers, raw={}, usage={})


def _noul(name: str, probability: float) -> JevAnswer:
    # Builds a valid noul answer for one probability of "true".
    return JevAnswer(
        question_name=name,
        question_type=JevQuestionType.NOUL,
        choice="true" if probability >= 0.5 else "false",
        probabilities={"true": probability, "false": 1.0 - probability},
        noul=probability,
    )


def _text(value: str) -> TextModelResponse:
    # Wraps plain model text, used for builder JSON and plain final answers.
    return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=value, raw={})


def _call(name: str, arguments: Mapping[str, Any], call_id: str) -> RawResponse:
    # One OpenAI Responses-style function call.
    return RawResponse({"output": [{"type": "function_call", "name": name, "arguments": json.dumps(dict(arguments)), "call_id": call_id}]})


def _state(*stages: Mapping[str, Any]) -> TextModelResponse:
    # A run-state builder answer with the given stages.
    payload = {
        "goal": "Write about the topic.",
        "objective": "A draft based on research.",
        "mission": "",
        "what_not_to_do": [],
        "constraints": [],
        "proposed_plan": ["Research", "Draft"],
        "sections": {"required_sequence": {"stages": list(stages)}},
    }
    return _text(json.dumps(payload))


def _entry(stage_id: str, work: Sequence[str] = (), *, outputs: Sequence[str] = (), inputs: Sequence[str] = (), missing: Sequence[str] = ()) -> dict[str, Any]:
    # One handoff entry; `work` lists the event IDs of the stage's work, in order.
    return {
        "stage_id": stage_id,
        "observed_work": [{"description": f"Work for {stage_id}.", "event_ids": list(work)}] if work else [],
        "outputs_produced": list(outputs),
        "inputs_used": list(inputs),
        "first_event_id": work[0] if work else "",
        "last_work_event_id": work[-1] if work else "",
        "failures": [],
        "missing_or_uncertain": list(missing),
    }


def _handoff(*entries: Mapping[str, Any]) -> TextModelResponse:
    # A handoff builder answer with the given stage entries.
    payload = {"overall_outcome": "The agent worked.", "limitations": [], "sections": {"required_sequence": {"stages": list(entries)}}}
    return _text(json.dumps(payload))


@tool
def lookup(topic: str) -> str:
    """Look up sources on one topic."""
    return f"sources:{topic}"


@tool
def write_draft(notes: str) -> str:
    """Write a draft from notes."""
    return f"draft:{notes}"


def _agent(runner: ScriptedRunner, *, required_sequence: bool = True) -> JevAgent:
    # A JevAgent with both tools and the scripted runner bound.
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini", tools=(lookup, write_draft), required_sequence=required_sequence)
    return bind_test_runner(JevAgent(settings), runner)


def _report(reply: Any) -> JevRunReport:
    # The run report attached to the reply metadata.
    report = reply.metadata[JEV_RUN_REPORT_METADATA_KEY]
    assert isinstance(report, JevRunReport)
    return report


class JevRequiredSequenceTests(unittest.IsolatedAsyncioTestCase):
    """Behavior of the required-sequence done check through the public JevAgent API."""

    async def test_disabled_setting_leaves_the_loop_unchanged(self) -> None:
        # [Silent Failure] without the setting no builder runs and no report is attached.
        runner = ScriptedRunner(_text("plain answer"))
        reply = await _agent(runner, required_sequence=False).arun(REQUEST)
        self.assertEqual(reply.content, "plain answer")
        self.assertEqual(len(runner.calls), 1)
        self.assertNotIn(JEV_RUN_REPORT_METADATA_KEY, reply.metadata)

    async def test_request_without_order_is_inactive_and_ungated(self) -> None:
        # [Edge Case] no required order means no stage prompt and no finish review.
        runner = ScriptedRunner(_state(), _text("answer"))
        reply = await _agent(runner).arun("Add tests and update the docs.")
        section = _report(reply).run_state.sections[JevRunSectionKey.REQUIRED_SEQUENCE]
        self.assertIs(section.status, JevSectionStatus.INACTIVE)
        self.assertEqual(section.reason, "request_has_no_required_order")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(_report(reply).finish_reviews, ())

    async def test_stage_not_quoted_from_request_is_inactive(self) -> None:
        # [Hidden Assumption] an invented stage turns the gate off instead of blocking a correct run.
        invented = {**DRAFT, "source_text": "publish it"}
        runner = ScriptedRunner(_state(RESEARCH, invented), _text("answer"))
        reply = await _agent(runner).arun(REQUEST)
        section = _report(reply).run_state.sections[JevRunSectionKey.REQUIRED_SEQUENCE]
        self.assertIs(section.status, JevSectionStatus.INACTIVE)
        self.assertEqual(section.reason, "stage_source_not_in_request")

    async def test_in_order_run_is_accepted_after_one_batched_jev_request(self) -> None:
        # [Silent Failure] the stage list reaches the main agent and a correct run finishes on its first attempt.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("write_draft", {"notes": "sources"}, "c2"),
            _text("Here is the draft."),
            _handoff(_entry("stage_1", ["E2"], outputs=["research notes"]), _entry("stage_2", ["E3"], inputs=["research notes"])),
        )
        decider = ScriptedDecider()
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decider):
            reply = await _agent(runner).arun(REQUEST)
        self.assertEqual(reply.content, "Here is the draft.")
        self.assertIn("Stage 1 (Research): Sources on the topic were looked up.", json.dumps(runner.calls[1]["kwargs"], default=str))
        self.assertEqual([question.name for question in decider.requests[0].questions], ["stage_1_work_shown", "stage_2_work_shown", "stage_2_uses_previous_output"])
        self.assertEqual(set(decider.requests[0].state["stages"]), {"stage_1", "stage_2"})
        record = _report(reply).finish_reviews[0]
        self.assertIs(record.action, FinishReviewAction.ACCEPT)
        review = record.reviews[0]
        self.assertIsInstance(review, JevRequiredSequenceReview)
        self.assertTrue(review.required_sequence_complete)
        self.assertIn("E3 [tool write_draft, success]", runner.calls[4]["prompt"])

    async def test_skipped_stage_sends_the_agent_back_naming_that_stage(self) -> None:
        # [Hidden Failure] a strong final answer does not stand in for a stage the run never did.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _text("Done."),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", missing=["No draft was written."])),
            _call("write_draft", {"notes": "sources"}, "c2"),
            _text("Draft written."),
            _handoff(_entry("stage_1", ["E2"], outputs=["notes"]), _entry("stage_2", ["E5"], inputs=["notes"])),
        )
        decider = ScriptedDecider()
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decider):
            reply = await _agent(runner).arun(REQUEST)
        self.assertEqual(reply.content, "Draft written.")
        first, second = _report(reply).finish_reviews
        self.assertIs(first.action, FinishReviewAction.CONTINUE)
        self.assertIs(first.reviews[0].stages[1].failure, JevStageFailure.NO_WORK)
        self.assertEqual([question.name for question in decider.requests[0].questions], ["stage_1_work_shown"])
        self.assertIn("Stage 2 (Draft) has no recorded work", json.dumps(runner.calls[4]["kwargs"], default=str))
        self.assertIn("E4 [finish review]", runner.calls[6]["prompt"])
        self.assertIs(second.action, FinishReviewAction.ACCEPT)

    async def test_rework_after_a_later_stage_began_is_out_of_order(self) -> None:
        # [Edge Case] going back to research after drafting started breaks the order, whatever the last stage says.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("write_draft", {"notes": "sources"}, "c2"),
            _call("lookup", {"topic": "more"}, "c3"),
            _text("Done."),
            _handoff(_entry("stage_1", ["E2", "E4"]), _entry("stage_2", ["E3"])),
            _text("Redrafted from the full research."),
            _handoff(_entry("stage_1", ["E2", "E4"]), _entry("stage_2", ["E7"])),
        )
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=ScriptedDecider()):
            reply = await _agent(runner).arun(REQUEST)
        first = _report(reply).finish_reviews[0]
        self.assertIs(first.reviews[0].stages[1].failure, JevStageFailure.OUT_OF_ORDER)
        self.assertIn("began at E3, before Stage 1 (Research) finished at E4", first.reviews[0].feedback)
        self.assertIs(_report(reply).finish_reviews[1].action, FinishReviewAction.ACCEPT)

    async def test_jev_rejecting_the_work_sends_the_agent_back(self) -> None:
        # [Hidden Failure] listed work that does not show the criterion is not accepted.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("write_draft", {"notes": "sources"}, "c2"),
            _text("Done."),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E3"])),
            _text("Finished the draft."),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E3", "E6"])),
        )
        decider = ScriptedDecider({"stage_2_work_shown": 0.1})
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decider):
            reply = await _agent(runner).arun(REQUEST)
        first, second = _report(reply).finish_reviews
        verdict = first.reviews[0].stages[1]
        self.assertIs(verdict.failure, JevStageFailure.WORK_NOT_SHOWN)
        self.assertAlmostEqual(verdict.work_shown_probability or 0.0, 0.1)
        self.assertIs(second.action, FinishReviewAction.ACCEPT)

    async def test_previous_output_not_used_is_rejected(self) -> None:
        # [Edge Case] a dependent stage must build on the previous stage's output.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("write_draft", {"notes": "unrelated"}, "c2"),
            _text("Done."),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E3"])),
        )
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=ScriptedDecider({"stage_2_uses_previous_output": 0.2})), patch("vidbyte.agents.jev.runtime.JEV_MAX_FINISH_REVIEW_CONTINUATIONS", 0):
            reply = await _agent(runner).arun(REQUEST)
        record = _report(reply).finish_reviews[0]
        self.assertIs(record.reviews[0].stages[1].failure, JevStageFailure.PREVIOUS_OUTPUT_NOT_USED)
        self.assertIn("worked from Stage 1 (Research)'s output (research notes)", record.reviews[0].feedback)

    async def test_continuation_cap_stops_the_run(self) -> None:
        # [Hidden Failure] with max_iterations unbounded, repeated failing finishes end with a clear stop reason.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _text("Done."),
            _handoff(_entry("stage_1"), _entry("stage_2")),
        )
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=ScriptedDecider()), patch("vidbyte.agents.jev.runtime.JEV_MAX_FINISH_REVIEW_CONTINUATIONS", 0):
            reply = await _agent(runner).arun(REQUEST)
        self.assertEqual(reply.metadata["stop_reason"], "finish_review_rejected")
        self.assertIs(_report(reply).finish_reviews[0].action, FinishReviewAction.STOP)

    async def test_missing_jev_key_falls_back_to_code_checks(self) -> None:
        # [Hidden Assumption] no TypeSafe key disables only the Jev questions; order and presence still gate.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("write_draft", {"notes": "sources"}, "c2"),
            _text("Done."),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E3"])),
        )
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", side_effect=ConfigurationError("no key")):
            reply = await _agent(runner).arun(REQUEST)
        review = _report(reply).finish_reviews[0].reviews[0]
        self.assertTrue(review.passed)
        self.assertFalse(review.jev_available)

    async def test_invalid_handoff_is_rebuilt_with_the_error_as_correction(self) -> None:
        # [Hidden Failure] a handoff citing an event that does not exist is never trusted.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("write_draft", {"notes": "sources"}, "c2"),
            _text("Done."),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E99"])),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E3"])),
        )
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=ScriptedDecider()):
            reply = await _agent(runner).arun(REQUEST)
        self.assertIn("# Correction", runner.calls[5]["prompt"])
        self.assertIn("E99", runner.calls[5]["prompt"])
        self.assertIs(_report(reply).finish_reviews[0].action, FinishReviewAction.ACCEPT)
        self.assertEqual(len(_report(reply).builder_usage), 3)

    async def test_handoff_invalid_twice_accepts_and_flags(self) -> None:
        # [Edge Case] a builder that cannot describe the run leaves the finish accepted but recorded.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _text("Done."),
            _handoff(_entry("stage_1", ["E9"]), _entry("stage_2")),
            _handoff(_entry("stage_1", ["E9"]), _entry("stage_2")),
        )
        reply = await _agent(runner).arun(REQUEST)
        record = _report(reply).finish_reviews[0]
        self.assertIs(record.action, FinishReviewAction.ACCEPT)
        self.assertIsNone(record.handoff)
        self.assertTrue(record.handoff_failure.startswith("handoff_build_failed"))

    async def test_is_done_finish_path_is_reviewed(self) -> None:
        # [Silent Failure] the isDone path goes through the same seam as a plain final response.
        runner = ScriptedRunner(
            _state(RESEARCH, DRAFT),
            _call("lookup", {"topic": "sdk"}, "c1"),
            _call("isDone", {"final_answer": "early"}, "c2"),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2")),
            _call("write_draft", {"notes": "sources"}, "c3"),
            _call("isDone", {"final_answer": "complete"}, "c4"),
            _handoff(_entry("stage_1", ["E2"]), _entry("stage_2", ["E4"])),
        )
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=ScriptedDecider()):
            reply = await _agent(runner).arun(REQUEST)
        self.assertEqual(reply.content, "complete")
        self.assertEqual([record.action for record in _report(reply).finish_reviews], [FinishReviewAction.CONTINUE, FinishReviewAction.ACCEPT])
        self.assertIn("Stage 2 (Draft) has no recorded work", json.dumps(runner.calls[4]["kwargs"], default=str))


class JevRequiredSequenceSettingsTests(unittest.TestCase):
    """Validation of the named setting."""

    def test_required_sequence_must_be_a_bool(self) -> None:
        # [Hidden Assumption] a truthy string never silently enables a completion gate.
        with self.assertRaisesRegex(ConfigurationError, "required_sequence"):
            JevAgentSettings(name="jev", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", required_sequence="yes")  # type: ignore[arg-type]

    def test_active_state_numbers_stages_in_code(self) -> None:
        # [Silent Failure] stage IDs come from position, and the first stage never depends on a previous one.
        state = JevRequiredSequence().parse_state({"stages": [{**RESEARCH, "depends_on_previous": True}, DRAFT]}, request=REQUEST)
        self.assertIsInstance(state, JevRequiredSequenceState)
        assert isinstance(state, JevRequiredSequenceState)
        self.assertEqual([stage.stage_id for stage in state.stages], ["stage_1", "stage_2"])
        self.assertFalse(state.stages[0].depends_on_previous)
        self.assertTrue(state.stages[1].depends_on_previous)



if __name__ == "__main__":
    unittest.main()

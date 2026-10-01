"""FILE: tests/test_jev_run_state_relation.py

PURPOSE: Verifies Jev's opt-in run-state relationship question, one-call gate input, and retain-or-replace state policy without live providers.
ROLE IN CODEBASE: Covers docs/design/jev-run-state-relation.md, including first-run omission, related and unrelated handoffs, delegated runs, failures, response reset, and legacy behavior.
ARCHITECTURE NOTE: The fixed question and criteria are inspected as prompt data; scripted probabilities exercise scoring and routing without claiming to test model understanding.
COMMON MODIFICATION PATTERNS: Add cases for each relation policy boundary, typed state handoff, and failure behavior while preserving production settings, registry, gate, runtime, and response wiring.
KNOWN EDGE CASES: An unavailable decision retains an existing record, replacement generation failure leaves no old record, and specialist routing uses a typed no-op for the legacy state class.
RELATED DOCS: docs/design/jev-run-state-relation.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: python -m unittest tests.test_jev_run_state_relation and python scripts/test-jev-run-state-relation.py.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevPreflightPreset,
    JevRuntimeSettings,
    JevSpecialist,
)
from vidbyte.agents.jev.done import JevRunState, JevRunStateRelation
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.settings import JevContinualSettings
from vidbyte.agents.pricing import UsageRollup
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_PREFLIGHT_REQUEST_FIELD,
    JEV_PREFLIGHT_RUN_STATE_FIELD,
    JEV_RUN_STATE_RELATION_THRESHOLD,
    JEV_SPECIALIST_NONE,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevDeliverable,
    JevMultiPart,
    JevQuestion,
    JevRunStateRecord,
    JevTargetOutcome,
    JevTargetOutcomeItem,
)
from vidbyte.lib.enums import (
    JevDoneCheck,
    JevPreflightQuestionKey,
    JevQuestionType,
    ModelProvider,
)
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse

_GATE_RUNNER_PATH = "vidbyte.agents.jev.gate.gate.DecisionModelHelper"
_RELATION_KEY = JevPreflightQuestionKey.RUN_STATE_RELATION
_FIRST_STATE = {
    "goal": "Publish accurate release notes for Vidbyte SDK v2.1.",
    "objective": "Document the authentication migration and compatibility changes in the v2.1 notes.",
    "mission": "Keep the notes specific to the Vidbyte SDK v2.1 release.",
    "what_not_to_do": ["Do not describe unrelated SDK versions."],
}
_REPLACEMENT_STATE = {
    "goal": "Explain the team's deployment runbook.",
    "objective": "Write a concise deployment runbook for the operations team.",
    "mission": "Describe the team's deploy and rollback procedure.",
    "what_not_to_do": ["Do not alter the release notes."],
}


class ScriptedGenerativeRunner:
    """Returns fixed structured text and records every prompt and conversation window."""

    def __init__(self, text: str = "completed", *, error: BaseException | None = None) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})
        self.error = error
        self.calls: list[str] = []
        self.messages: list[Any] = []

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        # Records the ordinary model input before returning or propagating the scripted boundary result.
        self.calls.append(prompt)
        self.messages.append(kwargs.get("messages"))
        if self.error is not None:
            raise self.error
        return self.response


class ScriptedDecisionRunner:
    """Returns caller-supplied probabilities and records the exact structured request."""

    def __init__(self, *, probability: float | tuple[float, ...] = 0.9, choices: Mapping[str, float] | None = None, omit: str | None = None, error: BaseException | None = None) -> None:
        self.probability = probability
        self.choices = choices
        self.omit = omit
        self.error = error
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Treats the probabilities as scripted policy inputs, not as a simulated semantic judgment.
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        answers = {
            question.name: self._answer(question)
            for question in request.questions
            if question.name != self.omit
        }
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 60, "output_tokens": 12})

    def _answer(self, question: JevQuestion) -> JevAnswer:
        # Makes one typed answer from the script without evaluating the request content.
        if question.question_type is JevQuestionType.CHOICE:
            values = self.choices or {JEV_SPECIALIST_NONE: 1.0}
            probabilities = {name: values.get(name, 0.0) for name in question.option_names()}
            selected = max(probabilities, key=probabilities.__getitem__)
            return JevAnswer(question_name=question.name, question_type=question.question_type, choice=selected, probabilities=probabilities, confidence=probabilities[selected])
        yes = self.probability[min(len(self.requests) - 1, len(self.probability) - 1)] if isinstance(self.probability, tuple) else self.probability
        return JevAnswer(question_name=question.name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _decision_helper(scripted: ScriptedDecisionRunner) -> type:
    # Keeps DecisionModelHelper's production scorer while replacing only its external request boundary.
    class ScriptedDecisionHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)
        noul_passes = staticmethod(DecisionModelHelper.noul_passes)

        def __new__(cls, *args: object, **kwargs: object) -> ScriptedDecisionRunner:
            return scripted

    return ScriptedDecisionHelper


def _record(*, with_sections: bool = True) -> JevRunStateRecord:
    # Builds a typed semantic record with usage and optional section fields for projection checks.
    return JevRunStateRecord(
        goal=_FIRST_STATE["goal"],
        objective=_FIRST_STATE["objective"],
        mission=_FIRST_STATE["mission"],
        what_not_to_do=("Do not describe unrelated SDK versions.",),
        multi_part=JevMultiPart((JevDeliverable("release_notes", "SDK v2.1 release notes", "The notes describe migration changes."),)) if with_sections else None,
        target_outcome=JevTargetOutcome((JevTargetOutcomeItem("migration_ready", "Developers can migrate", "SDK auth migration", "v2.1 only", "The notes explain token compatibility."),)) if with_sections else None,
        usage=UsageRollup(input_tokens=999, output_tokens=111),
    )


def _settings(*, specialists: tuple[JevSpecialist, ...] = ()) -> JevAgentSettings:
    # Keeps every test on the production JevAgent constructor with an offline generative model identity.
    return JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini", agents=specialists)


def _agent(*, preflight: tuple[JevPreflightPreset, ...] = (JevPreflightPreset.RUN_STATE_RELATION,), checks: tuple[JevDoneCheck, ...] = (), specialists: tuple[JevSpecialist, ...] = (), state_text: str | None = None, state_error: BaseException | None = None) -> tuple[JevAgent, ScriptedGenerativeRunner, ScriptedGenerativeRunner | None]:
    # Constructs production settings and binds offline main and run-state runners.
    main = ScriptedGenerativeRunner("main reply")
    state_payload: dict[str, Any] = dict(_REPLACEMENT_STATE)
    if JevDoneCheck.MULTI_PART in checks and state_text is None:
        state_payload[JevDoneCheck.MULTI_PART.value] = {"deliverables": []}
    if JevDoneCheck.TARGET_OUTCOME in checks and state_text is None:
        state_payload[JevDoneCheck.TARGET_OUTCOME.value] = {"items": []}
    state_runner = None if not preflight and not checks else ScriptedGenerativeRunner(state_text or json.dumps(state_payload), error=state_error)
    runtime = JevRuntimeSettings(decision=DecisionModelConfig(api_key="test-key"), preflight=preflight, continual=JevContinualSettings(checks=checks))
    agent = bind_test_runner(JevAgent(_settings(specialists=specialists), runtime), main)
    if agent.run_state is not None and state_runner is not None:
        bind_test_runner(agent.run_state, state_runner)
    return agent, main, state_runner


def _plain(value: object) -> object:
    # Converts frozen Jev mappings and tuple arrays into ordinary JSON-like values for exact assertions.
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class JevRunStateRelationQuestionTests(unittest.TestCase):
    """Pin the fixed question's registered scope, mirrored criteria, examples, and content floor."""

    def test_fixed_question_registration_and_policy_use_the_named_inclusive_threshold(self) -> None:
        question = JevPreflightRegistry.get(_RELATION_KEY)
        self.assertEqual(question.key, _RELATION_KEY)
        self.assertEqual(JevPresets.definition(JevPreflightPreset.RUN_STATE_RELATION).question_keys, (_RELATION_KEY,))
        self.assertEqual(JEV_RUN_STATE_RELATION_THRESHOLD, 0.5)
        self.assertEqual(JevPresets.definition(JevPreflightPreset.RUN_STATE_RELATION).threshold, JEV_RUN_STATE_RELATION_THRESHOLD)
        self.assertEqual(question.to_question().name, _RELATION_KEY.value)

    def test_question_criteria_name_concrete_links_and_reject_generic_topic_overlap(self) -> None:
        question = JevPreflightRegistry.get(_RELATION_KEY)
        self.assertEqual(question.instructions.question, "Does `request` have any substantive relationship to the work or identifiable content in `run_state`?")
        self.assertIn("same concrete project", question.instructions.rules[0])
        self.assertIn("different immediate goal", question.instructions.rules[0])
        self.assertIn("generic field", question.instructions.rules[0])
        self.assertIn("shared software vocabulary is not enough", question.instructions.rules[0])
        self.assertIn("requested operation or final output changes", question.instructions.definitions[0])
        self.assertIn("Choose true when", question.when_true.what)
        self.assertIn("Choose false when", question.when_false.what)
        self.assertIn("diagnose and fix a bug", question.when_true.boundary[0])
        self.assertIn("generic example", question.when_false.boundary[0])
        self.assertIn("same concrete project", question.when_false.not_for)
        self.assertIn("generic type of task", question.when_true.not_for)
        self.assertEqual(len(question.instructions.introduction.split(". ")), 3)

    def test_boundary_examples_share_the_same_record_and_change_the_identifiable_link(self) -> None:
        question = JevPreflightRegistry.get(_RELATION_KEY)
        true_record, true_request = question.when_true.boundary[0].split(" `request`: ", maxsplit=1)
        false_record, false_request = question.when_false.boundary[0].split(" `request`: ", maxsplit=1)
        self.assertEqual(true_record, false_record)
        self.assertIn("Vidbyte SDK's authentication client", true_request)
        self.assertIn("without referring to that SDK or its project", false_request)

    def test_fixed_question_uses_one_string_per_section_and_carries_more_than_two_thousand_tokens(self) -> None:
        if importlib.util.find_spec("tiktoken") is None:
            self.skipTest("tiktoken is unavailable for the question token floor")
        import tiktoken

        question = JevPreflightRegistry.get(_RELATION_KEY)
        content = "\n".join((
            question.instructions.render(),
            json.dumps(question.when_true.to_content()),
            json.dumps(question.when_false.to_content()),
            question.gap,
        ))
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode(content)), 2_000)
        self.assertEqual(len(question.instructions.definitions), 1)
        self.assertEqual(len(question.instructions.rules), 1)
        self.assertEqual(len(question.when_true.easy), 1)
        self.assertEqual(len(question.when_true.boundary), 1)
        self.assertEqual(len(question.when_false.easy), 1)
        self.assertEqual(len(question.when_false.boundary), 1)


class JevRunStateRelationGateTests(unittest.IsolatedAsyncioTestCase):
    """Verify one combined Jev request, explicit record projection, and per-pass relation state."""

    def setUp(self) -> None:
        self.agent, _, _ = _agent()
        assert isinstance(self.agent.preflight, JevPreflightGate)

    async def test_no_record_omits_question_state_and_result_on_first_run(self) -> None:
        gate = self.agent.preflight
        self.assertIsNone(gate.combine("Write the initial notes."))
        decision = ScriptedDecisionRunner()
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            self.assertTrue(await gate.pass_("Write the initial notes."))
        self.assertEqual(decision.requests, [])
        self.assertIsNone(gate.run_state_related)
        self.assertNotIn(JevPreflightPreset.RUN_STATE_RELATION, self.agent.response.results)

    def test_combine_uses_only_request_and_json_safe_semantic_record_projection(self) -> None:
        gate = self.agent.preflight
        record = _record()
        request = gate.combine("Explain the SDK bug.", record)
        assert request is not None
        state = _plain(request.state)
        self.assertEqual(set(state), {JEV_PREFLIGHT_REQUEST_FIELD, JEV_PREFLIGHT_RUN_STATE_FIELD})
        self.assertEqual(state[JEV_PREFLIGHT_REQUEST_FIELD], "Explain the SDK bug.")
        self.assertEqual(state[JEV_PREFLIGHT_RUN_STATE_FIELD], {
            "goal": record.goal,
            "objective": record.objective,
            "mission": record.mission,
            "what_not_to_do": ["Do not describe unrelated SDK versions."],
            "multi_part": {"deliverables": [{"id": "release_notes", "description": "SDK v2.1 release notes", "completion_signal": "The notes describe migration changes."}]},
            "target_outcome": {"items": [{"id": "migration_ready", "outcome": "Developers can migrate", "target": "SDK auth migration", "scope": "v2.1 only", "completion_criterion": "The notes explain token compatibility."}]},
        })
        self.assertNotIn("usage", str(state))
        self.assertEqual(tuple(question.name for question in request.questions), (_RELATION_KEY.value,))

    async def test_relation_probability_at_threshold_is_related(self) -> None:
        decision = ScriptedDecisionRunner(probability=0.5)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            self.assertTrue(await self.agent.preflight.pass_("new action", _record()))
        self.assertTrue(self.agent.preflight.run_state_related)
        self.assertEqual(self.agent.response.results[JevPreflightPreset.RUN_STATE_RELATION].score, 0.5)

    async def test_relation_probability_below_threshold_is_unrelated(self) -> None:
        decision = ScriptedDecisionRunner(probability=0.49)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            self.assertTrue(await self.agent.preflight.pass_("different task", _record()))
        self.assertFalse(self.agent.preflight.run_state_related)

    async def test_unavailable_decision_marks_result_unavailable_and_leaves_relation_none(self) -> None:
        decision = ScriptedDecisionRunner(error=ProviderRequestError("decision service unavailable", provider="typesafe"))
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            self.assertTrue(await self.agent.preflight.pass_("new request", _record()))
        result = self.agent.response.results[JevPreflightPreset.RUN_STATE_RELATION]
        self.assertFalse(result.available)
        self.assertIsNone(self.agent.preflight.run_state_related)

    async def test_missing_relation_answer_leaves_relation_none_and_resets_previous_value(self) -> None:
        first = ScriptedDecisionRunner(probability=0.9)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(first)):
            await self.agent.preflight.pass_("first request", _record())
        self.assertTrue(self.agent.preflight.run_state_related)
        second = ScriptedDecisionRunner(omit=_RELATION_KEY.value)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(second)):
            await self.agent.preflight.pass_("second request", _record())
        result = self.agent.response.results[JevPreflightPreset.RUN_STATE_RELATION]
        self.assertFalse(result.available)
        self.assertIsNone(self.agent.preflight.run_state_related)
        self.assertEqual(len(second.requests), 1)


class JevRunStateRelationRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify the production runtime retains or replaces state while passing the current message normally."""

    async def test_first_run_skips_relation_scoring_but_initializes_state_without_a_continuation(self) -> None:
        agent, main, state_runner = _agent()
        decision = ScriptedDecisionRunner()
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("Create the v2.1 notes.")
        self.assertEqual(decision.requests, [])
        self.assertNotIn(JevPreflightPreset.RUN_STATE_RELATION, agent.response.results)
        self.assertEqual(len(state_runner.calls if state_runner is not None else ()), 1)
        self.assertEqual(agent.run_state.request, "Create the v2.1 notes.")
        self.assertIsNone(agent.continuation)
        self.assertEqual(main.calls, ["Create the v2.1 notes."])

    async def test_related_record_is_preserved_and_reported_after_response_reset(self) -> None:
        agent, main, state_runner = _agent()
        assert isinstance(agent.run_state, JevRunStateRelation)
        original = _record()
        agent.run_state.record = original
        agent.run_state.request = "Create the v2.1 notes."
        agent.run_state.rendered = '{"prior":true}'
        agent.run_state.handoff = object()
        agent._response.state.output = "previous run"
        earlier = AgentMessage(sender="user", recipient="orchestrator", content="Earlier main-agent context.")
        agent.history.append(earlier)
        original_history = tuple(agent.history)
        original_context_manager = agent.context_manager
        decision = ScriptedDecisionRunner(probability=0.9)
        message = "Explain a bug in the Vidbyte SDK authentication client."
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun(message)
        self.assertIs(agent.run_state.record, original)
        self.assertEqual(agent.run_state.request, "Create the v2.1 notes.")
        self.assertEqual(agent.run_state.rendered, '{"prior":true}')
        self.assertIsNone(agent.run_state.handoff)
        self.assertIs(agent.response.run_state, original)
        self.assertEqual(agent.response.output, "main reply")
        self.assertEqual(agent.response.input, message)
        self.assertEqual(agent.response.results[JevPreflightPreset.RUN_STATE_RELATION].score, 0.9)
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])
        self.assertEqual(main.calls, [message])
        self.assertEqual(tuple(agent.history[:len(original_history)]), original_history)
        self.assertIs(agent.context_manager, original_context_manager)
        self.assertEqual(len(decision.requests), 1)

    async def test_each_repeated_run_gets_a_fresh_response_and_relation_decision(self) -> None:
        agent, main, state_runner = _agent()
        assert isinstance(agent.run_state, JevRunStateRelation)
        original = _record(with_sections=False)
        agent.run_state.record = original
        agent.run_state.request = "Create the v2.1 notes."
        decision = ScriptedDecisionRunner(probability=(0.8, 0.7))
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("First related request.")
            first_response = agent.response
            await agent.arun("Second related request.")
        self.assertIs(agent.run_state.record, original)
        self.assertEqual(agent.response.input, "Second related request.")
        self.assertEqual(agent.response.results[JevPreflightPreset.RUN_STATE_RELATION].score, 0.7)
        self.assertIs(agent.response.run_state, original)
        self.assertIsNot(agent.response, first_response)
        self.assertNotIn("First related request.", agent.response.input)
        self.assertEqual(len(decision.requests), 2)
        self.assertEqual(main.calls, ["First related request.", "Second related request."])
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])

    async def test_unrelated_result_generates_replacement_state_from_the_current_message(self) -> None:
        agent, main, state_runner = _agent()
        assert isinstance(agent.run_state, JevRunStateRelation) and state_runner is not None
        original = _record(with_sections=False)
        agent.run_state.record = original
        agent.run_state.request = "Create the v2.1 notes."
        agent.run_state.rendered = "old rendered state"
        decision = ScriptedDecisionRunner(probability=0.2)
        message = "Write a deployment runbook."
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun(message)
        self.assertEqual(state_runner.calls, [message])
        self.assertNotEqual(agent.run_state.record, original)
        self.assertEqual(agent.run_state.record.objective, _REPLACEMENT_STATE["objective"])
        self.assertEqual(agent.run_state.request, message)
        self.assertIs(agent.response.run_state, agent.run_state.record)
        self.assertEqual(main.calls, [message])
        self.assertFalse(agent.response.results[JevPreflightPreset.RUN_STATE_RELATION].passed)

    async def test_unavailable_relation_decision_preserves_existing_record(self) -> None:
        agent, main, state_runner = _agent()
        assert isinstance(agent.run_state, JevRunStateRelation)
        original = _record(with_sections=False)
        agent.run_state.record = original
        agent.run_state.request = "Create the v2.1 notes."
        agent.run_state.rendered = "existing state text"
        decision = ScriptedDecisionRunner(error=ProviderRequestError("down", provider="typesafe"))
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("Question about the SDK.")
        self.assertIs(agent.run_state.record, original)
        self.assertIs(agent.response.run_state, original)
        self.assertIsNone(agent.preflight.run_state_related)
        self.assertFalse(agent.response.results[JevPreflightPreset.RUN_STATE_RELATION].available)
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])
        self.assertEqual(main.calls, ["Question about the SDK."])

    async def test_missing_relation_answer_preserves_existing_record(self) -> None:
        agent, _, state_runner = _agent()
        assert isinstance(agent.run_state, JevRunStateRelation)
        original = _record(with_sections=False)
        agent.run_state.record = original
        decision = ScriptedDecisionRunner(omit=_RELATION_KEY.value)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("An SDK follow-up with no returned answer.")
        self.assertIsNone(agent.preflight.run_state_related)
        self.assertFalse(agent.response.results[JevPreflightPreset.RUN_STATE_RELATION].available)
        self.assertIs(agent.run_state.record, original)
        self.assertIs(agent.response.run_state, original)
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])

    async def test_replacement_failure_leaves_no_stale_state_and_typed_error_fails_open(self) -> None:
        error = ProviderRequestError("run-state generation unavailable", provider="openai")
        agent, main, state_runner = _agent(state_error=error)
        assert isinstance(agent.run_state, JevRunStateRelation) and state_runner is not None
        agent.run_state.record = _record(with_sections=False)
        decision = ScriptedDecisionRunner(probability=0.1)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("Write a deployment runbook.")
        self.assertEqual(state_runner.calls, ["Write a deployment runbook."])
        self.assertIsNone(agent.run_state.record)
        self.assertIsNone(agent.response.run_state)
        self.assertEqual(main.calls, ["Write a deployment runbook."])

    async def test_replacement_cancellation_propagates(self) -> None:
        agent, _, state_runner = _agent(state_error=asyncio.CancelledError())
        assert isinstance(agent.run_state, JevRunStateRelation) and state_runner is not None
        agent.run_state.record = _record(with_sections=False)
        decision = ScriptedDecisionRunner(probability=0.1)
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)), self.assertRaises(asyncio.CancelledError):
            await agent.arun("Write a deployment runbook.")
        self.assertIsNone(agent.run_state.record)

    async def test_done_continuation_exists_only_when_a_done_check_is_enabled(self) -> None:
        relation_only, _, _ = _agent()
        with_done_check, _, _ = _agent(checks=(JevDoneCheck.MULTI_PART,))
        self.assertIsInstance(relation_only.run_state, JevRunStateRelation)
        self.assertEqual(relation_only.run_state.checks, ())
        self.assertIsNone(relation_only.continuation)
        self.assertTrue(with_done_check.run_state.checks)
        self.assertIsNotNone(with_done_check.continuation)

    async def test_legacy_mode_keeps_per_run_begin_semantics(self) -> None:
        agent, _, state_runner = _agent(preflight=(), checks=(JevDoneCheck.MULTI_PART,))
        assert isinstance(agent.run_state, JevRunState) and not isinstance(agent.run_state, JevRunStateRelation)
        first = _record(with_sections=False)
        agent.run_state.record = first
        agent.run_state.request = "old request"
        agent.run_state.rendered = "old rendered"
        await agent.arun("A new request.")
        self.assertEqual(state_runner.calls, ["A new request."])
        self.assertEqual(agent.run_state.request, "A new request.")
        self.assertNotEqual(agent.response.run_state, first)
        self.assertEqual(agent.response.results, {})
        self.assertIsNotNone(agent.continuation)

    async def test_related_specialist_request_reports_preserved_record_before_delegation(self) -> None:
        specialist_runner = ScriptedGenerativeRunner("specialist reply")
        specialist_agent = bind_test_runner(BaseAgent(name="sdk", system_prompt="Work on the SDK.", provider="openai", model_name="gpt-4.1-mini"), specialist_runner)
        specialist = JevSpecialist("sdk", "Changes to the Vidbyte SDK project.", specialist_agent)
        agent, main, state_runner = _agent(specialists=(specialist,))
        assert isinstance(agent.run_state, JevRunStateRelation)
        original = _record(with_sections=False)
        agent.run_state.record = original
        decision = ScriptedDecisionRunner(probability=0.9, choices={"sdk": 1.0, JEV_SPECIALIST_NONE: 0.0})
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("Explain an issue in the SDK.")
        self.assertIs(agent.response.run_state, original)
        self.assertIs(agent.run_state.record, original)
        self.assertEqual(specialist_runner.calls, ["Explain an issue in the SDK."])
        self.assertEqual(main.calls, [])
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])

    async def test_unrelated_specialist_request_replaces_state_before_delegation(self) -> None:
        specialist_runner = ScriptedGenerativeRunner("specialist reply")
        specialist_agent = bind_test_runner(BaseAgent(name="ops", system_prompt="Work on deployments.", provider="openai", model_name="gpt-4.1-mini"), specialist_runner)
        specialist = JevSpecialist("ops", "Deployment runbooks and operations procedures.", specialist_agent)
        agent, main, state_runner = _agent(specialists=(specialist,))
        assert isinstance(agent.run_state, JevRunStateRelation) and state_runner is not None
        agent.run_state.record = _record(with_sections=False)
        decision = ScriptedDecisionRunner(probability=0.1, choices={"ops": 1.0, JEV_SPECIALIST_NONE: 0.0})
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("Write a deployment runbook.")
        self.assertEqual(state_runner.calls, ["Write a deployment runbook."])
        self.assertEqual(agent.response.run_state.objective, _REPLACEMENT_STATE["objective"])
        self.assertEqual(specialist_runner.calls, ["Write a deployment runbook."])
        self.assertEqual(main.calls, [])

    async def test_legacy_specialist_route_uses_the_base_no_op_without_generating_state(self) -> None:
        specialist_runner = ScriptedGenerativeRunner("specialist reply")
        specialist_agent = bind_test_runner(BaseAgent(name="ops", system_prompt="Work on deployments.", provider="openai", model_name="gpt-4.1-mini"), specialist_runner)
        specialist = JevSpecialist("ops", "Deployment runbooks and operations procedures.", specialist_agent)
        agent, main, state_runner = _agent(preflight=(), checks=(JevDoneCheck.MULTI_PART,), specialists=(specialist,))
        assert isinstance(agent.run_state, JevRunState) and not isinstance(agent.run_state, JevRunStateRelation)
        decision = ScriptedDecisionRunner(choices={"ops": 1.0, JEV_SPECIALIST_NONE: 0.0})
        with patch(_GATE_RUNNER_PATH, new=_decision_helper(decision)):
            await agent.arun("Write a deployment runbook.")
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])
        self.assertIsNone(agent.response.run_state)
        self.assertEqual(specialist_runner.calls, ["Write a deployment runbook."])
        self.assertEqual(main.calls, [])

    async def test_closed_gate_returns_before_any_state_handoff(self) -> None:
        agent, _, state_runner = _agent()
        assert agent.run_state is not None
        begin = AsyncMock()
        delegated = AsyncMock()
        with patch.object(agent.preflight, "pass_", new=AsyncMock(return_value=False)), patch.object(agent.run_state, "begin", new=begin), patch.object(agent.run_state, "begin_delegated", new=delegated):
            await agent.arun("Stopped by the gate.")
        begin.assert_not_awaited()
        delegated.assert_not_awaited()
        self.assertEqual(state_runner.calls if state_runner is not None else [], [])
        self.assertEqual(agent.response.results, {})


if __name__ == "__main__":
    unittest.main()

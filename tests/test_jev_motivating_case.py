"""FILE: tests/test_jev_motivating_case.py

PURPOSE: Verifies JevAgent's motivating-case done check (JevPresets.MotivatingCase) without network access.
ROLE IN CODEBASE: Covers docs/design/jev-motivating-case.md: state and handoff validation, code evidence checks, the answer combination, and the finish-attempt loop.
ARCHITECTURE NOTE: A scripted generative runner stands in for the model, and a rule-based fake decision runner stands in for Jev so answers depend on the verified excerpts it receives.
COMMON MODIFICATION PATTERNS: Add a labeled case whenever a question, threshold, code check, or continuation rule changes.
KNOWN EDGE CASES: The generative runner is shared by the main loop and both builders, so scripted responses are consumed in call order.
RELATED DOCS: docs/design/jev-motivating-case.md and skills/asking-jev-questions/SKILL.md.
TESTS: python -m pytest tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

import json
import os
import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevPresets as RootJevPresets
from vidbyte import VidbyteSDK, tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevPresets
from vidbyte.agents.jev.motivating_case import (
    MotivatingCaseHandoff,
    MotivatingCasePolicy,
    MotivatingCaseState,
    RunEventLedger,
    ScenarioEvidenceChecker,
    ScenarioExercise,
)
from vidbyte.agents.jev.motivating_case.questions import (
    ASSERTS_EXPECTED,
    CODE_HANDLES_CASE,
    DISCLOSES_UNVERIFIED,
    ENVIRONMENT_BLOCKED,
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    OUTCOME_RESULT,
    OUTCOME_SKIPPED,
    OUTCOME_UNCLEAR,
    RECALL_GUARD,
    SETUP_BUILDS_CASE,
)
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevQuestion
from vidbyte.lib.dataclasses.tools import ToolPermission
from vidbyte.lib.enums import JevQuestionType, JevScenarioOutcome, ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    OutputSchemaViolationError,
    ProviderResponseError,
)
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCallContext, ToolCallState, ToolResult

REQUEST = "Fix export_csv: it crashes when the rows list is empty ([]). It should return a header-only CSV."
RUNTIME_MODULE = "vidbyte.agents.jev.runtime.DecisionModelRunner"


def _scenario(**overrides: Any) -> dict[str, Any]:
    # Builds one valid scenario payload for REQUEST, letting a test change selected fields.
    values: dict[str, Any] = {
        "id": "empty_rows",
        "role": "motivating",
        "kind": "empty_or_missing",
        "source_quote": "it crashes when the rows list is empty ([])",
        "target": "export_csv",
        "condition": "export_csv receives a rows list with zero rows",
        "near_miss": "a rows list with one row, or None",
        "expected_behavior": "",
        "literal_inputs": ["[]"],
        "exercise_mode": "run",
    }
    values.update(overrides)
    return values


def _state_payload(*scenarios: dict[str, Any], restriction: str = "") -> dict[str, Any]:
    # Builds a state-builder payload with the given scenarios.
    return {"ordinary_flow": "export_csv receives several rows", "testing_restriction_quote": restriction, "scenarios": list(scenarios)}


def _state(*scenarios: dict[str, Any], restriction: str = "", request: str = REQUEST) -> MotivatingCaseState:
    # Parses a state payload exactly as the runtime does.
    return MotivatingCaseState.from_payload(_state_payload(*scenarios, restriction=restriction), request)


def _exercise(**fields: str) -> dict[str, str]:
    # Builds one handoff entry with every field present and blanks for absent claims.
    names = ("case_name", "setup_ref", "setup_quote", "outcome_ref", "outcome_quote", "inspection_ref", "inspection_quote", "blocker_ref", "blocker_quote")
    entry = {"scenario_id": fields.pop("scenario_id", "empty_rows")}
    entry.update({name: fields.get(name, "") for name in names})
    return entry


def _context(tool_name: str, arguments: dict[str, Any], output: str, *, state: ToolCallState = ToolCallState.SUCCEEDED, internal: bool = False) -> ToolCallContext:
    # Builds one recorded tool call as the runtime stores it.
    result = ToolResult.success(tool_name, output) if state is ToolCallState.SUCCEEDED else ToolResult.error(tool_name, output)
    return ToolCallContext(tool_name=tool_name, arguments=arguments, state=state, result=result, metadata={"internal": True} if internal else {})


_PERMISSIONS = {"write_file": ToolPermission.WRITE, "run_command": ToolPermission.EXECUTE, "read_file": ToolPermission.READ}


def _ledger(*contexts: ToolCallContext) -> RunEventLedger:
    # Builds a ledger with the test tools' declared permissions.
    return RunEventLedger.from_contexts(contexts, _PERMISSIONS.get)


def _noul(name: str, probability: float) -> JevAnswer:
    # Builds a normalized noul answer.
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if probability >= 0.5 else "false", probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


def _choice(name: str, label: str, probability: float = 0.9) -> JevAnswer:
    # Builds a normalized outcome_result choice answer concentrated on one label.
    labels = (OUTCOME_PASSED, OUTCOME_FAILED, OUTCOME_SKIPPED, OUTCOME_UNCLEAR)
    rest = (1.0 - probability) / (len(labels) - 1)
    probabilities = {item: (probability if item == label else rest) for item in labels}
    return JevAnswer(question_name=name, question_type=JevQuestionType.CHOICE, choice=label, probabilities=probabilities, confidence=probability)


def _rule_answer(question: JevQuestion, state: Any, *, recall: float = 0.1) -> JevAnswer:
    # A stand-in for Jev that recognizes the fixture's literal markers in the named state fields.
    fields = dict(state) if not isinstance(state, str) else {}
    setup = str(fields.get("setup_excerpt", ""))
    if question.name == RECALL_GUARD:
        return _noul(question.name, recall)
    if question.name == SETUP_BUILDS_CASE:
        return _noul(question.name, 0.95 if "([])" in setup else 0.05)
    if question.name == ASSERTS_EXPECTED:
        return _noul(question.name, 0.9 if "==" in setup else 0.1)
    if question.name == OUTCOME_RESULT:
        outcome = str(fields.get("outcome_excerpt", "")).lower()
        label = OUTCOME_FAILED if "failed" in outcome else OUTCOME_SKIPPED if "skipped" in outcome else OUTCOME_PASSED if "passed" in outcome else OUTCOME_UNCLEAR
        return _choice(question.name, label)
    if question.name == CODE_HANDLES_CASE:
        return _noul(question.name, 0.9 if "if not rows" in str(fields.get("code_excerpt", "")) else 0.1)
    if question.name == ENVIRONMENT_BLOCKED:
        return _noul(question.name, 0.95 if "command not found" in str(fields.get("blocker_excerpt", "")) else 0.05)
    if question.name == DISCLOSES_UNVERIFIED:
        return _noul(question.name, 0.9 if "not verified" in str(fields.get("final_reply", "")) else 0.05)
    raise AssertionError(f"unexpected question {question.name}")


class FakeJev:
    """Decision runner stand-in that records requests and answers by rule."""

    def __init__(self, answer: Callable[[JevQuestion, Any], JevAnswer] = _rule_answer) -> None:
        # Retains the answering rule and every request for assertions.
        self.answer = answer
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Answers every question in the request against its shared state.
        self.requests.append(request)
        answers = {question.name: self.answer(question, request.state) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-test", answers=answers, raw={})

    def question_names(self) -> list[str]:
        # Flattens asked question names in order.
        return [question.name for request in self.requests for question in request.questions]


class ScriptedRunner:
    """Generative runner stand-in shared by the main loop and both builders; raises scripted exceptions."""

    def __init__(self, *responses: object) -> None:
        # Retains responses in call order.
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Returns or raises the next scripted response.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RawResponse:
    """OpenAI Responses-shaped raw payload for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        # Exposes the attributes BaseAgent reads from a runner response.
        self.text = ""
        self.raw = raw


def _text(text: str) -> TextModelResponse:
    # A plain generative reply.
    return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


def _json(payload: dict[str, Any]) -> TextModelResponse:
    # A structured builder reply.
    return _text(json.dumps(payload))


def _call(name: str, arguments: dict[str, Any], call_id: str) -> RawResponse:
    # One model-issued tool call.
    return RawResponse({"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


COMMAND_OUTPUTS: dict[str, str] = {}


@tool(permission=ToolPermission.WRITE)
def write_file(path: str, content: str) -> str:
    """Write a file."""
    return f"wrote {path}"


@tool(permission=ToolPermission.EXECUTE)
def run_command(command: str) -> str:
    """Run a shell command."""
    return COMMAND_OUTPUTS.get(command, "")


def _agent(runner: ScriptedRunner, *, done_criteria: JevPresets | None = JevPresets.MotivatingCase) -> JevAgent:
    # Builds a JevAgent with write/execute tools allowed and the scripted runner bound.
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini", tools=(write_file, run_command), permission_policy=PermissionPolicy.allow_all())
    with patch.dict(os.environ, {"TYPESAFE_API_KEY": "typesafe-test-key"}):
        return bind_test_runner(JevAgent(settings, done_criteria=done_criteria), runner)


class StateRecordTests(unittest.TestCase):
    """Pins the request-derived state contract."""

    def test_valid_state_round_trips(self) -> None:
        # [Silent Failure] enum fields, blank expected behavior, and literal inputs survive parsing unchanged.
        state = _state(_scenario())
        scenario = state.scenarios[0]
        self.assertIsNone(scenario.expected_behavior)
        self.assertEqual(scenario.literal_inputs, ("[]",))
        self.assertTrue(scenario.blocks_finish())
        self.assertEqual(state.to_payload()["scenarios"][0]["kind"], "empty_or_missing")

    def test_empty_scenarios_are_valid(self) -> None:
        # [Edge Case] a request with no boundary condition yields an empty, inactive state.
        self.assertTrue(_state().is_empty())

    def test_non_verbatim_quote_is_rejected(self) -> None:
        # [Hidden Failure] a paraphrased quote would let the builder invent a scenario the user never raised.
        with self.assertRaisesRegex(OutputSchemaViolationError, "verbatim"):
            _state(_scenario(source_quote="it fails on empty input"))

    def test_quote_matching_ignores_whitespace_layout(self) -> None:
        # [Edge Case] a quote re-wrapped across lines still matches the request.
        _state(_scenario(source_quote="it crashes   when the rows\nlist is empty"))

    def test_duplicate_ids_and_motivating_cap_are_rejected(self) -> None:
        # [Hidden Assumption] scenario ids key the handoff, so duplicates must not reach the check.
        with self.assertRaises(OutputSchemaViolationError):
            _state(_scenario(), _scenario())
        many = [_scenario(id=f"case_{index}") for index in range(4)]
        with self.assertRaisesRegex(OutputSchemaViolationError, "motivating"):
            _state(*many)

    def test_restriction_quote_must_be_verbatim(self) -> None:
        # [Hidden Failure] an invented testing restriction would excuse every unexercised case.
        with self.assertRaises(OutputSchemaViolationError):
            _state(_scenario(), restriction="do not run tests")

    def test_implied_scenarios_never_block(self) -> None:
        # [Hidden Assumption] only user-named cases can hold a run open.
        self.assertFalse(_state(_scenario(role="implied")).scenarios[0].blocks_finish())


class HandoffRecordTests(unittest.TestCase):
    """Pins exact coverage of the finish-attempt handoff."""

    def test_missing_or_extra_scenarios_are_rejected(self) -> None:
        # [Hidden Failure] a handoff that drops a scenario would silently skip its check.
        state = _state(_scenario(), _scenario(id="retry", role="requested"))
        with self.assertRaisesRegex(OutputSchemaViolationError, "exactly match"):
            MotivatingCaseHandoff.from_payload({"scenarios": [_exercise()]}, state)
        with self.assertRaisesRegex(OutputSchemaViolationError, "unique"):
            MotivatingCaseHandoff.from_payload({"scenarios": [_exercise(), _exercise()]}, state)

    def test_blank_fields_become_absent_and_order_follows_state(self) -> None:
        # [Silent Failure] "" must mean absent, not an empty quote that matches everything.
        state = _state(_scenario(), _scenario(id="retry", role="requested"))
        handoff = MotivatingCaseHandoff.from_payload({"scenarios": [_exercise(scenario_id="retry"), _exercise()]}, state)
        self.assertEqual([item.scenario_id for item in handoff.exercises], ["empty_rows", "retry"])
        self.assertIsNone(handoff.exercises[0].setup_quote)


class EvidenceCheckTests(unittest.TestCase):
    """Pins the code facts Jev never judges."""

    def setUp(self) -> None:
        # One scenario and a ledger where a test file is written and then run.
        self.scenario = _state(_scenario()).scenarios[0]
        self.write = _context("write_file", {"path": "tests/test_export.py", "content": "def test_empty():\n    assert export_csv([]) == 'a\\n'"}, "wrote tests/test_export.py")
        self.run = _context("run_command", {"command": "pytest tests/test_export.py"}, "1 passed in 0.01s")

    def test_verified_setup_and_outcome_make_run_ok(self) -> None:
        # [Silent Failure] a correct write-then-run pair is recognized as a current, covering run.
        ledger = _ledger(self.write, self.run)
        evidence = ScenarioEvidenceChecker(ledger).check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e1", setup_quote="assert export_csv([])", outcome_ref="e2", outcome_quote="1 passed"))
        self.assertTrue(evidence.run_ok)
        self.assertFalse(evidence.stale)

    def test_fabricated_ref_and_paraphrased_quote_are_dropped(self) -> None:
        # [Hidden Failure] the handoff builder cannot create evidence by naming a missing event or paraphrasing.
        ledger = _ledger(self.write, self.run)
        checker = ScenarioEvidenceChecker(ledger)
        no_literals = _state(_scenario(literal_inputs=[])).scenarios[0]
        self.assertIsNone(checker.check(no_literals, ScenarioExercise("empty_rows", setup_ref="e9", setup_quote="export_csv([])")).setup_excerpt)
        paraphrased = checker.check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e1", setup_quote="tests the empty list", outcome_ref="e2", outcome_quote="1 passed"))
        self.assertTrue(paraphrased.recovered_by_literal)
        self.assertEqual(paraphrased.setup_event_id, "e1")

    def test_write_after_run_makes_it_stale(self) -> None:
        # [Hidden Failure] a passing run before the final code change does not verify the final code.
        later_write = _context("write_file", {"path": "export.py", "content": "def export_csv(rows): ..."}, "wrote export.py")
        ledger = _ledger(self.write, self.run, later_write)
        evidence = ScenarioEvidenceChecker(ledger).check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="1 passed"))
        self.assertTrue(evidence.stale)
        self.assertFalse(evidence.run_ok)

    def test_run_before_setup_and_failed_run_are_not_ok(self) -> None:
        # [Hidden Failure] ordering and success are exact checks, not Jev judgments.
        ledger = _ledger(self.run, self.write)
        evidence = ScenarioEvidenceChecker(ledger).check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e2", setup_quote="export_csv([])", outcome_ref="e1", outcome_quote="1 passed"))
        self.assertFalse(evidence.run_ok)
        failed = _context("run_command", {"command": "pytest tests/test_export.py"}, "boom", state=ToolCallState.FAILED)
        evidence = ScenarioEvidenceChecker(_ledger(self.write, failed)).check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="boom"))
        self.assertFalse(evidence.run_ok)

    def test_outcome_must_be_an_execute_event(self) -> None:
        # [Hidden Assumption] reading a file that says "passed" is not a run.
        read = _context("read_file", {"path": "log.txt"}, "1 passed")
        evidence = ScenarioEvidenceChecker(_ledger(self.write, read)).check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="1 passed"))
        self.assertIsNone(evidence.outcome_excerpt)

    def test_run_of_a_different_file_does_not_cover_setup(self) -> None:
        # [Silent Failure] a passing run of another test file must not verify this setup.
        other = _context("run_command", {"command": "pytest tests/test_other.py"}, "3 passed")
        evidence = ScenarioEvidenceChecker(_ledger(self.write, other)).check(self.scenario, ScenarioExercise("empty_rows", setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="3 passed"))
        self.assertFalse(evidence.run_ok)

    def test_literal_recovery_uses_an_inline_execution_as_its_own_outcome(self) -> None:
        # [Edge Case] an unlinked `python -c "export_csv([])"` run is still found by the user's exact value.
        inline = _context("run_command", {"command": 'python -c "print(export_csv([]))"'}, "a\n")
        evidence = ScenarioEvidenceChecker(_ledger(inline)).check(self.scenario, ScenarioExercise("empty_rows"))
        self.assertTrue(evidence.recovered_by_literal)
        self.assertEqual((evidence.setup_event_id, evidence.outcome_event_id), ("e1", "e1"))
        self.assertTrue(evidence.run_ok)

    def test_quotes_match_full_output_and_internal_tools_are_skipped(self) -> None:
        # [Hidden Assumption] quotes resolve against raw output, and isDone never becomes an event.
        long_output = "x" * 20_000 + "\ntest_empty PASSED\n1 passed"
        run = _context("run_command", {"command": "pytest"}, long_output)
        done = _context("isDone", {"final_answer": "done"}, "done", internal=True)
        ledger = _ledger(self.write, run, done)
        self.assertEqual([event.event_id for event in ledger.events()], ["e1", "e2"])
        evidence = ScenarioEvidenceChecker(ledger).check(self.scenario, ScenarioExercise("empty_rows", case_name="test_empty", setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="test_empty PASSED"))
        self.assertTrue(evidence.run_ok)
        self.assertEqual(evidence.case_name, "test_empty")


class PolicyCombinationTests(unittest.IsolatedAsyncioTestCase):
    """Pins how Jev answers and code facts combine into outcomes."""

    async def _decide(self, state: MotivatingCaseState, contexts: tuple[ToolCallContext, ...], exercises: list[dict[str, str]], final: str = "Done.") -> Any:
        # Runs the policy over a ledger and handoff with the rule-based fake Jev.
        self.jev = FakeJev()
        handoff = MotivatingCaseHandoff.from_payload({"scenarios": exercises}, state)
        return await MotivatingCasePolicy(self.jev).evaluate(state, _ledger(*contexts), handoff, final, prior_continuations=0)  # type: ignore[arg-type]

    async def test_near_miss_setup_is_not_exercised(self) -> None:
        # [Silent Failure] a passing one-row test must not satisfy an empty-list request.
        write = _context("write_file", {"path": "t.py", "content": "assert export_csv([{'a': 1}])"}, "ok")
        run = _context("run_command", {"command": "pytest t.py"}, "1 passed")
        decision = await self._decide(_state(_scenario(literal_inputs=[])), (write, run), [_exercise(setup_ref="e1", setup_quote="export_csv([{'a': 1}])", outcome_ref="e2", outcome_quote="1 passed")])
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.NOT_EXERCISED)
        self.assertFalse(decision.accepted())
        self.assertIn("a rows list with one row, or None", decision.feedback())

    async def test_exercised_case_is_accepted(self) -> None:
        # [Edge Case] the motivating case built, run after the last write, and passing is accepted.
        write = _context("write_file", {"path": "t.py", "content": "assert export_csv([])"}, "ok")
        run = _context("run_command", {"command": "pytest t.py"}, "1 passed")
        decision = await self._decide(_state(_scenario()), (write, run), [_exercise(setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="1 passed")])
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.EXERCISED)
        self.assertTrue(decision.accepted())

    async def test_expected_behavior_requires_an_assertion(self) -> None:
        # [Silent Failure] running the case without checking its result is not verification.
        scenario = _scenario(expected_behavior="returns a header-only CSV")
        write = _context("write_file", {"path": "t.py", "content": "export_csv([])"}, "ok")
        run = _context("run_command", {"command": "pytest t.py"}, "1 passed")
        decision = await self._decide(_state(scenario), (write, run), [_exercise(setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="1 passed")])
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.NOT_EXERCISED)
        self.assertIn(ASSERTS_EXPECTED, self.jev.question_names())

    async def test_skipped_run_is_not_exercised(self) -> None:
        # [Hidden Failure] a skipped or deselected check reports success at the process level only.
        write = _context("write_file", {"path": "t.py", "content": "assert export_csv([])"}, "ok")
        run = _context("run_command", {"command": "pytest t.py"}, "1 skipped")
        decision = await self._decide(_state(_scenario()), (write, run), [_exercise(setup_ref="e1", setup_quote="export_csv([])", outcome_ref="e2", outcome_quote="1 skipped")])
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.NOT_EXERCISED)

    async def test_inspection_satisfies_only_inspect_modes(self) -> None:
        # [Edge Case] reading the handling branch counts only where the state allows inspection.
        read = _context("read_file", {"path": "export.py"}, "def export_csv(rows):\n    if not rows:\n        return HEADER")
        exercise = [_exercise(inspection_ref="e1", inspection_quote="if not rows:")]
        allowed = await self._decide(_state(_scenario(exercise_mode="run_or_inspect")), (read,), exercise)
        self.assertEqual(allowed.verdicts[0].outcome, JevScenarioOutcome.INSPECTED)
        required = await self._decide(_state(_scenario(exercise_mode="run")), (read,), exercise)
        self.assertEqual(required.verdicts[0].outcome, JevScenarioOutcome.NOT_EXERCISED)
        self.assertNotIn(CODE_HANDLES_CASE, self.jev.question_names())

    async def test_blocked_case_needs_disclosure(self) -> None:
        # [Edge Case] an environment blocker is acceptable only when the reply tells the user.
        blocked = _context("run_command", {"command": "pytest"}, "bash: pytest: command not found", state=ToolCallState.FAILED)
        exercise = [_exercise(blocker_ref="e1", blocker_quote="pytest: command not found")]
        silent = await self._decide(_state(_scenario()), (blocked,), exercise, final="Fixed it.")
        self.assertEqual(silent.verdicts[0].outcome, JevScenarioOutcome.BLOCKED)
        self.assertFalse(silent.accepted())
        self.assertIn("Tell the user", silent.feedback())
        honest = await self._decide(_state(_scenario()), (blocked,), exercise, final="Fixed it; the empty case is not verified because pytest is missing.")
        self.assertTrue(honest.accepted())

    async def test_restriction_quote_turns_missing_run_into_blocked(self) -> None:
        # [Hidden Assumption] a user who said not to run tests is never pushed to run them.
        request = REQUEST + " Please don't run the test suite."
        state = _state(_scenario(), restriction="don't run the test suite", request=request)
        decision = await self._decide(state, (), [_exercise()], final="Done; the empty case is not verified.")
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.BLOCKED)
        self.assertTrue(decision.accepted())

    async def test_implied_scenario_is_reported_but_accepted(self) -> None:
        # [Hidden Assumption] implied cases never cause a continuation.
        decision = await self._decide(_state(_scenario(role="implied")), (), [_exercise()])
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.NOT_EXERCISED)
        self.assertTrue(decision.accepted())

    async def test_questions_are_omitted_without_excerpts(self) -> None:
        # [Edge Case] with no evidence and no reply, Jev is not called for that scenario.
        decision = await self._decide(_state(_scenario()), (), [_exercise()], final="")
        self.assertEqual(self.jev.requests, [])
        self.assertEqual(decision.verdicts[0].outcome, JevScenarioOutcome.NOT_EXERCISED)


class MotivatingCaseRunTests(unittest.IsolatedAsyncioTestCase):
    """Pins the preset end to end through the real JevAgent loop."""

    def setUp(self) -> None:
        # Resets command outputs shared by the module-level tool.
        COMMAND_OUTPUTS.clear()

    async def _run(self, runner: ScriptedRunner, jev: FakeJev) -> Any:
        # Runs the preset with the fake Jev injected where the runtime builds its decision runner.
        with patch(RUNTIME_MODULE, lambda config: jev):
            return await _agent(runner).arun(REQUEST)

    async def test_near_miss_continues_then_accepts_the_real_case(self) -> None:
        # [Silent Failure] the one-row test is rejected with feedback, and the empty-list test is accepted.
        COMMAND_OUTPUTS.update({"pytest tests/test_export.py": "1 passed", "pytest tests/test_export.py -k test_empty": "test_empty PASSED\n1 passed"})
        runner = ScriptedRunner(
            _json(_state_payload(_scenario())),
            _call("write_file", {"path": "tests/test_export.py", "content": "def test_one():\n    assert export_csv([{'a': 1}])"}, "c1"),
            _call("run_command", {"command": "pytest tests/test_export.py"}, "c2"),
            _text("Fixed export_csv."),
            _json({"scenarios": [_exercise(setup_ref="e1", setup_quote="export_csv([{'a': 1}])", outcome_ref="e2", outcome_quote="1 passed")]}),
            _call("write_file", {"path": "tests/test_export.py", "content": "def test_empty():\n    assert export_csv([]) == 'a\\n'"}, "c3"),
            _call("run_command", {"command": "pytest tests/test_export.py -k test_empty"}, "c4"),
            _text("Fixed export_csv and tested the empty list."),
            _json({"scenarios": [_exercise(case_name="test_empty", setup_ref="e3", setup_quote="assert export_csv([])", outcome_ref="e4", outcome_quote="test_empty PASSED")]}),
        )
        reply = await self._run(runner, FakeJev())
        self.assertEqual(reply.content, "Fixed export_csv and tested the empty list.")
        report = reply.metadata["done_criteria"]
        self.assertEqual((report["status"], report["continuations"]), ("evaluated", 1))
        self.assertEqual(report["review"]["scenarios"]["empty_rows"]["outcome"], "exercised")
        feedback_prompt = runner.calls[5]["kwargs"]
        self.assertIn("a rows list with one row, or None", json.dumps(feedback_prompt, default=str))
        self.assertEqual(runner.responses, [])

    async def test_is_done_rejection_becomes_the_tool_result(self) -> None:
        # [Hidden Failure] a rejected isDone gets a tool result and the same loop continues.
        runner = ScriptedRunner(
            _json(_state_payload(_scenario())),
            _call("isDone", {"final_answer": "done early"}, "c1"),
            _json({"scenarios": [_exercise()]}),
            _call("run_command", {"command": 'python -c "print(export_csv([]))"'}, "c2"),
            _call("isDone", {"final_answer": "done; ran the empty list"}, "c3"),
            _json({"scenarios": [_exercise()]}),
        )
        COMMAND_OUTPUTS['python -c "print(export_csv([]))"'] = "a\npassed"
        reply = await self._run(runner, FakeJev(lambda q, s: _rule_answer(q, s) if q.name != SETUP_BUILDS_CASE else _noul(q.name, 0.95 if "export_csv([])" in str(dict(s).get("setup_excerpt", "")) else 0.05)))
        self.assertEqual(reply.content, "done; ran the empty list")
        rejected_turn = json.dumps(runner.calls[3]["kwargs"], default=str)
        self.assertIn("motivating-case check", rejected_turn)
        self.assertEqual(reply.metadata["done_criteria"]["review"]["scenarios"]["empty_rows"]["recovered_by_literal"], True)

    async def test_continuations_are_capped(self) -> None:
        # [Hidden Failure] an agent that never tests the case cannot loop forever.
        runner = ScriptedRunner(
            _json(_state_payload(_scenario())),
            _text("attempt 1"), _json({"scenarios": [_exercise()]}),
            _text("attempt 2"), _json({"scenarios": [_exercise()]}),
            _text("attempt 3"), _json({"scenarios": [_exercise()]}),
        )
        reply = await self._run(runner, FakeJev())
        self.assertEqual(reply.content, "attempt 3")
        report = reply.metadata["done_criteria"]
        self.assertEqual((report["status"], report["continuations"]), ("unresolved_at_limit", 2))

    async def test_empty_state_skips_the_check_when_recall_guard_agrees(self) -> None:
        # [Edge Case] a request with no boundary condition costs one recall question and no review.
        jev = FakeJev()
        runner = ScriptedRunner(_json(_state_payload()), _text("answer"))
        reply = await self._run(runner, jev)
        self.assertEqual(reply.content, "answer")
        self.assertEqual(jev.question_names(), [RECALL_GUARD])
        self.assertEqual(reply.metadata["done_criteria"]["status"], "inactive")

    async def test_recall_guard_rebuilds_an_empty_state(self) -> None:
        # [Hidden Failure] a builder that missed the edge case gets one rebuild with a reviewer note.
        jev = FakeJev(lambda q, s: _rule_answer(q, s, recall=0.9))
        runner = ScriptedRunner(_json(_state_payload()), _json(_state_payload(_scenario(role="implied"))), _text("answer"), _json({"scenarios": [_exercise()]}))
        reply = await self._run(runner, jev)
        self.assertIn("Reviewer note", runner.calls[1]["prompt"] + json.dumps(runner.calls[1]["kwargs"], default=str))
        report = reply.metadata["done_criteria"]
        self.assertEqual(report["recall_guard"]["builder_disagreement"], False)
        self.assertEqual(report["status"], "evaluated")

    async def test_builder_and_review_failures_fail_open(self) -> None:
        # [Hidden Failure] infrastructure failures are recorded and never change the run's outcome.
        failing_state = ScriptedRunner(ProviderResponseError("state builder down", provider="openai"), _text("answer"))
        reply = await self._run(failing_state, FakeJev())
        self.assertEqual((reply.content, reply.metadata["done_criteria"]["status"]), ("answer", "state_unavailable"))
        failing_review = ScriptedRunner(_json(_state_payload(_scenario())), _text("answer"), ProviderResponseError("handoff builder down", provider="openai"))
        reply = await self._run(failing_review, FakeJev())
        self.assertEqual((reply.content, reply.metadata["done_criteria"]["status"]), ("answer", "review_failed"))

    def test_missing_typesafe_key_fails_at_construction(self) -> None:
        # [Hidden Assumption] an enabled check reports missing credentials up front; without a preset none are needed.
        settings = JevAgentSettings(name="jev", system_prompt="x", provider="openai", model_name="gpt-4.1-mini")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            with self.assertRaisesRegex(ConfigurationError, "TYPESAFE_API_KEY"):
                JevAgent(settings, done_criteria=JevPresets.MotivatingCase)
            self.assertIsNone(JevAgent(settings).done_criteria)

    async def test_without_preset_no_builder_or_jev_runs(self) -> None:
        # [Hidden Assumption] the seam is inert for plain JevAgent and ordinary runtimes.
        runner = ScriptedRunner(_text("answer"))
        with patch(RUNTIME_MODULE, side_effect=AssertionError("no decision runner")):
            reply = await _agent(runner, done_criteria=None).arun(REQUEST)
        self.assertEqual(len(runner.calls), 1)
        self.assertNotIn("done_criteria", reply.metadata)


class PublicSurfaceTests(unittest.IsolatedAsyncioTestCase):
    """Pins the preset's public API."""

    def test_presets_are_exported_and_raw_strings_rejected(self) -> None:
        # [Hidden Assumption] only JevPresets members enable a preset.
        self.assertIs(RootJevPresets, JevPresets)
        settings = JevAgentSettings(name="jev", system_prompt="x", provider="openai", model_name="gpt-4.1-mini")
        with self.assertRaises(ConfigurationError):
            JevAgent(settings, done_criteria="motivating_case")  # type: ignore[arg-type]
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "typesafe-test-key"}):
            agent = VidbyteSDK().agents.jev(settings, done_criteria=JevPresets.MotivatingCase)
        self.assertIs(agent.done_criteria, JevPresets.MotivatingCase)

    async def test_default_runtime_accepts_every_finish_attempt(self) -> None:
        # [Hidden Assumption] the base seam never continues a run.
        self.assertIsNone(await AgentRuntime._finish_attempt_feedback(object(), object(), object()))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

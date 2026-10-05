"""FILE: tests/test_jev_compute_reset.py

PURPOSE: Verifies the first mid-run compute move without network calls: the run-local compute budget, the helper agents compute moves start, the REPEATING reset move, and the controller that acts on a recognized situation and brings the helper's report back to the main agent.
ROLE IN CODEBASE: Covers vidbyte/agents/jev/compute/budget.py, helpers.py, reset.py, the controller's act step, JevComputeSettings' budget fields, and JevRunState.add_helper_evidence.
ARCHITECTURE NOTE: Scripted runners replace the main agent's model, a patched arun replaces the brief writer, a scripted stand-in replaces Jev's request, and helper runs are patched where a test is not about the helper itself; the loop, controller, budget, and records run for real.
COMMON MODIFICATION PATTERNS: Add a case when a move, a budget limit, or the message the main agent reads changes.
KNOWN EDGE CASES: A failed helper is charged and recorded but changes nothing in the main loop; a situation without a move is recorded and not acted on.
RELATED DOCS: docs/design/jev-compute-reset.md.
TESTS: python -m pytest tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevContinualSettings, JevRuntimeSettings
from vidbyte.agents.jev.compute.budget import JevComputeBudget
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.reset import JevComputeReset
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_COMPUTE_HELPER_REPORT_MAX_CHARS, JEV_COMPUTE_RESET_SOURCE
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevComputeHelperResult,
    JevContinuationEvidence,
    JevDecisionRequest,
    JevRunBrief,
    JevRunBriefApproach,
    JevRunBriefPayload,
    JevRunBriefQuote,
    JevRunBriefQuotePayload,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult
from vidbyte.lib.enums import AgentRuntimeType, JevComputeMoveStatus, JevComputeSituation, JevDoneCheck, JevQuestionType, JevRunBriefOutcome, ModelProvider
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

REQUEST = "Get the test suite passing."
_HELPER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
Q = JevRunBriefQuote


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "fixer", "system_prompt": "Fix the code.", "provider": "openai", "model_name": "gpt-4.1", "api_key": "main-key", "tools": (run_tests,)}
    values.update(overrides)
    return JevAgentSettings(**values)


@tool
def run_tests(path: str) -> str:
    """Run the test file at the given path and return the test output."""
    return "ImportError: No module named 'yaml'"


class BindingTool:
    """A tool double that, like the SDK's agent-bound builtins, clones itself for a new agent."""

    def __init__(self) -> None:
        self.clones = 0

    def clone_for_fork(self) -> object:
        self.clones += 1
        return run_tests


def _stuck_brief(**overrides: Any) -> JevRunBrief:
    values: dict[str, Any] = {
        "goal": "Get the test suite passing",
        "iteration": 3,
        "through_event": 7,
        "approaches": (
            JevRunBriefApproach("reinstall", "ImportError for yaml", "reinstalled the requirements", JevRunBriefOutcome.FAILED, (Q("E3", "ImportError"),)),
            JevRunBriefApproach("rerun", "ImportError for yaml", "reran the tests", JevRunBriefOutcome.UNRESOLVED, (Q("E5", "ImportError"),)),
        ),
        "open_failures": (Q("E5", "ImportError: No module named 'yaml'"),),
    }
    values.update(overrides)
    return JevRunBrief(**values)


class JevComputeBudgetTests(unittest.TestCase):
    def test_limits_are_checked_in_order_and_spending_counts_toward_them(self) -> None:
        budget = JevComputeBudget(JevComputeSettings(max_moves=2, max_helpers=3, cooldown_iterations=4))
        self.assertIsNone(budget.blocked(3, 1))
        self.assertIs(budget.blocked(3, 4), JevComputeMoveStatus.HELPER_LIMIT)
        budget.spend(3, 1)
        self.assertIs(budget.blocked(6, 1), JevComputeMoveStatus.COOLDOWN)
        self.assertIsNone(budget.blocked(7, 1))
        budget.spend(7, 1)
        self.assertIs(budget.blocked(20, 1), JevComputeMoveStatus.MOVE_LIMIT)
        budget.begin()
        self.assertIsNone(budget.blocked(1, 1))

    def test_zero_moves_keeps_recognition_and_blocks_every_move(self) -> None:
        self.assertIs(JevComputeBudget(JevComputeSettings(max_moves=0)).blocked(1, 1), JevComputeMoveStatus.MOVE_LIMIT)

    def test_settings_validate_the_budget(self) -> None:
        for kwargs in ({"max_moves": -1}, {"max_helpers": 0}, {"cooldown_iterations": True}, {"helper_max_iterations": 0}, {"helper_max_tokens": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                JevComputeSettings(**kwargs)


class JevComputeHelpersTests(unittest.IsolatedAsyncioTestCase):
    def test_a_helper_is_a_separate_linear_agent_with_the_main_model_tools_and_limits(self) -> None:
        binding = BindingTool()
        helpers = JevComputeHelpers(_settings(tools=(binding,)), JevComputeSettings(helper_max_iterations=7, helper_max_tokens=9_000))
        helper = helpers.build("reset")
        self.assertEqual(helper.name, "fixer-compute-reset")
        self.assertIs(helper.runtime_type, AgentRuntimeType.LINEAR)
        self.assertEqual((helper.runner_config.model_name, helper.runner_config.api_key), ("gpt-4.1", "main-key"))
        self.assertEqual((helper.agent_loop_settings.max_iterations, helper.agent_loop_settings.max_tokens), (7, 9_000))
        self.assertEqual(binding.clones, 1)
        self.assertEqual(helper.history, [])

    async def test_run_returns_the_report_and_the_helpers_run_as_evidence(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        call = ToolCallContext(tool_name="run_tests", arguments={"path": "tests"}, state=ToolCallState.SUCCEEDED, result=ToolResult.success("run_tests", "3 passed"), iteration_count=1)
        reply = SimpleNamespace(content="Cause: missing PyYAML. Added it; 3 passed.", metadata={"iteration_outputs": ("Looking at imports.",), "tool_calls": (call, "not a call")})
        with patch("vidbyte.agents.base.BaseAgent.arun", new=AsyncMock(return_value=reply)):
            result = await helpers.run("reset", "fix it", source=JEV_COMPUTE_RESET_SOURCE)
        assert result is not None
        self.assertEqual(result.output, "Cause: missing PyYAML. Added it; 3 passed.")
        self.assertEqual(result.evidence.source, JEV_COMPUTE_RESET_SOURCE)
        self.assertEqual(result.evidence.responses, ("Looking at imports.", reply.content))
        self.assertEqual(result.evidence.tool_calls, (call,))

    async def test_an_outage_or_an_empty_report_returns_none(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        for arun in (AsyncMock(side_effect=VidbyteSdkError("down")), AsyncMock(return_value=SimpleNamespace(content="   ", metadata={}))):
            with self.subTest(arun=arun), patch("vidbyte.agents.base.BaseAgent.arun", new=arun):
                self.assertIsNone(await helpers.run("reset", "fix it", source=JEV_COMPUTE_RESET_SOURCE))


class JevComputeResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_helper_is_told_the_problem_what_failed_and_the_open_errors(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        result = JevComputeHelperResult(output="fixed", evidence=JevContinuationEvidence(source=JEV_COMPUTE_RESET_SOURCE, responses=("fixed",), tool_calls=()))
        with patch.object(helpers, "run", new=AsyncMock(return_value=result)) as run:
            outcome = await JevComputeReset(helpers).run(REQUEST, _stuck_brief())
        self.assertEqual(outcome, ("ImportError for yaml", result))
        prompt = run.await_args.args[1]
        self.assertIn("<problem>\nImportError for yaml\n</problem>", prompt)
        self.assertIn("- reinstalled the requirements (failed): E3: ImportError", prompt)
        self.assertIn("- reran the tests (unresolved): E5: ImportError", prompt)
        self.assertIn("- E5: ImportError: No module named 'yaml'", prompt)
        self.assertIn(REQUEST, prompt)
        self.assertEqual(run.await_args.kwargs["source"], JEV_COMPUTE_RESET_SOURCE)

    async def test_no_stuck_problem_starts_no_helper(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        solved = _stuck_brief(approaches=(JevRunBriefApproach("fix", "ImportError for yaml", "added PyYAML", JevRunBriefOutcome.WORKED, (Q("E3", "ok"),)),))
        with patch.object(helpers, "run", new=AsyncMock()) as run:
            self.assertIsNone(await JevComputeReset(helpers).run(REQUEST, solved))
        run.assert_not_awaited()

    def test_the_main_agent_reads_the_problem_and_a_clipped_report(self) -> None:
        reset = JevComputeReset(JevComputeHelpers(_settings(), JevComputeSettings()))
        message = reset.message("ImportError for yaml", "x" * (JEV_COMPUTE_HELPER_REPORT_MAX_CHARS * 2))
        self.assertIn("<problem>\nImportError for yaml\n</problem>", message)
        self.assertIn("characters left out", message)
        self.assertLess(len(message), JEV_COMPUTE_HELPER_REPORT_MAX_CHARS * 2)


class JevRunStateHelperEvidenceTests(unittest.TestCase):
    def test_helper_evidence_follows_the_main_work_that_preceded_it(self) -> None:
        settings = _settings()
        run_state = JevRunState(settings, JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,))), JevResponse())
        call = ToolCallContext(tool_name="run_tests", arguments={"path": "tests"}, state=ToolCallState.SUCCEEDED, result=ToolResult.success("run_tests", "1 failed"), iteration_count=1)
        helper = JevContinuationEvidence(source=JEV_COMPUTE_RESET_SOURCE, responses=("fixed",), tool_calls=())
        run_state.add_helper_evidence(["running tests"], [call], helper)
        self.assertEqual([segment.source for segment in run_state._evidence_segments], ["main:1", JEV_COMPUTE_RESET_SOURCE])
        self.assertEqual(run_state._evidence_segments[0].tool_calls, (call,))


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


class ScriptedJev:
    """Answers every question with one P(yes), recording each request."""

    def __init__(self, yes: float) -> None:
        self.yes = yes
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        answers: Mapping[str, JevAnswer] = {question.name: _answer(question.name, self.yes) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 50, "output_tokens": 5})


def _jev(scripted: ScriptedJev) -> type:
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedHelper


class ScriptedRunner:
    """Main-agent runner that returns scripted responses and keeps each call's messages."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.messages: list[tuple[Any, ...]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.messages.append(tuple(kwargs.get("messages") or ()))
        return self.responses.pop(0)


def _call(name: str, arguments: dict[str, Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(text="", raw={"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


def _stuck_payload() -> JevRunBriefPayload:
    return JevRunBriefPayload.model_validate({
        "goal": "Get the test suite passing",
        "goal_evidence": [{"event": "E1", "quote": "Get the test suite passing."}],
        "current_step": None,
        "next_steps": [],
        "items": [],
        "approaches": [{"id": "rerun", "target": "ImportError for yaml", "approach": "reran the tests", "outcome": "failed", "evidence": [{"event": "E2", "quote": "ImportError: No module named 'yaml'"}]}],
        "open_failures": [{"event": "E3", "quote": "ImportError: No module named 'yaml'"}],
    })


class JevComputeControllerMoveTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, compute: JevComputeSettings, tests: int = 4) -> tuple[JevAgent, ScriptedRunner]:
        runner = ScriptedRunner(*(_call("run_tests", {"path": "tests"}, f"c{index}") for index in range(tests)), _call("isDone", {"final_answer": "suite passing"}, "end"))
        runtime = JevRuntimeSettings(decision=DecisionModelConfig(api_key="typesafe-key"), compute=compute)
        return bind_test_runner(JevAgent(_settings(), runtime), runner), runner

    async def test_a_recognized_repeat_hands_the_problem_to_a_helper_and_the_main_agent_reads_its_report(self) -> None:
        agent, runner = self._agent(JevComputeSettings(situations=(JevComputeSituation.REPEATING,)))
        assert agent.compute is not None
        result = JevComputeHelperResult(output="Cause: PyYAML missing from requirements. Added it; suite passes.", evidence=JevContinuationEvidence(source=JEV_COMPUTE_RESET_SOURCE, responses=("done",), tool_calls=()))
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=_stuck_payload()))),
            patch(_HELPER, new=_jev(ScriptedJev(0.95))),
            patch.object(agent.compute.reset.helpers, "run", new=AsyncMock(return_value=result)) as helper,
        ):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "suite passing")
        helper.assert_awaited_once()
        moves = agent.response.compute_moves
        self.assertEqual([(move.situation, move.iteration, move.status, move.helpers) for move in moves], [(JevComputeSituation.REPEATING, 3, JevComputeMoveStatus.COMPLETED, 1)])
        self.assertEqual(moves[0].output, result.output)
        after_move = runner.messages[3]
        self.assertTrue(any(message.get("role") == "user" and result.output in str(message.get("content")) for message in after_move))
        self.assertFalse(any(result.output in str(message.get("content")) for message in runner.messages[2]))

    async def test_a_failed_helper_is_charged_and_changes_nothing_in_the_loop(self) -> None:
        agent, runner = self._agent(JevComputeSettings(situations=(JevComputeSituation.REPEATING,)))
        assert agent.compute is not None
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=_stuck_payload()))),
            patch(_HELPER, new=_jev(ScriptedJev(0.95))),
            patch.object(agent.compute.reset.helpers, "run", new=AsyncMock(return_value=None)),
        ):
            await agent.arun(REQUEST)
        self.assertEqual([(move.status, move.helpers) for move in agent.response.compute_moves], [(JevComputeMoveStatus.FAILED, 1)])
        self.assertEqual(agent.compute.budget.moves, 1)
        self.assertFalse(any(message.get("role") == "user" for call in runner.messages for message in call))

    async def test_a_blocked_move_is_recorded_without_starting_a_helper(self) -> None:
        agent, _ = self._agent(JevComputeSettings(situations=(JevComputeSituation.REPEATING,), max_moves=0))
        assert agent.compute is not None
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=_stuck_payload()))),
            patch(_HELPER, new=_jev(ScriptedJev(0.95))),
            patch.object(agent.compute.reset.helpers, "run", new=AsyncMock()) as helper,
        ):
            await agent.arun(REQUEST)
        helper.assert_not_awaited()
        self.assertEqual([(move.status, move.helpers, move.output) for move in agent.response.compute_moves], [(JevComputeMoveStatus.MOVE_LIMIT, 0, None)])

    async def test_an_unrecognized_situation_or_one_without_a_move_starts_no_helper(self) -> None:
        for yes, situations in ((0.1, (JevComputeSituation.REPEATING,)), (0.95, (JevComputeSituation.SELF_CONTAINED_STEP,))):
            agent, _ = self._agent(JevComputeSettings(situations=situations))
            assert agent.compute is not None
            payload = _stuck_payload().model_copy(update={"next_steps": [JevRunBriefQuotePayload(event="E1", quote="Get the test suite passing.")]})
            with (
                self.subTest(yes=yes, situations=situations),
                patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=payload))),
                patch(_HELPER, new=_jev(ScriptedJev(yes))),
                patch.object(agent.compute.reset.helpers, "run", new=AsyncMock()) as helper,
            ):
                await agent.arun(REQUEST)
                helper.assert_not_awaited()
                self.assertEqual(agent.response.compute_moves, [])
                self.assertEqual(len(agent.response.compute_decisions), 1)


if __name__ == "__main__":
    unittest.main()

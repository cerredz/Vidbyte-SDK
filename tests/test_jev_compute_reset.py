"""FILE: tests/test_jev_compute_reset.py

PURPOSE: Verifies the FRESH_AGENT compute move, its run-local budget and helper, and the evidence passed to and returned from that helper.
ROLE IN CODEBASE: Covers JevComputeBudget, JevComputeHelpers, JevComputeReset, controller action, and helper evidence in JevRunState.
ARCHITECTURE NOTE: Scripted runners and patched decision and brief-writer calls exercise the real checkpoint without network calls.
COMMON MODIFICATION PATTERNS: Add a focused case when helper input, budget behavior, move reporting, or evidence ordering changes.
KNOWN EDGE CASES: A failed helper is charged but does not change the main loop; recognized options without a move are recorded without action.
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
from vidbyte.agents.jev import (
    JevAgent,
    JevAgentSettings,
    JevComputeSettings,
    JevContinualSettings,
    JevRuntimeSettings,
)
from vidbyte.agents.jev.compute.budget import JevComputeBudget
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.reset import JevComputeReset
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_HELPER_REPORT_MAX_CHARS,
    JEV_COMPUTE_RESET_SOURCE,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevComputeHelperResult,
    JevContinuationEvidence,
    JevDecisionRequest,
    JevRunBrief,
    JevRunBriefAppendPayload,
    JevRunBriefNote,
    JevRunFacts,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult
from vidbyte.lib.enums import (
    AgentRuntimeType,
    DecisionModelMode,
    JevComputeMoveStatus,
    JevDoneCheck,
    JevDynamicComputeOption,
    JevQuestionType,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

REQUEST = "Get the test suite passing."
_DECISION_HELPER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "fixer", "system_prompt": "Fix the code.", "provider": "openai", "model_name": "gpt-4.1", "api_key": "main-key", "tools": (run_tests,)}
    values.update(overrides)
    return JevAgentSettings(**values)


@tool
def run_tests(path: str) -> str:
    """Run the test file at the given path and return the test output."""
    return "ImportError: No module named 'yaml'"


class BindingTool:
    """A tool double that clones itself for a new agent."""

    def __init__(self) -> None:
        self.clones = 0

    def clone_for_fork(self) -> object:
        self.clones += 1
        return run_tests


def _brief() -> JevRunBrief:
    return JevRunBrief(
        goal=REQUEST,
        notes=(JevRunBriefNote("E2", "The test command returned a missing yaml module error."),),
        iteration=3,
        through_event=3,
    )


def _facts() -> JevRunFacts:
    return JevRunFacts(iteration=3, tool_calls=2, error_streak=1, tokens_used=200)


def _events() -> JevRunEventLog:
    return JevRunEventLog.from_run(REQUEST, ["The test command returned a missing yaml module error."], [])


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
        helper = helpers.build("fresh_agent")
        self.assertEqual(helper.name, "fixer-compute-fresh_agent")
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
            result = await helpers.run("fresh_agent", "review current state", source=JEV_COMPUTE_RESET_SOURCE)
        assert result is not None
        self.assertEqual(result.output, "Cause: missing PyYAML. Added it; 3 passed.")
        self.assertEqual(result.evidence.source, JEV_COMPUTE_RESET_SOURCE)
        self.assertEqual(result.evidence.responses, ("Looking at imports.", reply.content))
        self.assertEqual(result.evidence.tool_calls, (call,))

    async def test_an_outage_or_an_empty_report_returns_none(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        for arun in (AsyncMock(side_effect=VidbyteSdkError("down")), AsyncMock(return_value=SimpleNamespace(content="   ", metadata={}))):
            with self.subTest(arun=arun), patch("vidbyte.agents.base.BaseAgent.arun", new=arun):
                self.assertIsNone(await helpers.run("fresh_agent", "review current state", source=JEV_COMPUTE_RESET_SOURCE))


class JevComputeResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_helper_receives_the_shared_verified_state(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        result = JevComputeHelperResult(output="A missing dependency caused the error.", evidence=JevContinuationEvidence(source=JEV_COMPUTE_RESET_SOURCE, responses=("report",), tool_calls=()))
        with patch.object(helpers, "run", new=AsyncMock(return_value=result)) as run:
            returned = await JevComputeReset(helpers).run(REQUEST, _brief(), _facts(), _events())
        self.assertIs(returned, result)
        prompt = run.await_args.args[1]
        self.assertIn(f"<request>\n{REQUEST}\n</request>", prompt)
        self.assertIn("<verified_run_brief>", prompt)
        self.assertIn(_brief().render(), prompt)
        self.assertIn('<exact_run_facts>\n{"error_streak": 1, "iteration": 3, "tokens_used": 200, "tool_calls": 2}\n</exact_run_facts>', prompt)
        self.assertIn("<recent_numbered_events>\nE2 ASSISTANT iteration=1: The test command returned a missing yaml module error.", prompt)
        self.assertNotIn("<approaches_already_tried>", prompt)
        self.assertNotIn("<open_errors>", prompt)
        self.assertEqual(run.await_args.kwargs["source"], JEV_COMPUTE_RESET_SOURCE)

    def test_the_main_agent_reads_a_clipped_report(self) -> None:
        reset = JevComputeReset(JevComputeHelpers(_settings(), JevComputeSettings()))
        message = reset.message("x" * (JEV_COMPUTE_HELPER_REPORT_MAX_CHARS * 2))
        self.assertIn("<helper_report>", message)
        self.assertIn("chars omitted", message)
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
    """Answer each requested sign with one P(true) and retain the question batch."""

    def __init__(self, yes: float) -> None:
        self.yes = yes
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        answers: Mapping[str, JevAnswer] = {question.name: _answer(question.name, self.yes) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 50, "output_tokens": 5})


def _scripted_helper(scripted: ScriptedJev) -> type:
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedHelper


class ScriptedRunner:
    """Main-agent runner that returns scripted tool calls and keeps each call's messages."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.messages: list[tuple[Any, ...]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.messages.append(tuple(kwargs.get("messages") or ()))
        if self.count:
            index = self.count
            self.count -= 1
            return SimpleNamespace(text="", raw={"output": [{"type": "function_call", "name": "run_tests", "arguments": json.dumps({"path": "tests"}), "call_id": f"c{index}"}]})
        return SimpleNamespace(text="suite passing", raw={"output": []})


class JevComputeControllerMoveTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, compute: JevComputeSettings, calls: int = 4) -> tuple[JevAgent, ScriptedRunner]:
        runtime = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=compute)
        runner = ScriptedRunner(calls)
        return bind_test_runner(JevAgent(_settings(), runtime), runner), runner

    async def test_fresh_agent_selection_runs_helper_and_appends_report(self) -> None:
        agent, runner = self._agent(JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.FRESH_AGENT,)))
        assert agent.compute is not None
        scripted = ScriptedJev(0.95)
        result = JevComputeHelperResult(output="The test output points to a missing dependency.", evidence=JevContinuationEvidence(source=JEV_COMPUTE_RESET_SOURCE, responses=("checked the import",), tool_calls=()))
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=JevRunBriefAppendPayload.model_validate({"notes": []})))),
            patch(_DECISION_HELPER, new=_scripted_helper(scripted)),
            patch.object(agent.compute.reset.helpers, "run", new=AsyncMock(return_value=result)) as helper,
        ):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "suite passing")
        helper.assert_awaited_once()
        move = agent.response.compute_moves[0]
        self.assertEqual((move.option, move.iteration, move.status, move.helpers), (JevDynamicComputeOption.FRESH_AGENT, 3, JevComputeMoveStatus.COMPLETED, 1))
        self.assertEqual(move.output, result.output)
        after_move = runner.messages[3]
        self.assertTrue(any(message.get("role") == "user" and result.output in str(message.get("content")) for message in after_move))
        self.assertFalse(any(result.output in str(message.get("content")) for message in runner.messages[2]))

    async def test_a_failed_helper_is_charged_but_does_not_change_the_loop(self) -> None:
        agent, runner = self._agent(JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.FRESH_AGENT,)))
        assert agent.compute is not None
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=JevRunBriefAppendPayload.model_validate({"notes": []})))),
            patch(_DECISION_HELPER, new=_scripted_helper(ScriptedJev(0.95))),
            patch.object(agent.compute.reset.helpers, "run", new=AsyncMock(return_value=None)),
        ):
            await agent.arun(REQUEST)
        self.assertEqual([(move.status, move.helpers) for move in agent.response.compute_moves], [(JevComputeMoveStatus.FAILED, 1)])
        self.assertEqual(agent.compute.budget.moves, 1)
        self.assertFalse(any(message.get("role") == "user" for call in runner.messages for message in call))

    async def test_a_blocked_move_is_recorded_without_starting_a_helper(self) -> None:
        agent, _ = self._agent(JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.FRESH_AGENT,), max_moves=0))
        assert agent.compute is not None
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=JevRunBriefAppendPayload.model_validate({"notes": []})))),
            patch(_DECISION_HELPER, new=_scripted_helper(ScriptedJev(0.95))),
            patch.object(agent.compute.reset.helpers, "run", new=AsyncMock()) as helper,
        ):
            await agent.arun(REQUEST)
        helper.assert_not_awaited()
        move = agent.response.compute_moves[0]
        self.assertEqual((move.status, move.helpers, move.output), (JevComputeMoveStatus.MOVE_LIMIT, 0, None))

    async def test_an_unrecognized_or_unimplemented_option_starts_no_helper(self) -> None:
        cases = (
            (0.1, JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.FRESH_AGENT,)), None),
            (0.95, JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.SUBAGENT,)), JevDynamicComputeOption.SUBAGENT),
        )
        for yes, compute, selected in cases:
            agent, _ = self._agent(compute)
            assert agent.compute is not None
            with (
                self.subTest(yes=yes, options=compute.dynamic_compute),
                patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=JevRunBriefAppendPayload.model_validate({"notes": []})))),
                patch(_DECISION_HELPER, new=_scripted_helper(ScriptedJev(yes))),
                patch.object(agent.compute.reset.helpers, "run", new=AsyncMock()) as helper,
            ):
                await agent.arun(REQUEST)
                helper.assert_not_awaited()
                self.assertEqual(agent.response.compute_moves, [])
                if selected is not None:
                    self.assertIs(agent.response.compute_decisions[0].option, selected)
                else:
                    self.assertIsNone(agent.response.compute_decisions[0].option)


if __name__ == "__main__":
    unittest.main()

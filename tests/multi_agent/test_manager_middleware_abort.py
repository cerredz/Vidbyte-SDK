"""Context Protocol Header

Description:
    Tests that a middleware abort on the MultiAgent manager ends the team run.
Purpose:
    A security or budget stop on the manager (an output guard, a kill switch,
    a spend ceiling) must end the run visibly: a stopped structured phase is
    never retried as a parse failure, which would pay for the same model call
    again, and a stopped final synthesis is never returned as the team's
    answer with completed=True.
Architecture:
    A real BaseAgent manager on an offline scripted runner, forked through
    manager_agent_factory so every phase fork keeps the runner, drives a
    MagenticOneOrchestrator inside a public MultiAgent run.
Relations:
    Regression tests for the @intent middleware-abort-ends-the-run sites in
    vidbyte/agents/multi/orchestrator.py, matching
    tests/test_algorithms_honor_middleware_abort.py for the single-agent algorithms.
"""

from __future__ import annotations

import json
import unittest
from functools import partial
from typing import Any

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.multi import AgentBinding, AgentTransfer, MagenticOneOrchestrator, MultiAgent
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.multi_agent import MultiAgentSettings
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import MultiAgentExecutionError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.middleware.base import AgentMiddleware

PHASE_PROMPTS = {"plan": "PHASE=plan", "progress": "PHASE=progress", "replan": "PHASE=replan", "finalize": "PHASE=finalize"}
ABORT_REASON = "output guard: secret in reply"


class ManagerRunner:
    """Offline manager model that answers each phase and counts the paid calls per phase."""

    def __init__(self, *, plan_reply: str | None = None) -> None:
        self.calls = {phase: 0 for phase in PHASE_PROMPTS}
        self.decisions = 0
        self._plan_reply = plan_reply or json.dumps({"plan_summary": "one task", "tasks": [{"task_id": "task-1", "goal": "do work", "owner": "worker"}]})

    def run(self, prompt: str, system: str = "", **_: object) -> TextModelResponse:
        phase = next(name for name, marker in PHASE_PROMPTS.items() if marker in prompt)
        self.calls[phase] += 1
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text=self._reply(phase), raw={}, usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})

    def _reply(self, phase: str) -> str:
        # Plan one task, delegate it once, then finish; the synthesis is plain text.
        if phase in ("plan", "replan"):
            return self._plan_reply
        if phase == "progress":
            self.decisions += 1
            if self.decisions == 1:
                return json.dumps({"action": "delegate", "task_id": "task-1", "owner": "worker", "instruction": "run"})
            return json.dumps({"action": "finish", "final_answer": "done", "progress_made": True})
        return "The team's answer."


class OutputGuard(AgentMiddleware):
    """Aborts the manager after the model replied (the call is already paid) for one phase."""

    def __init__(self, phase: str | None) -> None:
        self.phase = phase

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if self.phase is not None and PHASE_PROMPTS[self.phase] in ctx.message:
            return MiddlewareDecision.abort(ABORT_REASON)
        return MiddlewareDecision.continue_()


class StaticWorker(BaseAgent):
    """Provider-free worker that completes its task with a fixed reply."""

    def __init__(self) -> None:
        super().__init__(name="worker", system_prompt="work")

    def fork(self, settings: AgentForkSettings | None = None) -> "StaticWorker":
        return StaticWorker()

    async def generate_reply(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        return AgentMessage(sender=self.name, recipient="team", content="worker output")


def _fork_manager(runner: ManagerRunner, source: BaseAgent, phase: str, settings: AgentForkSettings) -> BaseAgent:
    # Every run and phase fork keeps the offline manager runner and the guard middleware.
    return bind_test_runner(source.fork(settings), runner)


def _team(runner: ManagerRunner, *, abort_phase: str | None, parse_retries: int = 2) -> MultiAgent:
    # A public team whose real manager agent carries the output guard for one phase; one
    # iteration makes each phase attempt exactly one model call, so calls count attempts.
    manager = bind_test_runner(BaseAgent(name="manager", system_prompt="manage", provider="openai", model_name="gpt-5.4-mini", middleware=(OutputGuard(abort_phase),), max_iterations=1), runner)
    orchestrator = MagenticOneOrchestrator(manager, planning_prompt=PHASE_PROMPTS["plan"], progress_prompt=PHASE_PROMPTS["progress"], replanning_prompt=PHASE_PROMPTS["replan"], final_prompt=PHASE_PROMPTS["finalize"], parse_retries=parse_retries, manager_agent_factory=partial(_fork_manager, runner))
    return MultiAgent(name="team", system_prompt="coordinate", orchestrator=orchestrator, agents=(AgentBinding(StaticWorker(), transfer=AgentTransfer()),), settings=MultiAgentSettings(max_rounds=4))


class ManagerMiddlewareAbortTests(unittest.IsolatedAsyncioTestCase):
    """A manager stopped by its own middleware ends the team run."""

    async def test_completes_normally_without_an_abort(self) -> None:
        # [Control] The harness itself runs a full plan, delegate, finish and synthesis.
        runner = ManagerRunner()
        team = _team(runner, abort_phase=None)

        reply = await team.generate_reply("complete the task")

        self.assertEqual(reply.content, "The team's answer.")
        result = team.last_result
        assert result is not None
        self.assertTrue(result.completed)
        self.assertEqual(runner.calls, {"plan": 1, "progress": 2, "replan": 0, "finalize": 1})

    async def test_aborted_structured_phase_is_not_retried_as_a_parse_failure(self) -> None:
        # [Hidden Failure] An abort after the model call is one paid call; a retry would pay for it again.
        runner = ManagerRunner()
        team = _team(runner, abort_phase="plan", parse_retries=2)

        with self.assertRaises(MultiAgentExecutionError) as caught:
            await team.generate_reply("complete the task")

        self.assertEqual(runner.calls["plan"], 1)
        self.assertIn("stopped by middleware", str(caught.exception))
        self.assertNotIn("parse retries", str(caught.exception))
        self.assertEqual(caught.exception.details["phase"], "plan")
        self.assertEqual(caught.exception.details["attempts"], 1)
        self.assertEqual(getattr(caught.exception.__cause__, "stop_reason", None), "middleware_abort")
        self.assertEqual(runner.calls["progress"], 0)

    async def test_aborted_final_synthesis_is_not_returned_as_the_answer(self) -> None:
        # [Silent Failure] The SDK's stop text must not become the team's answer with completed=True.
        runner = ManagerRunner()
        team = _team(runner, abort_phase="finalize")

        with self.assertRaises(MultiAgentExecutionError) as caught:
            await team.generate_reply("complete the task")

        self.assertIn("stopped by middleware", str(caught.exception))
        self.assertEqual(caught.exception.details["phase"], "finalize")
        self.assertEqual(runner.calls["finalize"], 1)
        result = team.last_result
        self.assertFalse(result is not None and result.completed)

    async def test_unparseable_phase_reply_is_still_retried(self) -> None:
        # [Control] An ordinary invalid plan is a parse failure and keeps its bounded retries.
        runner = ManagerRunner(plan_reply="not a plan")
        team = _team(runner, abort_phase=None, parse_retries=2)

        with self.assertRaises(MultiAgentExecutionError) as caught:
            await team.generate_reply("complete the task")

        self.assertEqual(runner.calls["plan"], 3)
        self.assertIn("bounded parse retries", str(caught.exception))
        self.assertEqual(caught.exception.details["attempts"], 3)


if __name__ == "__main__":
    unittest.main()

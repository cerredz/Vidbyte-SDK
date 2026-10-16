"""FILE: tests/multi_agent/test_manager_phase_conversion_retry.py

PURPOSE:
    Proves that a manager reply whose fields contradict its action is retried
    within the manager's parse-retry budget instead of ending the team run.
    The provider-facing phase schemas allow every field for every action, so a
    finish that echoes a task id, a delegate that carries an empty final
    answer, or a plan with a blank task goal parses cleanly and is only
    rejected when it becomes a public OrchestratorDecision or OrchestratorPlan.
    That rejection is an invalid manager reply like any other and must be
    retried, and an exhausted budget must fail as a bounded-parse-retry error.
ROLE IN CODEBASE:
    Regression tests for MagenticOneOrchestrator._structured_phase in
    vidbyte/agents/multi/orchestrator.py, which converts each parsed phase
    reply to its public contract inside the retry loop.
ARCHITECTURE NOTE:
    A real BaseAgent manager on an offline scripted text runner, forked through
    manager_agent_factory so every run and phase fork keeps the runner, drives
    a MagenticOneOrchestrator inside a public MultiAgent run. Custom phase
    prompts let the runner tell the phases apart; max_iterations=1 makes each
    phase attempt exactly one model call, so call counts equal attempts.
COMMON MODIFICATION PATTERNS:
    Add a scenario by scripting the plan or progress replies passed to
    ManagerRunner; the last scripted reply for a phase repeats once used up.
KNOWN EDGE CASES:
    A middleware-aborted phase is still not retried; that control lives in
    tests/multi_agent/test_manager_middleware_abort.py.
RELATED DOCS:
    vidbyte/agents/multi/README.md
TESTS:
    python -m pytest tests/multi_agent/test_manager_phase_conversion_retry.py
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
from vidbyte.lib.dataclasses.multi_agent import MultiAgentSettings
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import MultiAgentExecutionError
from vidbyte.lib.runners import TextModelResponse

PHASE_PROMPTS = {"plan": "PHASE=plan", "progress": "PHASE=progress", "replan": "PHASE=replan", "finalize": "PHASE=finalize"}
RETRY_SUFFIX = "Your prior response was invalid"
VALID_PLAN = json.dumps({"plan_summary": "one task", "tasks": [{"task_id": "task-1", "goal": "do work", "owner": "worker"}]})
BLANK_GOAL_PLAN = json.dumps({"plan_summary": "one task", "tasks": [{"task_id": "task-1", "goal": "   ", "owner": "worker"}]})
DELEGATE = json.dumps({"action": "delegate", "task_id": "task-1", "owner": "worker", "instruction": "run"})
DELEGATE_WITH_EMPTY_ANSWER = json.dumps({"action": "delegate", "task_id": "task-1", "owner": "worker", "instruction": "run", "final_answer": ""})
FINISH = json.dumps({"action": "finish", "final_answer": "done", "progress_made": True})
FINISH_ECHOING_TASK = json.dumps({"action": "finish", "task_id": "task-1", "final_answer": "done", "progress_made": True})


class ManagerRunner:
    """Offline manager model that plays scripted replies per phase and records every paid prompt."""

    def __init__(self, *, plan: tuple[str, ...] = (VALID_PLAN,), progress: tuple[str, ...] = (DELEGATE, FINISH)) -> None:
        self.prompts: dict[str, list[str]] = {phase: [] for phase in PHASE_PROMPTS}
        self._scripts = {"plan": plan, "replan": plan, "progress": progress}

    @property
    def calls(self) -> dict[str, int]:
        return {phase: len(prompts) for phase, prompts in self.prompts.items()}

    def run(self, prompt: str, system: str = "", **_: object) -> TextModelResponse:
        phase = next(name for name, marker in PHASE_PROMPTS.items() if marker in prompt)
        self.prompts[phase].append(prompt)
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text=self._reply(phase), raw={}, usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})

    def _reply(self, phase: str) -> str:
        # Each structured phase plays its script in order and repeats the last reply; the synthesis is plain text.
        script = self._scripts.get(phase)
        if script is None:
            return "The team's answer."
        return script[min(len(self.prompts[phase]), len(script)) - 1]


class StaticWorker(BaseAgent):
    """Provider-free worker that completes its task with a fixed reply and records each invocation."""

    def __init__(self, invocations: list[str]) -> None:
        super().__init__(name="worker", system_prompt="work")
        self.invocations = invocations

    def fork(self, settings: AgentForkSettings | None = None) -> "StaticWorker":
        return StaticWorker(self.invocations)

    async def generate_reply(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        self.invocations.append(str(message))
        return AgentMessage(sender=self.name, recipient="team", content="worker output")


def _fork_manager(runner: ManagerRunner, source: BaseAgent, phase: str, settings: AgentForkSettings) -> BaseAgent:
    # Every run and phase fork keeps the offline manager runner.
    return bind_test_runner(source.fork(settings), runner)


def _team(runner: ManagerRunner, invocations: list[str], *, parse_retries: int = 2) -> MultiAgent:
    # A public team whose real manager agent makes exactly one model call per phase attempt.
    manager = bind_test_runner(BaseAgent(name="manager", system_prompt="manage", provider="openai", model_name="gpt-5.4-mini", max_iterations=1), runner)
    orchestrator = MagenticOneOrchestrator(manager, planning_prompt=PHASE_PROMPTS["plan"], progress_prompt=PHASE_PROMPTS["progress"], replanning_prompt=PHASE_PROMPTS["replan"], final_prompt=PHASE_PROMPTS["finalize"], parse_retries=parse_retries, manager_agent_factory=partial(_fork_manager, runner))
    return MultiAgent(name="team", system_prompt="coordinate", orchestrator=orchestrator, agents=(AgentBinding(StaticWorker(invocations), transfer=AgentTransfer()),), settings=MultiAgentSettings(max_rounds=4))


class ManagerPhaseConversionRetryTests(unittest.IsolatedAsyncioTestCase):
    """A manager reply that parses but contradicts its own action is retried, not run-ending."""

    async def test_finish_that_echoes_a_task_id_is_retried_and_the_team_completes(self) -> None:
        # [Hidden Failure] A finish carrying the task it closes is a manager slip the retry budget must absorb.
        runner = ManagerRunner(progress=(DELEGATE, FINISH_ECHOING_TASK, FINISH))
        invocations: list[str] = []
        team = _team(runner, invocations)

        reply = await team.generate_reply("complete the task")

        self.assertEqual(reply.content, "The team's answer.")
        result = team.last_result
        assert result is not None
        self.assertTrue(result.completed)
        self.assertEqual(runner.calls, {"plan": 1, "progress": 3, "replan": 0, "finalize": 1})
        self.assertNotIn(RETRY_SUFFIX, runner.prompts["progress"][1])
        self.assertIn(RETRY_SUFFIX, runner.prompts["progress"][2])
        self.assertEqual(len(invocations), 1)

    async def test_delegate_with_an_empty_final_answer_is_retried_and_the_team_completes(self) -> None:
        # [Hidden Failure] An empty final_answer on a delegate is rejected by the public contract and retried.
        runner = ManagerRunner(progress=(DELEGATE_WITH_EMPTY_ANSWER, DELEGATE, FINISH))
        invocations: list[str] = []
        team = _team(runner, invocations)

        reply = await team.generate_reply("complete the task")

        self.assertEqual(reply.content, "The team's answer.")
        result = team.last_result
        assert result is not None
        self.assertTrue(result.completed)
        self.assertEqual(runner.calls, {"plan": 1, "progress": 3, "replan": 0, "finalize": 1})
        self.assertIn(RETRY_SUFFIX, runner.prompts["progress"][1])
        self.assertEqual(len(invocations), 1)

    async def test_plan_with_a_blank_task_goal_is_retried_and_the_next_plan_is_used(self) -> None:
        # [Hidden Failure] A blank goal parses under the provider schema but is not a valid TaskSpec.
        runner = ManagerRunner(plan=(BLANK_GOAL_PLAN, VALID_PLAN))
        invocations: list[str] = []
        team = _team(runner, invocations)

        reply = await team.generate_reply("complete the task")

        self.assertEqual(reply.content, "The team's answer.")
        result = team.last_result
        assert result is not None
        self.assertTrue(result.completed)
        self.assertEqual(runner.calls, {"plan": 2, "progress": 2, "replan": 0, "finalize": 1})
        self.assertIn(RETRY_SUFFIX, runner.prompts["plan"][1])
        self.assertEqual(len(invocations), 1)

    async def test_contradictory_reply_on_every_attempt_exhausts_the_bounded_parse_retries(self) -> None:
        # [Boundary] The budget is parse_retries + 1 attempts, then the existing bounded-retry error, not a bare ValueError.
        runner = ManagerRunner(progress=(FINISH_ECHOING_TASK,))
        invocations: list[str] = []
        team = _team(runner, invocations, parse_retries=1)

        with self.assertRaises(MultiAgentExecutionError) as caught:
            await team.generate_reply("complete the task")

        self.assertIn("bounded parse retries", str(caught.exception))
        self.assertEqual(caught.exception.details["phase"], "progress")
        self.assertEqual(caught.exception.details["attempts"], 2)
        self.assertEqual(caught.exception.details["error_type"], "ValueError")
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertEqual(runner.calls["progress"], 2)
        self.assertEqual(invocations, [])


if __name__ == "__main__":
    unittest.main()

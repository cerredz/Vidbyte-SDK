"""FILE: tests/multi_agent/test_manager_middleware_abort.py

PURPOSE:
    Proves that a middleware abort on the MultiAgent manager ends the team run.
    A security or budget stop on the manager (an output guard, a kill switch,
    a spend ceiling) must end the run visibly: a stopped structured phase is
    never retried as a parse failure, which would pay for the same model call
    again, and a stopped final synthesis is never returned as the team's
    answer with completed=True. A synthesis stopped by the manager's own
    budget or guard (max_iterations, a tool-settings denial, an unmet output
    contract) ends the run the same way.
ROLE IN CODEBASE:
    Regression tests for the @intent middleware-abort-ends-the-run sites in
    vidbyte/agents/multi/orchestrator.py (MagenticOneOrchestrator._structured_phase
    and MagenticOneOrchestrator.finalize), and for the
    @intent a-stopped-synthesis-is-not-an-answer site in finalize.
ARCHITECTURE NOTE:
    A real BaseAgent manager on an offline scripted text runner, forked through
    manager_agent_factory so every run and phase fork keeps the runner and the
    guard middleware, drives a MagenticOneOrchestrator inside a public
    MultiAgent run. Custom phase prompts let the runner and the guard tell the
    phases apart; max_iterations=1 makes each phase attempt one model call, so a
    synthesis whose model calls a tool stops on max_iterations. Stops the offline
    runner cannot reach come from ScriptedSynthesisManager, a run manager whose
    synthesis reply carries one runtime stop_reason.
COMMON MODIFICATION PATTERNS:
    Add a phase scenario by adding its marker to PHASE_PROMPTS and its reply to
    ManagerRunner._reply, then pass that phase as abort_phase to _team.
KNOWN EDGE CASES:
    The guard aborts in after_model_response, so the aborted call was already
    made and is counted; an ordinary unparseable reply must still be retried.
RELATED DOCS:
    vidbyte/agents/multi/README.md
TESTS:
    python -m pytest tests/multi_agent/test_manager_middleware_abort.py; the
    single-agent counterpart is tests/test_algorithms_honor_middleware_abort.py.
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
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentStopReason
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.multi_agent import MultiAgentSettings
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import MultiAgentExecutionError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.tools import tool

PHASE_PROMPTS = {"plan": "PHASE=plan", "progress": "PHASE=progress", "replan": "PHASE=replan", "finalize": "PHASE=finalize"}
ABORT_REASON = "output guard: secret in reply"
STOP_NOTICE = "Agent runtime stopped after reaching max_iterations."
# The only stops that end a run with an answer; every other runtime stop leaves a notice or a rejected draft.
ANSWER_STOPS = (AgentStopReason.FINAL_RESPONSE.value, AgentStopReason.IS_DONE.value, None)
NON_ANSWER_STOPS = tuple(reason.value for reason in AgentStopReason if reason.value not in ANSWER_STOPS and reason is not AgentStopReason.MIDDLEWARE_ABORT)


@tool
def cite_source(claim: str) -> str:
    """Find a citation for a claim."""
    return f"source for {claim}"


class ManagerRunner:
    """Offline manager model that answers each phase and counts the paid calls per phase."""

    def __init__(self, *, plan_reply: str | None = None, synthesis_calls_tool: bool = False) -> None:
        self.calls = {phase: 0 for phase in PHASE_PROMPTS}
        self.decisions = 0
        self._plan_reply = plan_reply or json.dumps({"plan_summary": "one task", "tasks": [{"task_id": "task-1", "goal": "do work", "owner": "worker"}]})
        self._synthesis_calls_tool = synthesis_calls_tool

    def run(self, prompt: str, system: str = "", **_: object) -> TextModelResponse:
        phase = next(name for name, marker in PHASE_PROMPTS.items() if marker in prompt)
        self.calls[phase] += 1
        if phase == "finalize" and self._synthesis_calls_tool:
            # The synthesis keeps calling a tool instead of answering, so the manager's loop budget ends it.
            call = {"type": "function_call", "name": "cite_source", "arguments": json.dumps({"claim": "done"})}
            return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text="", raw={"output": [call]})
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


class ScriptedSynthesisManager(BaseAgent):
    """Provider-free run manager that answers the final synthesis with one fixed reply."""

    def __init__(self, synthesis: AgentMessage) -> None:
        super().__init__(name="manager", system_prompt="manage")
        self.synthesis = synthesis

    async def generate_reply(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        return self.synthesis


def _synthesis(content: str, stop_reason: str | None) -> AgentMessage:
    # The reply shape AgentRuntime returns: the text plus the stop_reason that ended the run, when one is set.
    metadata = {} if stop_reason is None else {"stop_reason": stop_reason}
    return AgentMessage(sender="manager", recipient="team", content=content, metadata=metadata)


def _fork_manager(runner: ManagerRunner, source: BaseAgent, phase: str, settings: AgentForkSettings) -> BaseAgent:
    # Every run and phase fork keeps the offline manager runner and the guard middleware.
    return bind_test_runner(source.fork(settings), runner)


def _fork_scripted_synthesis(runner: ManagerRunner, template: BaseAgent, synthesis: AgentMessage, source: BaseAgent, phase: str, settings: AgentForkSettings) -> BaseAgent:
    # Structured phases fork the real manager; only the run manager, which writes the synthesis, is scripted.
    if phase == "run":
        return ScriptedSynthesisManager(synthesis)
    return bind_test_runner(template.fork(settings), runner)


def _team(runner: ManagerRunner, *, abort_phase: str | None, parse_retries: int = 2, synthesis: AgentMessage | None = None) -> MultiAgent:
    # A public team whose real manager agent carries the output guard for one phase; one
    # iteration makes each phase attempt exactly one model call, so calls count attempts.
    manager = bind_test_runner(BaseAgent(name="manager", system_prompt="manage", provider="openai", model_name="gpt-5.4-mini", tools=(cite_source,), middleware=(OutputGuard(abort_phase),), max_iterations=1), runner)
    factory = partial(_fork_manager, runner) if synthesis is None else partial(_fork_scripted_synthesis, runner, manager, synthesis)
    orchestrator = MagenticOneOrchestrator(manager, planning_prompt=PHASE_PROMPTS["plan"], progress_prompt=PHASE_PROMPTS["progress"], replanning_prompt=PHASE_PROMPTS["replan"], final_prompt=PHASE_PROMPTS["finalize"], parse_retries=parse_retries, manager_agent_factory=factory)
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

    async def test_budget_stopped_final_synthesis_is_not_returned_as_the_answer(self) -> None:
        # [Silent Failure] A synthesis that keeps calling a tool stops on max_iterations; its notice is not an answer.
        runner = ManagerRunner(synthesis_calls_tool=True)
        team = _team(runner, abort_phase=None)

        with self.assertRaises(MultiAgentExecutionError) as caught:
            await team.generate_reply("complete the task")

        self.assertIn("stopped before it answered", str(caught.exception))
        self.assertEqual(caught.exception.details, {"phase": "finalize", "stop_reason": "max_iterations"})
        self.assertEqual(runner.calls["finalize"], 1)
        result = team.last_result
        self.assertFalse(result is not None and result.completed)

    async def test_every_non_answer_synthesis_stop_ends_the_run(self) -> None:
        # [Silent Failure] Budgets, tool-settings guards and unmet output contracts all leave a non-answer.
        for stop_reason in NON_ANSWER_STOPS:
            with self.subTest(stop_reason=stop_reason):
                team = _team(ManagerRunner(), abort_phase=None, synthesis=_synthesis(STOP_NOTICE, stop_reason))

                with self.assertRaises(MultiAgentExecutionError) as caught:
                    await team.generate_reply("complete the task")

                self.assertEqual(caught.exception.details, {"phase": "finalize", "stop_reason": stop_reason})
                result = team.last_result
                self.assertFalse(result is not None and result.completed)

    async def test_answered_synthesis_is_returned_for_every_answer_stop(self) -> None:
        # [Control] A final response, an isDone answer, or a reply with no stop_reason is still the team's answer.
        for stop_reason in ANSWER_STOPS:
            with self.subTest(stop_reason=stop_reason):
                team = _team(ManagerRunner(), abort_phase=None, synthesis=_synthesis("The team's answer.", stop_reason))

                reply = await team.generate_reply("complete the task")

                self.assertEqual(reply.content, "The team's answer.")
                result = team.last_result
                assert result is not None
                self.assertTrue(result.completed)

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

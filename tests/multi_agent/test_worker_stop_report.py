"""FILE: tests/multi_agent/test_worker_stop_report.py

PURPOSE:
    Proves that a worker whose run stopped on its own budget or guard is
    recorded as a failed attempt, not a completed task. A worker that hits
    max_iterations, max_tool_calls, its timeout, or an unmet output contract
    ends with the SDK's stop notice ("Agent runtime stopped after reaching
    max_iterations."), not an answer, so the notice must never become the
    task's result and the team must not finish with completed=True on it.
ROLE IN CODEBASE:
    Regression tests for the @intent limit-stops-are-failed-attempts site in
    vidbyte/agents/multi/transfer.py (AgentTransfer.default_report_parser),
    which reuses OUTPUT_DELIVERABLE_STOP_REASONS from
    vidbyte/lib/constants/outputs.py as the one definition of an accepted answer.
ARCHITECTURE NOTE:
    The unit tests call the default parser directly on reply shapes AgentRuntime
    returns. The team tests drive a public MultiAgent run with a scripted
    orchestrator and a real BaseAgent worker on an offline runner whose model
    keeps calling a tool, so the worker's own max_iterations ends its run.
COMMON MODIFICATION PATTERNS:
    Add a stop reason to STOPPED_REPLIES when the runtime gains a new budget or
    guard; add a reply shape to the control test when a new accepted stop exists.
KNOWN EDGE CASES:
    A reply with no stop_reason (a custom or compound worker that sets none)
    keeps the plain completed outcome; a middleware abort stays BLOCKED and
    non-retryable rather than becoming a retryable failure.
RELATED DOCS:
    vidbyte/agents/multi/README.md
TESTS:
    python -m pytest tests/multi_agent/test_worker_stop_report.py; the middleware
    abort counterparts are in tests/multi_agent/test_behavior.py.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from functools import partial
from typing import Any

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.multi import AgentBinding, AgentTransfer, MultiAgent
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, MultiAgentSettings, OrchestrationContext, OrchestratorDecision, OrchestratorPlan, TaskBlocker, TaskLedgerSnapshot, TaskSpec
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools import tool

# The replies AgentRuntime returns when a run ends on a budget or guard: the SDK's notice, or the
# model's last draft after its output contract retries ran out. Neither is an accepted answer.
STOPPED_REPLIES = {
    "max_iterations": "Agent runtime stopped after reaching max_iterations.",
    "max_tool_calls": "Agent runtime stopped after reaching max_tool_calls.",
    "timeout": "Agent runtime stopped after reaching timeout_seconds.",
    "contract_unsatisfied": "EMEA churn is probably about 7%.",
}
_DISPATCH = AgentDispatch(run_id="run", base_revision=0, task_id="task-1", owner="worker", goal="goal", instruction="run")
_LEDGER = TaskLedgerSnapshot(run_id="run", goal="goal")
_DELEGATE = OrchestratorDecision(action=OrchestratorAction.DELEGATE, task_id="task-1", owner="worker", instruction="Measure EMEA churn.")
_FINISH = OrchestratorDecision(action=OrchestratorAction.FINISH, final_answer="EMEA churn is 7%.")


@tool
def lookup_churn(region: str) -> str:
    """Look up the churn rate of a region."""
    return f"{region} churn is 7%"


class ToolLoopRunner:
    """Offline worker model that calls lookup_churn a set number of times, then answers with isDone."""

    def __init__(self, lookups_before_answer: int) -> None:
        self.lookups_before_answer = lookups_before_answer
        self.calls = 0

    def run(self, prompt: str, system: str = "", **_: object) -> TextModelResponse:
        self.calls += 1
        if self.calls <= self.lookups_before_answer:
            call = {"type": "function_call", "name": "lookup_churn", "arguments": json.dumps({"region": "EMEA"})}
        else:
            call = {"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": "EMEA churn is 7% (dashboard)."})}
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text="", raw={"output": [call]})


class ScriptedOrchestrator:
    """Run-local orchestrator that plans one task and returns a fixed decision sequence."""

    def __init__(self, decisions: Sequence[OrchestratorDecision]) -> None:
        self._decisions = list(decisions)

    def fork(self) -> "ScriptedOrchestrator":
        return ScriptedOrchestrator(tuple(self._decisions))

    async def plan(self, context: OrchestrationContext) -> OrchestratorPlan:
        return OrchestratorPlan(plan_summary="measure churn", tasks=(TaskSpec(task_id="task-1", goal="measure EMEA churn", owner="worker"),))

    async def decide(self, context: OrchestrationContext) -> OrchestratorDecision:
        return self._decisions.pop(0)

    async def replan(self, context: OrchestrationContext) -> OrchestratorPlan:
        return await self.plan(context)

    async def finalize(self, context: Any) -> str:
        return "EMEA churn is 7%."

    async def aclose(self) -> None:
        return None


def _reply(content: str, metadata: dict[str, Any] | None = None) -> AgentMessage:
    return AgentMessage(sender="worker", recipient="team", content=content, metadata=metadata or {})


def _fork_worker(runner: ToolLoopRunner, source: BaseAgent, settings: AgentForkSettings) -> BaseAgent:
    # Every run-local worker fork keeps the offline runner and the template's own loop budget.
    return bind_test_runner(source.fork(settings), runner)


def _team(runner: ToolLoopRunner, decisions: Sequence[OrchestratorDecision], *, max_iterations: int, max_task_attempts: int = 3) -> MultiAgent:
    # A real BaseAgent worker on the offline runner, so its own max_iterations ends its run.
    worker = BaseAgent(name="worker", system_prompt="Research with tools.", provider="openai", model_name="gpt-5.4-mini", tools=[lookup_churn], max_iterations=max_iterations)
    binding = AgentBinding(worker, transfer=AgentTransfer(), fork_factory=partial(_fork_worker, runner))
    settings = MultiAgentSettings(max_rounds=len(decisions), max_replans=0, max_task_attempts=max_task_attempts)
    return MultiAgent(name="team", system_prompt="coordinate", orchestrator=ScriptedOrchestrator(decisions), agents=(binding,), settings=settings)


class DefaultReportParserStopTests(unittest.TestCase):
    """The default parser reports a limit-stopped worker run as a failed attempt."""

    def test_limit_stopped_reply_is_a_retryable_failure(self) -> None:
        # [Silent Failure] The SDK's stop notice is not output, so it is never reported as a completed result.
        for stop_reason, content in STOPPED_REPLIES.items():
            with self.subTest(stop_reason=stop_reason):
                reply = _reply(content, {"stop_reason": stop_reason})

                report = AgentTransfer.default_report_parser(reply, _DISPATCH, _LEDGER)

                self.assertEqual(report.status, TaskStatus.FAILED)
                self.assertIsNone(report.result)
                self.assertEqual(report.evidence, ())
                self.assertEqual(report.blockers, (TaskBlocker(code="worker_stopped", message=f"Worker run stopped before answering: {stop_reason}", retryable=True, metadata={"stop_reason": stop_reason}),))

    def test_accepted_and_unmarked_replies_still_complete_and_abort_still_blocks(self) -> None:
        # [Control] final_response, is_done, and a reply with no stop_reason keep completing; middleware_abort stays blocked.
        for metadata in ({"stop_reason": "final_response"}, {"stop_reason": "is_done"}, {}):
            with self.subTest(metadata=metadata):
                report = AgentTransfer.default_report_parser(_reply("EMEA churn is 7%.", metadata), _DISPATCH, _LEDGER)

                self.assertEqual(report.status, TaskStatus.COMPLETED)
                self.assertEqual(report.result, "EMEA churn is 7%.")
                self.assertEqual([(item.value, item.verified) for item in report.evidence], [("EMEA churn is 7%.", False)])
                self.assertEqual(report.blockers, ())
        aborted = AgentTransfer.default_report_parser(_reply("Agent runtime stopped by middleware: kill_switch", {"stop_reason": "middleware_abort", "middleware_abort_reason": "kill_switch"}), _DISPATCH, _LEDGER)

        self.assertEqual(aborted.status, TaskStatus.BLOCKED)
        self.assertEqual([(item.code, item.retryable) for item in aborted.blockers], [("middleware_abort", False)])


class WorkerLimitStopTeamTests(unittest.IsolatedAsyncioTestCase):
    """A team does not finish on a worker that ran out of budget before answering."""

    async def test_worker_that_answers_completes_its_task(self) -> None:
        # [Control] The harness itself delegates, lets the worker answer, and finishes completed.
        runner = ToolLoopRunner(lookups_before_answer=1)
        team = _team(runner, (_DELEGATE, _FINISH), max_iterations=6)

        await team.generate_reply("What is EMEA churn?")

        result = team.last_result
        assert result is not None
        task = result.ledger.tasks[0]
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.result, "EMEA churn is 7% (dashboard).")
        self.assertTrue(result.completed)
        self.assertEqual(result.stop_reason, MultiAgentStopReason.COMPLETED)

    async def test_worker_stopped_by_max_iterations_does_not_complete_its_task(self) -> None:
        # [Silent Failure] The stop notice must not become the task result, and the team must not report completed=True.
        runner = ToolLoopRunner(lookups_before_answer=99)
        team = _team(runner, (_DELEGATE, _FINISH, _FINISH), max_iterations=2)

        await team.generate_reply("What is EMEA churn?")

        result = team.last_result
        assert result is not None
        task = result.ledger.tasks[0]
        self.assertEqual(runner.calls, 2)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIsNone(task.result)
        self.assertEqual([(item.code, item.retryable, dict(item.metadata)) for item in task.blockers], [("worker_stopped", True, {"stop_reason": "max_iterations"})])
        self.assertFalse(result.completed)
        # The failed dispatch and the two rejected finishes are three stalls; since #1122 that triggers a replan, and none are allowed.
        self.assertEqual(result.stop_reason, MultiAgentStopReason.MAX_REPLANS)

    async def test_repeated_limit_stops_end_in_blocked_after_max_attempts(self) -> None:
        # [Edge Case] The failure is retryable, but the ledger still bounds re-dispatches by max_task_attempts.
        runner = ToolLoopRunner(lookups_before_answer=99)
        team = _team(runner, (_DELEGATE, _DELEGATE, _FINISH), max_iterations=2, max_task_attempts=2)

        await team.generate_reply("What is EMEA churn?")

        result = team.last_result
        assert result is not None
        task = result.ledger.tasks[0]
        self.assertEqual(task.attempts, 2)
        self.assertEqual(task.status, TaskStatus.BLOCKED)
        self.assertIsNone(task.result)
        self.assertFalse(result.completed)


if __name__ == "__main__":
    unittest.main()

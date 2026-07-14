"""Context Protocol Header

Description:
    Tests multi-agent dispatch, containment, context rendering, and finalization.
Purpose:
    Protects the linear transfer boundary and context-layer ownership introduced
    while resolving PR review comments.
Architecture:
    Provider-free worker and orchestrator fakes drive public MultiAgent runs.
Relations:
    Exercises vidbyte.agents.multi and vidbyte.context.MultiAgentContext.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.multi import AgentBinding, AgentTransfer, MultiAgent
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context.multi_agent import MultiAgentContext
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, MultiAgentSettings, OrchestrationContext, OrchestratorDecision, OrchestratorPlan, TaskEvidence, TaskLedgerSnapshot, TaskSpec
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus
from vidbyte.lib.errors import AgentTransferError


class ScriptedWorker(BaseAgent):
    """Isolated BaseAgent worker that records invocation and cleanup events."""

    def __init__(self, events: list[str], *, name: str = "worker", content: str = "worker output") -> None:
        super().__init__(name=name, system_prompt="work")
        self._events = events
        self._content = content

    def fork(self, settings: AgentForkSettings | None = None) -> "ScriptedWorker":
        # Run isolation returns a distinct worker while sharing only the test event sink.
        return ScriptedWorker(self._events, name=self.name, content=self._content)

    async def generate_reply(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        # Record the exact protocol position before returning a deterministic reply.
        self._events.append("worker.generate_reply")
        return AgentMessage(sender=self.name, recipient="team", content=self._content)

    async def close_mcp_servers(self) -> None:
        # Cleanup observability confirms the run-local fork was closed.
        self._events.append("worker.close")


class ScriptedOrchestrator:
    """Run-local orchestrator that returns a fixed plan and decision sequence."""

    def __init__(self, decisions: Sequence[OrchestratorDecision], *, final_content: str = "final answer") -> None:
        self._decisions = list(decisions)
        self._final_content = final_content
        self.closed = False

    def fork(self) -> "ScriptedOrchestrator":
        # Each facade invocation consumes its own decision list.
        return ScriptedOrchestrator(tuple(self._decisions), final_content=self._final_content)

    async def plan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # The single task is sufficient to exercise the complete dispatch boundary.
        return OrchestratorPlan(plan_summary="one task", tasks=(TaskSpec(task_id="task-1", goal="do work", owner="worker"),))

    async def decide(self, context: OrchestrationContext) -> OrchestratorDecision:
        # Tests provide enough decisions for the configured finite round budget.
        return self._decisions.pop(0)

    async def replan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Replan preserves the task identity for protocol completeness.
        return await self.plan(context)

    async def finalize(self, context: Any) -> str:
        # Finalization output remains deterministic across stop reasons.
        return self._final_content

    async def aclose(self) -> None:
        # The run-local orchestrator participates in lifecycle cleanup.
        self.closed = True


class MultiAgentBehaviorTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end behavior checks around the decomposed runtime."""

    async def test_dispatch_boundary_runs_in_documented_order(self) -> None:
        # [Hidden Failure] Approval/build/invoke/parse/validate/commit must stay sequential.
        events: list[str] = []

        def before_dispatch(*_: Any) -> None:
            events.append("before_dispatch")
            return None

        def request_builder(*_: Any) -> str:
            events.append("request_builder")
            return "assignment"

        def report_parser(reply: AgentMessage, dispatch: Any, ledger: Any) -> AgentReport:
            events.append("report_parser")
            evidence = TaskEvidence(source="worker", value=reply.content)
            return AgentReport(task_id=dispatch.task_id, status=TaskStatus.COMPLETED, result=reply.content, evidence=(evidence,))

        def report_validator(report: AgentReport, *_: Any) -> AgentReport:
            events.append("report_validator")
            return report

        async def on_event(event: Any, snapshot: Any) -> None:
            if event.kind == "task_reported":
                events.append("ledger.apply_report")

        transfer = AgentTransfer(before_dispatch=before_dispatch, request_builder=request_builder, report_parser=report_parser, report_validator=report_validator)
        team = self._team(events, transfer=transfer, on_event=on_event)
        reply = await team.generate_reply("complete the task")

        expected = ["before_dispatch", "request_builder", "worker.generate_reply", "report_parser", "report_validator", "ledger.apply_report"]
        self.assertEqual([event for event in events if event in expected], expected)
        self.assertEqual(reply.content, "final answer")
        result = team.last_result
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.stop_reason, MultiAgentStopReason.COMPLETED)
        self.assertIn("worker.close", events)

    async def test_builder_failure_closes_in_progress_ledger_attempt(self) -> None:
        # [Hidden Failure] An ordinary transfer exception cannot strand IN_PROGRESS state.
        events: list[str] = []

        def broken_builder(*_: Any) -> str:
            raise RuntimeError("unsafe detail")

        decision = OrchestratorDecision(action=OrchestratorAction.DELEGATE, task_id="task-1", owner="worker", instruction="run")
        team = self._team(events, transfer=AgentTransfer(request_builder=broken_builder), decisions=(decision,), settings=MultiAgentSettings(max_rounds=1))
        reply = await team.generate_reply("complete the task")

        self.assertEqual(reply.content, "final answer")
        result = team.last_result
        ledger = team.last_ledger
        self.assertIsNotNone(result)
        self.assertIsNotNone(ledger)
        assert result is not None and ledger is not None
        self.assertEqual(result.stop_reason, MultiAgentStopReason.MAX_ROUNDS)
        self.assertEqual(ledger.tasks[0].status, TaskStatus.FAILED)
        self.assertEqual(ledger.tasks[0].blockers[0].code, "dispatch_boundary_error")

    async def test_replan_resets_worker_before_next_dispatch(self) -> None:
        # [Hidden Failure] Replanning replaces opted-in worker state before more work runs.
        events: list[str] = []
        decisions = (
            OrchestratorDecision(action=OrchestratorAction.REPLAN),
            OrchestratorDecision(action=OrchestratorAction.DELEGATE, task_id="task-1", owner="worker", instruction="run"),
            OrchestratorDecision(action=OrchestratorAction.FINISH, final_answer="candidate"),
        )
        team = self._team(events, transfer=AgentTransfer(), decisions=decisions, settings=MultiAgentSettings(max_rounds=3, max_replans=1))

        await team.generate_reply("complete the task")

        result = team.last_result
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.replans, 1)
        self.assertEqual(result.stop_reason, MultiAgentStopReason.COMPLETED)
        self.assertEqual(events.count("worker.close"), 2)

    async def test_verified_evidence_gate_rejects_unverified_worker_prose(self) -> None:
        # [Silent Failure] Fluent default worker output cannot satisfy a proof-required finish.
        events: list[str] = []
        team = self._team(events, transfer=AgentTransfer(), settings=MultiAgentSettings(max_rounds=2, require_verified_evidence=True))

        await team.generate_reply("complete the task")

        result = team.last_result
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.stop_reason, MultiAgentStopReason.MAX_ROUNDS)
        self.assertFalse(result.completed)
        self.assertFalse(result.ledger.tasks[0].evidence[0].verified)

    async def test_default_request_builder_rejects_non_json_payload(self) -> None:
        # [Edge Case] Opaque payloads fail safely instead of being stringified into assignments.
        dispatch = AgentDispatch(run_id="run", base_revision=0, task_id="task", owner="worker", goal="goal", instruction="run", payload=object())

        with self.assertRaises(AgentTransferError):
            await AgentTransfer().build_request(dispatch, TaskLedgerSnapshot(run_id="run", goal="goal"))

    def test_context_renderer_uses_primitives_and_explicit_trust_boundaries(self) -> None:
        # [Silent Failure] User/ledger data stays untrusted and caller history stays excluded.
        request = AgentInput(prompt="user request")
        context = OrchestrationContext(
            request=request,
            team_instructions="trusted instructions",
            team=(AgentCard(name="worker", description="does work", system_prompt="hidden"),),
            ledger=TaskLedgerSnapshot(run_id="run", goal="user request"),
            settings=MultiAgentSettings(),
            context=BaseContext(memory="base-context-secret"),
            history=(AgentMessage(sender="caller", recipient="team", content="history-secret"),),
        )

        rendered = MultiAgentContext.render_orchestration(context)

        self.assertIn("<request>\n<untrusted_data>\nuser request", rendered)
        self.assertIn("<team_instructions>\ntrusted instructions", rendered)
        self.assertIn("<ledger>\n<untrusted_data>", rendered)
        self.assertNotIn("history-secret", rendered)
        self.assertNotIn("base-context-secret", rendered)
        self.assertNotIn("hidden", rendered)

    def _team(
        self,
        events: list[str],
        *,
        transfer: AgentTransfer,
        decisions: Sequence[OrchestratorDecision] | None = None,
        settings: MultiAgentSettings | None = None,
        on_event: Any = None,
    ) -> MultiAgent:
        # Build a public facade over provider-free fakes for each isolated test.
        scripted = decisions or (
            OrchestratorDecision(action=OrchestratorAction.DELEGATE, task_id="task-1", owner="worker", instruction="run"),
            OrchestratorDecision(action=OrchestratorAction.FINISH, final_answer="candidate"),
        )
        binding = AgentBinding(ScriptedWorker(events), transfer=transfer)
        return MultiAgent(name="team", system_prompt="coordinate", orchestrator=ScriptedOrchestrator(scripted), agents=(binding,), settings=settings, on_event=on_event)


if __name__ == "__main__":
    unittest.main()

"""Context Protocol Header

Description:
    Runs the bounded plan, decide, delegate, replan, and finish protocol.
Purpose:
    Presents a one-level controller flow while delegating specialized work to
    pre-run, ledger, dispatch, orchestrator, and post-run collaborators.
Architecture:
    MultiAgentRunner executes initialization, initial plan, serial rounds, and finalization.
Relations:
    Invoked by MultiAgentLifecycle and constructed by the MultiAgent facade.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from vidbyte.agents.multi.dispatcher import MultiAgentDispatcher
from vidbyte.agents.multi.ledger_controller import MultiAgentOrchestratorLedger
from vidbyte.agents.multi.orchestrator_runtime import MultiAgentOrchestratorRunner
from vidbyte.agents.multi.post_run import MultiAgentPostRunner
from vidbyte.agents.multi.pre_run import MultiAgentPreRunner
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.lib.dataclasses.multi_agent import MultiAgentResult, MultiAgentRunState, OrchestratorDecision
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus
from vidbyte.lib.errors import MultiAgentExecutionError

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentRunner:
    """Execute the finite deterministic controller around probabilistic manager policy."""

    def __init__(self, agent: MultiAgent, validator: MultiAgentValidator, pre_run: MultiAgentPreRunner, ledger: MultiAgentOrchestratorLedger, dispatcher: MultiAgentDispatcher, orchestrator: MultiAgentOrchestratorRunner, post_run: MultiAgentPostRunner) -> None:
        self._agent = agent
        self._validator = validator
        self._pre_run = pre_run
        self._ledger = ledger
        self._dispatcher = dispatcher
        self._orchestrator = orchestrator
        self._post_run = post_run

    async def run_with_timeout(self, state: MultiAgentRunState) -> MultiAgentResult:
        # The hard run budget covers initialization, all rounds, and terminal synthesis.
        timeout = self._agent.settings.run_timeout_seconds
        if timeout is None:
            return await self.run(state)
        try:
            async with asyncio.timeout(timeout):
                return await self.run(state)
        except TimeoutError as exc:
            return self._post_run.timeout_result(state, cause=exc)

    async def run(self, state: MultiAgentRunState) -> MultiAgentResult:
        # The core protocol reads as initialize, plan, execute rounds, then finalize.
        await self._pre_run.initialize(state)
        await self._ledger.apply_initial_plan(state)
        stop_reason, completed = await self.run_rounds(state)
        self._validate_limit_return(state, stop_reason)
        return await self._post_run.finalize_result(state, stop_reason, completed)

    async def run_rounds(self, state: MultiAgentRunState) -> tuple[MultiAgentStopReason, bool]:
        # Exactly one manager-selected action may execute per finite round.
        while state.rounds < self._agent.settings.max_rounds:
            state.rounds += 1
            outcome = await self._run_round(state)
            if outcome is not None:
                return outcome
        return MultiAgentStopReason.MAX_ROUNDS, False

    async def _run_round(self, state: MultiAgentRunState) -> tuple[MultiAgentStopReason, bool] | None:
        # Decision acquisition and state annotations happen before action dispatch.
        orchestrator = self._validator.require_orchestrator(state)
        decision = await self._orchestrator.call(state, "decide", orchestrator.decide(self._ledger.context(state)))
        self._ledger.remember_candidate(state, decision)
        await self._ledger.update_next_action(state, decision)
        if decision.action is OrchestratorAction.FINISH:
            return await self._handle_finish(state, decision)
        if decision.action is OrchestratorAction.REPLAN:
            return await self._handle_replan(state)
        progressed = await self._dispatcher.delegate(state, decision)
        self._update_stalls(state, decision, progressed)
        if state.stalls < self._agent.settings.replan_after_stalls:
            return None
        return await self._handle_replan(state)

    async def _handle_finish(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> tuple[MultiAgentStopReason, bool] | None:
        # Full completion always requires gates; partial completion requires explicit policy.
        if await self._ledger.finish_gate_passes(state, decision):
            state.finish_decision = decision
            return MultiAgentStopReason.COMPLETED, True
        if self._agent.settings.allow_partial_finish and state.candidate_answer and state.candidate_answer.strip():
            state.finish_decision = decision
            return MultiAgentStopReason.PARTIAL, False
        await self._ledger.reject_finish(state)
        return None

    async def _handle_replan(self, state: MultiAgentRunState) -> tuple[MultiAgentStopReason, bool] | None:
        # Replan exhaustion and unrecoverable required work are explicit terminal reasons.
        if not await self._ledger.try_replan(state):
            return MultiAgentStopReason.MAX_REPLANS, False
        if state.unrecoverable:
            return MultiAgentStopReason.UNRECOVERABLE, False
        return None

    def _update_stalls(self, state: MultiAgentRunState, decision: OrchestratorDecision, progressed: bool) -> None:
        # Only substantive, non-looping, non-failed work reduces accumulated stalls.
        failed = self._decision_report_failed(state, decision)
        if progressed and not decision.loop_detected and not failed:
            state.stalls = max(0, state.stalls - 1)
            return
        state.stalls += 1

    def _decision_report_failed(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> bool:
        # Match the latest report to this decision before treating it as a stall signal.
        report = state.last_report
        return report is not None and report.task_id == decision.task_id and report.status in (TaskStatus.FAILED, TaskStatus.BLOCKED)

    def _validate_limit_return(self, state: MultiAgentRunState, stop_reason: MultiAgentStopReason) -> None:
        # Hard-limit outcomes require explicit permission before terminal synthesis.
        limited = stop_reason in (MultiAgentStopReason.MAX_ROUNDS, MultiAgentStopReason.MAX_REPLANS, MultiAgentStopReason.UNRECOVERABLE)
        if limited and not self._agent.settings.return_partial_on_limit:
            raise MultiAgentExecutionError("Multi-agent run reached a configured limit without partial-return permission.", details={"run_id": state.run_id, "stop_reason": stop_reason.value})


__all__ = ["MultiAgentRunner"]

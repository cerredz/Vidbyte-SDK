"""Context Protocol Header

Description:
    Executes one ledger-authorized worker dispatch through its transfer boundary.
Purpose:
    Makes the dispatch path read sequentially from approval through report commit
    while containing every ordinary post-start failure in the TaskLedger.
Architecture:
    MultiAgentDispatcher owns decision-to-dispatch conversion, worker invocation,
    report parsing/validation, and failure closure.
Relations:
    Invoked by MultiAgentRunner; delegates ledger notifications to MultiAgentOrchestratorLedger.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from vidbyte.agents.multi.ledger_controller import MultiAgentOrchestratorLedger
from vidbyte.agents.multi.tracing import MultiAgentTracer
from vidbyte.agents.multi.transfer import AgentBinding
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.lib.dataclasses.multi_agent import (
    AgentDispatch,
    AgentReport,
    MultiAgentRunState,
    OrchestratorDecision,
    TaskBlocker,
)
from vidbyte.lib.enums.multi_agent import TaskStatus
from vidbyte.lib.errors import AgentTransferError, TaskLedgerError

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentDispatcher:
    """Run one worker boundary and commit exactly one terminal attempt report."""

    def __init__(self, agent: MultiAgent, validator: MultiAgentValidator, ledger: MultiAgentOrchestratorLedger, tracer: MultiAgentTracer) -> None:
        self._agent = agent
        self._validator = validator
        self._ledger = ledger
        self._tracer = tracer

    async def delegate(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> bool:
        # Validate the decision shape before asking the ledger to consume an attempt.
        self._validate_delegate_decision(decision)
        ledger = self._validator.require_ledger(state)
        try:
            dispatch = self._build_dispatch(state, decision)
            ledger.start_task(dispatch)
            await self._ledger.after_commit(state, "task_started")
        except (TaskLedgerError, ValueError):
            ledger.record_decision_rejection("Delegate decision rejected by ledger readiness or ownership checks.", task_id=decision.task_id, owner=decision.owner)
            await self._ledger.after_commit(state, "delegate_rejected")
            return False
        return await self.dispatch(state, dispatch)

    async def dispatch(self, state: MultiAgentRunState, dispatch: AgentDispatch) -> bool:
        # The top-level boundary intentionally mirrors the developer-facing dispatch protocol.
        ledger = self._validator.require_ledger(state)
        try:
            binding = self._require_binding(dispatch.owner)
            snapshot = ledger.snapshot()
            blocker = await binding.transfer.approve_dispatch(dispatch, snapshot)
            report = self._blocked_report(dispatch, blocker)
            if report is None:
                request = await binding.transfer.build_request(dispatch, snapshot)
                reply = await self.worker_generate_reply(state, binding, dispatch, request)
                report = await binding.transfer.parse_report(reply, dispatch, ledger.snapshot())
                report = await binding.transfer.validate_report(report, dispatch, ledger.snapshot())
            return await self._apply_report(state, dispatch, report)
        except Exception as exc:
            return await self._record_dispatch_failure(state, dispatch, exc)

    async def worker_generate_reply(self, state: MultiAgentRunState, binding: AgentBinding, dispatch: AgentDispatch, request: str | AgentInput) -> AgentMessage:
        # Low-level retries remain inside one semantic ledger attempt.
        span = self._tracer.start_span("multi_agent.worker", run_id=state.run_id, task_id=dispatch.task_id, owner=dispatch.owner, attempt=dispatch.attempt, round=state.rounds)
        try:
            reply, invocation = await self._invoke_with_retries(state, binding, dispatch, request)
            self._tracer.end_span(span, output=self._tracer.output(status="reported", invocation=invocation))
            return reply
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _invoke_with_retries(self, state: MultiAgentRunState, binding: AgentBinding, dispatch: AgentDispatch, request: str | AgentInput) -> tuple[AgentMessage, int]:
        # Retry only invocation exceptions; parsing and validation each execute once.
        last_error: Exception | None = None
        for invocation in range(1, binding.transfer.max_invocation_retries + 2):
            try:
                reply = await self._invoke_once(state, binding, dispatch, request, invocation)
                return reply, invocation
            except Exception as exc:
                last_error = exc
        raise AgentTransferError("Worker invocation failed after bounded retries.", details={"task_id": dispatch.task_id, "owner": dispatch.owner, "attempts": binding.transfer.max_invocation_retries + 1, "error_type": type(last_error).__name__ if last_error else "UnknownWorkerError"}) from last_error

    async def _invoke_once(self, state: MultiAgentRunState, binding: AgentBinding, dispatch: AgentDispatch, request: str | AgentInput, invocation: int) -> AgentMessage:
        # The transfer override wins over the team-wide worker timeout.
        worker = state.workers[dispatch.owner]
        timeout = binding.transfer.timeout_seconds or self._agent.settings.worker_timeout_seconds
        call = worker.generate_reply(request, recipient=self._agent.name, trace_metadata={"multi_agent_run_id": state.run_id, "task_id": dispatch.task_id, "owner": dispatch.owner, "attempt": dispatch.attempt, "invocation": invocation})
        return await call if timeout is None else await asyncio.wait_for(call, timeout=timeout)

    def _build_dispatch(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> AgentDispatch:
        # Dispatch identity derives from the current ledger record, not manager-supplied goal text.
        ledger = self._validator.require_ledger(state)
        assert decision.task_id is not None and decision.owner is not None and decision.instruction is not None
        record = ledger.task(decision.task_id)
        payload = record.payload if decision.payload is None else decision.payload
        return AgentDispatch(run_id=state.run_id, base_revision=ledger.revision, task_id=record.task_id, owner=decision.owner, goal=record.goal, acceptance_criteria=record.acceptance_criteria, instruction=decision.instruction, payload=payload, attempt=record.attempts + 1, metadata={"round": state.rounds})

    async def _apply_report(self, state: MultiAgentRunState, dispatch: AgentDispatch, report: AgentReport) -> bool:
        # Report commit is the final step in the successful dispatch sequence.
        ledger = self._validator.require_ledger(state)
        state.last_report = report
        _, progressed = ledger.apply_report(report, owner=dispatch.owner)
        await self._ledger.after_commit(state, "task_reported")
        return progressed

    async def _record_dispatch_failure(self, state: MultiAgentRunState, dispatch: AgentDispatch, error: Exception) -> bool:
        # Ordinary boundary failures always close the in-progress attempt as failed or blocked.
        ledger = self._validator.require_ledger(state)
        blocker = TaskBlocker(code="dispatch_boundary_error", message="Worker dispatch failed at a configured transfer boundary.", retryable=True, metadata={"error_type": type(error).__name__})
        ledger.record_dispatch_failure(dispatch.task_id, owner=dispatch.owner, blocker=blocker)
        await self._ledger.after_commit(state, "dispatch_failed")
        return False

    def _require_binding(self, owner: str) -> AgentBinding:
        # Unknown manager-selected owners fail inside the post-start containment boundary.
        binding = self._agent._bindings_by_owner.get(owner)
        if binding is None:
            raise AgentTransferError("Dispatch owner has no configured worker binding.", details={"owner": owner})
        return binding

    def _validate_delegate_decision(self, decision: OrchestratorDecision) -> None:
        # Delegate decisions must identify one task, owner, and concrete worker instruction.
        if decision.task_id is None or decision.owner is None or decision.instruction is None:
            raise AgentTransferError("Delegate decision is missing task_id, owner, or instruction.")

    def _blocked_report(self, dispatch: AgentDispatch, blocker: TaskBlocker | None) -> AgentReport | None:
        # A policy denial bypasses worker invocation but still closes the ledger attempt.
        if blocker is None:
            return None
        return AgentReport(task_id=dispatch.task_id, status=TaskStatus.BLOCKED, blockers=(blocker,))


__all__ = ["MultiAgentDispatcher"]

"""Context Protocol Header

Description:
    Coordinates orchestrator decisions with TaskLedger policy and context snapshots.
Purpose:
    Keeps plan commits, completion gates, replanning, event callbacks, and context
    construction outside the public facade and round runner.
Architecture:
    MultiAgentOrchestratorLedger delegates structural mutation to TaskLedger and
    context assembly to vidbyte.context.MultiAgentContext.
Relations:
    Used by MultiAgentRunner and MultiAgentDispatcher.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from vidbyte.agents.multi.cleanup import MultiAgentCleanup
from vidbyte.agents.multi.orchestrator_runtime import MultiAgentOrchestratorRunner
from vidbyte.agents.multi.tracing import MultiAgentTracer
from vidbyte.agents.multi.transfer import AgentTransfer
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.context.multi_agent import MultiAgentContext
from vidbyte.lib.dataclasses.multi_agent import (
    MultiAgentRunState,
    OrchestrationContext,
    OrchestratorDecision,
    OrchestratorPlan,
    TaskLedgerSnapshot,
)
from vidbyte.lib.enums.multi_agent import TaskStatus

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentOrchestratorLedger:
    """Apply manager policy through the ledger's deterministic state machine."""

    def __init__(
        self,
        agent: MultiAgent,
        validator: MultiAgentValidator,
        context: MultiAgentContext,
        orchestrator: MultiAgentOrchestratorRunner,
        cleanup: MultiAgentCleanup,
        tracer: MultiAgentTracer,
    ) -> None:
        self._agent = agent
        self._validator = validator
        self._context = context
        self._orchestrator = orchestrator
        self._cleanup = cleanup
        self._tracer = tracer

    async def apply_initial_plan(self, state: MultiAgentRunState) -> None:
        # Planning must commit atomically before the first worker can receive a dispatch.
        orchestrator = self._validator.require_orchestrator(state)
        plan = await self._orchestrator.call(state, "plan", orchestrator.plan(self.context(state)))
        self._validator.require_ledger(state).apply_plan(plan)
        await self.after_commit(state, "plan_applied")

    async def update_next_action(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> None:
        # A concise manager hint is observable ledger state, not hidden controller memory.
        if decision.next_action is None:
            return
        self._validator.require_ledger(state).set_next_action(decision.next_action)
        await self.after_commit(state, "next_action")

    def remember_candidate(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> None:
        # The latest non-blank candidate is retained only for allowed limit/timeout returns.
        if isinstance(decision.final_answer, str) and decision.final_answer.strip():
            state.candidate_answer = decision.final_answer

    async def finish_gate_passes(self, state: MultiAgentRunState, decision: OrchestratorDecision) -> bool:
        # Structural completion is the first mandatory gate.
        ledger = self._validator.require_ledger(state)
        if not ledger.all_required_complete():
            return False
        # Verified evidence becomes mandatory only when the developer enables that policy.
        if self._agent.settings.require_verified_evidence and not ledger.required_tasks_have_verified_evidence():
            return False
        # Without an extension callback, the deterministic ledger gates are sufficient.
        if self._agent._completion_check is None:
            return True
        result = self._agent._completion_check(self.context(state), decision)
        return bool(await AgentTransfer.maybe_await(result))

    async def reject_finish(self, state: MultiAgentRunState) -> None:
        # Rejected finish intent becomes an audit event and one stall signal.
        ledger = self._validator.require_ledger(state)
        ledger.record_decision_rejection("Finish rejected because completion gates are not satisfied.")
        await self.after_commit(state, "finish_rejected")
        state.stalls += 1

    async def try_replan(self, state: MultiAgentRunState) -> bool:
        # Replanning is refused before manager invocation once the explicit budget is exhausted.
        if state.replans >= self._agent.settings.max_replans:
            return False
        ledger = self._validator.require_ledger(state)
        before = ledger.snapshot()
        before_ready = self._ready_task_ids(ledger, before)
        span = self._tracer.start_span("multi_agent.replan", run_id=state.run_id, replans=state.replans, round=state.rounds, stalls=state.stalls, revision=ledger.revision)
        try:
            plan = await self._request_replan(state)
            ledger.apply_plan(plan, replan=True)
            state.replans += 1
            material_change = self._material_replan_change(ledger, before, before_ready)
            state.stalls = 0 if material_change else 1
            state.unrecoverable = ledger.required_work_is_unrecoverable()
            await self.after_commit(state, "plan_replaced")
            await self._cleanup.reset_workers(state)
            output = self._tracer.output(revision=ledger.revision, replans=state.replans, material_change=material_change, unrecoverable=state.unrecoverable)
            self._tracer.end_span(span, output=output)
            return True
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def after_commit(self, state: MultiAgentRunState, status: str) -> None:
        # Public snapshots update before event callbacks observe the new revision.
        ledger = self._validator.require_ledger(state)
        snapshot = ledger.snapshot()
        self._agent.last_ledger = snapshot
        span = self._tracer.start_span("multi_agent.ledger_update", run_id=state.run_id, revision=snapshot.revision, status=status)
        event = ledger.latest_event
        if not self._should_emit_event(state, event):
            self._tracer.end_span(span, output=self._tracer.output(revision=snapshot.revision, status=status))
            return
        await self._emit_event(state, snapshot, event, span, status)

    def context(self, state: MultiAgentRunState) -> OrchestrationContext:
        # All custom context construction flows through the shared context abstraction.
        ledger = self._validator.require_ledger(state)
        return self._context.build(
            request=state.request,
            team_instructions=self._agent.system_prompt,
            team=tuple(binding.agent.card() for binding in self._agent._bindings),
            ledger=ledger.snapshot(),
            settings=self._agent.settings,
            context=state.context,
            history=(*self._agent.history, *state.history),
            round=state.rounds,
            replans=state.replans,
            stalls=state.stalls,
            last_report=state.last_report,
        )

    async def _request_replan(self, state: MultiAgentRunState) -> OrchestratorPlan:
        # The run-local orchestrator receives the latest immutable context snapshot.
        orchestrator = self._validator.require_orchestrator(state)
        return await self._orchestrator.call(state, "replan", orchestrator.replan(self.context(state)))

    def _material_replan_change(self, ledger: Any, before: TaskLedgerSnapshot, before_ready: tuple[str, ...]) -> bool:
        # A replan only clears stalls when structure, facts, or dispatchable work changes.
        after = ledger.snapshot()
        after_ready = self._ready_task_ids(ledger, after)
        return self._signature(before) != self._signature(after) or before_ready != after_ready

    def _ready_task_ids(self, ledger: Any, snapshot: TaskLedgerSnapshot) -> tuple[str, ...]:
        # Superseded work never contributes to recovery readiness.
        return tuple(sorted(task.task_id for task in snapshot.tasks if task.status is not TaskStatus.SUPERSEDED and ledger.is_ready(task.task_id)))

    def _should_emit_event(self, state: MultiAgentRunState, event: Any) -> bool:
        # Retained events emit at most once and only when a callback exists.
        return self._agent._on_event is not None and event is not None and event.index > state.last_emitted_event_index

    async def _emit_event(self, state: MultiAgentRunState, snapshot: TaskLedgerSnapshot, event: Any, span: Any, status: str) -> None:
        # Callback failures remain observable but never roll back committed ledger state.
        state.last_emitted_event_index = event.index
        callback = self._agent._on_event
        assert callback is not None
        try:
            await AgentTransfer.maybe_await(callback(event, snapshot))
            self._tracer.end_span(span, output=self._tracer.output(revision=snapshot.revision, status=status, event_callback="completed"))
        except Exception as exc:
            state.event_error_types.append(type(exc).__name__)
            self._tracer.end_span(span, output=self._tracer.output(revision=snapshot.revision, status=status, event_callback="failed", error_type=type(exc).__name__))

    @classmethod
    def _signature(cls, snapshot: TaskLedgerSnapshot) -> tuple[Any, ...]:
        # Compare control-relevant values without invoking arbitrary object equality.
        active = tuple(sorted((task.task_id, task.goal, task.owner, task.depends_on, task.required, task.acceptance_criteria, task.max_attempts, cls._fingerprint(task.payload), cls._fingerprint(dict(task.metadata))) for task in snapshot.tasks if task.status is not TaskStatus.SUPERSEDED))
        facts = (snapshot.verified_facts, snapshot.facts_to_find, snapshot.facts_to_derive, snapshot.educated_guesses)
        return active, facts

    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        # Deterministic JSON handles plain values; opaque values use type and identity only.
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return f"opaque:{type(value).__module__}.{type(value).__qualname__}:{id(value)}"


__all__ = ["MultiAgentOrchestratorLedger"]

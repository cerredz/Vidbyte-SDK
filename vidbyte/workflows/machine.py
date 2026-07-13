"""FILE: vidbyte/workflows/machine.py
PURPOSE: Executes compiled workflows as append-only, checkpointed control planes.
ROLE IN CODEBASE: Invokes stages, gates, routers, approval, detours, and isolated children.

ARCHITECTURE NOTE:
    Every control-changing fact is appended before it becomes projected runtime state.
    Candidate reducer updates remain isolated until stage validation, route guards, and
    approval pass. Checkpoints cache projections; events remain canonical. Workflow
    position and lifecycle are orthogonal, so suspensions return nonterminal results.

PUBLIC API INVENTORY:
    StateMachine introspection properties: Immutable compiled definition views.
    arun()/run(): Start execution from typed initial state and observations.
    aresume()/resume(): Continue the exact pending durable boundary.
    inspect(): Read-only current or time-travel projection.

COMMON MODIFICATION PATTERNS:
    Add static authority in graph.py, event schema in events.py, replay behavior in
    projection.py, then emit it here at exactly one control boundary.

WHAT NOT TO DO IN THIS FILE:
    1. Do not accept destinations absent from compiled outcome/command maps.
    2. Do not mutate committed state before all deterministic gates pass.
    3. Do not claim external tool/filesystem side effects can be rolled back.
    4. Do not store one run's mutable projection on StateMachine.
    5. Do not swallow CancelledError or other BaseException control signals.

KNOWN EDGE CASES:
    A crash after an external effect but before its event requires stage/tool idempotency.
    Explicit interrupts replay the Python stage; approvals resume a persisted candidate
    without rerunning its source stage.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; repository tests plus adversarial inline smoke.

CONCURRENCY:
    Each _WorkflowRun owns its projection/ledger. Stores provide append synchronization;
    compiled graph records and the StateMachine facade are safe for concurrent callers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
import inspect
import time
from typing import Any, Generic
from uuid import uuid4

from .approval import ApprovalContext, ConfirmationPolicy, NeverConfirm
from .budget import BudgetLedger, UnknownCostPolicy, UsageReport, WorkflowBudget
from .contracts import (
    PendingRequest,
    PendingRequestKind,
    ResumeCommand,
    RoutingContext,
    StageContext,
    StageExecution,
    StagePolicy,
    StageResult,
    StateMachineResult,
    StateT,
    TransitionRecord,
    ValidationContext,
    ValidationPhase,
    ValidationRecord,
    ValidationResult,
    ValidationStatus,
    Validator,
    ValidatorErrorPolicy,
    WorkflowCommand,
    WorkflowFeedback,
    WorkflowInterrupt,
    WorkflowLifecycleStatus,
    WorkflowObserver,
    _StageInterruptSignal,
)
from .detours import DetourFrame, DetourReturnMode, WorkflowSignal
from .errors import (
    StageExecutionError,
    WorkflowApprovalError,
    WorkflowBudgetError,
    WorkflowCommandError,
    WorkflowDetourError,
    WorkflowError,
    WorkflowErrorRecord,
    WorkflowExecutionError,
    WorkflowInterruptError,
    WorkflowPersistenceError,
    WorkflowResumeError,
    WorkflowRoutingError,
    WorkflowStateError,
    WorkflowStuckError,
    WorkflowSubgraphError,
    WorkflowValidationError,
)
from .events import WorkflowEvent, WorkflowEventFactory, WorkflowEventType
from .graph import _BranchRoute, _CompiledGraph, _DirectRoute, _StageDefinition
from .persistence import WorkflowCheckpoint, WorkflowCheckpointPolicy, WorkflowStore, assert_checkpoint_compatible
from .projection import (
    WorkflowProjection,
    WorkflowProjector,
    _budget_to_dict,
    _error_to_dict,
    _feedback_to_dict,
    _pending_to_dict,
    _stage_to_dict,
    _detour_to_dict,
    _transition_to_dict,
    _usage_from_dict,
    _usage_to_dict,
)
from .stores.memory import InMemoryWorkflowStore
from .subgraphs import ChildFailurePolicy, Send, SubgraphExecutor, _effective_child_budget, _planned_child_run_id


@dataclass(frozen=True, slots=True)
class _ValidationDecision:
    """Effective outcome and ordered evidence from one validator sequence."""

    passed: bool
    result: ValidationResult | None
    records: tuple[ValidationRecord, ...]
    must_raise: bool = False


@dataclass(frozen=True, slots=True)
class _StageDecision(Generic[StateT]):
    """Validated candidate plus its bounded control request."""

    source: str
    state_before: StateT
    candidate_state: StateT
    stage_result: StageResult[StateT]
    command: WorkflowCommand[StateT]
    can_commit: bool
    trigger: str
    feedback: tuple[WorkflowFeedback, ...]
    execution: StageExecution

    @property
    def outcome(self) -> str:
        # Returns the semantic route code after command normalization.
        return self.stage_result.outcome


@dataclass(frozen=True, slots=True)
class _SelectedRoute(Generic[StateT]):
    """One statically authorized direct or routed destination."""

    route: _DirectRoute[StateT]
    branch_key: str | None = None
    router: str | None = None
    command: bool = False

    @property
    def target(self) -> str:
        # Exposes the immutable compiled destination.
        return self.route.target


class _SubgraphSuspension(BaseException):
    """Internal unwind carrying isolated child summaries to a durable parent boundary."""

    def __init__(self, command: WorkflowCommand[Any], base_candidate: Any, children: Sequence[Mapping[str, Any]]) -> None:
        # Retains only data that the parent immediately persists before returning.
        super().__init__("child_subgraph_suspended")
        self.command = command
        self.base_candidate = base_candidate
        self.children = tuple(dict(item) for item in children)


class _EventRuntime(Generic[StateT]):
    """Appends, projects, observes, and checkpoints one run's canonical stream."""

    def __init__(
        self,
        definition: _CompiledGraph[StateT],
        store: WorkflowStore,
        run_id: str,
        observers: Sequence[WorkflowObserver],
        checkpoint_policy: WorkflowCheckpointPolicy,
        *,
        projection: WorkflowProjection[StateT] | None = None,
    ) -> None:
        # Creates a sequenced factory whose wall-clock origin survives cold resume.
        self.definition = definition
        self.store = store
        self.run_id = run_id
        self.observers = tuple(observers)
        self.checkpoint_policy = checkpoint_policy
        self.projector: WorkflowProjector[StateT] = WorkflowProjector()
        self.projection = projection
        self.observer_errors: list[str] = [] if projection is None else projection.observer_errors
        started_at = _parse_datetime(projection.started_at) if projection and projection.started_at else None
        self.factory = WorkflowEventFactory(definition.definition_id, run_id, started_at=started_at)

    async def begin(self, state: StateT, observations: Mapping[str, Any], metadata: Mapping[str, Any]) -> WorkflowProjection[StateT]:
        # Creates sequence one atomically and projects the initial typed state.
        event = self.factory.create(
            WorkflowEventType.RUN_STARTED,
            sequence=1,
            super_step=0,
            stage=self.definition.entry,
            payload={"state": self.definition.state_schema.encode(state), "observations": observations, "metadata": metadata, "current_stage": self.definition.entry},
        )
        await self.store.begin_run(event)
        self.projection = self.projector.apply(self.definition, None, event)
        await self._notify(event)
        return self.projection

    async def emit(self, event_type: WorkflowEventType, *, stage: str | None = None, payload: Mapping[str, Any] | None = None, super_step: int | None = None) -> WorkflowEvent:
        # Persists the next event under compare-and-set before projection/observation.
        projection = self.require_projection()
        event = self.factory.create(
            event_type,
            sequence=projection.last_event_sequence + 1,
            super_step=projection.super_step if super_step is None else super_step,
            stage=stage,
            payload=payload,
        )
        await self.store.append(event, expected_sequence=projection.last_event_sequence)
        self.projector.apply(self.definition, projection, event)
        await self._notify(event)
        return event

    async def checkpoint(self, *, force: bool = False) -> WorkflowCheckpoint | None:
        # Writes one immutable cache after first appending its canonical boundary marker.
        if not force and self.checkpoint_policy is WorkflowCheckpointPolicy.MANUAL:
            return None
        checkpoint_id = f"wck_{uuid4().hex}"
        await self.emit(WorkflowEventType.CHECKPOINT_WRITTEN, stage=self.require_projection().current_stage, payload={"checkpoint_id": checkpoint_id})
        checkpoint = replace(self.require_projection().checkpoint(self.definition), checkpoint_id=checkpoint_id)
        await self.store.put_checkpoint(checkpoint)
        self.require_projection().checkpoint_id = checkpoint_id
        return checkpoint

    def require_projection(self) -> WorkflowProjection[StateT]:
        # Reports internal lifecycle misuse without fabricating a run snapshot.
        if self.projection is None:
            raise WorkflowExecutionError("Workflow projection was accessed before RUN_STARTED.", details={"run_id": self.run_id})
        return self.projection

    async def _notify(self, event: WorkflowEvent) -> None:
        # Isolates observer exceptions after the canonical append has succeeded.
        for observer in self.observers:
            try:
                await observer.on_event(event)
            except Exception as exc:
                self.observer_errors.append(f"{type(observer).__name__}: {type(exc).__name__}")


class _ValidationRunner(Generic[StateT]):
    """Runs ordered validators and applies the compiled non-decision policy."""

    def __init__(self, definition: _CompiledGraph[StateT], events: _EventRuntime[StateT]) -> None:
        # Retains only immutable settings and the run-local event boundary.
        self.definition = definition
        self.events = events

    async def evaluate(self, validators: Sequence[Validator[StateT]], context: ValidationContext[StateT]) -> _ValidationDecision:
        # Stops at the first effective rejection while retaining all prior evidence.
        records: list[ValidationRecord] = []
        for validator in validators:
            record = await self._evaluate_one(validator, context)
            records.append(record)
            decision = self._interpret(record.result, tuple(records))
            if decision is not None:
                return decision
        return _ValidationDecision(True, None, tuple(records))

    async def _evaluate_one(self, validator: Validator[StateT], context: ValidationContext[StateT]) -> ValidationRecord:
        # Converts ordinary callback failure/contract violation to structured ERROR.
        name = _validator_name(validator)
        started = time.perf_counter()
        try:
            result = await validator.validate(context)
        except Exception as exc:
            result = ValidationResult.errored(self.definition.settings.validation_error_outcome, f"Validator '{name}' raised {type(exc).__name__}.", details={"validator": name, "error_type": type(exc).__name__})
        if not isinstance(result, ValidationResult):
            result = ValidationResult.errored(self.definition.settings.validation_error_outcome, f"Validator '{name}' returned {type(result).__name__}.", details={"validator": name, "actual_type": type(result).__name__})
        if result.usage is not None:
            await _charge_usage(self.definition, self.events, context.stage, result.usage)
        record = ValidationRecord(context.phase, name, result, _duration_ms(started), context.target)
        await self.events.emit(WorkflowEventType.VALIDATION_FINISHED, stage=context.stage, payload={"phase": context.phase.value, "validator": name, "status": result.status.value, "code": result.code, "target": context.target})
        return record

    def _interpret(self, result: ValidationResult, records: tuple[ValidationRecord, ...]) -> _ValidationDecision | None:
        # Applies fail-open, fail-closed, or raise behavior to abstention/error.
        if result.status is ValidationStatus.PASS:
            return None
        if result.status is ValidationStatus.REJECT:
            return _ValidationDecision(False, result, records)
        policy = self.definition.settings.validator_error_policy
        if policy is ValidatorErrorPolicy.FAIL_OPEN:
            return None
        if policy is ValidatorErrorPolicy.RAISE:
            return _ValidationDecision(False, result, records, True)
        effective = ValidationResult.rejected(result.code or self.definition.settings.validation_error_outcome, result.feedback or "Validator did not pass.", score=result.score, details=result.details, usage=result.usage)
        return _ValidationDecision(False, effective, records)


class _WorkflowRun(Generic[StateT]):
    """Owns one start/resume execution over an immutable compiled definition."""

    def __init__(
        self,
        definition: _CompiledGraph[StateT],
        store: WorkflowStore,
        run_id: str,
        *,
        observers: Sequence[WorkflowObserver],
        checkpoint_policy: WorkflowCheckpointPolicy,
        confirmation_policy: ConfirmationPolicy,
        projection: WorkflowProjection[StateT] | None = None,
    ) -> None:
        # Creates run-local event, validation, and confirmation collaborators.
        self.definition = definition
        self.store = store
        self.run_id = run_id
        self.events = _EventRuntime(definition, store, run_id, observers, checkpoint_policy, projection=projection)
        self.validators = _ValidationRunner(definition, self.events)
        self.confirmation_policy = confirmation_policy

    async def start(self, initial_state: StateT, observations: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None) -> StateMachineResult[StateT]:
        # Stores definition identity, appends RUN_STARTED, and drives until a boundary.
        await self._prepare_definition()
        try:
            state = self.definition.state_schema.validate(initial_state)
            projected_observations = self.definition.state_schema.initialize_observations(observations)
            await self.events.begin(state, projected_observations, dict(metadata or {}))
            return await self._bounded(self._drive())
        except BaseException as exc:
            return await self._handle_escape(exc)

    async def resume(self, command: ResumeCommand | None) -> StateMachineResult[StateT]:
        # Applies one exact pending response or restarts an incomplete crash boundary.
        await self._prepare_definition()
        projection = self.events.require_projection()
        if projection.lifecycle in (WorkflowLifecycleStatus.FINISHED, WorkflowLifecycleStatus.ERROR):
            raise WorkflowResumeError("Finished or errored workflows cannot be resumed.", details={"run_id": self.run_id, "lifecycle": projection.lifecycle.value})
        pending = projection.pending
        if pending is not None:
            if command is None:
                raise WorkflowResumeError("A pending workflow requires ResumeCommand.", details={"run_id": self.run_id, "request_id": pending.request_id, "kind": pending.kind.value})
            if command.request_id != pending.request_id:
                raise WorkflowResumeError("ResumeCommand does not match the pending request.", details={"run_id": self.run_id, "expected_request_id": pending.request_id, "actual_request_id": command.request_id})
            if pending.kind is PendingRequestKind.APPROVAL and command.approved is None:
                raise WorkflowApprovalError("Transition approvals require ResumeCommand.approve() or reject().", details={"request_id": command.request_id})
            if pending.kind is PendingRequestKind.INTERRUPT and command.approved is not None:
                raise WorkflowInterruptError("Stage interrupts require ResumeCommand.resume(), not approve/reject.", details={"request_id": command.request_id})
            if pending.kind is PendingRequestKind.SUBGRAPH:
                child_kind = pending.metadata.get("child_request_kind")
                if child_kind == PendingRequestKind.APPROVAL.value and command.approved is None:
                    raise WorkflowApprovalError("Pending child approval requires approve() or reject().", details={"request_id": command.request_id})
                if child_kind == PendingRequestKind.INTERRUPT.value and command.approved is not None:
                    raise WorkflowInterruptError("Pending child interrupt requires ResumeCommand.resume().", details={"request_id": command.request_id})
        else:
            if command is not None:
                raise WorkflowResumeError("ResumeCommand was supplied but the workflow has no pending request.", details={"run_id": self.run_id})
            if not projection.incomplete_stage:
                raise WorkflowResumeError("Workflow is not suspended and has no incomplete stage boundary.", details={"run_id": self.run_id, "lifecycle": projection.lifecycle.value})
        try:
            if pending is not None and command is not None:
                if pending.kind is PendingRequestKind.APPROVAL:
                    return await self._bounded(self._resume_approval(command))
                if pending.kind is PendingRequestKind.INTERRUPT:
                    active = dict(projection.pending_data)
                    value = command.value
                    await self.events.emit(WorkflowEventType.INTERRUPT_RESPONDED, stage=pending.stage, payload={"request_id": command.request_id, "resume_key": active.get("resume_key"), "value": value, "pending_data": active})
                    if active.get("mode") == "command":
                        return await self._bounded(self._resume_command_interrupt(active, value))
                    return await self._bounded(self._drive())
                if pending.kind is PendingRequestKind.SUBGRAPH:
                    return await self._bounded(self._resume_subgraph(command))
                raise WorkflowSubgraphError("Pending child graph request kind is unsupported.", details={"run_id": self.run_id, "request_id": command.request_id})
            mode = projection.pending_data.get("mode")
            if mode == "approval_response":
                return await self._bounded(self._continue_approval_response(projection.pending_data))
            if mode == "command" and "resume_value" in projection.pending_data:
                return await self._bounded(self._resume_command_interrupt(projection.pending_data, projection.pending_data.get("resume_value")))
            if mode == "subgraph":
                return await self._bounded(self._continue_subgraph_boundary(projection.pending_data))
            return await self._bounded(self._drive())
        except BaseException as exc:
            return await self._handle_escape(exc)

    async def _prepare_definition(self) -> None:
        # Requires explicit version for durable stores and verifies/stores identity.
        if self.store.durable and self.definition.version is None:
            raise WorkflowPersistenceError("Durable workflow execution requires an explicit StateGraph version.", details={"workflow": self.definition.name, "definition_id": self.definition.definition_id})
        await self.store.put_definition(self.definition.definition_record)

    async def _drive(self) -> StateMachineResult[StateT]:
        # Advances declared stages until terminal, suspension, detour return, or error.
        while True:
            projection = self.events.require_projection()
            current_stage = projection.current_stage
            if current_stage is None:
                raise WorkflowExecutionError("Projection has no current workflow stage.", details={"run_id": self.run_id})
            if current_stage in self.definition.terminals:
                return await self._finish(current_stage)
            if current_stage not in self.definition.stages:
                raise WorkflowExecutionError("Projection points at an unknown workflow stage.", details={"run_id": self.run_id, "stage": current_stage})
            decision = await self._run_stage(current_stage)
            if isinstance(decision, StateMachineResult):
                return decision
            if decision.command.metadata.get("tool_boundary_detour") is True:
                await self._enter_tool_detour(decision)
                continue
            if decision.command.return_from_detour is not None:
                returned = await self._return_from_detour(decision)
                if isinstance(returned, str):
                    return await self._finish(returned)
                if isinstance(returned, StateMachineResult):
                    return returned
                continue
            terminal_or_result = await self._advance(decision)
            if terminal_or_result is None:
                continue
            if isinstance(terminal_or_result, StateMachineResult):
                return terminal_or_result
            return await self._finish(terminal_or_result)

    async def _run_stage(self, stage_name: str) -> _StageDecision[StateT] | StateMachineResult[StateT]:
        # Executes one visit with deterministic retries, immediate observations, and gates.
        definition = self.definition.stages[stage_name]
        projection = self.events.require_projection()
        active = projection.pending_data.get("active_stage") if projection.incomplete_stage else None
        if isinstance(active, Mapping) and active.get("stage") == stage_name:
            visit = int(active["visit"])
            first_attempt = int(active.get("attempt", 1))
            idempotency_key = str(active["idempotency_key"])
            restarting = True
            budget = BudgetLedger(self.definition.settings.budget, cost_model=self.definition.settings.cost_model, snapshot=projection.budget)
        else:
            budget = BudgetLedger(self.definition.settings.budget, cost_model=self.definition.settings.cost_model, snapshot=projection.budget)
            budget.consume_super_step(stage_name)
            budget.assert_stage_visits(stage_name, definition.policy.max_visits)
            visit = budget.stage_visits[stage_name]
            first_attempt = 1
            idempotency_key = f"{self.run_id}:{stage_name}:{visit}"
            restarting = False
        policy = definition.policy
        for attempt in range(first_attempt, policy.retry.max_attempts + 1):
            active_payload = {"stage": stage_name, "visit": visit, "attempt": attempt, "idempotency_key": idempotency_key}
            event_type = WorkflowEventType.STAGE_RESTARTED if restarting else WorkflowEventType.STAGE_STARTED
            await self.events.emit(event_type, stage=stage_name, super_step=budget.super_steps, payload={"stage": stage_name, "visit": visit, "attempt": attempt, "idempotency_key": idempotency_key, "active_stage": active_payload, "budget": _budget_to_dict(budget.snapshot())})
            restarting = False
            state_before = self._clone_state(self.events.require_projection().state, boundary=f"stage:{stage_name}:before")
            stage_input = self._clone_state(state_before, boundary=f"stage:{stage_name}:input")
            interrupt_ordinal = 0

            async def observe(channel: str, value: Any) -> Any:
                # Enforces declared immediate writes before appending their reduced value.
                if channel not in definition.writes:
                    raise WorkflowStateError("Stage attempted an undeclared immediate observation write.", details={"stage": stage_name, "channel": channel, "allowed_writes": sorted(definition.writes)})
                current = self.events.require_projection().observations
                updated = self.definition.state_schema.apply_observation(current, channel, value)
                await self.events.emit(WorkflowEventType.OBSERVATION_RECORDED, stage=stage_name, payload={"channel": channel, "observations": updated})
                return self.events.require_projection().observations[channel]

            def interrupt(request: WorkflowInterrupt) -> Any:
                # Replays values by stable stage/visit/call ordinal or unwinds for suspension.
                nonlocal interrupt_ordinal
                ordinal = interrupt_ordinal
                interrupt_ordinal += 1
                key = f"{stage_name}:{visit}:{ordinal}"
                if key in self.events.require_projection().resume_values:
                    value = self.events.require_projection().resume_values[key]
                    return request.schema.model_validate(value) if request.schema is not None else value
                raise _StageInterruptSignal(request, ordinal)

            context = StageContext(
                run_id=self.run_id,
                stage=stage_name,
                state=stage_input,
                visit=visit,
                attempt=attempt,
                transition_count=budget.transitions,
                feedback=tuple(projection.feedback),
                history=tuple(projection.stages),
                observations=projection.observations,
                metadata=projection.metadata,
                super_step=budget.super_steps,
                idempotency_key=idempotency_key,
                _observe_handler=observe,
                _interrupt_handler=interrupt,
            )
            started = time.perf_counter()
            try:
                raw = await self._invoke_stage(definition, context)
            except _StageInterruptSignal as signal:
                return await self._suspend_interrupt(stage_name, visit, attempt, idempotency_key, signal.request, signal.ordinal)
            except Exception as exc:
                record = StageExecution(stage_name, visit, attempt, None, False, _duration_ms(started), {}, (), type(exc).__name__, f"Stage attempt failed with {type(exc).__name__}.")
                retrying = self._should_retry(exc, policy, attempt)
                next_active = {**active_payload, "attempt": attempt + 1} if retrying else active_payload
                await self.events.emit(WorkflowEventType.STAGE_FAILED, stage=stage_name, payload={"execution": _stage_to_dict(record), "active_stage": next_active})
                if retrying:
                    await self._wait_before_retry(policy, attempt)
                    continue
                if isinstance(exc, WorkflowError):
                    raise
                if policy.error_outcome is not None:
                    feedback = WorkflowFeedback("stage_error", stage_name, policy.error_outcome, f"Stage '{stage_name}' exhausted its execution policy.", {"error_type": type(exc).__name__, "attempts": attempt})
                    error_command: WorkflowCommand[StateT] = WorkflowCommand(outcome=policy.error_outcome)
                    error_result = StageResult(state_before, policy.error_outcome)
                    return _StageDecision(stage_name, state_before, state_before, error_result, error_command, False, "stage_error", (feedback,), record)
                raise StageExecutionError(f"Stage '{stage_name}' failed after {attempt} attempt(s).", details={"run_id": self.run_id, "stage": stage_name, "attempts": attempt, "error_type": type(exc).__name__}) from exc
            try:
                command, candidate, usage = await self._normalize_stage_output(stage_name, definition, state_before, raw)
            except _SubgraphSuspension as suspension:
                return await self._suspend_subgraphs(stage_name, visit, attempt, idempotency_key, state_before, suspension, _duration_ms(started))
            for action in command.metadata.get("action_decisions", ()):
                if not isinstance(action, Mapping):
                    continue
                event_type = WorkflowEventType.ACTION_AUTHORIZED if bool(action.get("allowed")) else WorkflowEventType.ACTION_DENIED
                await self.events.emit(event_type, stage=stage_name, payload={"code": action.get("code"), "reason": action.get("reason"), "metadata": action.get("metadata", {})})
            if usage is not None:
                await _charge_usage(self.definition, self.events, stage_name, usage)
            outcome = command.outcome or "success"
            stage_result = StageResult(candidate, outcome, command.metadata)
            if command.metadata.get("tool_boundary_detour") is True:
                record = StageExecution(stage_name, visit, attempt, outcome, False, _duration_ms(started), command.metadata, (), state_before=self._snapshot(state_before), candidate_state=self._snapshot(state_before))
                await self.events.emit(WorkflowEventType.STAGE_FINISHED, stage=stage_name, payload={"execution": _stage_to_dict(record)})
                return _StageDecision(stage_name, state_before, state_before, StageResult(state_before, outcome, command.metadata), command, False, "tool_boundary_detour", tuple(projection.feedback), record)
            validation = await self._validate_stage(definition, stage_name, state_before, stage_result)
            if validation.must_raise:
                self._raise_validation(stage_name, validation.result, ValidationPhase.STAGE)
            accepted = validation.passed
            record = StageExecution(stage_name, visit, attempt, outcome, accepted, _duration_ms(started), command.metadata, validation.records, state_before=self._snapshot(state_before), candidate_state=self._snapshot(candidate))
            await self.events.emit(WorkflowEventType.STAGE_FINISHED, stage=stage_name, payload={"execution": _stage_to_dict(record)})
            if accepted:
                decision = _StageDecision(stage_name, state_before, candidate, stage_result, command, True, "command" if command.goto else "stage_outcome", tuple(projection.feedback), record)
                if command.interrupt is not None:
                    return await self._suspend_command_interrupt(decision, visit, attempt, idempotency_key)
                return decision
            validation_result = validation.result or ValidationResult.rejected(self.definition.settings.validation_error_outcome, "Stage validation rejected the candidate.")
            feedback = self._validation_feedback("stage_validation", stage_name, validation_result, validation.records)
            rejected_command: WorkflowCommand[StateT] = WorkflowCommand(outcome=validation_result.code, metadata=command.metadata)
            return _StageDecision(stage_name, state_before, state_before, StageResult(state_before, validation_result.code, command.metadata), rejected_command, False, "stage_validation", (feedback,), record)
        raise StageExecutionError(f"Stage '{stage_name}' exhausted its retry loop.", details={"run_id": self.run_id, "stage": stage_name})

    async def _invoke_stage(self, definition: _StageDefinition[StateT], context: StageContext[StateT]) -> Any:
        # Applies the stage-local wall-clock timeout around exactly one callback.
        policy_runner = getattr(definition.stage, "run_with_policy", None)
        if callable(policy_runner):
            kwargs: dict[str, Any] = {"capabilities": definition.capabilities, "model_route": definition.model_route}
            try:
                parameters = tuple(inspect.signature(policy_runner).parameters.values())
                accepts_kwargs = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
                parameter_names = {parameter.name for parameter in parameters}
            except (TypeError, ValueError):
                accepts_kwargs = False
                parameter_names = set()
            if accepts_kwargs or "detour_rules" in parameter_names:
                kwargs["detour_rules"] = tuple((item.rule.rule_id, item.rule.matcher) for item in self.definition.detours)
            if accepts_kwargs or "model_call_limit" in parameter_names:
                global_limit = self.definition.settings.budget.max_model_calls
                if global_limit is not None:
                    remaining = global_limit - self.events.require_projection().usage.model_calls
                    if remaining <= 0:
                        raise WorkflowBudgetError("Workflow model-call budget is exhausted before agent stage execution.", details={"run_id": self.run_id, "stage": context.stage, "actual": self.events.require_projection().usage.model_calls, "limit": global_limit})
                    kwargs["model_call_limit"] = remaining
            invocation = policy_runner(context, **kwargs)
        else:
            invocation = definition.stage.run(context)
        if definition.policy.timeout_seconds is None:
            return await invocation
        return await asyncio.wait_for(invocation, timeout=definition.policy.timeout_seconds)

    async def _normalize_stage_output(self, stage_name: str, definition: _StageDefinition[StateT], state_before: StateT, value: Any) -> tuple[WorkflowCommand[StateT], StateT, UsageReport | None]:
        # Converts StageResult/WorkflowCommand into an isolated reducer candidate.
        if isinstance(value, StageResult):
            if not self.definition.state_schema.root_compatible:
                raise WorkflowCommandError("Whole-state StageResult is available only for root-compatible schemas; use WorkflowCommand.update.", details={"stage": stage_name})
            command: WorkflowCommand[StateT] = WorkflowCommand(update={"__root__": value.state}, outcome=value.outcome, metadata=value.metadata)
        elif isinstance(value, WorkflowCommand):
            command = value
        else:
            raise StageExecutionError(f"Stage '{stage_name}' returned {type(value).__name__}; expected StageResult or WorkflowCommand.", details={"run_id": self.run_id, "stage": stage_name, "actual_type": type(value).__name__})
        try:
            candidate = self.definition.state_schema.apply(state_before, command.update, allowed_writes=definition.writes) if command.update else self._clone_state(state_before, boundary=f"stage:{stage_name}:empty_update")
        except WorkflowError:
            raise
        except Exception as exc:
            raise WorkflowStateError("Workflow command update failed state reduction.", details={"run_id": self.run_id, "stage": stage_name, "error_type": type(exc).__name__}) from exc
        usage: UsageReport | None
        if command.sends:
            candidate, child_usage = await self._execute_sends(stage_name, definition, candidate, command)
            usage = command.usage.combined_with(child_usage) if command.usage is not None else child_usage
        else:
            usage = command.usage
        return command, self._clone_state(candidate, boundary=f"stage:{stage_name}:candidate"), usage

    async def _validate_stage(self, definition: _StageDefinition[StateT], stage_name: str, state_before: StateT, result: StageResult[StateT]) -> _ValidationDecision:
        # Runs stage gates against isolated candidate and read-only observations.
        projection = self.events.require_projection()
        context = ValidationContext(self.run_id, ValidationPhase.STAGE, stage_name, self._clone_state(state_before, boundary="validation_before"), self._clone_state(result.state, boundary="validation_candidate"), result, result.outcome, None, tuple(projection.feedback), projection.observations, projection.metadata)
        return await self.validators.evaluate(definition.validators, context)

    async def _advance(self, initial: _StageDecision[StateT]) -> str | StateMachineResult[StateT] | None:
        # Resolves selection/guard redirects until a route commits, suspends, or detours.
        decision = initial
        while True:
            selected = await self._select_route(decision)
            budget = BudgetLedger(self.definition.settings.budget, cost_model=self.definition.settings.cost_model, snapshot=self.events.require_projection().budget)
            sequence = budget.consume_transition()
            await self.events.emit(
                WorkflowEventType.TRANSITION_SELECTED,
                stage=decision.source,
                payload={"sequence": sequence, "source": decision.source, "outcome": decision.outcome, "target": selected.target, "branch_key": selected.branch_key, "router": selected.router, "trigger": decision.trigger, "command": selected.command, "budget": _budget_to_dict(budget.snapshot())},
            )
            started = time.perf_counter()
            guards = await self._run_guards(decision, selected)
            if guards.must_raise:
                self._raise_validation(decision.source, guards.result, ValidationPhase.TRANSITION, target=selected.target)
            if not guards.passed:
                result = guards.result or ValidationResult.rejected(self.definition.settings.validation_error_outcome, "Transition guard rejected the candidate.")
                feedback = self._validation_feedback("transition_guard", decision.source, result, guards.records)
                record = TransitionRecord(sequence, decision.source, selected.target, decision.outcome, False, decision.trigger, guards.records, _duration_ms(started))
                await self.events.emit(WorkflowEventType.TRANSITION_REJECTED, stage=decision.source, payload={"transition": _transition_to_dict(record), "feedback": _feedback_to_dict(feedback), "target": selected.target, "code": result.code})
                projection = self.events.require_projection()
                decision = _StageDecision(decision.source, projection.state, projection.state, StageResult(projection.state, result.code, decision.command.metadata), WorkflowCommand(outcome=result.code, metadata=decision.command.metadata), False, "transition_guard", (*decision.feedback, feedback), decision.execution)
                continue
            approval_result = await self._maybe_suspend_approval(decision, selected, sequence, guards.records, started)
            if approval_result is not None:
                return approval_result
            record = TransitionRecord(sequence, decision.source, selected.target, decision.outcome, True, decision.trigger, guards.records, _duration_ms(started))
            detoured = await self._maybe_enter_detour(decision, selected, record)
            if detoured:
                return None
            return await self._commit_transition(decision, selected, record)

    async def _select_route(self, decision: _StageDecision[StateT]) -> _SelectedRoute[StateT]:
        # Resolves command goto separately from semantic outcome/conditional routing.
        if decision.command.goto is not None:
            command_route = self.definition.command_routes.get((decision.source, decision.command.goto))
            if command_route is None:
                raise WorkflowCommandError("WorkflowCommand.goto is not authorized by a declared command edge.", details={"run_id": self.run_id, "stage": decision.source, "goto": decision.command.goto, "allowed_targets": sorted(target for source, target in self.definition.command_routes if source == decision.source)})
            return _SelectedRoute(command_route, command=True)
        outcome_route = self.definition.routes.get((decision.source, decision.outcome))
        if outcome_route is None:
            raise WorkflowRoutingError("No semantic route is declared for the stage outcome.", details={"run_id": self.run_id, "stage": decision.source, "outcome": decision.outcome})
        if isinstance(outcome_route, _DirectRoute):
            return _SelectedRoute(outcome_route)
        projection = self.events.require_projection()
        context = RoutingContext(self.run_id, decision.source, self._clone_state(decision.candidate_state, boundary="routing_candidate"), StageResult(self._clone_state(decision.candidate_state, boundary="routing_result"), decision.outcome, decision.command.metadata), decision.feedback, projection.observations, projection.metadata)
        router_name = _router_name(outcome_route.router)
        try:
            raw_key = await outcome_route.router.route(context)
        except Exception as exc:
            raise WorkflowRoutingError("Conditional workflow router failed.", details={"run_id": self.run_id, "stage": decision.source, "router": router_name, "error_type": type(exc).__name__}) from exc
        key = raw_key.strip() if isinstance(raw_key, str) else ""
        selected = outcome_route.routes.get(key)
        if selected is None:
            raise WorkflowRoutingError("Conditional workflow router returned an undeclared key.", details={"run_id": self.run_id, "stage": decision.source, "router": router_name, "branch_key": key or "<empty>", "available_keys": tuple(outcome_route.routes)})
        return _SelectedRoute(selected, branch_key=key, router=router_name)

    async def _run_guards(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT]) -> _ValidationDecision:
        # Evaluates target guards against candidate state before approval or commit.
        projection = self.events.require_projection()
        context = ValidationContext(
            self.run_id,
            ValidationPhase.TRANSITION,
            decision.source,
            self._clone_state(projection.state, boundary="guard_before"),
            self._clone_state(decision.candidate_state, boundary="guard_candidate"),
            StageResult(self._clone_state(decision.candidate_state, boundary="guard_result"), decision.outcome, decision.command.metadata),
            decision.outcome,
            selected.target,
            decision.feedback,
            projection.observations,
            projection.metadata,
        )
        return await self.validators.evaluate(selected.route.guards, context)

    async def _maybe_suspend_approval(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT], sequence: int, validations: tuple[ValidationRecord, ...], started: float) -> StateMachineResult[StateT] | None:
        # Persists a fully guarded candidate when required edge/risk policy requests input.
        projection = self.events.require_projection()
        gate = selected.route.approval
        context = ApprovalContext(self.run_id, decision.source, selected.target, decision.outcome, selected.route.risk, gate, projection.metadata)
        optional = self.confirmation_policy.requires_confirmation(context)
        required = (gate.required if gate is not None else False) or optional
        if not required:
            return None
        if gate is None:
            raise WorkflowApprovalError("Confirmation policy selected an edge without ApprovalGate rejection behavior.", details={"run_id": self.run_id, "stage": decision.source, "target": selected.target})
        request_id = f"wreq_{uuid4().hex}"
        pending = PendingRequest(request_id, PendingRequestKind.APPROVAL, decision.source, gate.reason or f"Approve transition to '{selected.target}'?", {"target": selected.target, "risk": selected.route.risk.name})
        transition = TransitionRecord(sequence, decision.source, selected.target, decision.outcome, False, decision.trigger, validations, _duration_ms(started))
        pending_data = {
            "source": decision.source,
            "target": selected.target,
            "outcome": decision.outcome,
            "trigger": decision.trigger,
            "command": selected.command,
            "candidate_state": self.definition.state_schema.encode(decision.candidate_state),
            "can_commit": decision.can_commit,
            "feedback": [_feedback_to_dict(item) for item in decision.feedback],
            "signals": [{"signal_type": item.signal_type, "source": item.source, "data": dict(item.data)} for item in decision.command.signals],
            "transition_sequence": sequence,
            "transition": _transition_to_dict(transition),
            "rejection_outcome": gate.rejection_outcome,
            "branch_key": selected.branch_key,
            "router": selected.router,
        }
        await self.events.emit(WorkflowEventType.APPROVAL_REQUESTED, stage=decision.source, payload={"pending": _pending_to_dict(pending), "pending_data": pending_data, "lifecycle": WorkflowLifecycleStatus.WAITING_FOR_CONFIRMATION.value})
        await self.events.checkpoint(force=True)
        return await self._result()

    async def _resume_approval(self, command: ResumeCommand) -> StateMachineResult[StateT]:
        # Continues the persisted edge exactly, or routes rejection without rerunning stage.
        projection = self.events.require_projection()
        pending = projection.pending
        if pending is None:
            raise WorkflowApprovalError("Approval response has no pending request.", details={"run_id": self.run_id})
        data = dict(projection.pending_data)
        source = str(data["source"])
        original_record = _transition_record_from_payload(data["transition"])
        response_record = replace(original_record, accepted=bool(command.approved))
        response_payload = {"request_id": command.request_id, "approved": command.approved, "value": command.value, "pending_data": data}
        if not command.approved:
            response_payload["transition"] = _transition_to_dict(response_record)
        await self.events.emit(WorkflowEventType.APPROVAL_RESPONDED, stage=source, payload=response_payload)
        continuation = {**data, "mode": "approval_response", "response_approved": bool(command.approved), "response_request_id": command.request_id}
        return await self._continue_approval_response(continuation)

    async def _continue_approval_response(self, data: Mapping[str, Any]) -> StateMachineResult[StateT]:
        # Replays a persisted approval response boundary without asking or rerunning work.
        source = str(data["source"])
        target = str(data["target"])
        approved = bool(data.get("response_approved"))
        request_id = str(data.get("response_request_id") or "persisted-approval")
        original_record = _transition_record_from_payload(data["transition"])
        response_record = replace(original_record, accepted=approved)
        if not approved:
            outcome = str(data["rejection_outcome"])
            feedback = WorkflowFeedback("approval_rejected", source, outcome, "The pending transition was rejected by a human.", {"target": target, "request_id": request_id})
            state = self.events.require_projection().state
            execution = self.events.require_projection().stages[-1] if self.events.require_projection().stages else _placeholder_execution(source)
            decision = _StageDecision(source, state, state, StageResult(state, outcome), WorkflowCommand(outcome=outcome), False, "approval_rejection", (feedback,), execution)
            terminal = await self._advance(decision)
            if isinstance(terminal, str):
                return await self._finish(terminal)
            if isinstance(terminal, StateMachineResult):
                return terminal
            return await self._drive()
        candidate = self.definition.state_schema.decode(data["candidate_state"])
        route = self._compiled_route(source, target, bool(data.get("command", False)), str(data["outcome"]))
        selected = _SelectedRoute(route, data.get("branch_key"), data.get("router"), bool(data.get("command", False)))
        signals = tuple(WorkflowSignal(str(item["signal_type"]), str(item["source"]), item.get("data", {})) for item in data.get("signals", ()))
        state_before = self.events.require_projection().state
        execution = self.events.require_projection().stages[-1] if self.events.require_projection().stages else _placeholder_execution(source)
        replay_command: WorkflowCommand[StateT] = WorkflowCommand(goto=target, signals=signals) if selected.command else WorkflowCommand(outcome=str(data["outcome"]), signals=signals)
        decision = _StageDecision(source, state_before, candidate, StageResult(candidate, str(data["outcome"])), replay_command, bool(data.get("can_commit", True)), str(data.get("trigger", "approval")), tuple(_feedback_from_payload(item) for item in data.get("feedback", ())), execution)
        detoured = await self._maybe_enter_detour(decision, selected, response_record)
        if detoured:
            return await self._drive()
        terminal = await self._commit_transition(decision, selected, response_record)
        return await self._finish(terminal) if isinstance(terminal, str) else await self._drive()

    def _compiled_route(self, source: str, target: str, command: bool, outcome: str) -> _DirectRoute[StateT]:
        # Re-resolves a persisted continuation against the same compiled definition.
        if command:
            command_route = self.definition.command_routes.get((source, target))
            if command_route is not None:
                return command_route
        outcome_route = self.definition.routes.get((source, outcome))
        if isinstance(outcome_route, _DirectRoute) and outcome_route.target == target:
            return outcome_route
        if isinstance(outcome_route, _BranchRoute):
            matches = [value for value in outcome_route.routes.values() if value.target == target]
            if len(matches) == 1:
                return matches[0]
        raise WorkflowResumeError("Persisted continuation is no longer authorized by the compiled graph.", details={"source": source, "target": target, "outcome": outcome})

    async def _maybe_enter_detour(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT], record: TransitionRecord) -> bool:
        # Evaluates emitted signals in order and pushes the first matching declared rule.
        if not decision.command.signals or not self.definition.detours:
            return False
        for signal in decision.command.signals:
            await self.events.emit(WorkflowEventType.SIGNAL_RECORDED, stage=decision.source, payload={"signal_type": signal.signal_type, "source": signal.source, "data": dict(signal.data)})
        matches = [(rule, signal) for rule in self.definition.detours for signal in decision.command.signals if rule.rule.matcher.matches(signal)]
        if not matches:
            return False
        rule, signal = matches[0]
        projection = self.events.require_projection()
        budget = BudgetLedger(self.definition.settings.budget, cost_model=self.definition.settings.cost_model, snapshot=projection.budget)
        budget.consume_transition()
        budget.enter_detour()
        continuation = {
            "candidate_state": self.definition.state_schema.encode(decision.candidate_state),
            "target": selected.target,
            "source": decision.source,
            "outcome": decision.outcome,
            "can_commit": decision.can_commit,
            "feedback": [_feedback_to_dict(item) for item in decision.feedback],
            "transition": _transition_to_dict(record),
            "active_stage": {
                "stage": decision.source,
                "visit": decision.execution.visit,
                "attempt": decision.execution.attempt,
                "idempotency_key": f"{self.run_id}:{decision.source}:{decision.execution.visit}",
            },
        }
        frame = DetourFrame(rule.rule.rule_id, decision.source, rule.target, rule.return_mode, signal, continuation)
        await self.events.emit(WorkflowEventType.DETOUR_ENTERED, stage=decision.source, payload={"frame": _detour_to_dict(frame), "target": rule.target, "candidate_rule_ids": [item[0].rule.rule_id for item in matches], "budget": _budget_to_dict(budget.snapshot())})
        await self.events.checkpoint(force=True)
        return True

    async def _enter_tool_detour(self, decision: _StageDecision[StateT]) -> None:
        # Persists an immediate post-tool detour and retries its interrupted source on return.
        if not decision.command.signals or not self.definition.detours:
            raise WorkflowDetourError("Tool-bound detour requested without emitted signals or declared rules.", details={"run_id": self.run_id, "stage": decision.source})
        for signal in decision.command.signals:
            await self.events.emit(WorkflowEventType.SIGNAL_RECORDED, stage=decision.source, payload={"signal_type": signal.signal_type, "source": signal.source, "data": dict(signal.data)})
        candidate_ids = decision.command.metadata.get("candidate_rule_ids", ())
        allowed_ids = {str(value) for value in candidate_ids} if isinstance(candidate_ids, (tuple, list, set, frozenset)) else set()
        matches = [
            (definition, signal)
            for definition in self.definition.detours
            for signal in decision.command.signals
            if (not allowed_ids or definition.rule.rule_id in allowed_ids) and definition.rule.matcher.matches(signal)
        ]
        if not matches:
            raise WorkflowDetourError("Tool-bound detour evidence no longer matches the compiled graph.", details={"run_id": self.run_id, "stage": decision.source, "candidate_rule_ids": sorted(allowed_ids)})
        definition, signal = matches[0]
        budget = BudgetLedger(self.definition.settings.budget, cost_model=self.definition.settings.cost_model, snapshot=self.events.require_projection().budget)
        budget.consume_transition()
        budget.enter_detour()
        frame = DetourFrame(
            definition.rule.rule_id,
            decision.source,
            definition.target,
            DetourReturnMode.RETRY_SOURCE,
            signal,
            {
                "tool_boundary": True,
                "active_stage": {
                    "stage": decision.source,
                    "visit": decision.execution.visit,
                    "attempt": decision.execution.attempt,
                    "idempotency_key": f"{self.run_id}:{decision.source}:{decision.execution.visit}",
                },
            },
        )
        await self.events.emit(
            WorkflowEventType.DETOUR_ENTERED,
            stage=decision.source,
            payload={
                "frame": _detour_to_dict(frame),
                "target": definition.target,
                "candidate_rule_ids": [item[0].rule.rule_id for item in matches],
                "budget": _budget_to_dict(budget.snapshot()),
            },
        )
        await self.events.checkpoint(force=True)

    async def _return_from_detour(self, decision: _StageDecision[StateT]) -> str | StateMachineResult[StateT] | None:
        # Pops the exact top frame and retries source or resumes its saved target.
        projection = self.events.require_projection()
        if not projection.detour_stack:
            raise WorkflowDetourError("WorkflowCommand requested detour return with an empty stack.", details={"run_id": self.run_id, "stage": decision.source})
        if decision.command.update or decision.command.sends or decision.command.signals:
            raise WorkflowDetourError("Detour return commands cannot also update state, send children, or emit signals.", details={"stage": decision.source})
        frame = projection.detour_stack[-1]
        if decision.command.return_from_detour != frame.rule_id:
            raise WorkflowDetourError("Detour return does not match the active rule.", details={"expected_rule_id": frame.rule_id, "actual_rule_id": decision.command.return_from_detour})
        budget = BudgetLedger(self.definition.settings.budget, cost_model=self.definition.settings.cost_model, snapshot=projection.budget)
        budget.consume_transition()
        budget.leave_detour()
        if frame.return_mode is DetourReturnMode.RETRY_SOURCE:
            feedback = WorkflowFeedback("detour_return", decision.source, frame.rule_id, "Validation detour completed; retry the interrupted source stage.", {"rule_id": frame.rule_id})
            await self.events.emit(WorkflowEventType.DETOUR_RETURNED, stage=decision.source, payload={"rule_id": frame.rule_id, "target": frame.source_stage, "feedback": _feedback_to_dict(feedback), "active_stage": frame.continuation.get("active_stage"), "budget": _budget_to_dict(budget.snapshot())})
            await self.events.checkpoint(force=True)
            return None
        continuation = frame.continuation
        target = str(continuation["target"])
        await self.events.emit(WorkflowEventType.DETOUR_RETURNED, stage=decision.source, payload={"rule_id": frame.rule_id, "target": target, "budget": _budget_to_dict(budget.snapshot())})
        candidate = self.definition.state_schema.decode(continuation["candidate_state"])
        source = str(continuation["source"])
        route = self._compiled_route(source, target, False, str(continuation["outcome"]))
        selected = _SelectedRoute(route)
        record = _transition_record_from_payload(continuation["transition"])
        resumed = _StageDecision(source, projection.state, candidate, StageResult(candidate, str(continuation["outcome"])), WorkflowCommand(outcome=str(continuation["outcome"])), bool(continuation.get("can_commit", True)), "detour_resume", tuple(_feedback_from_payload(item) for item in continuation.get("feedback", ())), decision.execution)
        terminal = await self._commit_transition(resumed, selected, replace(record, accepted=True))
        return terminal

    async def _commit_transition(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT], record: TransitionRecord) -> str | None:
        # Appends the sole authoritative candidate commit and enters its declared target.
        projection = self.events.require_projection()
        committed = self._clone_state(decision.candidate_state if decision.can_commit else projection.state, boundary="state_commit")
        feedback = () if decision.can_commit else decision.feedback
        await self.events.emit(WorkflowEventType.STATE_COMMITTED, stage=decision.source, payload={"state": self.definition.state_schema.encode(committed), "target": selected.target, "transition": _transition_to_dict(record), "feedback": [_feedback_to_dict(item) for item in feedback]})
        await self.events.checkpoint()
        return selected.target if selected.target in self.definition.terminals else None

    async def _execute_sends(self, stage_name: str, definition: _StageDefinition[StateT], candidate: StateT, command: WorkflowCommand[StateT]) -> tuple[StateT, UsageReport]:
        # Runs isolated children concurrently, joins in Send order, and charges usage.
        if not self.definition.subgraphs:
            raise WorkflowSubgraphError("WorkflowCommand.sends used by a graph with no declared subgraphs.", details={"stage": stage_name})
        projection = self.events.require_projection()
        active = projection.pending_data.get("active_stage")
        invocation_id = str(active.get("idempotency_key")) if isinstance(active, Mapping) and active.get("idempotency_key") else f"{self.run_id}:{stage_name}:unknown"
        sends_payload = [{"subgraph": send.subgraph, "key": send.key, "child_run_id": _planned_child_run_id(self.run_id, invocation_id, send), "input": send.input, "metadata": dict(send.metadata)} for send in command.sends]
        await self.events.emit(WorkflowEventType.SENDS_STARTED, stage=stage_name, payload={"sends": sends_payload})
        executor = SubgraphExecutor(self.definition.subgraphs, max_concurrency=self.definition.settings.budget.max_subgraph_concurrency)
        projection = self.events.require_projection()
        summaries = await executor.execute(command.sends, parent_state=candidate, parent_run_id=self.run_id, invocation_id=invocation_id, metadata=projection.metadata, store=self.store, parent_budget=self.definition.settings.budget, parent_snapshot=projection.budget)
        usage = UsageReport.zero()
        joined = candidate
        records: list[dict[str, Any]] = []
        suspended = False
        for send, summary in zip(command.sends, summaries, strict=True):
            lifecycle = getattr(summary.lifecycle, "value", summary.lifecycle)
            binding = self.definition.subgraphs[send.subgraph]
            record = _child_record(send, summary)
            records.append(record)
            if lifecycle in (WorkflowLifecycleStatus.WAITING_FOR_CONFIRMATION.value, WorkflowLifecycleStatus.INTERRUPTED.value):
                suspended = True
                await self.events.emit(WorkflowEventType.CHILD_SUSPENDED, stage=stage_name, payload={"subgraph": send.subgraph, "key": send.key, "child_run_id": summary.child_run_id, "lifecycle": lifecycle, "pending": record.get("pending")})
                continue
            if lifecycle == WorkflowLifecycleStatus.ERROR.value and binding.failure_policy is ChildFailurePolicy.COLLECT:
                usage = usage.combined_with(summary.usage)
                await self.events.emit(WorkflowEventType.CHILD_FINISHED, stage=stage_name, payload={"subgraph": send.subgraph, "key": send.key, "child_run_id": summary.child_run_id, "lifecycle": lifecycle, "terminal": summary.terminal, "usage": _usage_to_dict(summary.usage), "error": _error_to_dict(summary.error)})
                continue
            if lifecycle != WorkflowLifecycleStatus.FINISHED.value:
                raise WorkflowSubgraphError("Child subgraph suspended before deterministic join.", details={"subgraph": send.subgraph, "key": send.key, "child_run_id": summary.child_run_id, "lifecycle": getattr(summary.lifecycle, "value", summary.lifecycle)})
            usage = usage.combined_with(summary.usage)
            await self.events.emit(WorkflowEventType.CHILD_FINISHED, stage=stage_name, payload={"subgraph": send.subgraph, "key": send.key, "child_run_id": summary.child_run_id, "lifecycle": lifecycle, "terminal": summary.terminal, "usage": _usage_to_dict(summary.usage), "error": _error_to_dict(summary.error)})
        if suspended:
            raise _SubgraphSuspension(command, candidate, records)
        for record in records:
            if record["lifecycle"] == WorkflowLifecycleStatus.FINISHED.value:
                joined = self.definition.state_schema.apply(joined, record.get("update", {}), allowed_writes=definition.writes)
        return joined, usage

    async def _suspend_subgraphs(self, stage: str, visit: int, attempt: int, idempotency_key: str, state_before: StateT, suspension: _SubgraphSuspension, duration_ms: float) -> StateMachineResult[StateT]:
        # Persists completed/suspended siblings so the parent stage is never relaunched.
        command = suspension.command
        data = {
            "mode": "subgraph",
            "source": stage,
            "visit": visit,
            "attempt": attempt,
            "idempotency_key": idempotency_key,
            "state_before": self.definition.state_schema.encode(state_before),
            "base_candidate": self.definition.state_schema.encode(suspension.base_candidate),
            "signals": [{"signal_type": item.signal_type, "source": item.source, "data": dict(item.data)} for item in command.signals],
            "metadata": dict(command.metadata),
            "usage": _usage_to_dict(command.usage) if command.usage is not None else None,
            "children": list(suspension.children),
            "duration_ms": duration_ms,
        }
        return await self._persist_next_subgraph_request(data)

    async def _persist_next_subgraph_request(self, data: Mapping[str, Any]) -> StateMachineResult[StateT]:
        # Selects the first input-ordered suspended child and checkpoints its exact request.
        for child in data.get("children", ()):
            pending_data = child.get("pending") if isinstance(child, Mapping) else None
            if not isinstance(pending_data, Mapping):
                continue
            child_pending = _pending_from_payload(pending_data)
            pending = PendingRequest(child_pending.request_id, PendingRequestKind.SUBGRAPH, str(data["source"]), child_pending.prompt, {"subgraph": child.get("subgraph"), "key": child.get("key"), "child_run_id": child.get("child_run_id"), "child_request_kind": child_pending.kind.value, **dict(child_pending.metadata)})
            await self.events.emit(WorkflowEventType.INTERRUPT_REQUESTED, stage=str(data["source"]), payload={"pending": _pending_to_dict(pending), "pending_data": data, "lifecycle": WorkflowLifecycleStatus.INTERRUPTED.value})
            await self.events.checkpoint(force=True)
            return await self._result()
        raise WorkflowSubgraphError("Subgraph suspension has no resumable child request.", details={"run_id": self.run_id, "stage": data.get("source")})

    async def _resume_subgraph(self, command: ResumeCommand) -> StateMachineResult[StateT]:
        # Resumes one child, preserves completed siblings, and joins only after all finish.
        projection = self.events.require_projection()
        data = deepcopy(dict(projection.pending_data))
        children = list(data.get("children", ()))
        matched_index: int | None = None
        for index, child in enumerate(children):
            pending = child.get("pending") if isinstance(child, Mapping) else None
            if isinstance(pending, Mapping) and pending.get("request_id") == command.request_id:
                matched_index = index
                break
        if matched_index is None:
            raise WorkflowSubgraphError("Parent subgraph request no longer identifies a suspended child.", details={"run_id": self.run_id, "request_id": command.request_id})
        child = dict(children[matched_index])
        subgraph_name = str(child["subgraph"])
        binding = self.definition.subgraphs[subgraph_name]
        send = _send_from_child_record(child)
        effective_data = child.get("effective_budget")
        budget = _workflow_budget_from_dict(effective_data) if isinstance(effective_data, Mapping) else _effective_child_budget(binding, send, self.definition.settings.budget)
        child_machine = binding.machine._with_budget(budget)
        try:
            result = await child_machine.aresume(str(child["child_run_id"]), command=command, store=self.store)
        except WorkflowError as exc:
            if binding.failure_policy is not ChildFailurePolicy.COLLECT or not hasattr(exc, "result"):
                raise
            result = exc.result
        lifecycle = getattr(result.lifecycle, "value", result.lifecycle)
        child["lifecycle"] = lifecycle
        child["terminal"] = result.terminal
        child["usage"] = _usage_to_dict(result.usage)
        child["error"] = _error_to_dict(result.error)
        child["pending"] = _pending_to_dict(result.pending)
        if lifecycle == WorkflowLifecycleStatus.FINISHED.value:
            update = binding.summary_mapper(result, send)
            if not isinstance(update, Mapping):
                raise WorkflowSubgraphError("Subgraph summary mapper must return a mapping after resume.", details={"subgraph": subgraph_name, "key": send.key, "actual_type": type(update).__name__})
            undeclared = set(update) - set(binding.writes)
            if undeclared:
                raise WorkflowSubgraphError("Resumed subgraph summary wrote undeclared parent channels.", details={"subgraph": subgraph_name, "key": send.key, "undeclared": sorted(undeclared), "allowed": sorted(binding.writes)})
            child["update"] = dict(update)
        children[matched_index] = child
        data["children"] = children
        data["last_resumed_child_index"] = matched_index
        await self.events.emit(WorkflowEventType.INTERRUPT_RESPONDED, stage=str(data["source"]), payload={"request_id": command.request_id, "value": command.value, "approved": command.approved, "pending_data": data})
        return await self._continue_subgraph_boundary(data)

    async def _continue_subgraph_boundary(self, source_data: Mapping[str, Any]) -> StateMachineResult[StateT]:
        # Completes a persisted child response event before selecting the next join boundary.
        data = deepcopy(dict(source_data))
        children = list(data.get("children", ()))
        resumed_index = data.pop("last_resumed_child_index", None)
        if isinstance(resumed_index, int) and 0 <= resumed_index < len(children):
            child = children[resumed_index]
            lifecycle = str(child.get("lifecycle"))
            child_event = WorkflowEventType.CHILD_FINISHED if lifecycle in (WorkflowLifecycleStatus.FINISHED.value, WorkflowLifecycleStatus.ERROR.value) else WorkflowEventType.CHILD_SUSPENDED
            await self.events.emit(
                child_event,
                stage=str(data["source"]),
                payload={
                    "subgraph": child.get("subgraph"),
                    "key": child.get("key"),
                    "child_run_id": child.get("child_run_id"),
                    "lifecycle": lifecycle,
                    "terminal": child.get("terminal"),
                    "usage": child.get("usage"),
                    "error": child.get("error"),
                    "pending": child.get("pending"),
                    "pending_data": data,
                },
            )
        if any(isinstance(item.get("pending"), Mapping) for item in children):
            return await self._persist_next_subgraph_request(data)
        return await self._complete_subgraph_stage(data)

    async def _complete_subgraph_stage(self, data: Mapping[str, Any]) -> StateMachineResult[StateT]:
        # Applies input-ordered child summaries, validates the parent candidate, and routes.
        source = str(data["source"])
        definition = self.definition.stages[source]
        candidate = self.definition.state_schema.decode(data["base_candidate"])
        usage = _usage_from_dict(data["usage"]) if isinstance(data.get("usage"), Mapping) else UsageReport.zero()
        for child in data.get("children", ()):
            lifecycle = str(child.get("lifecycle"))
            child_usage = _usage_from_dict(child.get("usage", {}))
            usage = usage.combined_with(child_usage)
            if lifecycle == WorkflowLifecycleStatus.FINISHED.value:
                candidate = self.definition.state_schema.apply(candidate, child.get("update", {}), allowed_writes=definition.writes)
            elif lifecycle != WorkflowLifecycleStatus.ERROR.value or self.definition.subgraphs[str(child["subgraph"])].failure_policy is not ChildFailurePolicy.COLLECT:
                raise WorkflowSubgraphError("Child batch cannot join from a nonterminal lifecycle.", details={"subgraph": child.get("subgraph"), "key": child.get("key"), "lifecycle": lifecycle})
        if not _usage_is_zero(usage):
            await _charge_usage(self.definition, self.events, source, usage)
        state_before = self.definition.state_schema.decode(data["state_before"])
        signals = tuple(WorkflowSignal(str(item["signal_type"]), str(item["source"]), item.get("data", {})) for item in data.get("signals", ()))
        metadata = dict(data.get("metadata", {}))
        resumed_command: WorkflowCommand[StateT] = WorkflowCommand(outcome="success", signals=signals, metadata=metadata)
        stage_result = StageResult(candidate, "success", metadata)
        validation = await self._validate_stage(definition, source, state_before, stage_result)
        if validation.must_raise:
            self._raise_validation(source, validation.result, ValidationPhase.STAGE)
        record = StageExecution(source, int(data["visit"]), int(data["attempt"]), "success", validation.passed, float(data.get("duration_ms", 0.0)), metadata, validation.records, state_before=self._snapshot(state_before), candidate_state=self._snapshot(candidate))
        await self.events.emit(WorkflowEventType.STAGE_FINISHED, stage=source, payload={"execution": _stage_to_dict(record)})
        if validation.passed:
            decision = _StageDecision(source, state_before, candidate, stage_result, resumed_command, True, "subgraph_join", tuple(self.events.require_projection().feedback), record)
        else:
            result = validation.result or ValidationResult.rejected(self.definition.settings.validation_error_outcome, "Stage validation rejected the subgraph join.")
            feedback = self._validation_feedback("stage_validation", source, result, validation.records)
            state = self.events.require_projection().state
            decision = _StageDecision(source, state, state, StageResult(state, result.code, metadata), WorkflowCommand(outcome=result.code, metadata=metadata), False, "stage_validation", (feedback,), record)
        terminal = await self._advance(decision)
        if isinstance(terminal, str):
            return await self._finish(terminal)
        if isinstance(terminal, StateMachineResult):
            return terminal
        return await self._drive()

    async def _bounded(self, awaitable: Any) -> Any:
        # Enforces the remaining accumulated execution-time ceiling across resume calls.
        limit = self.definition.settings.budget.timeout_seconds
        if limit is None:
            return await awaitable
        projection = self.events.require_projection()
        consumed = (sum(item.duration_ms for item in projection.stages) + sum(item.duration_ms for item in projection.transitions)) / 1000.0
        remaining = limit - consumed
        if remaining <= 0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise WorkflowBudgetError("Workflow elapsed-time budget exhausted before new work.", details={"run_id": self.run_id, "elapsed_seconds": consumed, "limit": limit})
        try:
            async with asyncio.timeout(remaining):
                return await awaitable
        except TimeoutError as exc:
            raise WorkflowBudgetError("Workflow elapsed-time budget exceeded.", details={"run_id": self.run_id, "elapsed_seconds": limit, "limit": limit}) from exc

    async def _suspend_interrupt(self, stage: str, visit: int, attempt: int, idempotency_key: str, request: WorkflowInterrupt, ordinal: int) -> StateMachineResult[StateT]:
        # Persists a replay ordinal and returns INTERRUPTED without retaining Python frames.
        request_id = f"wreq_{uuid4().hex}"
        resume_key = f"{stage}:{visit}:{ordinal}"
        pending = PendingRequest(request_id, PendingRequestKind.INTERRUPT, stage, request.prompt, {"namespace": request.namespace, "ordinal": ordinal, "schema": request.schema.__name__ if request.schema else None, **dict(request.metadata)})
        active = {"stage": stage, "visit": visit, "attempt": attempt, "idempotency_key": idempotency_key}
        pending_data = {"mode": "stage", "resume_key": resume_key, "active_stage": active, "schema_name": request.schema.__name__ if request.schema else None}
        await self.events.emit(WorkflowEventType.INTERRUPT_REQUESTED, stage=stage, payload={"pending": _pending_to_dict(pending), "pending_data": pending_data, "lifecycle": WorkflowLifecycleStatus.INTERRUPTED.value})
        await self.events.checkpoint(force=True)
        return await self._result()

    async def _suspend_command_interrupt(self, decision: _StageDecision[StateT], visit: int, attempt: int, idempotency_key: str) -> StateMachineResult[StateT]:
        # Suspends a completed stage command and persists its candidate continuation.
        request = decision.command.interrupt
        if request is None:
            raise WorkflowInterruptError("Command interrupt suspension requires WorkflowInterrupt.", details={"stage": decision.source})
        request_id = f"wreq_{uuid4().hex}"
        pending = PendingRequest(request_id, PendingRequestKind.INTERRUPT, decision.source, request.prompt, {"namespace": request.namespace, "schema": request.schema.__name__ if request.schema else None, **dict(request.metadata)})
        pending_data = {
            "mode": "command",
            "candidate_state": self.definition.state_schema.encode(decision.candidate_state),
            "source": decision.source,
            "outcome": "success",
            "signals": [{"signal_type": item.signal_type, "source": item.source, "data": dict(item.data)} for item in decision.command.signals],
            "metadata": dict(decision.command.metadata),
            "visit": visit,
            "attempt": attempt,
            "idempotency_key": idempotency_key,
        }
        await self.events.emit(WorkflowEventType.INTERRUPT_REQUESTED, stage=decision.source, payload={"pending": _pending_to_dict(pending), "pending_data": pending_data, "lifecycle": WorkflowLifecycleStatus.INTERRUPTED.value})
        await self.events.checkpoint(force=True)
        return await self._result()

    async def _resume_command_interrupt(self, data: Mapping[str, Any], value: Any) -> StateMachineResult[StateT]:
        # Routes a completed command candidate after external input without rerunning stage.
        source = str(data["source"])
        candidate = self.definition.state_schema.decode(data["candidate_state"])
        state = self.events.require_projection().state
        signals = tuple(WorkflowSignal(str(item["signal_type"]), str(item["source"]), item.get("data", {})) for item in data.get("signals", ()))
        metadata = {**dict(data.get("metadata", {})), "interrupt_resume_value": value}
        command: WorkflowCommand[StateT] = WorkflowCommand(outcome=str(data.get("outcome", "success")), signals=signals, metadata=metadata)
        execution = self.events.require_projection().stages[-1] if self.events.require_projection().stages else _placeholder_execution(source)
        decision = _StageDecision(source, state, candidate, StageResult(candidate, command.outcome or "success", metadata), command, True, "command_interrupt", tuple(self.events.require_projection().feedback), execution)
        terminal = await self._advance(decision)
        if isinstance(terminal, str):
            return await self._finish(terminal)
        if isinstance(terminal, StateMachineResult):
            return terminal
        return await self._drive()

    async def _finish(self, terminal: str) -> StateMachineResult[StateT]:
        # Appends normal terminal/lifecycle evidence and an immutable final checkpoint.
        status = self.definition.terminals[terminal]
        await self.events.emit(WorkflowEventType.RUN_FINISHED, stage=terminal, payload={"workflow": self.definition.name, "terminal": terminal, "terminal_status": status.value})
        await self.events.checkpoint(force=True)
        return await self._result()

    async def _handle_escape(self, error: BaseException) -> StateMachineResult[StateT]:
        # Records best-effort error/cancellation evidence, attaches a snapshot, then raises.
        if isinstance(error, asyncio.CancelledError) or not isinstance(error, Exception):
            await self._record_cancel(error)
            raise error
        wrapped: WorkflowError
        if isinstance(error, WorkflowError):
            wrapped = error
        else:
            wrapped = WorkflowExecutionError("Workflow failed with an unexpected runtime error.", details={"run_id": self.run_id, "workflow": self.definition.name, "error_type": type(error).__name__})
        projection = self.events.projection
        if projection is not None and projection.lifecycle not in (WorkflowLifecycleStatus.ERROR, WorkflowLifecycleStatus.FINISHED):
            record = WorkflowErrorRecord.from_error(wrapped)
            event_type = WorkflowEventType.STUCK_DETECTED if isinstance(wrapped, WorkflowStuckError) else WorkflowEventType.RUN_FAILED
            try:
                await self.events.emit(event_type, stage=projection.current_stage, payload={"error": _error_to_dict(record)})
                await self.events.checkpoint(force=True)
                result = await self._result()
                setattr(wrapped, "result", result)
            except BaseException as persistence_error:
                if isinstance(wrapped, WorkflowPersistenceError):
                    raise wrapped
                setattr(wrapped, "persistence_error", WorkflowErrorRecord.from_error(persistence_error))
        if wrapped is error:
            raise wrapped
        raise wrapped from error

    async def _record_cancel(self, error: BaseException) -> None:
        # Preserves cancellation while attempting one safe interruption checkpoint.
        projection = self.events.projection
        if projection is None:
            return
        try:
            record = WorkflowErrorRecord.from_error(error)
            await self.events.emit(WorkflowEventType.RUN_CANCELLED, stage=projection.current_stage, payload={"error": _error_to_dict(record)})
            await self.events.checkpoint(force=True)
        except BaseException:
            return

    async def _result(self, *, through_sequence: int | None = None) -> StateMachineResult[StateT]:
        # Builds one immutable public projection plus the complete visible event prefix.
        projection = self.events.require_projection()
        canonical_events = await self.store.events(self.run_id, through_sequence=through_sequence)
        projection.observer_errors[:] = self.events.observer_errors
        return StateMachineResult(
            run_id=self.run_id,
            definition_id=self.definition.definition_id,
            lifecycle=projection.lifecycle,
            terminal_status=projection.terminal_status,
            terminal=projection.terminal,
            state=self._clone_state(projection.state, boundary="result"),
            observations=projection.observations,
            pending=projection.pending,
            usage=projection.usage,
            checkpoint_id=projection.checkpoint_id,
            metadata=projection.metadata,
            stages=tuple(projection.stages),
            transitions=tuple(projection.transitions),
            events=canonical_events,
            observer_errors=tuple(self.events.observer_errors),
            error=projection.error,
            duration_ms=projection.duration_ms,
        )

    def _clone_state(self, value: StateT, *, boundary: str) -> StateT:
        # Round-trips typed state to isolate every executable/inspection boundary.
        try:
            return self.definition.state_schema.validate(value)
        except WorkflowError:
            raise
        except Exception as exc:
            raise WorkflowStateError("Workflow state failed validation or cloning.", details={"run_id": self.run_id, "boundary": boundary, "error_type": type(exc).__name__}) from exc

    def _snapshot(self, value: StateT) -> Any | None:
        # Records encoded state evidence only when explicitly enabled by settings.
        if not self.definition.settings.record_state_snapshots:
            return None
        payload = dict(self.definition.state_schema.encode(value))
        for name, channel in self.definition.state_schema.channels.items():
            if channel.sensitive and name in payload:
                payload[name] = "<sensitive>"
        return payload

    @staticmethod
    def _should_retry(error: Exception, policy: StagePolicy, attempt: int) -> bool:
        # Keeps workflow policy/stuck/budget failures outside user callback retry loops.
        return not isinstance(error, WorkflowError) and attempt < policy.retry.max_attempts and isinstance(error, policy.retry.retry_for)

    @staticmethod
    async def _wait_before_retry(policy: StagePolicy, attempt: int) -> None:
        # Sleeps with deterministic exponential backoff and no jitter.
        delay = policy.retry.delay_seconds * (policy.retry.backoff_multiplier ** (attempt - 1))
        if delay > 0:
            await asyncio.sleep(delay)

    def _validation_feedback(self, kind: str, source: str, result: ValidationResult, records: Sequence[ValidationRecord]) -> WorkflowFeedback:
        # Creates a bounded recovery packet without candidate state or prompt content.
        return WorkflowFeedback(kind, source, result.code, result.feedback, {**dict(result.details), "validators": tuple(record.validator for record in records), "status": result.status.value, "score": result.score})

    def _raise_validation(self, stage: str, result: ValidationResult | None, phase: ValidationPhase, *, target: str | None = None) -> None:
        # Raises the configured non-recoverable validation boundary with safe IDs.
        effective = result or ValidationResult.errored(self.definition.settings.validation_error_outcome, "Validator did not produce a result.")
        raise WorkflowValidationError("Workflow validation did not pass.", details={"run_id": self.run_id, "stage": stage, "phase": phase.value, "target": target, "status": effective.status.value, "code": effective.code})


class StateMachine(Generic[StateT]):
    """Immutable reusable façade around one compiled event-sourced definition."""

    def __init__(self, definition: _CompiledGraph[StateT]) -> None:
        # Stores immutable executable structure and a concurrent process-local default store.
        self._definition = definition
        self._default_store = InMemoryWorkflowStore()

    @property
    def name(self) -> str:
        # Returns the declared graph name.
        return self._definition.name

    @property
    def version(self) -> str | None:
        # Returns the caller-managed behavior version used for durable resume.
        return self._definition.version

    @property
    def definition_id(self) -> str:
        # Returns the deterministic compiled definition fingerprint.
        return self._definition.definition_id

    @property
    def entry(self) -> str:
        # Returns the declared initial executable stage.
        return self._definition.entry

    @property
    def stages(self) -> tuple[str, ...]:
        # Returns executable stage names in declaration order.
        return tuple(self._definition.stages)

    @property
    def terminals(self) -> Mapping[str, Any]:
        # Returns the immutable normal-terminal status map.
        return self._definition.terminals

    @property
    def definition(self) -> Mapping[str, Any]:
        # Exposes canonical JSON-ready structure for state/data-dependency introspection.
        return self._definition.definition_record.structure

    def _with_budget(self, budget: Any) -> "StateMachine[StateT]":
        # Creates a run-local stricter child facade without mutating the compiled parent.
        settings = replace(self._definition.settings, budget=budget, max_transitions=None, timeout_seconds=None)
        return StateMachine(replace(self._definition, settings=settings))

    async def arun(
        self,
        initial_state: StateT,
        *,
        run_id: str | None = None,
        observations: Mapping[str, Any] | None = None,
        ledger: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        observers: Sequence[WorkflowObserver] = (),
        store: WorkflowStore | None = None,
        checkpoint_policy: WorkflowCheckpointPolicy = WorkflowCheckpointPolicy.PER_STEP,
        confirmation_policy: ConfirmationPolicy | None = None,
    ) -> StateMachineResult[StateT]:
        # Starts one isolated run after normalizing compatibility and persistence inputs.
        resolved_run_id = _run_id(run_id)
        if observations is not None and ledger is not None:
            raise WorkflowExecutionError("Use observations or legacy ledger, not both.", details={"run_id": resolved_run_id})
        initial_observations = observations if observations is not None else ledger
        if initial_observations is not None and not isinstance(initial_observations, Mapping):
            raise WorkflowExecutionError("Workflow observations must be a mapping.", details={"run_id": resolved_run_id, "actual_type": type(initial_observations).__name__})
        if metadata is not None and not isinstance(metadata, Mapping):
            raise WorkflowExecutionError("Workflow metadata must be a mapping.", details={"run_id": resolved_run_id, "actual_type": type(metadata).__name__})
        resolved_store = _store(store, self._default_store)
        policy = checkpoint_policy if isinstance(checkpoint_policy, WorkflowCheckpointPolicy) else WorkflowCheckpointPolicy(checkpoint_policy)
        confirmation = _confirmation_policy(confirmation_policy)
        run = _WorkflowRun(self._definition, resolved_store, resolved_run_id, observers=observers, checkpoint_policy=policy, confirmation_policy=confirmation)
        return await run.start(initial_state, initial_observations, metadata)

    async def aresume(
        self,
        run_id: str,
        *,
        command: ResumeCommand | None = None,
        store: WorkflowStore | None = None,
        observers: Sequence[WorkflowObserver] = (),
        confirmation_policy: ConfirmationPolicy | None = None,
        checkpoint_policy: WorkflowCheckpointPolicy = WorkflowCheckpointPolicy.PER_STEP,
    ) -> StateMachineResult[StateT]:
        # Replays a compatible projection, then continues only its exact durable boundary.
        resolved_run_id = _run_id(run_id, generate=False)
        if command is not None and not isinstance(command, ResumeCommand):
            raise WorkflowResumeError("StateMachine.aresume command must be ResumeCommand.", details={"run_id": resolved_run_id, "actual_type": type(command).__name__})
        resolved_store = _store(store, self._default_store)
        projection = await self._load_projection(resolved_store, resolved_run_id)
        policy = checkpoint_policy if isinstance(checkpoint_policy, WorkflowCheckpointPolicy) else WorkflowCheckpointPolicy(checkpoint_policy)
        run = _WorkflowRun(self._definition, resolved_store, resolved_run_id, observers=observers, checkpoint_policy=policy, confirmation_policy=_confirmation_policy(confirmation_policy), projection=projection)
        return await run.resume(command)

    async def inspect(self, run_id: str, *, store: WorkflowStore | None = None, through_sequence: int | None = None) -> StateMachineResult[StateT]:
        # Replays one event prefix without invoking executable graph components.
        resolved_run_id = _run_id(run_id, generate=False)
        if through_sequence is not None and (not isinstance(through_sequence, int) or isinstance(through_sequence, bool) or through_sequence <= 0):
            raise WorkflowResumeError("inspect through_sequence must be a positive integer.", details={"run_id": resolved_run_id, "through_sequence": through_sequence})
        resolved_store = _store(store, self._default_store)
        projection = await self._load_projection(resolved_store, resolved_run_id, through_sequence=through_sequence)
        runtime = _WorkflowRun(self._definition, resolved_store, resolved_run_id, observers=(), checkpoint_policy=WorkflowCheckpointPolicy.MANUAL, confirmation_policy=NeverConfirm(), projection=projection)
        return await runtime._result(through_sequence=through_sequence)

    def run(self, initial_state: StateT, **kwargs: Any) -> StateMachineResult[StateT]:
        # Bridges async start only outside an active event loop.
        return _sync(self.arun(initial_state, **kwargs), method="run")

    def resume(self, run_id: str, **kwargs: Any) -> StateMachineResult[StateT]:
        # Bridges async resume only outside an active event loop.
        return _sync(self.aresume(run_id, **kwargs), method="resume")

    async def _load_projection(self, store: WorkflowStore, run_id: str, *, through_sequence: int | None = None) -> WorkflowProjection[StateT]:
        # Restores the latest compatible cache and replays every subsequent canonical fact.
        checkpoint = await store.latest_checkpoint(run_id, through_sequence=through_sequence)
        if checkpoint is not None:
            assert_checkpoint_compatible(checkpoint, self._definition.definition_record)
            events = await store.events(run_id, after_sequence=checkpoint.event_sequence, through_sequence=through_sequence)
            projection = WorkflowProjector[StateT]().replay(self._definition, events, checkpoint=checkpoint)
        else:
            events = await store.events(run_id, through_sequence=through_sequence)
            if not events:
                raise WorkflowResumeError("Workflow run was not found in the selected store.", details={"run_id": run_id, "definition_id": self.definition_id})
            projection = WorkflowProjector[StateT]().replay(self._definition, events)
        if projection.definition_id != self.definition_id:
            raise WorkflowResumeError("Stored run belongs to a different compiled definition.", details={"run_id": run_id, "stored_definition_id": projection.definition_id, "definition_id": self.definition_id})
        return projection


def _run_id(value: str | None, *, generate: bool = True) -> str:
    # Normalizes caller identity or creates one namespaced workflow run ID.
    if value is None:
        if generate:
            return f"wrun_{uuid4().hex}"
        raise WorkflowResumeError("run_id is required for resume or inspect.", details={})
    if not isinstance(value, str) or not value.strip():
        raise WorkflowExecutionError("Workflow run_id must be a non-empty string.", details={"actual_type": type(value).__name__})
    return value.strip()


def _store(value: WorkflowStore | None, default: WorkflowStore) -> WorkflowStore:
    # Validates the pluggable append/checkpoint boundary structurally.
    resolved = default if value is None else value
    required = ("put_definition", "get_definition", "begin_run", "append", "events", "put_checkpoint", "latest_checkpoint")
    if any(not callable(getattr(resolved, name, None)) for name in required) or not hasattr(resolved, "durable"):
        raise WorkflowPersistenceError("Workflow store does not implement the required async contract.", details={"actual_type": type(resolved).__name__})
    return resolved


def _confirmation_policy(value: ConfirmationPolicy | None) -> ConfirmationPolicy:
    # Uses opt-in confirmation by default while preserving mandatory edge gates.
    resolved = NeverConfirm() if value is None else value
    if not callable(getattr(resolved, "requires_confirmation", None)):
        raise WorkflowApprovalError("Confirmation policy must provide requires_confirmation(context).", details={"actual_type": type(resolved).__name__})
    return resolved


def _sync(awaitable: Any, *, method: str) -> Any:
    # Rejects nested event loops and otherwise delegates to asyncio.run.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    if hasattr(awaitable, "close"):
        awaitable.close()
    raise WorkflowExecutionError(f"StateMachine.{method}() cannot run inside an active event loop; use the async method.", details={"method": method})


def _validator_name(validator: Any) -> str:
    # Reads validator identity defensively so diagnostics survive broken properties.
    try:
        name = validator.name
    except Exception:
        return type(validator).__name__
    return str(name).strip() or type(validator).__name__


def _router_name(router: Any) -> str:
    # Reads router identity defensively for route-selection evidence.
    try:
        name = router.name
    except Exception:
        return type(router).__name__
    return str(name).strip() or type(router).__name__


async def _charge_usage(definition: _CompiledGraph[Any], events: _EventRuntime[Any], stage: str, usage: UsageReport) -> None:
    # Appends actual usage even when its newly aggregated value crosses a hard ceiling.
    ledger = BudgetLedger(definition.settings.budget, cost_model=definition.settings.cost_model, snapshot=events.require_projection().budget)
    try:
        ledger.add_usage(usage)
    except WorkflowBudgetError:
        await events.emit(WorkflowEventType.USAGE_RECORDED, stage=stage, payload={"usage": _usage_to_dict(ledger.usage), "budget": _budget_to_dict(ledger.snapshot())})
        raise
    await events.emit(WorkflowEventType.USAGE_RECORDED, stage=stage, payload={"usage": _usage_to_dict(ledger.usage), "budget": _budget_to_dict(ledger.snapshot())})


def _duration_ms(started: float) -> float:
    # Converts a monotonic start marker to non-negative milliseconds.
    return max(0.0, (time.perf_counter() - started) * 1000.0)


def _parse_datetime(value: str) -> datetime | None:
    # Restores the original wall-clock event origin for resumed elapsed evidence.
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _transition_record_from_payload(value: Mapping[str, Any]) -> TransitionRecord:
    # Reconstructs persisted continuation evidence without importing projector internals.
    from .projection import _transition_from_dict

    return _transition_from_dict(value)


def _feedback_from_payload(value: Mapping[str, Any]) -> WorkflowFeedback:
    # Reconstructs persisted recovery feedback.
    from .projection import _feedback_from_dict

    return _feedback_from_dict(value)


def _placeholder_execution(stage: str) -> StageExecution:
    # Supplies bounded evidence only for legacy streams missing a completed stage record.
    return StageExecution(stage, 1, 1, None, False, 0.0, {}, ())


def _child_record(send: Send, summary: Any) -> dict[str, Any]:
    # Serializes one isolated child outcome plus enough Send data for cold resume.
    return {
        "subgraph": send.subgraph,
        "key": send.key,
        "input": send.input,
        "metadata": dict(send.metadata),
        "budget": _workflow_budget_to_dict(send.budget) if send.budget is not None else None,
        "effective_budget": _workflow_budget_to_dict(summary.effective_budget) if summary.effective_budget is not None else None,
        "child_run_id": summary.child_run_id,
        "lifecycle": getattr(summary.lifecycle, "value", summary.lifecycle),
        "terminal": summary.terminal,
        "update": dict(summary.update),
        "usage": _usage_to_dict(summary.usage),
        "error": _error_to_dict(summary.error),
        "pending": _pending_to_dict(summary.pending),
    }


def _send_from_child_record(value: Mapping[str, Any]) -> Send:
    # Reconstructs a persisted child invocation for its summary mapper and budget.
    budget_data = value.get("budget")
    budget = _workflow_budget_from_dict(budget_data) if isinstance(budget_data, Mapping) else None
    return Send(str(value["subgraph"]), value.get("input"), str(value["key"]), budget, value.get("metadata", {}))


def _workflow_budget_to_dict(value: WorkflowBudget) -> dict[str, Any]:
    # Serializes every child-overridable ceiling without executable objects.
    return {name: (getattr(value, name).value if hasattr(getattr(value, name), "value") else getattr(value, name)) for name in ("max_super_steps", "max_transitions", "max_model_calls", "max_tool_calls", "max_tokens", "max_cost_usd", "timeout_seconds", "max_subgraph_concurrency", "max_recursion_depth", "max_detour_depth", "unknown_cost_policy")}


def _workflow_budget_from_dict(value: Mapping[str, Any]) -> WorkflowBudget:
    # Reconstructs one optional Send-specific child budget.
    return WorkflowBudget(
        max_super_steps=int(value.get("max_super_steps", 100)),
        max_transitions=int(value.get("max_transitions", 100)),
        max_model_calls=value.get("max_model_calls"),
        max_tool_calls=value.get("max_tool_calls"),
        max_tokens=value.get("max_tokens"),
        max_cost_usd=value.get("max_cost_usd"),
        timeout_seconds=value.get("timeout_seconds"),
        max_subgraph_concurrency=int(value.get("max_subgraph_concurrency", 8)),
        max_recursion_depth=int(value.get("max_recursion_depth", 8)),
        max_detour_depth=int(value.get("max_detour_depth", 4)),
        unknown_cost_policy=UnknownCostPolicy(value.get("unknown_cost_policy", UnknownCostPolicy.FAIL_CLOSED.value)),
    )


def _pending_from_payload(value: Mapping[str, Any]) -> PendingRequest:
    # Reconstructs a child's exact pending request for the parent-facing wrapper.
    return PendingRequest(str(value["request_id"]), PendingRequestKind(value["kind"]), str(value["stage"]), str(value["prompt"]), value.get("metadata", {}))


def _usage_is_zero(value: UsageReport) -> bool:
    # Avoids appending a synthetic usage event for a genuinely empty child batch.
    return value.model_calls == 0 and value.tool_calls == 0 and value.input_tokens in (0, None) and value.output_tokens in (0, None) and value.total_tokens in (0, None) and value.cost_usd in (0.0, None)


__all__ = ["StateMachine"]

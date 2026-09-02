"""FILE: vidbyte/workflows/machine.py
PURPOSE: Executes immutable workflow graphs with validate-before-commit state transitions.
ROLE IN CODEBASE: Constructed only by StateGraph.compile(); invokes stages, validators, routers, guards, and observers.

ARCHITECTURE NOTE:
    This file is the authoritative workflow control plane. Each stage receives a
    clone of committed state and returns a candidate. Stage validators run before
    route lookup; target guards run after lookup; only a fully accepted transition
    commits the candidate. Rejection redirects with unchanged committed state.

PUBLIC API INVENTORY:
    StateMachine.name / entry / stages / terminals: Immutable definition views.
    StateMachine.arun(): Async execution with per-run ledger, metadata, and observers.
    StateMachine.run(): Sync bridge that rejects active event loops.

COMMON MODIFICATION PATTERNS:
    Add static checks in graph.py, value fields in contracts.py, and adapters in
    their native modules. Change this file only when run ordering, validation
    normalization, transition accounting, or commit semantics must change.

WHAT NOT TO DO IN THIS FILE:
    1. Do not let a component return a target name outside the compiled route map.
    2. Do not commit candidate state before both validation phases permit it.
    3. Do not roll back or claim rollback of external filesystem/network effects.
    4. Do not store per-run state on the public StateMachine instance.
    5. Do not swallow CancelledError or other BaseException control signals.

KNOWN EDGE CASES:
    Guard rejection can redirect through another guarded route without rerunning
    the source stage. Every selection consumes max_transitions. A handled stage
    error routes with committed state and no candidate commit. Observer failures
    are captured but never affect workflow behavior.

COMMON ERRORS:
    WorkflowStateError for state isolation/shape, StageExecutionError for exhausted
    stage policy, WorkflowValidationError for RAISE policy, WorkflowRoutingError
    for undeclared outcomes/keys, and TransitionLimitError for runaway paths.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Run the existing suite and inline smoke covering commit, reject, guards,
    branches, retries, limits, cancellation, observers, and concurrent reuse.

CONCURRENCY:
    StateMachine is immutable and reentrant. _WorkflowRun, _RunState, records,
    counters, feedback, and ledgers are created per arun(). Custom components and
    caller-provided ledger values remain responsible for their own synchronization.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Generic
from uuid import uuid4

from vidbyte.workflows.contracts import MachineStatus, RoutingContext, StageContext, StageExecution, StagePolicy, StageResult, StateMachineResult, StateT, TransitionRecord, ValidationContext, ValidationPhase, ValidationRecord, ValidationResult, ValidationStatus, Validator, ValidatorErrorPolicy, WorkflowEvent, WorkflowEventType, WorkflowFeedback, WorkflowObserver
from vidbyte.workflows.errors import StageExecutionError, TransitionLimitError, WorkflowError, WorkflowExecutionError, WorkflowRoutingError, WorkflowStateError, WorkflowValidationError
from vidbyte.workflows.graph import _BranchRoute, _CompiledGraph, _DirectRoute, _StageDefinition


@dataclass(frozen=True, slots=True)
class _ValidationDecision:
    """Effective outcome and evidence from one ordered validator sequence."""

    passed: bool
    result: ValidationResult | None
    records: tuple[ValidationRecord, ...]
    must_raise: bool = False


@dataclass(frozen=True, slots=True)
class _StageAttempt(Generic[StateT]):
    """Successful candidate attempt or handled stage-error route proposal."""

    state_before: StateT
    stage_result: StageResult[StateT]
    record_index: int | None
    handled_error: WorkflowFeedback | None = None


@dataclass(frozen=True, slots=True)
class _StageDecision(Generic[StateT]):
    """Pending route decision produced by stage work or boundary rejection."""

    source: str
    state_before: StateT
    candidate_state: StateT
    stage_result: StageResult[StateT]
    can_commit: bool
    trigger: str
    feedback: tuple[WorkflowFeedback, ...]
    stage_record_index: int | None

    @property
    def outcome(self) -> str:
        # Exposes the semantic code used for route lookup.
        return self.stage_result.outcome


@dataclass(frozen=True, slots=True)
class _SelectedRoute(Generic[StateT]):
    """One resolved target and ordered guards selected from the compiled graph."""

    target: str
    guards: tuple[Validator[StateT], ...]
    branch_key: str | None = None
    router: str | None = None


@dataclass(slots=True)
class _RunState(Generic[StateT]):
    """Mutable execution state owned by exactly one workflow run."""

    committed_state: StateT
    current_stage: str
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]
    feedback: tuple[WorkflowFeedback, ...] = ()
    transition_count: int = 0
    visits: dict[str, int] = field(default_factory=dict)
    stages: list[StageExecution] = field(default_factory=list)
    transitions: list[TransitionRecord] = field(default_factory=list)

    def next_visit(self, stage: str) -> int:
        # Increments and returns the one-based visit count for a stage.
        visit = self.visits.get(stage, 0) + 1
        self.visits[stage] = visit
        return visit

    def add_stage(self, record: StageExecution) -> int:
        # Appends one attempt record and returns its stable list index.
        self.stages.append(record)
        return len(self.stages) - 1

    def attach_stage_validations(self, index: int, validations: tuple[ValidationRecord, ...]) -> None:
        # Replaces one immutable stage record with its completed gate evidence.
        self.stages[index] = replace(self.stages[index], validations=validations)

    def accept_stage(self, index: int) -> None:
        # Marks a candidate-producing stage accepted only after state commit.
        self.stages[index] = replace(self.stages[index], accepted=True)


class _RunRecorder:
    """Creates ordered lifecycle events and isolates observer failures."""

    def __init__(self, run_id: str, observers: Sequence[WorkflowObserver]) -> None:
        # Initializes per-run event order, timing, and observer diagnostics.
        self._run_id = run_id
        self._observers = tuple(observers)
        self._started = time.perf_counter()
        self.events: list[WorkflowEvent] = []
        self.observer_errors: list[str] = []

    async def emit(self, event_type: WorkflowEventType, *, stage: str | None = None, payload: Mapping[str, Any] | None = None) -> WorkflowEvent:
        # Records one event before notifying observers in declaration order.
        event = WorkflowEvent(sequence=len(self.events) + 1, event_type=event_type, run_id=self._run_id, stage=stage, occurred_at=datetime.now(timezone.utc), elapsed_ms=self.elapsed_ms(), payload=payload or {})
        self.events.append(event)
        await self._notify_observers(event)
        return event

    def elapsed_ms(self) -> float:
        # Returns monotonic run duration without relying on wall-clock adjustments.
        return (time.perf_counter() - self._started) * 1000.0

    async def _notify_observers(self, event: WorkflowEvent) -> None:
        # Treats every observer as fail-open so diagnostics cannot change control flow.
        for observer in self._observers:
            try:
                await observer.on_event(event)
            except Exception as exc:
                self.observer_errors.append(f"{type(observer).__name__}: {type(exc).__name__}")


class _ValidationRunner(Generic[StateT]):
    """Runs ordered validators and applies run-wide non-decision policy."""

    def __init__(self, definition: _CompiledGraph[StateT], recorder: _RunRecorder) -> None:
        # Stores immutable settings and the run-local event recorder.
        self._settings = definition.settings
        self._recorder = recorder

    async def evaluate(self, validators: Sequence[Validator[StateT]], context: ValidationContext[StateT]) -> _ValidationDecision:
        # Evaluates gates in order and stops at the first effective blocker.
        records: list[ValidationRecord] = []
        for validator in validators:
            record = await self._evaluate_one(validator, context)
            records.append(record)
            decision = self._interpret(record.result, tuple(records))
            if decision is not None:
                return decision
        return _ValidationDecision(passed=True, result=None, records=tuple(records))

    async def _evaluate_one(self, validator: Validator[StateT], context: ValidationContext[StateT]) -> ValidationRecord:
        # Invokes one validator, normalizes invalid behavior, and emits safe evidence.
        name = _validator_name(validator)
        started = time.perf_counter()
        result = await self._invoke(validator, context, name)
        record = ValidationRecord(phase=context.phase, validator=name, result=result, duration_ms=_duration_ms(started), target=context.target)
        await self._recorder.emit(WorkflowEventType.VALIDATION_FINISHED, stage=context.stage, payload={"phase": context.phase.value, "validator": name, "status": result.status.value, "code": result.code, "target": context.target})
        return record

    async def _invoke(self, validator: Validator[StateT], context: ValidationContext[StateT], name: str) -> ValidationResult:
        # Converts ordinary validator failures to ERROR while preserving cancellation.
        try:
            result = await validator.validate(context)
        except Exception as exc:
            return ValidationResult.errored(self._settings.validation_error_outcome, f"Validator '{name}' raised {type(exc).__name__}.", details={"validator": name, "error_type": type(exc).__name__})
        if not isinstance(result, ValidationResult):
            return ValidationResult.errored(self._settings.validation_error_outcome, f"Validator '{name}' returned {type(result).__name__}, expected ValidationResult.", details={"validator": name, "actual_type": type(result).__name__})
        return result

    def _interpret(self, result: ValidationResult, records: tuple[ValidationRecord, ...]) -> _ValidationDecision | None:
        # Applies fail-open, fail-closed, or raise semantics to one gate result.
        if result.status is ValidationStatus.PASS:
            return None
        if result.status is ValidationStatus.REJECT:
            return _ValidationDecision(passed=False, result=result, records=records)
        if self._settings.validator_error_policy is ValidatorErrorPolicy.FAIL_OPEN:
            return None
        if self._settings.validator_error_policy is ValidatorErrorPolicy.RAISE:
            return _ValidationDecision(passed=False, result=result, records=records, must_raise=True)
        effective = ValidationResult.rejected(result.code or self._settings.validation_error_outcome, result.feedback or "Validator did not produce a passing decision.", score=result.score, details=result.details)
        return _ValidationDecision(passed=False, result=effective, records=records)


class _WorkflowRun(Generic[StateT]):
    """Owns one complete execution of an immutable workflow definition."""

    def __init__(self, definition: _CompiledGraph[StateT], initial_state: StateT, *, run_id: str, ledger: MutableMapping[str, Any] | None, metadata: Mapping[str, Any] | None, observers: Sequence[WorkflowObserver]) -> None:
        # Initializes run-local collaborators without validating user state yet.
        if ledger is not None and not isinstance(ledger, MutableMapping):
            raise WorkflowExecutionError("StateMachine ledger must be a mutable mapping.", details={"run_id": run_id, "actual_type": type(ledger).__name__})
        if metadata is not None and not isinstance(metadata, Mapping):
            raise WorkflowExecutionError("StateMachine metadata must be a mapping.", details={"run_id": run_id, "actual_type": type(metadata).__name__})
        self._definition = definition
        self._initial_state = initial_state
        self._run_id = run_id
        self._ledger = ledger if ledger is not None else {}
        self._metadata = dict(metadata or {})
        self._recorder = _RunRecorder(run_id, observers)
        self._validators = _ValidationRunner(definition, self._recorder)
        self._runtime: _RunState[StateT] | None = None

    async def execute(self) -> StateMachineResult[StateT]:
        # Runs from initial-state isolation through a declared terminal result.
        try:
            await self._recorder.emit(WorkflowEventType.RUN_STARTED, stage=self._definition.entry, payload={"workflow": self._definition.name, "entry": self._definition.entry})
            committed = self._normalize_clone(self._initial_state, boundary="initial_state")
            self._runtime = _RunState(committed_state=committed, current_stage=self._definition.entry, ledger=self._ledger, metadata=self._metadata)
            return await self._execute_stages()
        except BaseException as exc:
            await self._emit_failure(exc)
            raise

    async def _execute_stages(self) -> StateMachineResult[StateT]:
        # Repeats stage work and transition resolution until a terminal is entered.
        while True:
            runtime = self._require_runtime()
            decision = await self._run_stage(runtime.current_stage)
            terminal = await self._advance(decision)
            if terminal is not None:
                return await self._finish(terminal)

    async def _run_stage(self, stage_name: str) -> _StageDecision[StateT]:
        # Executes one stage visit, then applies its ordered stage validators.
        runtime = self._require_runtime()
        definition = self._definition.stages[stage_name]
        visit = runtime.next_visit(stage_name)
        attempt = await self._execute_attempts(stage_name, definition, visit)
        if attempt.handled_error is not None:
            return self._handled_stage_error(stage_name, attempt)
        return await self._validate_stage(stage_name, definition, attempt)

    async def _execute_attempts(self, stage_name: str, definition: _StageDefinition[StateT], visit: int) -> _StageAttempt[StateT]:
        # Applies deterministic retry policy to stage invocation failures only.
        policy = definition.policy
        for attempt_number in range(1, policy.retry.max_attempts + 1):
            state_before = self._clone_committed(stage_name)
            stage_input = self._normalize_clone(state_before, boundary=f"stage:{stage_name}:attempt_input")
            try:
                return await self._execute_attempt(stage_name, definition, visit=visit, attempt_number=attempt_number, state_before=state_before, stage_input=stage_input)
            except _StageCallbackFailure as failure:
                await self._record_stage_failure(stage_name, visit=visit, attempt_number=attempt_number, duration_ms=failure.duration_ms, error=failure.cause)
                if self._should_retry(failure.cause, policy, attempt_number):
                    await self._wait_before_retry(policy, attempt_number)
                    continue
                if policy.error_outcome is not None:
                    feedback = WorkflowFeedback(kind="stage_error", source=stage_name, code=policy.error_outcome, message=f"Stage '{stage_name}' exhausted its execution policy.", details={"error_type": type(failure.cause).__name__, "attempts": attempt_number})
                    return _StageAttempt(state_before=self._require_runtime().committed_state, stage_result=StageResult(self._require_runtime().committed_state, outcome=policy.error_outcome), record_index=None, handled_error=feedback)
                raise StageExecutionError(f"Stage '{stage_name}' failed after {attempt_number} attempt(s).", details={"run_id": self._run_id, "stage": stage_name, "attempts": attempt_number, "error_type": type(failure.cause).__name__}) from failure.cause
        raise StageExecutionError(f"Stage '{stage_name}' exhausted its retry loop without a result.", details={"run_id": self._run_id, "stage": stage_name})

    async def _execute_attempt(self, stage_name: str, definition: _StageDefinition[StateT], *, visit: int, attempt_number: int, state_before: StateT, stage_input: StateT) -> _StageAttempt[StateT]:
        # Invokes one stage callback and records its validated candidate result.
        runtime = self._require_runtime()
        context = StageContext(run_id=self._run_id, stage=stage_name, state=stage_input, visit=visit, attempt=attempt_number, transition_count=runtime.transition_count, feedback=runtime.feedback, history=tuple(runtime.stages), ledger=runtime.ledger, metadata=runtime.metadata)
        await self._recorder.emit(WorkflowEventType.STAGE_STARTED, stage=stage_name, payload={"visit": visit, "attempt": attempt_number})
        started = time.perf_counter()
        try:
            raw_result = await self._invoke_stage(definition, context)
        except Exception as exc:
            raise _StageCallbackFailure(exc, _duration_ms(started)) from exc
        try:
            result = self._normalize_stage_result(stage_name, raw_result)
        except WorkflowError as exc:
            await self._record_stage_failure(stage_name, visit=visit, attempt_number=attempt_number, duration_ms=_duration_ms(started), error=exc)
            raise
        record = self._successful_stage_record(stage_name, visit=visit, attempt_number=attempt_number, state_before=state_before, result=result, duration_ms=_duration_ms(started))
        index = runtime.add_stage(record)
        await self._recorder.emit(WorkflowEventType.STAGE_FINISHED, stage=stage_name, payload={"visit": visit, "attempt": attempt_number, "outcome": result.outcome, "status": "candidate"})
        return _StageAttempt(state_before=state_before, stage_result=result, record_index=index)

    async def _invoke_stage(self, definition: _StageDefinition[StateT], context: StageContext[StateT]) -> Any:
        # Applies the stage-local timeout around exactly one callback invocation.
        if definition.policy.timeout_seconds is None:
            return await definition.stage.run(context)
        return await asyncio.wait_for(definition.stage.run(context), timeout=definition.policy.timeout_seconds)

    def _normalize_stage_result(self, stage_name: str, value: Any) -> StageResult[StateT]:
        # Enforces StageResult and StateT before custom validators inspect a candidate.
        if not isinstance(value, StageResult):
            raise StageExecutionError(f"Stage '{stage_name}' returned {type(value).__name__}; expected StageResult.", details={"run_id": self._run_id, "stage": stage_name, "actual_type": type(value).__name__})
        try:
            candidate = self._definition.state_contract.validate(value.state)
        except Exception as exc:
            raise WorkflowStateError(f"Stage '{stage_name}' returned candidate state that violates the graph contract.", details={"run_id": self._run_id, "stage": stage_name, "state_type": self._definition.state_contract.state_type.__name__, "error_type": type(exc).__name__}) from exc
        return StageResult(candidate, outcome=value.outcome, metadata=value.metadata)

    def _successful_stage_record(self, stage_name: str, *, visit: int, attempt_number: int, state_before: StateT, result: StageResult[StateT], duration_ms: float) -> StageExecution:
        # Builds an initially unaccepted record; commit is the only acceptance point.
        before_snapshot = self._snapshot(state_before, boundary="stage_state_before")
        candidate_snapshot = self._snapshot(result.state, boundary="stage_candidate_state")
        return StageExecution(stage=stage_name, visit=visit, attempt=attempt_number, outcome=result.outcome, accepted=False, duration_ms=duration_ms, metadata=result.metadata, validations=(), state_before=before_snapshot, candidate_state=candidate_snapshot)

    async def _record_stage_failure(self, stage_name: str, *, visit: int, attempt_number: int, duration_ms: float, error: Exception) -> None:
        # Appends and emits safe failure evidence without raw exception text or state.
        runtime = self._require_runtime()
        message = f"Stage attempt failed with {type(error).__name__}."
        record = StageExecution(stage=stage_name, visit=visit, attempt=attempt_number, outcome=None, accepted=False, duration_ms=duration_ms, metadata={}, validations=(), error_type=type(error).__name__, error_message=message)
        runtime.add_stage(record)
        await self._recorder.emit(WorkflowEventType.STAGE_FINISHED, stage=stage_name, payload={"visit": visit, "attempt": attempt_number, "status": "error", "error_type": type(error).__name__})

    async def _validate_stage(self, stage_name: str, definition: _StageDefinition[StateT], attempt: _StageAttempt[StateT]) -> _StageDecision[StateT]:
        # Runs stage-phase gates and converts rejection to an unchanged-state route.
        runtime = self._require_runtime()
        inspection_result = self._inspection_result(attempt.stage_result, boundary=f"stage:{stage_name}:validation_candidate")
        state_before = self._normalize_clone(attempt.state_before, boundary=f"stage:{stage_name}:validation_before")
        context = ValidationContext(run_id=self._run_id, phase=ValidationPhase.STAGE, stage=stage_name, state_before=state_before, candidate_state=inspection_result.state, stage_result=inspection_result, outcome=inspection_result.outcome, target=None, feedback=runtime.feedback, ledger=runtime.ledger, metadata=runtime.metadata)
        validation = await self._validators.evaluate(definition.validators, context)
        if attempt.record_index is not None:
            runtime.attach_stage_validations(attempt.record_index, validation.records)
        if validation.must_raise:
            self._raise_validation_error(stage_name, validation.result, phase=ValidationPhase.STAGE)
        if validation.passed:
            return _StageDecision(source=stage_name, state_before=attempt.state_before, candidate_state=attempt.stage_result.state, stage_result=attempt.stage_result, can_commit=True, trigger="stage_outcome", feedback=runtime.feedback, stage_record_index=attempt.record_index)
        return self._rejected_stage_decision(stage_name, attempt, validation)

    def _rejected_stage_decision(self, stage_name: str, attempt: _StageAttempt[StateT], validation: _ValidationDecision) -> _StageDecision[StateT]:
        # Discards a rejected candidate and routes its semantic code with feedback.
        runtime = self._require_runtime()
        result = validation.result or ValidationResult.rejected(self._definition.settings.validation_error_outcome, "Stage validation rejected the candidate.")
        feedback = self._validation_feedback("stage_validation", stage_name, result, records=validation.records)
        synthetic = StageResult(runtime.committed_state, outcome=result.code, metadata=attempt.stage_result.metadata)
        return _StageDecision(source=stage_name, state_before=runtime.committed_state, candidate_state=runtime.committed_state, stage_result=synthetic, can_commit=False, trigger="stage_validation", feedback=(feedback,), stage_record_index=attempt.record_index)

    def _handled_stage_error(self, stage_name: str, attempt: _StageAttempt[StateT]) -> _StageDecision[StateT]:
        # Routes an exhausted but declared stage error with unchanged committed state.
        runtime = self._require_runtime()
        feedback = attempt.handled_error
        return _StageDecision(source=stage_name, state_before=runtime.committed_state, candidate_state=runtime.committed_state, stage_result=attempt.stage_result, can_commit=False, trigger="stage_error", feedback=(feedback,) if feedback is not None else (), stage_record_index=None)

    async def _advance(self, initial: _StageDecision[StateT]) -> str | None:
        # Resolves transitions and guard redirects until one target is accepted.
        decision = initial
        while True:
            started = time.perf_counter()
            selected = await self._select_route(decision)
            sequence = self._consume_transition()
            await self._emit_transition_selected(decision, selected, sequence)
            if sequence > self._definition.settings.max_transitions:
                validation = _ValidationDecision(passed=False, result=None, records=())
                self._append_transition_record(sequence, decision, selected=selected, validation=validation, accepted=False, started=started)
                self._raise_transition_limit(decision, selected, sequence)
            guard_decision = await self._run_guards(decision, selected)
            if guard_decision.must_raise:
                self._append_transition_record(sequence, decision, selected=selected, validation=guard_decision, accepted=False, started=started)
                self._raise_validation_error(decision.source, guard_decision.result, phase=ValidationPhase.TRANSITION, target=selected.target)
            if guard_decision.passed:
                terminal = await self._accept_transition(decision, selected)
                self._append_transition_record(sequence, decision, selected=selected, validation=guard_decision, accepted=True, started=started)
                return terminal
            self._append_transition_record(sequence, decision, selected=selected, validation=guard_decision, accepted=False, started=started)
            decision = await self._redirect_guard_rejection(decision, selected, guard_decision)

    async def _select_route(self, decision: _StageDecision[StateT]) -> _SelectedRoute[StateT]:
        # Resolves a direct route or bounded branch key from the compiled map.
        route = self._definition.routes.get((decision.source, decision.outcome))
        if route is None:
            raise WorkflowRoutingError(f"No route is declared for stage '{decision.source}' outcome '{decision.outcome}'.", details={"run_id": self._run_id, "stage": decision.source, "outcome": decision.outcome})
        if isinstance(route, _DirectRoute):
            return _SelectedRoute(target=route.target, guards=route.guards)
        return await self._select_branch(decision, route)

    async def _select_branch(self, decision: _StageDecision[StateT], route: _BranchRoute[StateT]) -> _SelectedRoute[StateT]:
        # Invokes one router and requires its key to exist in the compiled branch map.
        runtime = self._require_runtime()
        inspection_result = self._inspection_result(decision.stage_result, boundary=f"stage:{decision.source}:routing_candidate")
        context = RoutingContext(run_id=self._run_id, stage=decision.source, candidate_state=inspection_result.state, stage_result=inspection_result, feedback=decision.feedback, ledger=runtime.ledger, metadata=runtime.metadata)
        router_name = _router_name(route.router)
        try:
            raw_key = await route.router.route(context)
        except Exception as exc:
            raise WorkflowRoutingError(f"Router '{router_name}' failed for stage '{decision.source}'.", details={"run_id": self._run_id, "stage": decision.source, "outcome": decision.outcome, "router": router_name, "error_type": type(exc).__name__}) from exc
        key = raw_key.strip() if isinstance(raw_key, str) else ""
        destination = route.routes.get(key)
        if destination is None:
            raise WorkflowRoutingError(f"Router '{router_name}' returned undeclared branch key '{key or '<empty>'}'.", details={"run_id": self._run_id, "stage": decision.source, "outcome": decision.outcome, "router": router_name, "branch_key": key, "available_keys": tuple(route.routes)})
        return _SelectedRoute(target=destination.target, guards=destination.guards, branch_key=key, router=router_name)

    def _consume_transition(self) -> int:
        # Counts every target selection before guards so redirect loops stay bounded.
        runtime = self._require_runtime()
        runtime.transition_count += 1
        return runtime.transition_count

    async def _emit_transition_selected(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT], sequence: int) -> None:
        # Emits every counted selection, including the attempt that exceeds the budget.
        await self._recorder.emit(WorkflowEventType.TRANSITION_SELECTED, stage=decision.source, payload={"sequence": sequence, "outcome": decision.outcome, "target": selected.target, "branch_key": selected.branch_key, "router": selected.router, "trigger": decision.trigger})

    def _raise_transition_limit(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT], sequence: int) -> None:
        # Raises after selection evidence is recorded without invoking target guards.
        raise TransitionLimitError(f"Workflow '{self._definition.name}' exceeded max_transitions={self._definition.settings.max_transitions}.", details={"run_id": self._run_id, "stage": decision.source, "outcome": decision.outcome, "target": selected.target, "transition_count": sequence, "max_transitions": self._definition.settings.max_transitions})

    async def _run_guards(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT]) -> _ValidationDecision:
        # Runs target-specific guards against the selected candidate before commit.
        runtime = self._require_runtime()
        inspection_result = self._inspection_result(decision.stage_result, boundary=f"stage:{decision.source}:guard_candidate")
        state_before = self._normalize_clone(runtime.committed_state, boundary=f"stage:{decision.source}:guard_before")
        context = ValidationContext(run_id=self._run_id, phase=ValidationPhase.TRANSITION, stage=decision.source, state_before=state_before, candidate_state=inspection_result.state, stage_result=inspection_result, outcome=decision.outcome, target=selected.target, feedback=decision.feedback, ledger=runtime.ledger, metadata=runtime.metadata)
        return await self._validators.evaluate(selected.guards, context)

    def _append_transition_record(self, sequence: int, decision: _StageDecision[StateT], *, selected: _SelectedRoute[StateT], validation: _ValidationDecision, accepted: bool, started: float) -> None:
        # Appends a transition record only after its acceptance status is known.
        record = TransitionRecord(sequence=sequence, source=decision.source, target=selected.target, outcome=decision.outcome, accepted=accepted, trigger=decision.trigger, validations=validation.records, duration_ms=_duration_ms(started))
        self._require_runtime().transitions.append(record)

    # @intent candidate-state-commit-boundary
    # Candidate state stays isolated until both gate phases accept it; recovery
    # edges preserve committed state, while external side effects remain caller-owned.
    async def _accept_transition(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT]) -> str | None:
        # Commits an accepted candidate or carries unchanged state over a recovery edge.
        runtime = self._require_runtime()
        if decision.can_commit:
            runtime.committed_state = self._normalize_clone(decision.candidate_state, boundary="state_commit")
            if decision.stage_record_index is not None:
                runtime.accept_stage(decision.stage_record_index)
            await self._recorder.emit(WorkflowEventType.STATE_COMMITTED, stage=decision.source, payload={"transition": runtime.transition_count, "target": selected.target})
            runtime.feedback = ()
        else:
            runtime.feedback = decision.feedback
        if selected.target in self._definition.terminals:
            return selected.target
        runtime.current_stage = selected.target
        return None

    async def _redirect_guard_rejection(self, decision: _StageDecision[StateT], selected: _SelectedRoute[StateT], validation: _ValidationDecision) -> _StageDecision[StateT]:
        # Discards the candidate and redirects the guard's semantic rejection code.
        runtime = self._require_runtime()
        result = validation.result or ValidationResult.rejected(self._definition.settings.validation_error_outcome, "Transition guard rejected the candidate.")
        await self._recorder.emit(WorkflowEventType.TRANSITION_REJECTED, stage=decision.source, payload={"transition": runtime.transition_count, "target": selected.target, "code": result.code})
        base_feedback = () if decision.can_commit else decision.feedback
        feedback = self._validation_feedback("transition_guard", decision.source, result, records=validation.records)
        synthetic = StageResult(runtime.committed_state, outcome=result.code, metadata=decision.stage_result.metadata)
        return _StageDecision(source=decision.source, state_before=runtime.committed_state, candidate_state=runtime.committed_state, stage_result=synthetic, can_commit=False, trigger="transition_guard", feedback=(*base_feedback, feedback), stage_record_index=decision.stage_record_index)

    async def _finish(self, terminal: str) -> StateMachineResult[StateT]:
        # Emits the terminal event and returns immutable state and evidence views.
        runtime = self._require_runtime()
        status = self._definition.terminals[terminal]
        await self._recorder.emit(WorkflowEventType.RUN_FINISHED, stage=terminal, payload={"workflow": self._definition.name, "terminal": terminal, "status": status.value, "transitions": runtime.transition_count})
        return StateMachineResult(run_id=self._run_id, status=status, terminal=terminal, state=runtime.committed_state, ledger=runtime.ledger, metadata=runtime.metadata, stages=tuple(runtime.stages), transitions=tuple(runtime.transitions), events=tuple(self._recorder.events), observer_errors=tuple(self._recorder.observer_errors), duration_ms=self._recorder.elapsed_ms())

    def _normalize_clone(self, value: StateT, *, boundary: str) -> StateT:
        # Validates, clones, and revalidates one authoritative state boundary.
        try:
            normalized = self._definition.state_contract.validate(value)
            cloned = self._definition.state_contract.clone(normalized)
            return self._definition.state_contract.validate(cloned)
        except Exception as exc:
            raise WorkflowStateError(f"Workflow state failed validation or cloning at '{boundary}'.", details={"run_id": self._run_id, "boundary": boundary, "state_type": self._definition.state_contract.state_type.__name__, "error_type": type(exc).__name__}) from exc

    def _clone_committed(self, stage_name: str) -> StateT:
        # Isolates one stage attempt from the latest committed state object.
        runtime = self._require_runtime()
        return self._normalize_clone(runtime.committed_state, boundary=f"stage:{stage_name}:input")

    def _snapshot(self, value: StateT, *, boundary: str) -> StateT | None:
        # Copies state evidence only when the caller opted into snapshot recording.
        if not self._definition.settings.record_state_snapshots:
            return None
        return self._normalize_clone(value, boundary=boundary)

    def _should_retry(self, error: Exception, policy: StagePolicy, attempt_number: int) -> bool:
        # Applies the stage's exception allowlist and total-attempt bound.
        return attempt_number < policy.retry.max_attempts and isinstance(error, policy.retry.retry_for)

    async def _wait_before_retry(self, policy: StagePolicy, attempt_number: int) -> None:
        # Sleeps with deterministic exponential backoff and no random jitter.
        delay = policy.retry.delay_seconds * (policy.retry.backoff_multiplier ** (attempt_number - 1))
        if delay > 0:
            await asyncio.sleep(delay)

    def _validation_feedback(self, kind: str, source: str, result: ValidationResult, *, records: Sequence[ValidationRecord]) -> WorkflowFeedback:
        # Builds one recovery packet without including candidate state or prompts.
        details = {**dict(result.details), "validators": tuple(record.validator for record in records), "status": result.status.value, "score": result.score}
        return WorkflowFeedback(kind=kind, source=source, code=result.code, message=result.feedback, details=details)

    def _inspection_result(self, result: StageResult[StateT], *, boundary: str) -> StageResult[StateT]:
        # Gives validators and routers an isolated view that cannot mutate the candidate.
        state = self._normalize_clone(result.state, boundary=boundary)
        return StageResult(state, outcome=result.outcome, metadata=result.metadata)

    def _raise_validation_error(self, stage: str, result: ValidationResult | None, *, phase: ValidationPhase, target: str | None = None) -> None:
        # Raises the configured validation failure with safe boundary identifiers.
        effective = result or ValidationResult.errored(self._definition.settings.validation_error_outcome, "Validator did not produce a result.")
        raise WorkflowValidationError(f"Workflow validation did not pass at the {phase.value} boundary for stage '{stage}'.", details={"run_id": self._run_id, "stage": stage, "phase": phase.value, "target": target, "status": effective.status.value, "code": effective.code})

    def _require_runtime(self) -> _RunState[StateT]:
        # Returns initialized run state or reports an internal lifecycle violation.
        if self._runtime is None:
            raise WorkflowExecutionError("Workflow runtime was accessed before initial state preparation.", details={"run_id": self._run_id, "workflow": self._definition.name})
        return self._runtime

    async def _emit_failure(self, error: BaseException) -> None:
        # Emits best-effort safe failure evidence without replacing the original error.
        stage = self._runtime.current_stage if self._runtime is not None else self._definition.entry
        try:
            await self._recorder.emit(WorkflowEventType.RUN_FAILED, stage=stage, payload={"workflow": self._definition.name, "error_type": type(error).__name__})
        except BaseException:
            return


class _StageCallbackFailure(Exception):
    """Internal carrier separating callback failure from machine contract errors."""

    def __init__(self, cause: Exception, duration_ms: float) -> None:
        # Stores the original callback exception and safe attempt duration.
        super().__init__(type(cause).__name__)
        self.cause = cause
        self.duration_ms = duration_ms


class StateMachine(Generic[StateT]):
    """Immutable, reusable runtime compiled from one validated StateGraph."""

    def __init__(self, definition: _CompiledGraph[StateT]) -> None:
        # Stores the immutable graph snapshot without any per-run mutable state.
        self._definition = definition

    @property
    def name(self) -> str:
        # Returns the declared workflow name.
        return self._definition.name

    @property
    def entry(self) -> str:
        # Returns the declared entry stage name.
        return self._definition.entry

    @property
    def stages(self) -> tuple[str, ...]:
        # Returns stage names in declaration order for introspection.
        return tuple(self._definition.stages)

    @property
    def terminals(self) -> Mapping[str, MachineStatus]:
        # Returns the immutable terminal-to-status mapping.
        return self._definition.terminals

    async def arun(self, initial_state: StateT, *, run_id: str | None = None, ledger: MutableMapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, observers: Sequence[WorkflowObserver] = ()) -> StateMachineResult[StateT]:
        # Executes one isolated run and converts machine-level timeouts/failures.
        if run_id is not None and not isinstance(run_id, str):
            raise WorkflowExecutionError("StateMachine run_id must be a string when provided.", details={"workflow": self.name, "actual_type": type(run_id).__name__})
        resolved_run_id = str(uuid4()) if run_id is None else run_id.strip()
        if not resolved_run_id:
            raise WorkflowExecutionError("StateMachine run_id cannot be empty.", details={"workflow": self.name})
        try:
            run = _WorkflowRun(self._definition, initial_state, run_id=resolved_run_id, ledger=ledger, metadata=metadata, observers=observers)
            if self._definition.settings.timeout_seconds is None:
                return await run.execute()
            async with asyncio.timeout(self._definition.settings.timeout_seconds):
                return await run.execute()
        except WorkflowError:
            raise
        except TimeoutError as exc:
            raise WorkflowExecutionError(f"Workflow '{self.name}' exceeded its run timeout.", details={"run_id": resolved_run_id, "workflow": self.name, "timeout_seconds": self._definition.settings.timeout_seconds}) from exc
        except Exception as exc:
            raise WorkflowExecutionError(f"Workflow '{self.name}' failed with an unexpected machine error.", details={"run_id": resolved_run_id, "workflow": self.name, "error_type": type(exc).__name__}) from exc

    def run(self, initial_state: StateT, *, run_id: str | None = None, ledger: MutableMapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, observers: Sequence[WorkflowObserver] = ()) -> StateMachineResult[StateT]:
        # Bridges async execution only when the caller has no active event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(initial_state, run_id=run_id, ledger=ledger, metadata=metadata, observers=observers))
        raise WorkflowExecutionError("StateMachine.run() cannot be called from an active event loop; use await arun() instead.", details={"workflow": self.name})


def _validator_name(validator: Validator[Any]) -> str:
    # Reads a validator name defensively so diagnostics survive broken properties.
    try:
        name = validator.name
    except Exception:
        return type(validator).__name__
    return str(name).strip() or type(validator).__name__


def _router_name(router: Any) -> str:
    # Reads a router name defensively for route-selection diagnostics.
    try:
        name = router.name
    except Exception:
        return type(router).__name__
    return str(name).strip() or type(router).__name__


def _duration_ms(started: float) -> float:
    # Converts a monotonic start point to a non-negative millisecond duration.
    return max(0.0, (time.perf_counter() - started) * 1000.0)


__all__ = ["StateMachine"]

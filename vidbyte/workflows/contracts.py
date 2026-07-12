"""FILE: vidbyte/workflows/contracts.py
PURPOSE: Defines the public typed language shared by workflow builders, adapters, and compiled runs.
ROLE IN CODEBASE: Imported by every vidbyte.workflows module and re-exported through vidbyte.workflows and vidbyte.

ARCHITECTURE NOTE:
    This file owns data and structural contracts only. Graph declaration lives in
    graph.py, execution lives in machine.py, and adapter behavior lives in the
    stage, validation, and routing modules. Frozen records copy caller mappings
    so execution evidence cannot be changed through the original dictionaries.

PUBLIC API INVENTORY:
    ValidationPhase / ValidationStatus / ValidatorErrorPolicy / MachineStatus:
        Stable string enums for validation and terminal behavior.
    WorkflowEventType: Stable event names emitted by a compiled run.
    RetryPolicy / StagePolicy / StateMachineSettings: Validated execution policy.
    WorkflowFeedback / StageResult / ValidationResult: Stage and gate payloads.
    StageContext / ValidationContext / RoutingContext: Callback input contracts.
    ValidationRecord / StageExecution / TransitionRecord / WorkflowEvent:
        Ordered execution evidence.
    StateMachineResult: Terminal result for a completed declared workflow.
    Stage / Validator / Router / WorkflowObserver: Structural extension protocols.
    RouteTarget: Branch destination plus target-specific transition guards.

COMMON MODIFICATION PATTERNS:
    Add public value fields here, then update machine.py construction, package
    exports, README.md, root README.md, llms.txt, and the approved design doc.
    Add behavior to the module that owns the operation rather than to records.

WHAT NOT TO DO IN THIS FILE:
    1. Do not select routes or commit state; machine.py owns runtime decisions.
    2. Do not import BaseAgent or BaseGrader; adapters own those dependencies.
    3. Do not persist or serialize records as a durable schema; v1 is in-memory.
    4. Do not make the ledger immutable inside callback contexts; its explicit
       purpose is to retain mechanical observations across rejected attempts.

KNOWN EDGE CASES:
    Frozen dataclasses can still contain mutable nested values supplied by SDK
    users. Top-level mappings are protected, but deep immutability is not claimed.
    State snapshots are optional because state can be large or sensitive.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Run the repository suite and the inline workflow smoke described in the design.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable


StateT = TypeVar("StateT")


class ValidationPhase(str, Enum):
    """Boundary at which a validator executes."""

    STAGE = "stage"
    TRANSITION = "transition"


class ValidationStatus(str, Enum):
    """Machine-readable outcome returned by a validator."""

    PASS = "pass"
    REJECT = "reject"
    ABSTAIN = "abstain"
    ERROR = "error"


class ValidatorErrorPolicy(str, Enum):
    """Runtime policy for validator abstentions, errors, and exceptions."""

    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN = "fail_open"
    RAISE = "raise"


class MachineStatus(str, Enum):
    """Declared status attached to a terminal graph node."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkflowEventType(str, Enum):
    """Ordered lifecycle events emitted by a workflow run."""

    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    STAGE_FINISHED = "stage_finished"
    VALIDATION_FINISHED = "validation_finished"
    TRANSITION_SELECTED = "transition_selected"
    TRANSITION_REJECTED = "transition_rejected"
    STATE_COMMITTED = "state_committed"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Deterministic retry settings for one stage invocation."""

    max_attempts: int = 1
    delay_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    retry_for: tuple[type[Exception], ...] = (Exception,)

    def __post_init__(self) -> None:
        # Rejects invalid retry bounds before a workflow can begin execution.
        if self.max_attempts <= 0:
            raise ValueError("RetryPolicy.max_attempts must be greater than zero.")
        if self.delay_seconds < 0:
            raise ValueError("RetryPolicy.delay_seconds cannot be negative.")
        if self.backoff_multiplier <= 0:
            raise ValueError("RetryPolicy.backoff_multiplier must be greater than zero.")
        retry_for = tuple(self.retry_for)
        if not retry_for or any(not isinstance(item, type) or not issubclass(item, Exception) for item in retry_for):
            raise ValueError("RetryPolicy.retry_for must contain one or more Exception subclasses.")
        object.__setattr__(self, "retry_for", retry_for)


@dataclass(frozen=True, slots=True)
class StagePolicy:
    """Timeout, retry, and handled-error routing policy for one stage."""

    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: float | None = None
    error_outcome: str | None = None

    def __post_init__(self) -> None:
        # Normalizes the optional recovery outcome and rejects invalid timeouts.
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("StagePolicy.timeout_seconds must be greater than zero when provided.")
        if self.error_outcome is not None:
            outcome = self.error_outcome.strip()
            if not outcome:
                raise ValueError("StagePolicy.error_outcome cannot be empty when provided.")
            object.__setattr__(self, "error_outcome", outcome)


@dataclass(frozen=True, slots=True)
class StateMachineSettings:
    """Run-wide limits, validator policy, and evidence-capture settings."""

    max_transitions: int = 100
    timeout_seconds: float | None = None
    validator_error_policy: ValidatorErrorPolicy = ValidatorErrorPolicy.FAIL_CLOSED
    validation_error_outcome: str = "validation_error"
    record_state_snapshots: bool = False

    def __post_init__(self) -> None:
        # Validates global limits and normalizes enum and outcome values.
        if self.max_transitions <= 0:
            raise ValueError("StateMachineSettings.max_transitions must be greater than zero.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("StateMachineSettings.timeout_seconds must be greater than zero when provided.")
        policy = self.validator_error_policy if isinstance(self.validator_error_policy, ValidatorErrorPolicy) else ValidatorErrorPolicy(self.validator_error_policy)
        outcome = self.validation_error_outcome.strip()
        if not outcome:
            raise ValueError("StateMachineSettings.validation_error_outcome cannot be empty.")
        object.__setattr__(self, "validator_error_policy", policy)
        object.__setattr__(self, "validation_error_outcome", outcome)


@dataclass(frozen=True, slots=True)
class WorkflowFeedback:
    """One structured reason delivered to a recovery stage."""

    kind: str
    source: str
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes routing identifiers and protects feedback detail mappings.
        object.__setattr__(self, "kind", _required_text(self.kind, "WorkflowFeedback.kind"))
        object.__setattr__(self, "source", _required_text(self.source, "WorkflowFeedback.source"))
        object.__setattr__(self, "code", _required_text(self.code, "WorkflowFeedback.code"))
        object.__setattr__(self, "message", self.message.strip())
        object.__setattr__(self, "details", _freeze_mapping(self.details))


@dataclass(frozen=True, slots=True)
class StageResult(Generic[StateT]):
    """Candidate state and semantic outcome proposed by a stage."""

    state: StateT
    outcome: str = "success"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensures every stage result carries a bounded non-empty outcome code.
        object.__setattr__(self, "outcome", _required_text(self.outcome, "StageResult.outcome"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured gate decision returned by every workflow validator."""

    status: ValidationStatus
    code: str = ""
    feedback: str = ""
    score: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes statuses and validates the code and optional unit score.
        status = self.status if isinstance(self.status, ValidationStatus) else ValidationStatus(self.status)
        code = self.code.strip() or status.value
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError("ValidationResult.score must be between 0.0 and 1.0 when provided.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "feedback", self.feedback.strip())
        object.__setattr__(self, "details", _freeze_mapping(self.details))

    @classmethod
    def passed(cls, *, code: str = "pass", feedback: str = "", score: float | None = None, details: Mapping[str, Any] | None = None) -> ValidationResult:
        # Builds a passing gate decision with optional diagnostic evidence.
        return cls(ValidationStatus.PASS, code=code, feedback=feedback, score=score, details=details or {})

    @classmethod
    def rejected(cls, code: str, feedback: str, *, score: float | None = None, details: Mapping[str, Any] | None = None) -> ValidationResult:
        # Builds a rejection whose code must resolve through the declared graph.
        return cls(ValidationStatus.REJECT, code=code, feedback=feedback, score=score, details=details or {})

    @classmethod
    def abstained(cls, code: str, feedback: str, *, details: Mapping[str, Any] | None = None) -> ValidationResult:
        # Builds a non-decision for normalization by the machine's error policy.
        return cls(ValidationStatus.ABSTAIN, code=code, feedback=feedback, details=details or {})

    @classmethod
    def errored(cls, code: str, feedback: str, *, details: Mapping[str, Any] | None = None) -> ValidationResult:
        # Builds a validator infrastructure failure without raising from the adapter.
        return cls(ValidationStatus.ERROR, code=code, feedback=feedback, details=details or {})


@dataclass(frozen=True, slots=True)
class StageContext(Generic[StateT]):
    """Per-attempt input provided to a workflow stage."""

    run_id: str
    stage: str
    state: StateT
    visit: int
    attempt: int
    transition_count: int
    feedback: tuple[WorkflowFeedback, ...]
    history: tuple[StageExecution, ...]
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Protects context metadata while preserving the explicitly mutable ledger.
        object.__setattr__(self, "run_id", _required_text(self.run_id, "StageContext.run_id"))
        object.__setattr__(self, "stage", _required_text(self.stage, "StageContext.stage"))
        if self.visit <= 0 or self.attempt <= 0 or self.transition_count < 0:
            raise ValueError("StageContext visit/attempt must be positive and transition_count cannot be negative.")
        if not isinstance(self.ledger, MutableMapping):
            raise TypeError("StageContext.ledger must be a mutable mapping.")
        object.__setattr__(self, "feedback", tuple(self.feedback))
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ValidationContext(Generic[StateT]):
    """Candidate and route information visible to a validator or guard."""

    run_id: str
    phase: ValidationPhase
    stage: str
    state_before: StateT
    candidate_state: StateT
    stage_result: StageResult[StateT]
    outcome: str
    target: str | None
    feedback: tuple[WorkflowFeedback, ...]
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Normalizes gate identifiers and protects validation metadata.
        phase = self.phase if isinstance(self.phase, ValidationPhase) else ValidationPhase(self.phase)
        object.__setattr__(self, "run_id", _required_text(self.run_id, "ValidationContext.run_id"))
        object.__setattr__(self, "stage", _required_text(self.stage, "ValidationContext.stage"))
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "outcome", _required_text(self.outcome, "ValidationContext.outcome"))
        object.__setattr__(self, "target", self.target.strip() if self.target is not None else None)
        object.__setattr__(self, "feedback", tuple(self.feedback))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class RoutingContext(Generic[StateT]):
    """Validated candidate information visible to a conditional router."""

    run_id: str
    stage: str
    candidate_state: StateT
    stage_result: StageResult[StateT]
    feedback: tuple[WorkflowFeedback, ...]
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Protects run metadata while retaining the shared run ledger reference.
        object.__setattr__(self, "run_id", _required_text(self.run_id, "RoutingContext.run_id"))
        object.__setattr__(self, "stage", _required_text(self.stage, "RoutingContext.stage"))
        object.__setattr__(self, "feedback", tuple(self.feedback))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    """Timed evidence for one top-level validator invocation."""

    phase: ValidationPhase
    validator: str
    result: ValidationResult
    duration_ms: float
    target: str | None = None

    def __post_init__(self) -> None:
        # Validates record identifiers and non-negative timing evidence.
        phase = self.phase if isinstance(self.phase, ValidationPhase) else ValidationPhase(self.phase)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "validator", _required_text(self.validator, "ValidationRecord.validator"))
        if self.duration_ms < 0:
            raise ValueError("ValidationRecord.duration_ms cannot be negative.")


@dataclass(frozen=True, slots=True)
class StageExecution:
    """One stage attempt, including retry failures and stage-phase validation."""

    stage: str
    visit: int
    attempt: int
    outcome: str | None
    accepted: bool
    duration_ms: float
    metadata: Mapping[str, Any]
    validations: tuple[ValidationRecord, ...]
    error_type: str | None = None
    error_message: str | None = None
    state_before: Any | None = None
    candidate_state: Any | None = None

    def __post_init__(self) -> None:
        # Normalizes immutable execution evidence without copying state snapshots.
        object.__setattr__(self, "stage", _required_text(self.stage, "StageExecution.stage"))
        if self.visit <= 0 or self.attempt <= 0 or self.duration_ms < 0:
            raise ValueError("StageExecution visit/attempt must be positive and duration_ms cannot be negative.")
        object.__setattr__(self, "outcome", self.outcome.strip() if self.outcome is not None else None)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        object.__setattr__(self, "validations", tuple(self.validations))


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """One selected direct or branch transition and its guard evidence."""

    sequence: int
    source: str
    target: str
    outcome: str
    accepted: bool
    trigger: str
    validations: tuple[ValidationRecord, ...]
    duration_ms: float

    def __post_init__(self) -> None:
        # Validates ordered transition evidence and protects guard record order.
        if self.sequence <= 0 or self.duration_ms < 0:
            raise ValueError("TransitionRecord.sequence must be positive and duration_ms cannot be negative.")
        object.__setattr__(self, "source", _required_text(self.source, "TransitionRecord.source"))
        object.__setattr__(self, "target", _required_text(self.target, "TransitionRecord.target"))
        object.__setattr__(self, "outcome", _required_text(self.outcome, "TransitionRecord.outcome"))
        object.__setattr__(self, "trigger", _required_text(self.trigger, "TransitionRecord.trigger"))
        object.__setattr__(self, "validations", tuple(self.validations))


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """Ordered, timestamped lifecycle signal delivered to observers."""

    sequence: int
    event_type: WorkflowEventType
    run_id: str
    stage: str | None
    occurred_at: datetime
    elapsed_ms: float
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Normalizes event identifiers and protects event payloads.
        event_type = self.event_type if isinstance(self.event_type, WorkflowEventType) else WorkflowEventType(self.event_type)
        if self.sequence <= 0 or self.elapsed_ms < 0:
            raise ValueError("WorkflowEvent.sequence must be positive and elapsed_ms cannot be negative.")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "run_id", _required_text(self.run_id, "WorkflowEvent.run_id"))
        object.__setattr__(self, "stage", self.stage.strip() if self.stage is not None else None)
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))


@dataclass(frozen=True, slots=True)
class StateMachineResult(Generic[StateT]):
    """Terminal state and ordered evidence returned by a completed workflow."""

    run_id: str
    status: MachineStatus
    terminal: str
    state: StateT
    ledger: Mapping[str, Any]
    metadata: Mapping[str, Any]
    stages: tuple[StageExecution, ...]
    transitions: tuple[TransitionRecord, ...]
    events: tuple[WorkflowEvent, ...]
    observer_errors: tuple[str, ...]
    duration_ms: float

    def __post_init__(self) -> None:
        # Freezes result collections while preserving caller-owned nested values.
        status = self.status if isinstance(self.status, MachineStatus) else MachineStatus(self.status)
        if self.duration_ms < 0:
            raise ValueError("StateMachineResult.duration_ms cannot be negative.")
        object.__setattr__(self, "run_id", _required_text(self.run_id, "StateMachineResult.run_id"))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "terminal", _required_text(self.terminal, "StateMachineResult.terminal"))
        object.__setattr__(self, "ledger", _freeze_mapping(self.ledger))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "transitions", tuple(self.transitions))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "observer_errors", tuple(self.observer_errors))


@runtime_checkable
class Stage(Protocol[StateT]):
    """Structural contract for one workflow stage."""

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT]:
        # Produces one candidate state and semantic route outcome.
        ...


@runtime_checkable
class Validator(Protocol[StateT]):
    """Structural contract shared by stage validators and transition guards."""

    @property
    def name(self) -> str:
        # Returns a stable identifier used in records and diagnostics.
        ...

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Inspects a candidate boundary without choosing a graph target.
        ...


@runtime_checkable
class Router(Protocol[StateT]):
    """Structural contract for bounded conditional branch selection."""

    @property
    def name(self) -> str:
        # Returns a stable identifier used in records and diagnostics.
        ...

    async def route(self, context: RoutingContext[StateT]) -> str:
        # Returns one branch key declared on the compiled graph.
        ...


@runtime_checkable
class WorkflowObserver(Protocol):
    """Asynchronous lifecycle-event consumer attached to one run."""

    async def on_event(self, event: WorkflowEvent) -> None:
        # Observes an ordered event without acquiring control-flow authority.
        ...


@dataclass(frozen=True, slots=True)
class RouteTarget(Generic[StateT]):
    """Conditional branch destination plus ordered target-specific guards."""

    target: str
    guards: tuple[Validator[StateT], ...] = ()

    def __post_init__(self) -> None:
        # Normalizes a branch target and protects guard declaration order.
        object.__setattr__(self, "target", _required_text(self.target, "RouteTarget.target"))
        object.__setattr__(self, "guards", tuple(self.guards))


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    # Copies a mapping into a read-only top-level view for durable evidence.
    return MappingProxyType(dict(value or {}))


def _required_text(value: str, field_name: str) -> str:
    # Normalizes a required identifier and reports the precise empty field.
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


__all__ = [
    "MachineStatus",
    "RetryPolicy",
    "RouteTarget",
    "Router",
    "RoutingContext",
    "Stage",
    "StageContext",
    "StageExecution",
    "StagePolicy",
    "StageResult",
    "StateMachineResult",
    "StateMachineSettings",
    "ValidationContext",
    "ValidationPhase",
    "ValidationRecord",
    "ValidationResult",
    "ValidationStatus",
    "Validator",
    "ValidatorErrorPolicy",
    "WorkflowEvent",
    "WorkflowEventType",
    "WorkflowFeedback",
    "WorkflowObserver",
]

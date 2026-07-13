"""FILE: vidbyte/workflows/contracts.py
PURPOSE: Defines the public typed language shared by workflow builders, adapters, and compiled runs.
ROLE IN CODEBASE: Imported by every vidbyte.workflows module and re-exported through vidbyte.workflows and vidbyte.

ARCHITECTURE NOTE:
    This file owns data and structural contracts only. Graph declaration lives in
    graph.py, execution lives in machine.py, and adapter behavior lives in the
    stage, validation, and routing modules. Frozen records copy caller mappings
    so execution evidence cannot be changed through the original dictionaries.

PUBLIC API INVENTORY:
    WorkflowLifecycleStatus / TerminalStatus / MachineStatus: Orthogonal run and
        declared-terminal status, including the compatibility terminal alias.
    RetryPolicy / StagePolicy / StateMachineSettings: Layered execution policy.
    WorkflowInterrupt / WorkflowCommand / ResumeCommand: Bounded control requests.
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
    3. Do not persist records here; events.py and persistence.py own durable schemas.
    4. Do not expose an untracked mutable ledger; observations are event-backed.

KNOWN EDGE CASES:
    Frozen dataclasses can still contain mutable nested values supplied by SDK
    users. Top-level mappings are protected, but deep immutability is not claimed.
    State snapshots are optional because state can be large or sensitive.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Run the repository suite and the inline workflow smoke described in the design.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from .approval import ApprovalGate, RiskLevel
from .budget import CostModel, UsageReport, WorkflowBudget
from .detours import WorkflowSignal
from .errors import WorkflowErrorRecord
from .events import WorkflowEvent, WorkflowEventType
from .subgraphs import Send


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


class WorkflowLifecycleStatus(str, Enum):
    """Execution condition independent from the graph's declared position."""

    RUNNING = "running"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    INTERRUPTED = "interrupted"
    FINISHED = "finished"
    ERROR = "error"


class TerminalStatus(str, Enum):
    """Declared status attached to a terminal graph node."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


# Preserves the PR #268 public name without creating a second terminal-status type.
MachineStatus = TerminalStatus


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Deterministic retry settings for one stage invocation."""

    max_attempts: int = 1
    delay_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    retry_for: tuple[type[Exception], ...] = (Exception,)

    def __post_init__(self) -> None:
        # Rejects invalid retry bounds before a workflow can begin execution.
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool) or self.max_attempts <= 0:
            raise ValueError("RetryPolicy.max_attempts must be an integer greater than zero.")
        if not isinstance(self.delay_seconds, (int, float)) or isinstance(self.delay_seconds, bool) or not isfinite(self.delay_seconds) or self.delay_seconds < 0:
            raise ValueError("RetryPolicy.delay_seconds must be a finite non-negative number.")
        if not isinstance(self.backoff_multiplier, (int, float)) or isinstance(self.backoff_multiplier, bool) or not isfinite(self.backoff_multiplier) or self.backoff_multiplier <= 0:
            raise ValueError("RetryPolicy.backoff_multiplier must be a finite number greater than zero.")
        try:
            retry_for = tuple(self.retry_for)
        except TypeError as exc:
            raise ValueError("RetryPolicy.retry_for must contain one or more Exception subclasses.") from exc
        if not retry_for or any(not isinstance(item, type) or not issubclass(item, Exception) for item in retry_for):
            raise ValueError("RetryPolicy.retry_for must contain one or more Exception subclasses.")
        object.__setattr__(self, "delay_seconds", float(self.delay_seconds))
        object.__setattr__(self, "backoff_multiplier", float(self.backoff_multiplier))
        object.__setattr__(self, "retry_for", retry_for)


@dataclass(frozen=True, slots=True)
class StagePolicy:
    """Visit, timeout, retry, and handled-error routing policy for one stage."""

    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: float | None = None
    max_visits: int | None = None
    error_outcome: str | None = None

    def __post_init__(self) -> None:
        # Normalizes the optional recovery outcome and rejects invalid timeouts.
        if not isinstance(self.retry, RetryPolicy):
            raise TypeError("StagePolicy.retry must be a RetryPolicy instance.")
        if self.timeout_seconds is not None:
            if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
                raise ValueError("StagePolicy.timeout_seconds must be a finite number greater than zero when provided.")
            object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        if self.max_visits is not None:
            if not isinstance(self.max_visits, int) or isinstance(self.max_visits, bool) or self.max_visits <= 0:
                raise ValueError("StagePolicy.max_visits must be an integer greater than zero when provided.")
        if self.error_outcome is not None:
            if not isinstance(self.error_outcome, str):
                raise TypeError("StagePolicy.error_outcome must be a string when provided.")
            outcome = self.error_outcome.strip()
            if not outcome:
                raise ValueError("StagePolicy.error_outcome cannot be empty when provided.")
            object.__setattr__(self, "error_outcome", outcome)


@dataclass(frozen=True, slots=True)
class StateMachineSettings:
    """Run-wide budgets, validator policy, and evidence-capture settings."""

    budget: WorkflowBudget = field(default_factory=WorkflowBudget)
    cost_model: CostModel | None = None
    max_transitions: int | None = None
    timeout_seconds: float | None = None
    validator_error_policy: ValidatorErrorPolicy = ValidatorErrorPolicy.FAIL_CLOSED
    validation_error_outcome: str = "validation_error"
    record_state_snapshots: bool = False

    def __post_init__(self) -> None:
        # Folds legacy limit arguments into the canonical WorkflowBudget record.
        if not isinstance(self.budget, WorkflowBudget):
            raise TypeError("StateMachineSettings.budget must be a WorkflowBudget instance.")
        budget = self.budget
        if self.max_transitions is not None:
            if not isinstance(self.max_transitions, int) or isinstance(self.max_transitions, bool) or self.max_transitions <= 0:
                raise ValueError("StateMachineSettings.max_transitions must be an integer greater than zero when provided.")
            budget = replace(budget, max_transitions=self.max_transitions)
        if self.timeout_seconds is not None:
            if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
                raise ValueError("StateMachineSettings.timeout_seconds must be a finite number greater than zero when provided.")
            budget = replace(budget, timeout_seconds=float(self.timeout_seconds))
        if self.cost_model is not None and not callable(getattr(self.cost_model, "estimate", None)):
            raise TypeError("StateMachineSettings.cost_model must provide estimate(usage) when provided.")
        if not isinstance(self.record_state_snapshots, bool):
            raise TypeError("StateMachineSettings.record_state_snapshots must be a boolean.")
        policy = self.validator_error_policy if isinstance(self.validator_error_policy, ValidatorErrorPolicy) else ValidatorErrorPolicy(self.validator_error_policy)
        if not isinstance(self.validation_error_outcome, str):
            raise TypeError("StateMachineSettings.validation_error_outcome must be a string.")
        outcome = self.validation_error_outcome.strip()
        if not outcome:
            raise ValueError("StateMachineSettings.validation_error_outcome cannot be empty.")
        object.__setattr__(self, "validator_error_policy", policy)
        object.__setattr__(self, "validation_error_outcome", outcome)
        object.__setattr__(self, "budget", budget)
        object.__setattr__(self, "max_transitions", budget.max_transitions)
        object.__setattr__(self, "timeout_seconds", budget.timeout_seconds)


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
        if not isinstance(self.message, str):
            raise TypeError("WorkflowFeedback.message must be a string.")
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
class WorkflowInterrupt:
    """One replayable request for external input at a stage call site."""

    namespace: str
    prompt: str
    schema: type[BaseModel] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates the durable request identity without serializing executable schema code.
        object.__setattr__(self, "namespace", _required_text(self.namespace, "WorkflowInterrupt.namespace"))
        object.__setattr__(self, "prompt", _required_text(self.prompt, "WorkflowInterrupt.prompt"))
        if self.schema is not None and (not isinstance(self.schema, type) or not issubclass(self.schema, BaseModel)):
            raise TypeError("WorkflowInterrupt.schema must be a Pydantic BaseModel class when provided.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


class PendingRequestKind(str, Enum):
    """Kind of durable external input that currently suspends a run."""

    APPROVAL = "approval"
    INTERRUPT = "interrupt"
    SUBGRAPH = "subgraph"


@dataclass(frozen=True, slots=True)
class PendingRequest:
    """Public bounded description of the exact request needed to resume a run."""

    request_id: str
    kind: PendingRequestKind
    stage: str
    prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes the external resume token and freezes diagnostic request facts.
        object.__setattr__(self, "request_id", _required_text(self.request_id, "PendingRequest.request_id"))
        object.__setattr__(self, "kind", self.kind if isinstance(self.kind, PendingRequestKind) else PendingRequestKind(self.kind))
        object.__setattr__(self, "stage", _required_text(self.stage, "PendingRequest.stage"))
        object.__setattr__(self, "prompt", _required_text(self.prompt, "PendingRequest.prompt"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ResumeCommand:
    """External response to one exact pending approval or stage interrupt."""

    request_id: str
    value: Any = None
    approved: bool | None = None

    def __post_init__(self) -> None:
        # Rejects ambiguous approval values while retaining arbitrary schema-validated input.
        object.__setattr__(self, "request_id", _required_text(self.request_id, "ResumeCommand.request_id"))
        if self.approved is not None and not isinstance(self.approved, bool):
            raise TypeError("ResumeCommand.approved must be a boolean or None.")

    @classmethod
    def approve(cls, request_id: str, value: Any = None) -> "ResumeCommand":
        # Creates an affirmative response for a pending transition approval.
        return cls(request_id=request_id, value=value, approved=True)

    @classmethod
    def reject(cls, request_id: str, value: Any = None) -> "ResumeCommand":
        # Creates a negative response for a pending transition approval.
        return cls(request_id=request_id, value=value, approved=False)

    @classmethod
    def resume(cls, request_id: str, value: Any) -> "ResumeCommand":
        # Creates a value response for a replayable StageContext.interrupt call.
        return cls(request_id=request_id, value=value, approved=None)


@dataclass(frozen=True, slots=True)
class WorkflowCommand(Generic[StateT]):
    """Reducer update plus one statically bounded control-flow request."""

    update: Mapping[str, Any] = field(default_factory=dict)
    outcome: str | None = None
    goto: str | None = None
    sends: tuple[Send, ...] = ()
    signals: tuple[WorkflowSignal, ...] = ()
    interrupt: WorkflowInterrupt | None = None
    return_from_detour: str | None = None
    usage: UsageReport | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensures updates accompany at most one primary control action.
        object.__setattr__(self, "update", _freeze_mapping(self.update))
        outcome = _optional_text(self.outcome, "WorkflowCommand.outcome")
        goto = _optional_text(self.goto, "WorkflowCommand.goto")
        return_from_detour = _optional_text(self.return_from_detour, "WorkflowCommand.return_from_detour")
        sends = tuple(self.sends)
        signals = tuple(self.signals)
        if any(not isinstance(item, Send) for item in sends):
            raise TypeError("WorkflowCommand.sends must contain Send values.")
        if any(not isinstance(item, WorkflowSignal) for item in signals):
            raise TypeError("WorkflowCommand.signals must contain WorkflowSignal values.")
        if self.interrupt is not None and not isinstance(self.interrupt, WorkflowInterrupt):
            raise TypeError("WorkflowCommand.interrupt must be WorkflowInterrupt when provided.")
        if self.usage is not None and not isinstance(self.usage, UsageReport):
            raise TypeError("WorkflowCommand.usage must be UsageReport when provided.")
        primary_count = sum((outcome is not None, goto is not None, bool(sends), self.interrupt is not None, return_from_detour is not None))
        if primary_count > 1:
            raise ValueError("WorkflowCommand may select only one of outcome, goto, sends, interrupt, or return_from_detour.")
        if primary_count == 0:
            outcome = "success"
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "goto", goto)
        object.__setattr__(self, "sends", sends)
        object.__setattr__(self, "signals", signals)
        object.__setattr__(self, "return_from_detour", return_from_detour)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


class _StageInterruptSignal(BaseException):
    """Internal non-retryable stack unwind used by StageContext.interrupt."""

    def __init__(self, request: WorkflowInterrupt, ordinal: int) -> None:
        # Carries only the deterministic call-site ordinal and typed request.
        super().__init__(request.prompt)
        self.request = request
        self.ordinal = ordinal


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured gate decision returned by every workflow validator."""

    status: ValidationStatus
    code: str = ""
    feedback: str = ""
    score: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    usage: UsageReport | None = None

    def __post_init__(self) -> None:
        # Normalizes statuses and validates the code and optional unit score.
        status = self.status if isinstance(self.status, ValidationStatus) else ValidationStatus(self.status)
        if not isinstance(self.code, str) or not isinstance(self.feedback, str):
            raise TypeError("ValidationResult.code and feedback must be strings.")
        code = self.code.strip() or status.value
        if self.score is not None:
            if not isinstance(self.score, (int, float)) or isinstance(self.score, bool) or not isfinite(self.score) or not 0.0 <= self.score <= 1.0:
                raise ValueError("ValidationResult.score must be a finite number between 0.0 and 1.0 when provided.")
            object.__setattr__(self, "score", float(self.score))
        if self.usage is not None and not isinstance(self.usage, UsageReport):
            raise TypeError("ValidationResult.usage must be UsageReport when provided.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "feedback", self.feedback.strip())
        object.__setattr__(self, "details", _freeze_mapping(self.details))

    @classmethod
    def passed(cls, *, code: str = "pass", feedback: str = "", score: float | None = None, details: Mapping[str, Any] | None = None, usage: UsageReport | None = None) -> ValidationResult:
        # Builds a passing gate decision with optional diagnostic evidence.
        return cls(ValidationStatus.PASS, code=code, feedback=feedback, score=score, details=details or {}, usage=usage)

    @classmethod
    def rejected(cls, code: str, feedback: str, *, score: float | None = None, details: Mapping[str, Any] | None = None, usage: UsageReport | None = None) -> ValidationResult:
        # Builds a rejection whose code must resolve through the declared graph.
        return cls(ValidationStatus.REJECT, code=code, feedback=feedback, score=score, details=details or {}, usage=usage)

    @classmethod
    def abstained(cls, code: str, feedback: str, *, details: Mapping[str, Any] | None = None, usage: UsageReport | None = None) -> ValidationResult:
        # Builds a non-decision for normalization by the machine's error policy.
        return cls(ValidationStatus.ABSTAIN, code=code, feedback=feedback, details=details or {}, usage=usage)

    @classmethod
    def errored(cls, code: str, feedback: str, *, details: Mapping[str, Any] | None = None, usage: UsageReport | None = None) -> ValidationResult:
        # Builds a validator infrastructure failure without raising from the adapter.
        return cls(ValidationStatus.ERROR, code=code, feedback=feedback, details=details or {}, usage=usage)


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
    observations: Mapping[str, Any]
    metadata: Mapping[str, Any]
    super_step: int = 0
    idempotency_key: str = ""
    _observe_handler: Callable[[str, Any], Awaitable[Any]] | None = field(default=None, repr=False, compare=False)
    _interrupt_handler: Callable[[WorkflowInterrupt], Any] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Deep-freezes projected observations and assigns a stable retry identity.
        object.__setattr__(self, "run_id", _required_text(self.run_id, "StageContext.run_id"))
        object.__setattr__(self, "stage", _required_text(self.stage, "StageContext.stage"))
        if self.visit <= 0 or self.attempt <= 0 or self.transition_count < 0 or self.super_step < 0:
            raise ValueError("StageContext visit/attempt must be positive and transition_count/super_step cannot be negative.")
        object.__setattr__(self, "feedback", tuple(self.feedback))
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "observations", _deep_freeze_mapping(self.observations))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        key = self.idempotency_key.strip() if isinstance(self.idempotency_key, str) else ""
        object.__setattr__(self, "idempotency_key", key or f"{self.run_id}:{self.stage}:{self.visit}")

    @property
    def ledger(self) -> Mapping[str, Any]:
        # Preserves read-only PR #268 access while removing untracked mutation.
        return self.observations

    async def observe(self, channel: str, value: Any) -> Any:
        # Appends and reduces one immediate observation through the owning runtime.
        if self._observe_handler is None:
            raise RuntimeError("StageContext.observe() requires a running state machine context.")
        return await self._observe_handler(_required_text(channel, "observation channel"), value)

    def interrupt(self, request: WorkflowInterrupt) -> Any:
        # Returns a replayed value or unwinds the stage at a durable interrupt boundary.
        if not isinstance(request, WorkflowInterrupt):
            raise TypeError("StageContext.interrupt() requires WorkflowInterrupt.")
        if self._interrupt_handler is None:
            raise RuntimeError("StageContext.interrupt() requires a running state machine context.")
        return self._interrupt_handler(request)


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
    observations: Mapping[str, Any]
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
        object.__setattr__(self, "observations", _deep_freeze_mapping(self.observations))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def ledger(self) -> Mapping[str, Any]:
        # Preserves read-only access for validators written against PR #268.
        return self.observations


@dataclass(frozen=True, slots=True)
class RoutingContext(Generic[StateT]):
    """Validated candidate information visible to a conditional router."""

    run_id: str
    stage: str
    candidate_state: StateT
    stage_result: StageResult[StateT]
    feedback: tuple[WorkflowFeedback, ...]
    observations: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Protects run metadata while retaining the shared run ledger reference.
        object.__setattr__(self, "run_id", _required_text(self.run_id, "RoutingContext.run_id"))
        object.__setattr__(self, "stage", _required_text(self.stage, "RoutingContext.stage"))
        object.__setattr__(self, "feedback", tuple(self.feedback))
        object.__setattr__(self, "observations", _deep_freeze_mapping(self.observations))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def ledger(self) -> Mapping[str, Any]:
        # Preserves read-only access for routers written against PR #268.
        return self.observations


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
class StateMachineResult(Generic[StateT]):
    """Projected run state and ordered evidence at any durable boundary."""

    run_id: str
    definition_id: str
    lifecycle: WorkflowLifecycleStatus
    terminal_status: TerminalStatus | None
    terminal: str | None
    state: StateT
    observations: Mapping[str, Any]
    pending: PendingRequest | None
    usage: UsageReport
    checkpoint_id: str | None
    metadata: Mapping[str, Any]
    stages: tuple[StageExecution, ...]
    transitions: tuple[TransitionRecord, ...]
    events: tuple[WorkflowEvent, ...]
    observer_errors: tuple[str, ...]
    error: WorkflowErrorRecord | None
    duration_ms: float

    def __post_init__(self) -> None:
        # Freezes projected collections and enforces lifecycle/terminal orthogonality.
        lifecycle = self.lifecycle if isinstance(self.lifecycle, WorkflowLifecycleStatus) else WorkflowLifecycleStatus(self.lifecycle)
        terminal_status = self.terminal_status if self.terminal_status is None or isinstance(self.terminal_status, TerminalStatus) else TerminalStatus(self.terminal_status)
        if self.duration_ms < 0:
            raise ValueError("StateMachineResult.duration_ms cannot be negative.")
        object.__setattr__(self, "run_id", _required_text(self.run_id, "StateMachineResult.run_id"))
        object.__setattr__(self, "definition_id", _required_text(self.definition_id, "StateMachineResult.definition_id"))
        object.__setattr__(self, "lifecycle", lifecycle)
        object.__setattr__(self, "terminal_status", terminal_status)
        object.__setattr__(self, "terminal", _optional_text(self.terminal, "StateMachineResult.terminal"))
        if lifecycle is WorkflowLifecycleStatus.FINISHED and (terminal_status is None or self.terminal is None):
            raise ValueError("A FINISHED StateMachineResult requires terminal_status and terminal.")
        if lifecycle is not WorkflowLifecycleStatus.FINISHED and (terminal_status is not None or self.terminal is not None):
            raise ValueError("Only a FINISHED StateMachineResult may carry a terminal status or name.")
        if not isinstance(self.usage, UsageReport):
            raise TypeError("StateMachineResult.usage must be UsageReport.")
        if self.pending is not None and not isinstance(self.pending, PendingRequest):
            raise TypeError("StateMachineResult.pending must be PendingRequest when provided.")
        object.__setattr__(self, "observations", _deep_freeze_mapping(self.observations))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "transitions", tuple(self.transitions))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "observer_errors", tuple(self.observer_errors))

    @property
    def status(self) -> TerminalStatus | None:
        # Preserves the PR #268 terminal-status attribute for completed runs.
        return self.terminal_status

    @property
    def ledger(self) -> Mapping[str, Any]:
        # Preserves a read-only compatibility projection over immediate observations.
        return self.observations


@runtime_checkable
class Stage(Protocol[StateT]):
    """Structural contract for one workflow stage."""

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT] | WorkflowCommand[StateT]:
        # Produces one whole-state candidate or reducer-backed bounded command.
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
    """Conditional branch destination plus guards and transition policy."""

    target: str
    guards: tuple[Validator[StateT], ...] = ()
    approval: ApprovalGate | None = None
    risk: RiskLevel = RiskLevel.LOW

    def __post_init__(self) -> None:
        # Normalizes a branch target and protects guard declaration order.
        object.__setattr__(self, "target", _required_text(self.target, "RouteTarget.target"))
        object.__setattr__(self, "guards", tuple(self.guards))
        if self.approval is not None and not isinstance(self.approval, ApprovalGate):
            raise TypeError("RouteTarget.approval must be ApprovalGate when provided.")
        object.__setattr__(self, "risk", self.risk if isinstance(self.risk, RiskLevel) else RiskLevel(self.risk))


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    # Copies a mapping into a read-only top-level view for durable evidence.
    if value is not None and not isinstance(value, Mapping):
        raise TypeError(f"Workflow mapping fields require Mapping values, got {type(value).__name__}.")
    return MappingProxyType(dict(value or {}))


def _deep_freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    # Recursively removes the old nested-mutation escape hatch from observations.
    if value is not None and not isinstance(value, Mapping):
        raise TypeError(f"Workflow observation fields require Mapping values, got {type(value).__name__}.")
    return MappingProxyType({str(key): _deep_freeze(item) for key, item in dict(value or {}).items()})


def _deep_freeze(value: Any) -> Any:
    # Freezes common nested containers while leaving typed scalar/domain objects intact.
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _required_text(value: str, field_name: str) -> str:
    # Normalizes a required identifier and reports the precise empty field.
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def _optional_text(value: str | None, field_name: str) -> str | None:
    # Normalizes optional identifiers while rejecting non-string values.
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string when provided, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty when provided.")
    return text


__all__ = [
    "MachineStatus",
    "PendingRequest",
    "PendingRequestKind",
    "RetryPolicy",
    "ResumeCommand",
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
    "TerminalStatus",
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
    "WorkflowCommand",
    "WorkflowInterrupt",
    "WorkflowLifecycleStatus",
    "WorkflowObserver",
]

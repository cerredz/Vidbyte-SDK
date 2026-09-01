"""FILE: vidbyte/sessions/failure/types.py

PURPOSE: Defines the finite failure-code vocabulary and safe immutable failure records.
ROLE IN CODEBASE: Supplies canonical codes, lifecycle enums, sanitization, exception mapping, and serialization.
ARCHITECTURE NOTE: Codes are stable data-contract values; raw exception text is never the failure identity.
COMMON MODIFICATION PATTERNS: Add a category-prefixed code with docs, mapping coverage, and a focused test.
KNOWN EDGE CASES: Keep detail values bounded and credential-free; unknown exceptions map to runtime.error.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/vocabulary.md.
TESTS: python scripts/test-session-failure-vocabulary.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import uuid4

_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404


class FailureCode(str, Enum):
    """Finite machine-readable vocabulary for deterministic SDK failures."""

    CONFIGURATION_INVALID = "configuration.invalid"
    CONFIGURATION_MISSING_REQUIRED = "configuration.missing_required"
    CONFIGURATION_UNSUPPORTED_COMBINATION = "configuration.unsupported_combination"
    CONFIGURATION_UNKNOWN_MODEL = "configuration.unknown_model"
    CONFIGURATION_INVALID_SCHEMA = "configuration.invalid_schema"
    CONFIGURATION_INVALID_PROVIDER = "configuration.invalid_provider"
    CONFIGURATION_INVALID_TOOL = "configuration.invalid_tool"
    CONFIGURATION_INVALID_MIDDLEWARE = "configuration.invalid_middleware"
    CONFIGURATION_INVALID_RUNTIME = "configuration.invalid_runtime"
    CONFIGURATION_INVALID_ARGUMENT = "configuration.invalid_argument"
    INPUT_EMPTY = "input.empty"
    INPUT_INVALID = "input.invalid"
    INPUT_TYPE_INVALID = "input.type_invalid"
    OUTPUT_MISSING = "output.missing"
    OUTPUT_INVALID = "output.invalid"
    OUTPUT_SCHEMA_VIOLATION = "output.schema_violation"
    CONTRACT_UNSATISFIED = "contract.unsatisfied"
    SERIALIZATION_INVALID = "serialization.invalid"
    MODEL_REQUEST_FAILED = "model.request_failed"
    MODEL_RESPONSE_INVALID = "model.response_invalid"
    MODEL_TIMEOUT = "model.timeout"
    MODEL_RATE_LIMITED = "model.rate_limited"
    MODEL_AUTHENTICATION_FAILED = "model.authentication_failed"
    MODEL_NOT_FOUND = "model.not_found"
    MODEL_UNSUPPORTED = "model.unsupported"
    MODEL_CONTEXT_LIMIT = "model.context_limit"
    MODEL_CONTENT_FILTERED = "model.content_filtered"
    MODEL_RETRY_EXHAUSTED = "model.retry_exhausted"
    MODEL_FALLBACK_EXHAUSTED = "model.fallback_exhausted"
    PROVIDER_SELECTION_FAILED = "provider.selection_failed"
    PROVIDER_CONFIGURATION_INVALID = "provider.configuration_invalid"
    TOOL_NOT_FOUND = "tool.not_found"
    TOOL_ARGUMENTS_INVALID = "tool.arguments_invalid"
    TOOL_PERMISSION_DENIED = "tool.permission_denied"
    TOOL_DISABLED = "tool.disabled"
    TOOL_TIMEOUT = "tool.timeout"
    TOOL_RATE_LIMITED = "tool.rate_limited"
    TOOL_EXECUTION_FAILED = "tool.execution_failed"
    TOOL_RESULT_INVALID = "tool.result_invalid"
    TOOL_RESULT_MISSING = "tool.result_missing"
    TOOL_RETRY_EXHAUSTED = "tool.retry_exhausted"
    TOOL_CALL_LIMIT_REACHED = "tool.call_limit_reached"
    TOOL_CALLS_PER_ITERATION_LIMIT = "tool.calls_per_iteration_limit"
    TOOL_IDENTICAL_CALL_LIMIT = "tool.identical_call_limit"
    TOOL_CONSECUTIVE_FAILURE_LIMIT = "tool.consecutive_failure_limit"
    TOOL_ERROR_LIMIT = "tool.error_limit"
    TOOL_SLIDING_WINDOW_LIMIT = "tool.sliding_window_limit"
    TOOL_LOOP_LIMIT = "tool.loop_limit"
    ACTION_POLICY_VIOLATION = "action.policy_violation"
    ACTION_UNSAFE = "action.unsafe"
    ACTION_FORBIDDEN = "action.forbidden"
    ACTION_INVALID_ARGUMENTS = "action.invalid_arguments"
    ACTION_WRONG_TARGET = "action.wrong_target"
    ACTION_OUT_OF_ORDER = "action.out_of_order"
    ACTION_DUPLICATE = "action.duplicate"
    ACTION_PRECONDITION_FAILED = "action.precondition_failed"
    ACTION_NO_PROGRESS = "action.no_progress"
    ACTION_LOOPING = "action.looping"
    ACTION_PARTIAL = "action.partial"
    ACTION_NOT_APPLIED = "action.not_applied"
    ACTION_CONFLICT = "action.conflict"
    ACTION_IDEMPOTENCY_VIOLATION = "action.idempotency_violation"
    ACTION_UNEXPECTED_SIDE_EFFECT = "action.unexpected_side_effect"
    RUNTIME_MAX_ITERATIONS = "runtime.max_iterations"
    RUNTIME_MAX_TOKENS = "runtime.max_tokens"
    RUNTIME_MAX_TOOL_CALLS = "runtime.max_tool_calls"
    RUNTIME_TIMEOUT = "runtime.timeout"
    RUNTIME_MIDDLEWARE_ABORT = "runtime.middleware_abort"
    RUNTIME_MIDDLEWARE_ERROR = "runtime.middleware_error"
    RUNTIME_ERROR = "runtime.error"
    RUNTIME_CANCELLED = "runtime.cancelled"
    RUNTIME_CONTEXT_BUILD_FAILED = "runtime.context_build_failed"
    RUNTIME_COMPACTION_FAILED = "runtime.compaction_failed"
    RUNTIME_QUEUE_LIMIT = "runtime.queue_limit"
    RESOURCE_EXHAUSTED = "resource.exhausted"
    SESSION_NOT_FOUND = "session.not_found"
    SESSION_CHECKPOINT_MISSING = "session.checkpoint_missing"
    SESSION_SERIALIZATION_FAILED = "session.serialization_failed"
    SESSION_VERSION_MISMATCH = "session.version_mismatch"
    SESSION_PERSISTENCE_FAILED = "session.persistence_failed"
    SESSION_RESUME_FAILED = "session.resume_failed"
    SESSION_FORK_FAILED = "session.fork_failed"
    SESSION_REWIND_INVALID = "session.rewind_invalid"
    SESSION_SCOPE_DENIED = "session.scope_denied"
    STATE_CORRUPTED = "state.corrupted"
    STATE_CONFLICT = "state.conflict"
    DATA_NOT_FOUND = "data.not_found"
    DATA_MALFORMED = "data.malformed"
    DATA_INCOMPLETE = "data.incomplete"
    DATA_STALE = "data.stale"
    DATA_CONFLICT = "data.conflict"
    DATA_SOURCE_UNAVAILABLE = "data.source_unavailable"
    DATA_PERMISSION_DENIED = "data.permission_denied"
    WORKFLOW_DEFINITION_INVALID = "workflow.definition_invalid"
    WORKFLOW_VALIDATION_FAILED = "workflow.validation_failed"
    WORKFLOW_STAGE_FAILED = "workflow.stage_failed"
    WORKFLOW_ROUTING_FAILED = "workflow.routing_failed"
    WORKFLOW_TRANSITION_LIMIT = "workflow.transition_limit"
    AGENT_HANDOFF_FAILED = "agent.handoff_failed"
    AGENT_TRANSFER_FAILED = "agent.transfer_failed"
    TEAM_TASK_BLOCKED = "team.task_blocked"
    TEAM_REPLAN_LIMIT = "team.replan_limit"
    TEAM_UNRECOVERABLE = "team.unrecoverable"
    USAGE_RECORDING_CORRUPTED = "usage.recording_corrupted"
    TRACE_CAPTURE_FAILED = "trace.capture_failed"
    TRACE_EXPORT_FAILED = "trace.export_failed"
    RECOVERY_HANDLER_FAILED = "recovery.handler_failed"
    RULE_EVALUATION_FAILED = "rule.evaluation_failed"

    @property
    def category(self) -> str:
        """Return the stable category prefix used for aggregation."""
        return self.value.split(".", 1)[0]

    @classmethod
    def from_value(cls, value: FailureCode | str) -> FailureCode:
        """Coerce a known string value into the closed vocabulary."""
        if isinstance(value, cls):
            return value
        return cls(str(value))

    @classmethod
    def from_exception(cls, exc: BaseException) -> FailureCode:
        """Map a known SDK exception family to one deterministic code."""
        name = type(exc).__name__.lower()
        module = type(exc).__module__.lower()
        status_code = getattr(exc, "status_code", None)
        status_codes = {_HTTP_TOO_MANY_REQUESTS: cls.MODEL_RATE_LIMITED, _HTTP_UNAUTHORIZED: cls.MODEL_AUTHENTICATION_FAILED, _HTTP_FORBIDDEN: cls.MODEL_AUTHENTICATION_FAILED, _HTTP_NOT_FOUND: cls.MODEL_NOT_FOUND}
        if status_code in status_codes:
            return status_codes[status_code]
        return cls._from_exception_name(name, module)

    @classmethod
    def _from_exception_name(cls, name: str, module: str) -> FailureCode:
        # @intent exception-vocabulary-is-closed
        # Specific SDK exception families map to versioned codes so new text
        # from a provider can never silently create a new taxonomy entry.
        # Keep exception-family matching ordered and data-driven so the vocabulary stays finite.
        families = (
            (("outputschemaviolation",), cls.OUTPUT_SCHEMA_VIOLATION),
            (("allmodelsfailed",), cls.MODEL_FALLBACK_EXHAUSTED),
            (("providerconfiguration",), cls.PROVIDER_CONFIGURATION_INVALID),
            (("providerselection",), cls.PROVIDER_SELECTION_FAILED),
            (("unsupportedprovider",), cls.MODEL_UNSUPPORTED),
            (("providerresponse",), cls.MODEL_RESPONSE_INVALID),
            (("providerrequest",), cls.MODEL_REQUEST_FAILED),
            (("permissiondenied",), cls.TOOL_PERMISSION_DENIED),
            (("reasoningtraceargument",), cls.TOOL_ARGUMENTS_INVALID),
            (("reasoningtracedefinition",), cls.CONFIGURATION_INVALID),
            (("toolregistry", "toolregistration"), cls.CONFIGURATION_INVALID_TOOL),
            (("toolexecution", "mcptoolexecution"), cls.TOOL_EXECUTION_FAILED),
            (("mcpinitialize", "mcpprotocol", "mcpconnection"), cls.DATA_SOURCE_UNAVAILABLE),
            (("mcptooldiscovery",), cls.TOOL_NOT_FOUND),
            (("sessionnotfound",), cls.SESSION_NOT_FOUND),
            (("checkpointnotfound",), cls.SESSION_CHECKPOINT_MISSING),
            (("sessionerror",), cls.SESSION_PERSISTENCE_FAILED),
            (("sessionserialization",), cls.SESSION_SERIALIZATION_FAILED),
            (("sessionversion",), cls.SESSION_VERSION_MISMATCH),
            (("sessionstore",), cls.SESSION_PERSISTENCE_FAILED),
            (("sessionusage",), cls.USAGE_RECORDING_CORRUPTED),
            (("agentfork",), cls.SESSION_FORK_FAILED),
            (("agenttransfer",), cls.AGENT_TRANSFER_FAILED),
            (("taskledger",), cls.TEAM_TASK_BLOCKED),
            (("aggregateexecution",), cls.TEAM_UNRECOVERABLE),
            (("pipelineexecution",), cls.WORKFLOW_STAGE_FAILED),
            (("tracerconfiguration",), cls.TRACE_EXPORT_FAILED),
            (("sourcepinmismatch",), cls.DATA_CONFLICT),
            (("sourcesecurity",), cls.DATA_PERMISSION_DENIED),
            (("sourceparse",), cls.DATA_MALFORMED),
            (("sourcefetch",), cls.DATA_SOURCE_UNAVAILABLE),
        )
        for tokens, code in families:
            if any(token in name for token in tokens):
                return code
        return cls._from_exception_fallback(name, module)

    @classmethod
    def _from_exception_fallback(cls, name: str, module: str) -> FailureCode:
        # @intent conservative-unknown-exception-fallback
        # Broad matches run only after specific families; unknown exceptions
        # stay runtime.error instead of being mistaken for a retryable class.
        # Apply broad families only after specific SDK exception names have been checked.
        if module.startswith("vidbyte.workflows"):
            return cls.WORKFLOW_STAGE_FAILED
        fallbacks = (("configuration", cls.CONFIGURATION_INVALID), ("cancel", cls.RUNTIME_CANCELLED), ("timeout", cls.MODEL_TIMEOUT), ("serialization", cls.SERIALIZATION_INVALID), ("agentexecution", cls.RUNTIME_ERROR))
        for token, code in fallbacks:
            if token in name:
                return code
        return cls.RUNTIME_ERROR


class FailurePhase(str, Enum):
    """Lifecycle boundary at which a failure was observed."""

    CONFIGURATION = "configuration"
    INPUT = "input"
    MODEL = "model"
    TOOL = "tool"
    ACTION = "action"
    OUTPUT = "output"
    LOOP = "loop"
    SESSION = "session"
    WORKFLOW = "workflow"
    DATA = "data"
    RESOURCE = "resource"
    OBSERVABILITY = "observability"
    RECOVERY = "recovery"
    RUNTIME = "runtime"
    UNKNOWN = "unknown"


class FailureStatus(str, Enum):
    """Lifecycle state of one observed failure."""

    OBSERVED = "observed"
    RECOVERING = "recovering"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"
    TERMINAL = "terminal"


class FailureDisposition(str, Enum):
    """Action to take after a failure is observed."""

    RECORD = "record"
    CONTINUE = "continue"
    ROUTE = "route"
    STOP = "stop"
    RAISE = "raise"


class RuleErrorMode(str, Enum):
    """Behavior when a rule or recovery handler itself raises."""

    OPEN = "open"
    CLOSED = "closed"


class FailureSeverity(str, Enum):
    """Human-facing severity independent of recovery disposition."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FailureSafety:
    """Sanitize and bound arbitrary failure details without throwing."""

    _SECRET_PARTS: ClassVar[tuple[str, ...]] = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
    _MAX_TEXT: ClassVar[int] = 500
    _MAX_ITEMS: ClassVar[int] = 32

    @classmethod
    def sanitize_mapping(cls, values: Mapping[str, Any] | None) -> dict[str, Any]:
        # @intent credential-safe-learning-records
        # Failure details are model-facing training signal, so bounds and key
        # redaction happen before a record can enter Session history.
        """Return a bounded, credential-safe mapping for failure details."""
        if not isinstance(values, Mapping):
            return {}
        safe: dict[str, Any] = {}
        for key, value in list(values.items())[: cls._MAX_ITEMS]:
            key_text = str(key)
            if any(part in key_text.upper() for part in cls._SECRET_PARTS):
                continue
            safe[key_text] = cls.sanitize_value(value)
        return safe

    @classmethod
    def sanitize_value(cls, value: Any) -> Any:
        """Convert one arbitrary value into a bounded JSON-friendly value."""
        if isinstance(value, Mapping):
            return cls.sanitize_mapping(value)
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(cls.sanitize_value(item) for item in list(value)[: cls._MAX_ITEMS])
        if isinstance(value, str):
            return value[: cls._MAX_TEXT]
        if isinstance(value, (bool, int, str)) or value is None:
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else str(value)
        return str(value)[: cls._MAX_TEXT]


@dataclass(frozen=True, slots=True)
class Failure:
    """Immutable canonical record for one deterministic failure observation."""

    code: FailureCode | str
    source: str
    phase: FailurePhase | str = FailurePhase.RUNTIME
    status: FailureStatus | str = FailureStatus.OBSERVED
    disposition: FailureDisposition | str = FailureDisposition.RECORD
    severity: FailureSeverity | str = FailureSeverity.ERROR
    summary: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    handled_by: str | None = None
    parent_id: str | None = None
    iteration: int | None = None
    step: str | None = None
    id: str = field(default_factory=lambda: f"fl_{uuid4().hex}")
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        """Validate stable fields and sanitize caller-provided detail values."""
        try:
            code = FailureCode.from_value(self.code)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unknown failure code: {self.code!r}") from exc
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "phase", FailurePhase(self.phase))
        object.__setattr__(self, "status", FailureStatus(self.status))
        object.__setattr__(self, "disposition", FailureDisposition(self.disposition))
        object.__setattr__(self, "severity", FailureSeverity(self.severity))
        if not str(self.source).strip():
            raise ValueError("Failure.source cannot be empty.")
        object.__setattr__(self, "source", str(self.source).strip())
        if self.iteration is not None and (isinstance(self.iteration, bool) or not isinstance(self.iteration, int) or self.iteration < 0):
            raise ValueError("Failure.iteration must be a non-negative integer when provided.")
        object.__setattr__(self, "summary", FailureSafety.sanitize_value(self.summary) if self.summary is not None else None)
        object.__setattr__(self, "details", FailureSafety.sanitize_mapping(self.details))

    @classmethod
    def from_exception(cls, exc: BaseException, *, phase: FailurePhase | str = FailurePhase.RUNTIME, source: str = "runtime", disposition: FailureDisposition | str = FailureDisposition.ROUTE, details: Mapping[str, Any] | None = None) -> Failure:
        """Build a canonical failure from an exception without exposing secrets."""
        code = FailureCode.from_exception(exc)
        exception_details = getattr(exc, "details", {})
        merged = {**FailureSafety.sanitize_mapping(exception_details), **FailureSafety.sanitize_mapping(details)}
        merged.setdefault("error_type", type(exc).__name__)
        return cls(code=code, source=source, phase=phase, disposition=disposition, summary=type(exc).__name__, details=merged)

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-friendly representation for traces and training data."""
        code = FailureCode.from_value(self.code)
        phase = FailurePhase(self.phase)
        status = FailureStatus(self.status)
        disposition = FailureDisposition(self.disposition)
        severity = FailureSeverity(self.severity)
        return {
            "id": self.id,
            "code": code.value,
            "category": code.category,
            "source": self.source,
            "phase": phase.value,
            "status": status.value,
            "disposition": disposition.value,
            "severity": severity.value,
            "summary": self.summary,
            "details": FailureSafety.sanitize_mapping(self.details),
            "handled_by": self.handled_by,
            "parent_id": self.parent_id,
            "iteration": self.iteration,
            "step": self.step,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True, slots=True)
class RecoveryAttempt:
    """Immutable result record for one Session-level recovery invocation."""

    failure_id: str
    handler: str
    succeeded: bool
    disposition: FailureDisposition | str = FailureDisposition.CONTINUE
    details: Mapping[str, Any] = field(default_factory=dict)
    error_type: str | None = None

    def __post_init__(self) -> None:
        """Normalize disposition and make recovery details safe to export."""
        object.__setattr__(self, "disposition", FailureDisposition(self.disposition))
        object.__setattr__(self, "details", FailureSafety.sanitize_mapping(self.details))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly recovery-attempt mapping."""
        disposition = FailureDisposition(self.disposition)
        return {"failure_id": self.failure_id, "handler": self.handler, "succeeded": self.succeeded, "disposition": disposition.value, "details": dict(self.details), "error_type": self.error_type}


__all__ = [
    "Failure",
    "FailureCode",
    "FailureDisposition",
    "FailurePhase",
    "FailureSafety",
    "FailureSeverity",
    "FailureStatus",
    "RecoveryAttempt",
    "RuleErrorMode",
]

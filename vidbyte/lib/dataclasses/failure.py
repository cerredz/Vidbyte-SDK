"""FILE: vidbyte/lib/dataclasses/failure.py

PURPOSE: Defines the immutable, safe failure records shared across Session failure routing.
ROLE IN CODEBASE: Supplies Failure, RecoveryAttempt, RecoveryResult, RecoveryBinding, and sanitization.
ARCHITECTURE NOTE: Every mapping field is sanitized and bounded here so no layer above must re-check safety.
COMMON MODIFICATION PATTERNS: Add a field with a validated default here rather than in a calling module.
KNOWN EDGE CASES: Keep detail values bounded and credential-free; secrets are stripped, not raised on.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/vocabulary.md.
TESTS: python scripts/test-session-failure-vocabulary.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol, runtime_checkable
from uuid import uuid4

from vidbyte.lib.enums.failure import (
    FailureCode,
    FailureDisposition,
    FailurePhase,
    FailureSeverity,
    FailureStatus,
    RuleErrorMode,
)


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


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Bounded outcome returned by one recovery handler invocation."""

    succeeded: bool
    disposition: FailureDisposition | str = FailureDisposition.CONTINUE
    value: Any = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize disposition and sanitize handler details."""
        object.__setattr__(self, "disposition", FailureDisposition(self.disposition))
        object.__setattr__(self, "details", FailureSafety.sanitize_mapping(self.details))

    def as_dict(self) -> dict[str, Any]:
        """Return a safe mapping for router history and model-facing metadata."""
        disposition = FailureDisposition(self.disposition)
        return {"succeeded": self.succeeded, "disposition": disposition.value, "value": FailureSafety.sanitize_value(self.value), "details": dict(self.details)}


@runtime_checkable
class RecoveryHandler(Protocol):
    """Structural contract for synchronous or asynchronous recovery handlers."""

    name: str
    on_error: RuleErrorMode

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:  # pragma: no cover - protocol declaration
        """Recover one exhausted failure for a Session."""
        ...


@dataclass(frozen=True, slots=True)
class RecoveryBinding:
    """Code-to-handler binding with recovered-event routing policy."""

    handler: RecoveryHandler
    include_recovered: bool


__all__ = [
    "Failure",
    "FailureSafety",
    "RecoveryAttempt",
    "RecoveryBinding",
    "RecoveryHandler",
    "RecoveryResult",
]

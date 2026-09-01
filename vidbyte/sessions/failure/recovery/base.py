"""FILE: vidbyte/sessions/failure/recovery/base.py

PURPOSE: Defines shared recovery handler, result, and typed terminal-error contracts.
ROLE IN CODEBASE: Provides the narrow protocol used by FailureRouter for every recovery mode.
ARCHITECTURE NOTE: This module stays dependency-light and sanitizes handler metadata at the boundary.
COMMON MODIFICATION PATTERNS: Extend the protocol only when all built-in handlers and router paths agree.
KNOWN EDGE CASES: Handler errors must remain typed and must not recurse into the same recovery binding.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from vidbyte.sessions.failure.types import (
    Failure,
    FailureCode,
    FailureDisposition,
    FailureSafety,
    RuleErrorMode,
)


class FailureRaisedError(RuntimeError):
    """Raised when a recovery policy requests raising without an original exception."""

    def __init__(self, failure: Failure) -> None:
        """Build a typed runtime error carrying the canonical failure record."""
        super().__init__(failure.summary or FailureCode.from_value(failure.code).value)
        self.failure = failure


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


class BaseRecoveryHandler:
    """Small base class that validates common recovery policy fields."""

    def __init__(self, *, name: str, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED, metadata: Mapping[str, Any] | None = None) -> None:
        """Store a stable handler name, error posture, and safe metadata."""
        if not str(name).strip():
            raise ValueError("Recovery handler name cannot be empty.")
        self.name = str(name).strip()
        self.on_error = RuleErrorMode(on_error)
        self.metadata = FailureSafety.sanitize_mapping(metadata)

    def result(self, succeeded: bool, disposition: FailureDisposition | str, *, value: Any = None, details: Mapping[str, Any] | None = None) -> RecoveryResult:
        """Build a result merged with handler metadata."""
        return RecoveryResult(succeeded=succeeded, disposition=disposition, value=value, details={**self.metadata, **FailureSafety.sanitize_mapping(details)})


__all__ = ["BaseRecoveryHandler", "FailureRaisedError", "RecoveryHandler", "RecoveryResult"]

"""FILE: vidbyte/lib/dataclasses/failure_recovery.py

PURPOSE: Owns strictly validated constructor inputs for every built-in Session recovery handler.
ROLE IN CODEBASE: vidbyte/sessions/failure/recovery/*.py constructors are thin adapters over these.
ARCHITECTURE NOTE: Each dataclass owns every validation rule in its own __post_init__; a handler's
    __init__ only coerces loose, ergonomic keyword arguments into one instance and stores it.
COMMON MODIFICATION PATTERNS: Add a field with its bound/default here, not as a bare literal in a
    handler module; reuse vidbyte/lib/constants/failure.py for any operational default.
WHAT NOT TO DO: Do not accept an `Enum | str` union field here; coerce to the enum in the handler's
    own __init__ before constructing the dataclass.
KNOWN EDGE CASES: `policy`/`trace` on ForkRecoverySettings stay `object | None` because Session policy
    and trace option types are intentionally kept callback-owned and out of this substrate layer.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.constants.failure import (
    DEFAULT_FORK_LABEL,
    DEFAULT_HUMAN_REVIEW_QUEUE,
    DEFAULT_TEACHER_HANDOFF_MAX_ATTEMPTS,
)
from vidbyte.lib.dataclasses.failure import FailureSafety
from vidbyte.lib.enums.failure import RuleErrorMode

_ZERO = 0


@dataclass(frozen=True, slots=True)
class RecoveryHandlerSettings:
    """Validated name, error posture, and safe metadata shared by every recovery handler."""

    name: str
    on_error: RuleErrorMode
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the handler name and sanitize caller-provided metadata."""
        if not str(self.name).strip():
            raise ValueError("Recovery handler name cannot be empty.")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "on_error", RuleErrorMode(self.on_error))
        object.__setattr__(self, "metadata", FailureSafety.sanitize_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class StopRecoverySettings:
    """Validated optional human-facing reason for StopRecovery."""

    reason: str | None = None

    def __post_init__(self) -> None:
        """Sanitize the reason and normalize a blank string to None."""
        sanitized = FailureSafety.sanitize_value(self.reason) if self.reason else None
        object.__setattr__(self, "reason", sanitized or None)


@dataclass(frozen=True, slots=True)
class ForkRecoverySettings:
    """Validated branch inputs for ForkRecovery."""

    at: str | None = None
    tools: tuple[object, ...] = ()
    middleware: tuple[object, ...] = ()
    policy: object | None = None
    trace: object | None = None
    tags: tuple[str, ...] = ()
    label: str = DEFAULT_FORK_LABEL

    def __post_init__(self) -> None:
        """Coerce sequence inputs to tuples and fall back to the default label."""
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "middleware", tuple(self.middleware))
        object.__setattr__(self, "tags", tuple(str(tag) for tag in self.tags))
        object.__setattr__(self, "label", str(self.label).strip() or DEFAULT_FORK_LABEL)


@dataclass(frozen=True, slots=True)
class CallbackRecoverySettings:
    """Validated callback for every callback-driven recovery handler."""

    callback: Callable[..., Any]

    def __post_init__(self) -> None:
        """Reject a non-callable before any recovery attempt can reach it."""
        if not callable(self.callback):
            raise TypeError("Recovery callback must be callable.")


@dataclass(frozen=True, slots=True)
class TeacherHandoffRecoverySettings:
    """Validated bounded-attempt inputs for TeacherHandoffRecovery."""

    max_attempts: int = DEFAULT_TEACHER_HANDOFF_MAX_ATTEMPTS
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """Enforce positive attempt counts and a positive timeout when provided."""
        if type(self.max_attempts) is not int or self.max_attempts <= _ZERO:
            raise ValueError("TeacherHandoffRecovery.max_attempts must be greater than zero.")
        if self.timeout_seconds is not None and self.timeout_seconds <= _ZERO:
            raise ValueError("TeacherHandoffRecovery.timeout_seconds must be greater than zero when provided.")


@dataclass(frozen=True, slots=True)
class AggregateRecoverySettings:
    """Validated model sequence for AggregateRecovery."""

    models: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        """Coerce the model sequence to a tuple for a stable, immutable record."""
        object.__setattr__(self, "models", tuple(self.models))


@dataclass(frozen=True, slots=True)
class HumanReviewRecoverySettings:
    """Validated review-queue name for HumanReviewRecovery."""

    queue: str = DEFAULT_HUMAN_REVIEW_QUEUE

    def __post_init__(self) -> None:
        """Fall back to the default queue name when given a blank string."""
        object.__setattr__(self, "queue", str(self.queue).strip() or DEFAULT_HUMAN_REVIEW_QUEUE)


@dataclass(frozen=True, slots=True)
class FailureRouterSettings:
    """Validated construction inputs for one Session's FailureRouter."""

    max_history: int
    enabled: bool = True
    on_capture: Callable[[Any], object] | None = None

    def __post_init__(self) -> None:
        """Enforce a positive bounded history so the ledger can never grow unbounded."""
        if isinstance(self.max_history, bool) or self.max_history <= _ZERO:
            raise ValueError("FailureRouter.max_history must be greater than zero.")
        if self.on_capture is not None and not callable(self.on_capture):
            raise TypeError("FailureRouter.on_capture must be callable.")


__all__ = [
    "AggregateRecoverySettings",
    "CallbackRecoverySettings",
    "FailureRouterSettings",
    "ForkRecoverySettings",
    "HumanReviewRecoverySettings",
    "RecoveryHandlerSettings",
    "StopRecoverySettings",
    "TeacherHandoffRecoverySettings",
]

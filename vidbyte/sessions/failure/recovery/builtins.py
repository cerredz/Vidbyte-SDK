"""FILE: vidbyte/sessions/failure/recovery/builtins.py

PURPOSE: Implements the initial parameterized Session recovery modes.
ROLE IN CODEBASE: Adapts continue, stop, raise, fork, and callback strategies to RecoveryResult.
ARCHITECTURE NOTE: Existing Session, compaction, teacher, aggregation, and review seams remain callback-owned.
COMMON MODIFICATION PATTERNS: Add explicit constructor parameters, validate bounds, and expose the result metadata.
KNOWN EDGE CASES: Fork requires a checkpoint; callbacks may be sync or async; handler errors have explicit posture.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from vidbyte.sessions.failure.recovery.base import (
    BaseRecoveryHandler,
    FailureRaisedError,
    RecoveryResult,
)
from vidbyte.sessions.failure.types import (
    Failure,
    FailureCode,
    FailureDisposition,
    FailureSafety,
    RuleErrorMode,
)

_ZERO = 0


class ContinueRecovery(BaseRecoveryHandler):
    """Record an exhausted failure and allow the owning run to continue."""

    def __init__(self, *, metadata: Mapping[str, Any] | None = None) -> None:
        """Create a no-op recovery with a continue disposition."""
        super().__init__(name="continue", on_error=RuleErrorMode.OPEN, metadata=metadata)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        """Return a successful continue result without mutating Session state."""
        del failure, session
        return self.result(True, FailureDisposition.CONTINUE)


class StopRecovery(BaseRecoveryHandler):
    """Stop a run cleanly after recording a terminal failure."""

    def __init__(self, *, reason: str | None = None, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED) -> None:
        """Create a stop handler with an optional human-facing reason."""
        super().__init__(name="stop", on_error=on_error, metadata=metadata)
        self.reason = FailureSafety.sanitize_value(reason) if reason else None

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        """Return a stop result with the canonical failure code."""
        del session
        details = {"failure_code": FailureCode.from_value(failure.code).value}
        if self.reason:
            details["reason"] = self.reason
        return self.result(True, FailureDisposition.STOP, details=details)


class RaiseRecovery(BaseRecoveryHandler):
    """Raise a typed error when a failure cannot be safely continued."""

    def __init__(self, *, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED, metadata: Mapping[str, Any] | None = None) -> None:
        """Create a handler that raises ``FailureRaisedError`` for every failure."""
        super().__init__(name="raise", on_error=on_error, metadata=metadata)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        """Raise the canonical failure as a typed exception."""
        del session
        raise FailureRaisedError(failure)


class ForkRecovery(BaseRecoveryHandler):
    """Fork a Session from the failure checkpoint or current head."""

    def __init__(self, *, at: str | None = None, tools: Sequence[object] = (), middleware: Sequence[object] = (), policy: object | None = None, trace: object | None = None, tags: Sequence[str] = (), label: str = "failure-fork", metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED) -> None:
        """Create a fork handler with explicit branch inputs and error posture."""
        super().__init__(name="fork", on_error=on_error, metadata=metadata)
        self.at = at
        self.tools = tuple(tools)
        self.middleware = tuple(middleware)
        self.policy = policy
        self.trace = trace
        self.tags = tuple(str(tag) for tag in tags)
        self.label = str(label).strip() or "failure-fork"

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        # @intent fork-recovery-preserves-session-lineage
        # A failure branch must retain the existing checkpoint lineage while
        # exposing explicit policy, trace, and tag overrides to the developer.
        """Create and return a child Session using the existing fork API."""
        del failure
        fork = getattr(session, "fork", None)
        if not callable(fork):
            raise TypeError("ForkRecovery requires a Session with fork().")
        if self.policy is None and self.trace is None and not self.tags:
            child = fork(at=self.at, tools=self.tools, middleware=self.middleware)
        else:
            fork_from = getattr(type(session), "fork_from", None)
            store = getattr(session, "_store", None)
            checkpoint = self.at or getattr(session, "head", None)
            if not callable(fork_from) or store is None or checkpoint is None:
                raise TypeError("ForkRecovery custom policy/trace/tags requires a Session fork_from() boundary and a checkpoint.")
            session_any = cast(Any, session)
            child = fork_from(
                store,
                checkpoint,
                tools=self.tools,
                middleware=self.middleware,
                policy=self.policy if self.policy is not None else session_any._policy,
                trace=self.trace if self.trace is not None else session_any._recorder_policy(),
                tags=self.tags or getattr(session, "_tags", ()),
            )
        return self.result(True, FailureDisposition.CONTINUE, value=child, details={"label": self.label, "checkpoint": self.at, "policy": self.policy, "trace": self.trace, "tags": self.tags})


class CallbackRecovery(BaseRecoveryHandler):
    """Base class for callback-driven recovery modes."""

    def __init__(self, *, name: str, callback: Callable[..., Any], metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED) -> None:
        """Validate and store one callback used by a concrete recovery mode."""
        super().__init__(name=name, on_error=on_error, metadata=metadata)
        if not callable(callback):
            raise TypeError(f"{name} recovery callback must be callable.")
        self.callback = callback

    def invoke(self, failure: Failure, session: object) -> Any:
        """Invoke the callback with the failure and bound Session."""
        value = self.callback(failure, session)
        return value


class CompactRecovery(CallbackRecovery):
    """Invoke a developer-provided context compaction strategy."""

    def __init__(self, callback: Callable[..., Any], *, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.OPEN) -> None:
        """Create a compaction callback recovery with an explicit error posture."""
        super().__init__(name="compact", callback=callback, metadata=metadata, on_error=on_error)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult | Awaitable[RecoveryResult]:
        """Run the compaction callback and preserve sync or async results."""
        value = self.invoke(failure, session)
        if inspect.isawaitable(value):
            return self._await_result(value)
        return self.result(True, FailureDisposition.CONTINUE, value=value)

    async def _await_result(self, value: Awaitable[Any]) -> RecoveryResult:
        # Await callback work without forcing synchronous callers into an event loop.
        return self.result(True, FailureDisposition.CONTINUE, value=await value)


class TeacherHandoffRecovery(CallbackRecovery):
    """Hand a failed trajectory segment to a teacher-model callback."""

    def __init__(self, callback: Callable[..., Any], *, max_attempts: int = 1, timeout_seconds: float | None = None, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED) -> None:
        """Create a bounded teacher handoff with optional timeout metadata."""
        super().__init__(name="teacher_handoff", callback=callback, metadata=metadata, on_error=on_error)
        if type(max_attempts) is not int or max_attempts <= _ZERO:
            raise ValueError("TeacherHandoffRecovery.max_attempts must be greater than zero.")
        if timeout_seconds is not None and timeout_seconds <= _ZERO:
            raise ValueError("TeacherHandoffRecovery.timeout_seconds must be greater than zero when provided.")
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult | Awaitable[RecoveryResult]:
        """Run the teacher callback with explicit attempt and timeout metadata."""
        value = self.invoke(failure, session)
        details = {"max_attempts": self.max_attempts, "timeout_seconds": self.timeout_seconds}
        if inspect.isawaitable(value):
            return self._await_result(value, details)
        return self.result(True, FailureDisposition.CONTINUE, value=value, details=details)

    async def _await_result(self, value: Awaitable[Any], details: Mapping[str, Any]) -> RecoveryResult:
        # Await the teacher callback while keeping its safety parameters observable.
        return self.result(True, FailureDisposition.CONTINUE, value=await value, details=details)


class AggregateRecovery(CallbackRecovery):
    """Run a developer-provided model aggregation callback at a failure point."""

    def __init__(self, callback: Callable[..., Any], *, models: Sequence[object] = (), metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.CLOSED) -> None:
        """Create an aggregation handler with an explicit model sequence."""
        super().__init__(name="aggregate", callback=callback, metadata=metadata, on_error=on_error)
        self.models = tuple(models)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult | Awaitable[RecoveryResult]:
        """Run aggregation and preserve its result for downstream training."""
        value = self.invoke(failure, session)
        details = {"model_count": len(self.models), "models": self.models}
        if inspect.isawaitable(value):
            return self._await_result(value, details)
        return self.result(True, FailureDisposition.CONTINUE, value=value, details=details)

    async def _await_result(self, value: Awaitable[Any], details: Mapping[str, Any]) -> RecoveryResult:
        # Await aggregation work while retaining the selected model metadata.
        return self.result(True, FailureDisposition.CONTINUE, value=await value, details=details)


class HumanReviewRecovery(CallbackRecovery):
    """Submit a failure and its trajectory context to human review."""

    def __init__(self, callback: Callable[..., Any], *, queue: str = "default", metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode | str = RuleErrorMode.OPEN) -> None:
        """Create a human-review handler targeting a named review queue."""
        super().__init__(name="human_review", callback=callback, metadata=metadata, on_error=on_error)
        self.queue = str(queue).strip() or "default"

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult | Awaitable[RecoveryResult]:
        """Submit review work and continue with a pending-review result."""
        value = self.invoke(failure, session)
        details = {"queue": self.queue}
        if inspect.isawaitable(value):
            return self._await_result(value, details)
        return self.result(True, FailureDisposition.CONTINUE, value=value, details=details)

    async def _await_result(self, value: Awaitable[Any], details: Mapping[str, Any]) -> RecoveryResult:
        # Await review submission while keeping the queue name in the outcome.
        return self.result(True, FailureDisposition.CONTINUE, value=await value, details=details)


__all__ = [
    "AggregateRecovery",
    "CallbackRecovery",
    "CompactRecovery",
    "ContinueRecovery",
    "ForkRecovery",
    "HumanReviewRecovery",
    "RaiseRecovery",
    "StopRecovery",
    "TeacherHandoffRecovery",
]

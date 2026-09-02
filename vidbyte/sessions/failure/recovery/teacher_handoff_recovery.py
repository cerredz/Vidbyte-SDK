"""FILE: vidbyte/sessions/failure/recovery/teacher_handoff_recovery.py

PURPOSE: Implements the teacher-handoff recovery mode.
ROLE IN CODEBASE: Hands a failed trajectory segment to a bounded teacher-model callback.
ARCHITECTURE NOTE: Fails closed by default; an unbounded teacher handoff could loop indefinitely.
COMMON MODIFICATION PATTERNS: Add a new bound to TeacherHandoffRecoverySettings, not a bare field here.
KNOWN EDGE CASES: max_attempts and timeout_seconds are validated by TeacherHandoffRecoverySettings.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from vidbyte.lib.constants.failure import DEFAULT_TEACHER_HANDOFF_MAX_ATTEMPTS
from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import TeacherHandoffRecoverySettings
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.callback_recovery import CallbackRecovery

__all__ = ["TeacherHandoffRecovery"]


class TeacherHandoffRecovery(CallbackRecovery):
    """Hand a failed trajectory segment to a teacher-model callback."""

    def __init__(self, callback: Callable[..., Any], *, max_attempts: int = DEFAULT_TEACHER_HANDOFF_MAX_ATTEMPTS, timeout_seconds: float | None = None, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.CLOSED) -> None:
        """Create a bounded teacher handoff with optional timeout metadata."""
        super().__init__(name="teacher_handoff", callback=callback, metadata=metadata, on_error=on_error)
        self._handoff_settings = TeacherHandoffRecoverySettings(max_attempts=max_attempts, timeout_seconds=timeout_seconds)

    @property
    def max_attempts(self) -> int:
        """Return the validated maximum handoff attempts."""
        return self._handoff_settings.max_attempts

    @property
    def timeout_seconds(self) -> float | None:
        """Return the validated handoff timeout, if any."""
        return self._handoff_settings.timeout_seconds

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

"""FILE: vidbyte/sessions/failure/recovery/human_review_recovery.py

PURPOSE: Implements the human-review recovery mode.
ROLE IN CODEBASE: Submits a failure and its trajectory context to a named human review queue.
ARCHITECTURE NOTE: Fails open by default; a broken review submission should not stop the run.
COMMON MODIFICATION PATTERNS: Keep queue routing callback-owned; this handler only names the queue.
KNOWN EDGE CASES: A blank queue name falls back to the default queue via HumanReviewRecoverySettings.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from vidbyte.lib.constants.failure import DEFAULT_HUMAN_REVIEW_QUEUE
from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import HumanReviewRecoverySettings
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.callback_recovery import CallbackRecovery

__all__ = ["HumanReviewRecovery"]


class HumanReviewRecovery(CallbackRecovery):
    """Submit a failure and its trajectory context to human review."""

    def __init__(self, callback: Callable[..., Any], *, queue: str = DEFAULT_HUMAN_REVIEW_QUEUE, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.OPEN) -> None:
        """Create a human-review handler targeting a named review queue."""
        super().__init__(name="human_review", callback=callback, metadata=metadata, on_error=on_error)
        self._review_settings = HumanReviewRecoverySettings(queue=queue)

    @property
    def queue(self) -> str:
        """Return this handler's validated review-queue name."""
        return self._review_settings.queue

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

"""FILE: vidbyte/sessions/failure/recovery/stop_recovery.py

PURPOSE: Implements the clean-stop recovery mode.
ROLE IN CODEBASE: Stops a run after recording a terminal failure with an optional human-facing reason.
ARCHITECTURE NOTE: Fails closed by default; a broken stop handler should not silently continue a run.
COMMON MODIFICATION PATTERNS: Add a new result detail alongside failure_code/reason, not a new field type.
KNOWN EDGE CASES: A blank or falsy reason is normalized to None by StopRecoverySettings.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import StopRecoverySettings
from vidbyte.lib.enums.failure import FailureCode, FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.base import BaseRecoveryHandler

__all__ = ["StopRecovery"]


class StopRecovery(BaseRecoveryHandler):
    """Stop a run cleanly after recording a terminal failure."""

    def __init__(self, *, reason: str | None = None, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.CLOSED) -> None:
        """Create a stop handler with an optional human-facing reason."""
        super().__init__(name="stop", on_error=on_error, metadata=metadata)
        self._stop_settings = StopRecoverySettings(reason=reason)

    @property
    def reason(self) -> str | None:
        """Return this handler's sanitized human-facing reason, if any."""
        return self._stop_settings.reason

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        """Return a stop result with the canonical failure code."""
        del session
        details = {"failure_code": FailureCode.from_value(failure.code).value}
        if self.reason:
            details["reason"] = self.reason
        return self.result(True, FailureDisposition.STOP, details=details)

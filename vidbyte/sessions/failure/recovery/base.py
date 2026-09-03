"""FILE: vidbyte/sessions/failure/recovery/base.py

PURPOSE: Defines the shared recovery handler base class used by every built-in recovery mode.
ROLE IN CODEBASE: Thin adapter over vidbyte.lib.dataclasses.failure_recovery.RecoveryHandlerSettings.
ARCHITECTURE NOTE: RecoveryResult, RecoveryHandler, and FailureRaisedError live in vidbyte/lib so the
    typed vocabulary they carry is reusable outside the Session recovery package.
COMMON MODIFICATION PATTERNS: Extend the protocol only when all built-in handlers and router paths agree.
KNOWN EDGE CASES: Handler errors must remain typed and must not recurse into the same recovery binding.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.failure import FailureSafety, RecoveryHandler, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import RecoveryHandlerSettings
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.lib.errors import FailureRaisedError

__all__ = ["BaseRecoveryHandler", "FailureRaisedError", "RecoveryHandler", "RecoveryResult"]


class BaseRecoveryHandler:
    """Small base class that validates common recovery policy fields."""

    def __init__(self, *, name: str, on_error: RuleErrorMode = RuleErrorMode.CLOSED, metadata: Mapping[str, Any] | None = None) -> None:
        """Coerce loose constructor arguments into one validated RecoveryHandlerSettings."""
        self._settings = RecoveryHandlerSettings(name=name, on_error=on_error, metadata=metadata or {})

    @property
    def name(self) -> str:
        """Return this handler's stable, non-empty name."""
        return self._settings.name

    @property
    def on_error(self) -> RuleErrorMode:
        """Return this handler's error posture."""
        return self._settings.on_error

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Return this handler's sanitized, bounded metadata."""
        return self._settings.metadata

    def result(self, succeeded: bool, disposition: FailureDisposition, *, value: Any = None, details: Mapping[str, Any] | None = None) -> RecoveryResult:
        """Build a result merged with handler metadata."""
        return RecoveryResult(succeeded=succeeded, disposition=disposition, value=value, details={**self.metadata, **FailureSafety.sanitize_mapping(details)})

"""FILE: vidbyte/sessions/failure/recovery/callback_recovery.py

PURPOSE: Defines the shared base for every callback-driven recovery mode.
ROLE IN CODEBASE: Validates and stores one developer callback used by compact, teacher-handoff,
    aggregate, and human-review recovery handlers.
ARCHITECTURE NOTE: A callback may be synchronous or asynchronous; concrete subclasses decide how to
    await it and what RecoveryResult details to attach.
COMMON MODIFICATION PATTERNS: Add a new callback-driven mode as its own file subclassing this one.
KNOWN EDGE CASES: A non-callable callback raises TypeError at construction time, not at recovery time.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from vidbyte.lib.dataclasses.failure import Failure
from vidbyte.lib.dataclasses.failure_recovery import CallbackRecoverySettings
from vidbyte.lib.enums.failure import RuleErrorMode
from vidbyte.sessions.failure.recovery.base import BaseRecoveryHandler

__all__ = ["CallbackRecovery"]


class CallbackRecovery(BaseRecoveryHandler):
    """Base class for callback-driven recovery modes."""

    def __init__(self, *, name: str, callback: Callable[..., Any], metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.CLOSED) -> None:
        """Validate and store one callback used by a concrete recovery mode."""
        super().__init__(name=name, on_error=on_error, metadata=metadata)
        self._callback_settings = CallbackRecoverySettings(callback=callback)

    @property
    def callback(self) -> Callable[..., Any]:
        """Return this handler's validated callback."""
        return self._callback_settings.callback

    def invoke(self, failure: Failure, session: object) -> Any:
        """Invoke the callback with the failure and bound Session."""
        return self.callback(failure, session)

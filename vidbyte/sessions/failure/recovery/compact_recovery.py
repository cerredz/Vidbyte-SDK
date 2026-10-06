"""FILE: vidbyte/sessions/failure/recovery/compact_recovery.py

PURPOSE: Implements the compaction recovery mode.
ROLE IN CODEBASE: Invokes a developer-provided context compaction strategy at a failure point.
ARCHITECTURE NOTE: Fails open by default; a broken compaction callback should not stop the run.
COMMON MODIFICATION PATTERNS: Keep compaction strategy selection callback-owned, not hardcoded here.
KNOWN EDGE CASES: The callback may return a value directly or an awaitable; both are preserved.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.callback_recovery import CallbackRecovery

__all__ = ["CompactRecovery"]


class CompactRecovery(CallbackRecovery):
    """Invoke a developer-provided context compaction strategy."""

    def __init__(self, callback: Callable[..., Any], *, metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.OPEN) -> None:
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

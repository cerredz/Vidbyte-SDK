"""FILE: vidbyte/sessions/failure/recovery/continue_recovery.py

PURPOSE: Implements the no-op continue recovery mode.
ROLE IN CODEBASE: Records an exhausted failure and lets the owning run keep going.
ARCHITECTURE NOTE: Always fail-open; a broken continue handler must never block a run.
COMMON MODIFICATION PATTERNS: Keep this handler stateless; add parameters only if a real caller needs them.
KNOWN EDGE CASES: None; this handler never inspects the failure or session it receives.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.base import BaseRecoveryHandler

__all__ = ["ContinueRecovery"]


class ContinueRecovery(BaseRecoveryHandler):
    """Record an exhausted failure and allow the owning run to continue."""

    def __init__(self, *, metadata: Mapping[str, Any] | None = None) -> None:
        """Create a no-op recovery with a continue disposition."""
        super().__init__(name="continue", on_error=RuleErrorMode.OPEN, metadata=metadata)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        """Return a successful continue result without mutating Session state."""
        del failure, session
        return self.result(True, FailureDisposition.CONTINUE)

"""FILE: vidbyte/sessions/failure/recovery/raise_recovery.py

PURPOSE: Implements the raise recovery mode.
ROLE IN CODEBASE: Raises a typed FailureRaisedError when a failure cannot be safely continued.
ARCHITECTURE NOTE: Fails closed by default; this handler never returns a successful RecoveryResult.
COMMON MODIFICATION PATTERNS: Keep this handler stateless; raising is its entire contract.
KNOWN EDGE CASES: None; the raised error always carries the canonical failure record.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.enums.failure import RuleErrorMode
from vidbyte.lib.errors import FailureRaisedError
from vidbyte.sessions.failure.recovery.base import BaseRecoveryHandler

__all__ = ["RaiseRecovery"]


class RaiseRecovery(BaseRecoveryHandler):
    """Raise a typed error when a failure cannot be safely continued."""

    def __init__(self, *, on_error: RuleErrorMode = RuleErrorMode.CLOSED, metadata: Mapping[str, Any] | None = None) -> None:
        """Create a handler that raises ``FailureRaisedError`` for every failure."""
        super().__init__(name="raise", on_error=on_error, metadata=metadata)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        """Raise the canonical failure as a typed exception."""
        del session
        raise FailureRaisedError(failure)

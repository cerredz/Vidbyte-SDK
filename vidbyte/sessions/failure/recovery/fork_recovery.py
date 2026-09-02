"""FILE: vidbyte/sessions/failure/recovery/fork_recovery.py

PURPOSE: Implements the fork recovery mode.
ROLE IN CODEBASE: Forks a Session from the failure checkpoint or current head to branch a repair attempt.
ARCHITECTURE NOTE: Fails closed by default; a broken fork must not silently continue the parent run.
COMMON MODIFICATION PATTERNS: Add a new branch input to ForkRecoverySettings, not as a bare constructor field.
KNOWN EDGE CASES: A custom policy/trace/tags requires the Session fork_from() boundary and a checkpoint.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import ForkRecoverySettings
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.base import BaseRecoveryHandler

__all__ = ["ForkRecovery"]


class ForkRecovery(BaseRecoveryHandler):
    """Fork a Session from the failure checkpoint or current head."""

    def __init__(self, *, at: str | None = None, tools: Sequence[object] = (), middleware: Sequence[object] = (), policy: object | None = None, trace: object | None = None, tags: Sequence[str] = (), label: str = "failure-fork", metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.CLOSED) -> None:
        """Create a fork handler with explicit branch inputs and error posture."""
        super().__init__(name="fork", on_error=on_error, metadata=metadata)
        self._fork_settings = ForkRecoverySettings(at=at, tools=tuple(tools), middleware=tuple(middleware), policy=policy, trace=trace, tags=tuple(tags), label=label)

    def recover(self, failure: Failure, *, session: object) -> RecoveryResult:
        # @intent fork-recovery-preserves-session-lineage
        # A failure branch must retain the existing checkpoint lineage while
        # exposing explicit policy, trace, and tag overrides to the developer.
        """Create and return a child Session using the existing fork API."""
        del failure
        settings = self._fork_settings
        fork = getattr(session, "fork", None)
        if not callable(fork):
            raise TypeError("ForkRecovery requires a Session with fork().")
        if settings.policy is None and settings.trace is None and not settings.tags:
            child = fork(at=settings.at, tools=settings.tools, middleware=settings.middleware)
        else:
            fork_from = getattr(type(session), "fork_from", None)
            store = getattr(session, "_store", None)
            checkpoint = settings.at or getattr(session, "head", None)
            if not callable(fork_from) or store is None or checkpoint is None:
                raise TypeError("ForkRecovery custom policy/trace/tags requires a Session fork_from() boundary and a checkpoint.")
            session_any = cast(Any, session)
            child = fork_from(
                store,
                checkpoint,
                tools=settings.tools,
                middleware=settings.middleware,
                policy=settings.policy if settings.policy is not None else session_any._policy,
                trace=settings.trace if settings.trace is not None else session_any._recorder_policy(),
                tags=settings.tags or getattr(session, "_tags", ()),
            )
        return self.result(True, FailureDisposition.CONTINUE, value=child, details={"label": settings.label, "checkpoint": settings.at, "policy": settings.policy, "trace": settings.trace, "tags": settings.tags})

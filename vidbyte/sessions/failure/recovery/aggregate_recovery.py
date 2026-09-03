"""FILE: vidbyte/sessions/failure/recovery/aggregate_recovery.py

PURPOSE: Implements the aggregate recovery mode.
ROLE IN CODEBASE: Runs a developer-provided model aggregation callback at a failure point.
ARCHITECTURE NOTE: Fails closed by default; aggregation results feed downstream training signal.
COMMON MODIFICATION PATTERNS: Keep model selection callback-owned; this handler only records which
    models were configured, not how they were called.
KNOWN EDGE CASES: The callback may return a value directly or an awaitable; both are preserved.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.failure import Failure, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import AggregateRecoverySettings
from vidbyte.lib.enums.failure import FailureDisposition, RuleErrorMode
from vidbyte.sessions.failure.recovery.callback_recovery import CallbackRecovery

__all__ = ["AggregateRecovery"]


class AggregateRecovery(CallbackRecovery):
    """Run a developer-provided model aggregation callback at a failure point."""

    def __init__(self, callback: Callable[..., Any], *, models: Sequence[object] = (), metadata: Mapping[str, Any] | None = None, on_error: RuleErrorMode = RuleErrorMode.CLOSED) -> None:
        """Create an aggregation handler with an explicit model sequence."""
        super().__init__(name="aggregate", callback=callback, metadata=metadata, on_error=on_error)
        self._aggregate_settings = AggregateRecoverySettings(models=tuple(models))

    @property
    def models(self) -> tuple[object, ...]:
        """Return the configured aggregation models."""
        return self._aggregate_settings.models

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

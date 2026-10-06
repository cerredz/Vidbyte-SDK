"""FILE: vidbyte/lib/jev/managed.py

PURPOSE: Groups every decision call in one block into a single managed Jev run on Vidbyte's gateway, then closes that run.
ROLE IN CODEBASE: JevRuntime wraps each JevAgent run in JevManagedRun; direct DecisionModelRunner callers can use it the same way. The TypeSafe adapter reads the active run to send X-Vidbyte-Run-Id.
ARCHITECTURE NOTE: The active run lives in a context variable owned by vidbyte/providers/typesafe.py, its only reader, so it follows asyncio fan-out without threading a parameter. This module only opens, joins, and closes runs.
COMMON MODIFICATION PATTERNS: Keep the close best-effort; the gateway's idle reaper is the backstop, so a close failure must never fail the caller's run.
KNOWN EDGE CASES: A config that is not managed opens nothing. A nested JevManagedRun (a specialist JevAgent) joins the outer run and leaves closing to it. A run that sent no call is not closed, because the gateway has no session for it.
RELATED DOCS: docs/design/jev-managed-runs.md.
TESTS: tests/test_jev_managed_runs.py.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import Token
from types import TracebackType

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_MANAGED_RUN_ID_PREFIX
from vidbyte.lib.dataclasses.jev import JevManagedRunScope
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.enums import DecisionModelMode
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.providers.typesafe import TypeSafeManagedRunContext

logger = logging.getLogger(__name__)


class JevManagedRun:
    """Async context manager that opens one managed Jev run and closes it on exit."""

    def __init__(self, config: DecisionModelConfig) -> None:
        # Keeps the decision config whose gateway the run is opened on and closed against.
        self._config = config
        self._scope: JevManagedRunScope | None = None
        self._token: Token[JevManagedRunScope | None] | None = None

    async def __aenter__(self) -> JevManagedRunScope | None:
        # Opens a run for a managed config, or joins the run already active in this task.
        if self._config.mode is not DecisionModelMode.VIDBYTE_MANAGED:
            return None
        active = TypeSafeManagedRunContext.current()
        if active is not None:
            return active
        self._scope = JevManagedRunScope(run_id=f"{JEV_MANAGED_RUN_ID_PREFIX}{uuid.uuid4().hex}")
        self._token = TypeSafeManagedRunContext.enter(self._scope)
        return self._scope

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        # Restores the previous run, then closes this one if it opened it and sent at least one call.
        if self._token is None or self._scope is None:
            return
        TypeSafeManagedRunContext.exit(self._token)
        scope, self._scope, self._token = self._scope, None, None
        if not scope.used:
            return
        # @intent a-failed-close-never-fails-the-run
        # The answer the caller paid for is already in hand; the gateway's reaper closes an idle run
        # within an hour, so a close failure costs at most a delayed part-cent and is only logged.
        try:
            await DecisionModelRunner(self._config).aclose_run(scope.run_id)
        except VidbyteSdkError as error:
            logger.warning("jev_managed_run_close_failed run_id=%s error_type=%s", scope.run_id, type(error).__name__)


__all__ = ["JevManagedRun"]

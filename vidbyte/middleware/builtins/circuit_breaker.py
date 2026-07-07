"""
FILE: vidbyte/middleware/builtins/circuit_breaker.py

PURPOSE:
    Provides a three-state circuit breaker middleware for agent model calls. Lets developers protect against sustained model failures by short-circuiting model calls when error rate exceeds a rolling-window threshold, then recovering gradually through a half-open probe phase.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - CircuitState (class): public or navigational symbol owned here.
    - CircuitBreakerMiddleware (class): public or navigational symbol owned here.
    - CircuitBreakerMiddleware (export): public or navigational symbol owned here.
    - CircuitState (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - ValueError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from enum import Enum

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class CircuitState(str, Enum):
    """Three states of a circuit breaker: allowing, blocking, or probing."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerMiddleware(AgentMiddleware):
    """Implement the three-state circuit breaker pattern over agent model calls."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] | None = None,
    ) -> None:
        # Validates that all timing and threshold parameters are positive non-zero values.
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be greater than zero.")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero.")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than zero.")
        if half_open_max_calls <= 0:
            raise ValueError("half_open_max_calls must be greater than zero.")
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.clock = clock or time.monotonic
        self._lock = asyncio.Lock()
        self._state: CircuitState = CircuitState.CLOSED
        self._error_timestamps: list[float] = []
        self._opened_at: float | None = None
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state for external observability."""
        return self._state

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Block the model call or allow a probe depending on the current circuit state."""
        del ctx
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return MiddlewareDecision.continue_()
            if self._state is CircuitState.OPEN:
                return self._handle_open_state()
            return self._handle_half_open_state()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Close the circuit when a probe succeeds in HALF_OPEN state."""
        del ctx
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._transition_to_closed()
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the error and transition state if the failure threshold is crossed."""
        del ctx
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._transition_to_open()
            elif self._state is CircuitState.CLOSED:
                self._record_error_and_maybe_open()
        return MiddlewareDecision.continue_()

    def _handle_open_state(self) -> MiddlewareDecision:
        """Abort immediately or transition to HALF_OPEN if the recovery timeout has elapsed."""
        now = self.clock()
        if self._opened_at is not None and now - self._opened_at >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 1  # the transition call itself counts as the first probe
            return MiddlewareDecision.continue_()
        return MiddlewareDecision.abort(
            "circuit_open",
            metadata={
                "recovery_timeout": self.recovery_timeout,
                "opened_at": self._opened_at,
            },
        )

    def _handle_half_open_state(self) -> MiddlewareDecision:
        """Allow calls up to the probe limit, blocking further ones until resolution."""
        if self._half_open_calls >= self.half_open_max_calls:
            return MiddlewareDecision.abort(
                "circuit_half_open_limit",
                metadata={"half_open_max_calls": self.half_open_max_calls},
            )
        self._half_open_calls += 1
        return MiddlewareDecision.continue_()

    def _record_error_and_maybe_open(self) -> None:
        """Add the current timestamp to the error window and trip the circuit if threshold is met."""
        now = self.clock()
        self._error_timestamps.append(now)
        self._prune_error_window(now)
        if len(self._error_timestamps) >= self.failure_threshold:
            self._transition_to_open()

    def _prune_error_window(self, now: float) -> None:
        """Remove error timestamps that have fallen outside the rolling window."""
        cutoff = now - self.window_seconds
        self._error_timestamps = [t for t in self._error_timestamps if t > cutoff]

    def _transition_to_open(self) -> None:
        """Move to OPEN state and record the time the circuit opened."""
        self._state = CircuitState.OPEN
        self._opened_at = self.clock()

    def _transition_to_closed(self) -> None:
        """Move to CLOSED state and reset all error tracking."""
        self._state = CircuitState.CLOSED
        self._error_timestamps = []
        self._opened_at = None
        self._half_open_calls = 0


__all__ = ["CircuitBreakerMiddleware", "CircuitState"]

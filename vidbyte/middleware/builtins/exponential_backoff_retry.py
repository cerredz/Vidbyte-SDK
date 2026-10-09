"""Context Protocol Header

Description:
    Provides exponential backoff retry middleware for direct text agent runs.
Purpose:
    Lets direct text agent runtimes retry transient model failures with
    exponential backoff and optional jitter, filtered to specific exception types.
Architecture:
    - ExponentialBackoffRetryMiddleware: Counts model errors and issues retry
      decisions with computed delays up to a configurable cap. The per-run
      attempt counter lives in ctx.run_state (ExponentialBackoffRetryRunState).
Relations:
    Used by AgentRuntime through the on_model_error middleware hook.
"""

from __future__ import annotations

import random

from vidbyte.lib.dataclasses.middleware import (
    ExponentialBackoffRetryRunState,
    MiddlewareContext,
    MiddlewareDecision,
)
from vidbyte.middleware.base import AgentMiddleware


class ExponentialBackoffRetryMiddleware(AgentMiddleware):
    """Retry model-call exceptions with exponential backoff and optional jitter."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_seconds: float = 1.0,
        cap_seconds: float = 60.0,
        jitter: bool = True,
        retry_on: tuple[type[BaseException], ...] | None = None,
    ) -> None:
        # Validates that backoff parameters form a consistent, meaningful configuration.
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if base_seconds <= 0:
            raise ValueError("base_seconds must be greater than zero.")
        if cap_seconds < base_seconds:
            raise ValueError("cap_seconds must be greater than or equal to base_seconds.")
        self.max_attempts = max_attempts
        self.base_seconds = base_seconds
        self.cap_seconds = cap_seconds
        self.jitter = jitter
        self.retry_on = retry_on

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Start a fresh attempt counter for this run without touching other runs sharing the instance."""
        ctx.run_state[self.__class__] = ExponentialBackoffRetryRunState()
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Retry with backoff until max_attempts is reached, then abort."""
        if not self._error_is_retryable(ctx.error):
            return MiddlewareDecision.abort(
                "model_error_not_retryable",
                metadata={"error_type": type(ctx.error).__name__ if ctx.error else None},
            )
        state = self._state_for(ctx)
        state.attempts += 1
        if state.attempts >= self.max_attempts:
            return MiddlewareDecision.abort(
                "model_retry_exhausted",
                metadata={
                    "attempt": state.attempts,
                    "max_attempts": self.max_attempts,
                    "error_type": type(ctx.error).__name__ if ctx.error else None,
                },
            )
        delay = self._compute_delay(state.attempts)
        return MiddlewareDecision.retry(
            "model_retry_backoff",
            sleep_seconds=delay,
            metadata={
                "attempt": state.attempts,
                "max_attempts": self.max_attempts,
                "delay_seconds": delay,
                "error_type": type(ctx.error).__name__ if ctx.error else None,
            },
        )

    def _error_is_retryable(self, error: BaseException | None) -> bool:
        """Return True when the error type matches the configured retry filter."""
        if self.retry_on is None:
            return True
        if not self.retry_on:
            return False
        return isinstance(error, self.retry_on)

    def _state_for(self, ctx: MiddlewareContext) -> ExponentialBackoffRetryRunState:
        # Returns the current run state, lazily creating it for direct hook tests.
        state = ctx.run_state.get(self.__class__)
        if not isinstance(state, ExponentialBackoffRetryRunState):
            state = ExponentialBackoffRetryRunState()
            ctx.run_state[self.__class__] = state
        return state

    def _compute_delay(self, attempts: int) -> float:
        """Compute the capped exponential delay for the current attempt, with optional jitter."""
        raw = min(self.cap_seconds, self.base_seconds * (2 ** (attempts - 1)))
        if self.jitter:
            return raw * random.uniform(0.5, 1.0)
        return raw


__all__ = ["ExponentialBackoffRetryMiddleware"]

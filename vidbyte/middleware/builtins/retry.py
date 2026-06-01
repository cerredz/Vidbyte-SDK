"""Context Protocol Header

Description:
    Provides deterministic model-call retry middleware.
Purpose:
    Lets direct text agent runtimes retry transient runner failures at a
    middleware-controlled boundary.
Architecture:
    - ModelRetryMiddleware: Counts model errors per run and requests retries.
    - _ModelRetryRunState: Per-run dataclass stored in MiddlewareContext.run_state.
Relations:
    Used by AgentRuntime through the on_model_error middleware hook.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


@dataclass
class _ModelRetryRunState:
    # Tracks the number of model-call errors within a single run.
    attempts: int = 0


class ModelRetryMiddleware(AgentMiddleware):
    """Retry model-call exceptions up to a configured attempt count."""

    def __init__(self, *, max_attempts: int = 2, sleep_seconds: float = 0) -> None:
        # Validates and stores configuration only; no per-run state on the instance.
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if sleep_seconds < 0:
            raise ValueError("sleep_seconds cannot be negative.")
        self.max_attempts = max_attempts
        self.sleep_seconds = sleep_seconds

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Initialize a fresh per-run attempt counter in ctx.run_state."""
        ctx.run_state[self.__class__] = _ModelRetryRunState()
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Retry until the configured attempt budget is exhausted."""
        state: _ModelRetryRunState = ctx.run_state.get(self.__class__) or _ModelRetryRunState()
        state.attempts += 1
        ctx.run_state[self.__class__] = state
        if state.attempts < self.max_attempts:
            return MiddlewareDecision.retry(
                "model_retry",
                sleep_seconds=self.sleep_seconds,
                metadata={
                    "attempt": state.attempts,
                    "max_attempts": self.max_attempts,
                    "error_type": type(ctx.error).__name__ if ctx.error else None,
                },
            )
        return MiddlewareDecision.abort(
            "model_retry_exhausted",
            metadata={
                "attempt": state.attempts,
                "max_attempts": self.max_attempts,
                "error_type": type(ctx.error).__name__ if ctx.error else None,
            },
        )


__all__ = ["ModelRetryMiddleware"]

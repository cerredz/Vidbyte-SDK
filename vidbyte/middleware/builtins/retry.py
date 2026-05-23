"""Context Protocol Header

Description:
    Provides deterministic model-call retry middleware.
Purpose:
    Lets direct text agent runtimes retry transient runner failures at a
    middleware-controlled boundary.
Architecture:
    - ModelRetryMiddleware: Counts model errors per run and requests retries.
Relations:
    Used by AgentRuntime through the on_model_error middleware hook.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class ModelRetryMiddleware(AgentMiddleware):
    """Retry model-call exceptions up to a configured attempt count."""

    def __init__(self, *, max_attempts: int = 2, sleep_seconds: float = 0) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if sleep_seconds < 0:
            raise ValueError("sleep_seconds cannot be negative.")
        self.max_attempts = max_attempts
        self.sleep_seconds = sleep_seconds
        self._attempts = 0

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Reset retry state at the start of each run."""
        del ctx
        self._attempts = 0
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Retry until the configured attempt budget is exhausted."""
        self._attempts += 1
        if self._attempts < self.max_attempts:
            return MiddlewareDecision.retry(
                "model_retry",
                sleep_seconds=self.sleep_seconds,
                metadata={
                    "attempt": self._attempts,
                    "max_attempts": self.max_attempts,
                    "error_type": type(ctx.error).__name__ if ctx.error else None,
                },
            )
        return MiddlewareDecision.abort(
            "model_retry_exhausted",
            metadata={
                "attempt": self._attempts,
                "max_attempts": self.max_attempts,
                "error_type": type(ctx.error).__name__ if ctx.error else None,
            },
        )


__all__ = ["ModelRetryMiddleware"]

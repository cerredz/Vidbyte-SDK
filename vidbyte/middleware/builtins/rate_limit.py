"""Context Protocol Header

Description:
    Provides token rate limiting middleware for direct text agent runs.
Purpose:
    Lets developers slow agent loops when provider-reported token usage crosses
    a configured window threshold.
Architecture:
    - TokenRateLimitMiddleware: Provider-usage-only rolling window limiter.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class TokenRateLimitMiddleware(AgentMiddleware):
    """Sleep when provider-reported token usage exceeds a time-window limit."""

    def __init__(
        self,
        *,
        max_tokens: int,
        per_seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero.")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be greater than zero.")
        self.max_tokens = max_tokens
        self.per_seconds = per_seconds
        self.clock = clock or time.monotonic
        self._window_started = self.clock()
        self._window_tokens = 0
        self._last_tokens_seen: int | None = None

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Throttle before the next iteration when the current window is exhausted."""
        if ctx.tokens_used is None:
            return MiddlewareDecision.continue_()
        now = self.clock()
        if now - self._window_started >= self.per_seconds:
            self._window_started = now
            self._window_tokens = 0
            self._last_tokens_seen = None

        previous = self._last_tokens_seen or 0
        delta = max(0, ctx.tokens_used - previous)
        self._window_tokens += delta
        self._last_tokens_seen = ctx.tokens_used

        if self._window_tokens <= self.max_tokens:
            return MiddlewareDecision.continue_()

        sleep_seconds = max(0, self.per_seconds - (now - self._window_started))
        self._window_started = now + sleep_seconds
        self._window_tokens = 0
        return MiddlewareDecision.sleep(
            sleep_seconds,
            reason="token_rate_limit",
            metadata={"max_tokens": self.max_tokens, "per_seconds": self.per_seconds},
        )


__all__ = ["TokenRateLimitMiddleware"]

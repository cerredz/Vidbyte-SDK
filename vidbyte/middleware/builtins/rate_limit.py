"""Context Protocol Header

Description:
    Provides token rate limiting middleware for direct text agent runs.
Purpose:
    Lets developers slow agent loops when provider-reported token usage crosses
    a configured window threshold.
Architecture:
    - TokenRateLimitMiddleware: Provider-usage-only rolling window limiter.
    - _TokenRateLimitRunState: Per-run dataclass stored in MiddlewareContext.run_state.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


@dataclass
class _TokenRateLimitRunState:
    # Per-run rolling window state; each run gets its own independent token budget.
    window_started: float = 0.0
    window_tokens: int = 0
    last_tokens_seen: int | None = None


class TokenRateLimitMiddleware(AgentMiddleware):
    """Sleep when provider-reported token usage exceeds a time-window limit."""

    def __init__(
        self,
        *,
        max_tokens: int,
        per_seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        # Validates and stores configuration only; no per-run state on the instance.
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero.")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be greater than zero.")
        self.max_tokens = max_tokens
        self.per_seconds = per_seconds
        self.clock = clock or time.monotonic

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Initialize a fresh per-run token window in ctx.run_state."""
        ctx.run_state[self.__class__] = _TokenRateLimitRunState(window_started=self.clock())
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Throttle before the next iteration when the current window is exhausted."""
        if ctx.tokens_used is None:
            return MiddlewareDecision.continue_()
        state: _TokenRateLimitRunState = ctx.run_state.get(self.__class__) or _TokenRateLimitRunState(
            window_started=self.clock()
        )
        now = self.clock()
        if now - state.window_started >= self.per_seconds:
            state.window_started = now
            state.window_tokens = 0
            state.last_tokens_seen = None

        previous = state.last_tokens_seen or 0
        delta = max(0, ctx.tokens_used - previous)
        state.window_tokens += delta
        state.last_tokens_seen = ctx.tokens_used
        ctx.run_state[self.__class__] = state

        if state.window_tokens <= self.max_tokens:
            return MiddlewareDecision.continue_()

        sleep_seconds = max(0, self.per_seconds - (now - state.window_started))
        state.window_started = now + sleep_seconds
        state.window_tokens = 0
        return MiddlewareDecision.sleep(
            sleep_seconds,
            reason="token_rate_limit",
            metadata={"max_tokens": self.max_tokens, "per_seconds": self.per_seconds},
        )


__all__ = ["TokenRateLimitMiddleware"]

"""Context Protocol Header

Description:
    Provides per-run cost budget middleware for direct text agent runs.
Purpose:
    Lets developers cap the estimated USD spend of a single agent run using
    a configurable blended cost-per-million-token rate, aborting before each
    iteration once the ceiling is reached.
Architecture:
    - CostBudgetMiddleware: Accumulates token deltas from after_model_response
      and aborts in before_iteration when estimated spend exceeds max_spend_usd.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class CostBudgetMiddleware(AgentMiddleware):
    """Abort a run when estimated token cost reaches the configured USD ceiling."""

    def __init__(self, *, max_spend_usd: float, cost_per_million_tokens: float) -> None:
        # Validates that both financial parameters are positive non-zero values.
        if max_spend_usd <= 0:
            raise ValueError("max_spend_usd must be greater than zero.")
        if cost_per_million_tokens <= 0:
            raise ValueError("cost_per_million_tokens must be greater than zero.")
        self.max_spend_usd = max_spend_usd
        self.cost_per_million_tokens = cost_per_million_tokens
        self._accumulated_tokens: int = 0
        self._last_tokens_seen: int | None = None
        self._estimated_spend_usd: float = 0.0

    @property
    def estimated_spend_usd(self) -> float:
        # Returns the current estimated USD spend accumulated for this middleware instance.
        return self._estimated_spend_usd

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Reset accumulated cost state so this instance can be safely reused across runs."""
        del ctx
        self._accumulated_tokens = 0
        self._last_tokens_seen = None
        self._estimated_spend_usd = 0.0
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the token delta from this model response and update the running cost estimate."""
        if ctx.tokens_used is None:
            return MiddlewareDecision.continue_()
        delta = max(0, ctx.tokens_used - (self._last_tokens_seen or 0))
        self._accumulated_tokens += delta
        self._last_tokens_seen = ctx.tokens_used
        self._estimated_spend_usd = self._accumulated_tokens / 1_000_000 * self.cost_per_million_tokens
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Abort before the next iteration when the estimated spend has reached the ceiling."""
        if self._estimated_spend_usd >= self.max_spend_usd:
            return MiddlewareDecision.abort(
                "cost_budget_exceeded",
                metadata={
                    "max_spend_usd": self.max_spend_usd,
                    "estimated_spend_usd": self._estimated_spend_usd,
                    "tokens_used": ctx.tokens_used,
                },
            )
        return MiddlewareDecision.continue_()


__all__ = ["CostBudgetMiddleware"]

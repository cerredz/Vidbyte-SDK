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
      Per-run accumulators live in ctx.run_state (CostBudgetRunState) because one
      instance is shared by nested and forked runs.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.middleware import (
    CostBudgetRunState,
    MiddlewareContext,
    MiddlewareDecision,
)
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.builtins.limit_validation import positive_real


class CostBudgetMiddleware(AgentMiddleware):
    """Abort a run when estimated token cost reaches the configured USD ceiling."""

    def __init__(self, *, max_spend_usd: float, cost_per_million_tokens: float) -> None:
        self.max_spend_usd = positive_real(max_spend_usd, "max_spend_usd")
        self.cost_per_million_tokens = positive_real(cost_per_million_tokens, "cost_per_million_tokens")
        self._estimated_spend_usd: float = 0.0

    @property
    def estimated_spend_usd(self) -> float:
        # Returns the most recent estimate written by any run sharing this instance.
        return self._estimated_spend_usd

    def estimated_spend_usd_for(self, run_state: Mapping[Any, Any]) -> float:
        """Return the estimated USD spend of the run that owns ``run_state``."""
        state = run_state.get(self.__class__)
        return state.estimated_spend_usd if isinstance(state, CostBudgetRunState) else 0.0

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Start fresh cost state for this run without touching other runs sharing the instance."""
        ctx.run_state[self.__class__] = CostBudgetRunState()
        self._estimated_spend_usd = 0.0
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the token delta from this model response and update the running cost estimate."""
        if ctx.tokens_used is None:
            return MiddlewareDecision.continue_()
        state = self._state_for(ctx)
        delta = max(0, ctx.tokens_used - (state.last_tokens_seen or 0))
        state.accumulated_tokens += delta
        state.last_tokens_seen = ctx.tokens_used
        state.estimated_spend_usd = state.accumulated_tokens / 1_000_000 * self.cost_per_million_tokens
        self._estimated_spend_usd = state.estimated_spend_usd
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Abort before the next iteration when the estimated spend has reached the ceiling."""
        spend = self._state_for(ctx).estimated_spend_usd
        if spend >= self.max_spend_usd:
            return MiddlewareDecision.abort(
                "cost_budget_exceeded",
                metadata={
                    "max_spend_usd": self.max_spend_usd,
                    "estimated_spend_usd": spend,
                    "tokens_used": ctx.tokens_used,
                },
            )
        return MiddlewareDecision.continue_()

    def _state_for(self, ctx: MiddlewareContext) -> CostBudgetRunState:
        # Returns the current run state, lazily creating it for direct hook tests.
        state = ctx.run_state.get(self.__class__)
        if not isinstance(state, CostBudgetRunState):
            state = CostBudgetRunState()
            ctx.run_state[self.__class__] = state
        return state


__all__ = ["CostBudgetMiddleware"]

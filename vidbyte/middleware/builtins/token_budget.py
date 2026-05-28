"""Context Protocol Header

Description:
    Provides per-run token budget middleware for direct text agent runs.
Purpose:
    Lets developers cap the total provider-reported tokens consumed by a single
    agent run, aborting before each iteration once the ceiling is reached.
Architecture:
    - TokenBudgetMiddleware: Reads ctx.tokens_used and aborts when >= max_tokens.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class TokenBudgetMiddleware(AgentMiddleware):
    """Abort a run when provider-reported cumulative token usage reaches the configured ceiling."""

    def __init__(self, *, max_tokens: int, abort_reason: str = "token_budget_exceeded") -> None:
        # Validates that max_tokens is a meaningful positive ceiling.
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero.")
        self.max_tokens = max_tokens
        self.abort_reason = abort_reason

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Abort before the next iteration when token usage has reached the ceiling."""
        if ctx.tokens_used is None:
            return MiddlewareDecision.continue_()
        if ctx.tokens_used >= self.max_tokens:
            return MiddlewareDecision.abort(
                self.abort_reason,
                metadata={"max_tokens": self.max_tokens, "tokens_used": ctx.tokens_used},
            )
        return MiddlewareDecision.continue_()


__all__ = ["TokenBudgetMiddleware"]

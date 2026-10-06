"""Context Protocol Header

Description:
    Provides per-run token budget middleware for direct text agent runs.
Purpose:
    Lets developers cap the total provider-reported tokens consumed by a single
    agent run, aborting or requesting one final answer once the ceiling is reached.
Architecture:
    - TokenBudgetMiddleware: Reads ctx.tokens_used and aborts when >= max_tokens,
      or injects one final-answer notice when soft overrun is enabled.
    - _TokenBudgetRunState: Tracks whether the final-answer notice was already
      requested for the current run.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision, MiddlewareTransform
from vidbyte.middleware.base import AgentMiddleware


TOKEN_BUDGET_FINAL_RESPONSE_NOTICE = (
    "Token budget notice: this run has reached or exceeded its configured token budget. "
    "Do not call additional tools or continue exploring. Provide the best final answer now, "
    "using only the information already available in the conversation."
)


@dataclass
class _TokenBudgetRunState:
    # Tracks whether this run already received the one allowed final-answer notice.
    final_response_requested: bool = False


class TokenBudgetMiddleware(AgentMiddleware):
    """Enforce provider-reported token ceilings with optional one-call final-answer overrun."""

    def __init__(self, *, max_tokens: int, abort_reason: str = "token_budget_exceeded", allow_final_response_over_budget: bool = False) -> None:
        # Validates that max_tokens is a meaningful positive ceiling.
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero.")
        self.max_tokens = max_tokens
        self.abort_reason = abort_reason
        self.allow_final_response_over_budget = allow_final_response_over_budget

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Initializes fresh per-run token budget state for this middleware instance.
        ctx.run_state[self.__class__] = _TokenBudgetRunState()
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Abort before the next iteration unless a one-time final-answer call is still available.
        if ctx.tokens_used is None:
            return MiddlewareDecision.continue_()
        if ctx.tokens_used < self.max_tokens:
            return MiddlewareDecision.continue_()
        state = self._state_for(ctx)
        if self.allow_final_response_over_budget and not state.final_response_requested:
            return MiddlewareDecision.continue_(
                metadata=self._budget_metadata(ctx.tokens_used, final_response_requested=True)
            )
        return MiddlewareDecision.abort(self.abort_reason, metadata=self._budget_metadata(ctx.tokens_used))

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Injects one final-answer instruction when soft overrun is enabled and the budget is spent.
        if not self.allow_final_response_over_budget:
            return MiddlewareDecision.continue_()
        if ctx.tokens_used is None or ctx.tokens_used < self.max_tokens:
            return MiddlewareDecision.continue_()
        state = self._state_for(ctx)
        if state.final_response_requested:
            return MiddlewareDecision.abort(self.abort_reason, metadata=self._budget_metadata(ctx.tokens_used))
        state.final_response_requested = True
        self._publish_result_metadata(ctx, ctx.tokens_used)
        return MiddlewareDecision.continue_(
            metadata=self._budget_metadata(ctx.tokens_used, final_response_requested=True),
            transform=MiddlewareTransform(system=self._build_system_with_notice(ctx.system)),
        )

    def _state_for(self, ctx: MiddlewareContext) -> _TokenBudgetRunState:
        # Returns the current run state, lazily creating it for direct hook tests.
        state = ctx.run_state.get(self.__class__)
        if not isinstance(state, _TokenBudgetRunState):
            state = _TokenBudgetRunState()
            ctx.run_state[self.__class__] = state
        return state

    def _budget_metadata(self, tokens_used: int, *, final_response_requested: bool = False) -> dict[str, object]:
        # Builds consistent metadata for token budget aborts and soft-overrun notices.
        metadata: dict[str, object] = {"max_tokens": self.max_tokens, "tokens_used": tokens_used}
        if final_response_requested:
            metadata["final_response_requested"] = True
        return metadata

    def _publish_result_metadata(self, ctx: MiddlewareContext, tokens_used: int) -> None:
        # Publishes public result metadata through AgentRuntime's run_state handoff channel.
        published = ctx.run_state.get("__result_metadata__")
        if not isinstance(published, dict):
            published = {}
            ctx.run_state["__result_metadata__"] = published
        published["token_budget"] = self._budget_metadata(tokens_used, final_response_requested=True)

    def _build_system_with_notice(self, system: str | None) -> str:
        # Appends the fixed SDK-controlled notice to the active system prompt.
        if system:
            return f"{system}\n\n{TOKEN_BUDGET_FINAL_RESPONSE_NOTICE}"
        return TOKEN_BUDGET_FINAL_RESPONSE_NOTICE


__all__ = ["TOKEN_BUDGET_FINAL_RESPONSE_NOTICE", "TokenBudgetMiddleware"]

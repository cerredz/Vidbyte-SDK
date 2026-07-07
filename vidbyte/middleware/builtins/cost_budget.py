"""
FILE: vidbyte/middleware/builtins/cost_budget.py

PURPOSE:
    Provides per-run cost budget middleware for direct text agent runs. Lets developers cap the estimated USD spend of a single agent run using a configurable blended cost-per-million-token rate, aborting before each iteration once the ceiling is reached.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - CostBudgetMiddleware (class): public or navigational symbol owned here.
    - CostBudgetMiddleware (export): public or navigational symbol owned here.

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

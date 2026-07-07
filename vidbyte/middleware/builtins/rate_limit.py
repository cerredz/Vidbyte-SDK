"""
FILE: vidbyte/middleware/builtins/rate_limit.py

PURPOSE:
    Provides token rate limiting middleware for direct text agent runs. Lets developers slow agent loops when provider-reported token usage crosses a configured window threshold.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - TokenRateLimitMiddleware (class): public or navigational symbol owned here.
    - TokenRateLimitMiddleware (export): public or navigational symbol owned here.

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

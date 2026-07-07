"""
FILE: vidbyte/middleware/builtins/retry.py

PURPOSE:
    Provides deterministic model-call retry middleware. Lets direct text agent runtimes retry transient runner failures at a middleware-controlled boundary.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - ModelRetryMiddleware (class): public or navigational symbol owned here.
    - ModelRetryMiddleware (export): public or navigational symbol owned here.

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

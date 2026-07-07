"""
FILE: vidbyte/middleware/builtins/exponential_backoff_retry.py

PURPOSE:
    Provides exponential backoff retry middleware for direct text agent runs. Lets direct text agent runtimes retry transient model failures with exponential backoff and optional jitter, filtered to specific exception types.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - ExponentialBackoffRetryMiddleware (class): public or navigational symbol owned here.
    - ExponentialBackoffRetryMiddleware (export): public or navigational symbol owned here.

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

import random

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class ExponentialBackoffRetryMiddleware(AgentMiddleware):
    """Retry model-call exceptions with exponential backoff and optional jitter."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_seconds: float = 1.0,
        cap_seconds: float = 60.0,
        jitter: bool = True,
        retry_on: tuple[type[BaseException], ...] | None = None,
    ) -> None:
        # Validates that backoff parameters form a consistent, meaningful configuration.
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if base_seconds <= 0:
            raise ValueError("base_seconds must be greater than zero.")
        if cap_seconds < base_seconds:
            raise ValueError("cap_seconds must be greater than or equal to base_seconds.")
        self.max_attempts = max_attempts
        self.base_seconds = base_seconds
        self.cap_seconds = cap_seconds
        self.jitter = jitter
        self.retry_on = retry_on
        self._attempts: int = 0

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Reset the attempt counter so this instance is safe to reuse across runs."""
        del ctx
        self._attempts = 0
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Retry with backoff until max_attempts is reached, then abort."""
        if not self._error_is_retryable(ctx.error):
            return MiddlewareDecision.abort(
                "model_error_not_retryable",
                metadata={"error_type": type(ctx.error).__name__ if ctx.error else None},
            )
        self._attempts += 1
        if self._attempts >= self.max_attempts:
            return MiddlewareDecision.abort(
                "model_retry_exhausted",
                metadata={
                    "attempt": self._attempts,
                    "max_attempts": self.max_attempts,
                    "error_type": type(ctx.error).__name__ if ctx.error else None,
                },
            )
        delay = self._compute_delay()
        return MiddlewareDecision.retry(
            "model_retry_backoff",
            sleep_seconds=delay,
            metadata={
                "attempt": self._attempts,
                "max_attempts": self.max_attempts,
                "delay_seconds": delay,
                "error_type": type(ctx.error).__name__ if ctx.error else None,
            },
        )

    def _error_is_retryable(self, error: BaseException | None) -> bool:
        """Return True when the error type matches the configured retry filter."""
        if self.retry_on is None:
            return True
        if not self.retry_on:
            return False
        return isinstance(error, self.retry_on)

    def _compute_delay(self) -> float:
        """Compute the capped exponential delay for the current attempt, with optional jitter."""
        raw = min(self.cap_seconds, self.base_seconds * (2 ** (self._attempts - 1)))
        if self.jitter:
            return raw * random.uniform(0.5, 1.0)
        return raw


__all__ = ["ExponentialBackoffRetryMiddleware"]

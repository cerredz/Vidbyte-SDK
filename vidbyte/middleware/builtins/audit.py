"""
FILE: vidbyte/middleware/builtins/audit.py

PURPOSE:
    Provides structured audit logging middleware for agent runtime hooks. Lets developers observe direct text runtime lifecycle events without coupling application logging to AgentRuntime internals.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - AuditLogMiddleware (class): public or navigational symbol owned here.
    - AuditLogMiddleware (export): public or navigational symbol owned here.

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
    - None observed in this file; preserve this when adding new failure paths.

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

from collections.abc import Callable, Iterable
from typing import Any

from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
)
from vidbyte.middleware.base import AgentMiddleware


class AuditLogMiddleware(AgentMiddleware):
    """Emit structured events for configured middleware hooks."""

    def __init__(
        self,
        sink: Callable[[MiddlewareEvent], object] | list[MiddlewareEvent],
        *,
        hooks: Iterable[MiddlewareHook] | None = None,
    ) -> None:
        self.sink = sink
        self.hooks = None if hooks is None else frozenset(hooks)

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    def _emit(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if self.hooks is not None and ctx.hook not in self.hooks:
            return MiddlewareDecision.continue_()
        event = MiddlewareEvent(
            middleware_name=self.middleware_name,
            hook=ctx.hook,
            action=MiddlewareAction.CONTINUE,
            metadata=self._metadata(ctx),
        )
        if isinstance(self.sink, list):
            self.sink.append(event)
        else:
            self.sink(event)
        return MiddlewareDecision.continue_()

    @staticmethod
    def _metadata(ctx: MiddlewareContext) -> dict[str, Any]:
        return {
            "agent_name": ctx.agent_name,
            "iteration_count": ctx.iteration_count,
            "model_call_count": ctx.model_call_count,
            "tool_call_count": ctx.tool_call_count,
            "tokens_used": ctx.tokens_used,
            "tool_name": ctx.tool_call.tool_name if ctx.tool_call else None,
            "tool_is_internal": ctx.tool_is_internal,
            "error_type": type(ctx.error).__name__ if ctx.error else None,
        }


__all__ = ["AuditLogMiddleware"]

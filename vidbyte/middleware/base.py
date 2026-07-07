"""
FILE: vidbyte/middleware/base.py

PURPOSE:
    Defines the public base class for agent runtime middleware. Lets SDK users create middleware by subclassing one class and overriding only the runtime lifecycle hooks they need.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.

FUNCTION INVENTORY:
    - AgentMiddleware (class): public or navigational symbol owned here.
    - AgentMiddleware (export): public or navigational symbol owned here.

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

from abc import ABC

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision


class AgentMiddleware(ABC):
    """Base class for deterministic agent runtime middleware."""

    name: str | None = None
    fail_closed: bool = True

    @property
    def middleware_name(self) -> str:
        """Return a stable display name for metadata and audit events."""
        return self.name or self.__class__.__name__

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before the direct text runtime starts."""
        del ctx
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before each direct text runtime iteration."""
        del ctx
        return MiddlewareDecision.continue_()

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run immediately before invoking the model runner."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run after a successful model response has been received."""
        del ctx
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run when model invocation raises an exception."""
        del ctx
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before permission checks, validation, and local tool execution."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run after a tool call was executed or denied."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run after one direct text runtime iteration completes."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before returning the final runtime result."""
        del ctx
        return MiddlewareDecision.continue_()


__all__ = ["AgentMiddleware"]

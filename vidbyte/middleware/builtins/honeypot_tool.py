"""
FILE: vidbyte/middleware/builtins/honeypot_tool.py

PURPOSE:
    Provides honeypot tool detection middleware for agent tool calls. Lets developers detect prompt injection or hallucination by planting decoy forbidden tool names that trigger an immediate abort if called.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - HoneypotToolMiddleware (class): public or navigational symbol owned here.
    - HoneypotToolMiddleware (export): public or navigational symbol owned here.

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

from collections.abc import Iterable

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class HoneypotToolMiddleware(AgentMiddleware):
    """Abort when the model attempts to call a planted trap tool name."""

    def __init__(self, *, trap_tool_names: Iterable[str], abort_reason: str = "honeypot_triggered") -> None:
        # Validates and stores the set of trap tool names as a frozen lookup set.
        self._traps = frozenset(trap_tool_names)
        if not self._traps:
            raise ValueError("trap_tool_names must contain at least one name.")
        self._abort_reason = abort_reason

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Checks if the requested tool name matches any honeypot trap name.
        if ctx.tool_call is None or ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        if ctx.tool_call.tool_name in self._traps:
            return MiddlewareDecision.abort(
                self._abort_reason,
                metadata={"trapped_tool": ctx.tool_call.tool_name},
            )
        return MiddlewareDecision.continue_()


__all__ = ["HoneypotToolMiddleware"]

"""Context Protocol Header

Description:
    Provides honeypot tool detection middleware for agent tool calls.
Purpose:
    Lets developers detect prompt injection or hallucination by planting
    decoy forbidden tool names that trigger an immediate abort if called.
Architecture:
    - HoneypotToolMiddleware: Watches for tool call names matching a configured
      set of trap tool names and aborts on match.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
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

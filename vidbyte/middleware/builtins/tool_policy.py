"""Context Protocol Header

Description:
    Provides allowlist and denylist middleware for agent tool calls.
Purpose:
    Lets developers enforce runtime-specific tool policy before permission
    checks, validation, or tool execution occur.
Architecture:
    - ToolPolicyMiddleware: Name-based user tool allow/deny policy.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime before_tool_call.
"""

from __future__ import annotations

from collections.abc import Iterable

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class ToolPolicyMiddleware(AgentMiddleware):
    """Allow or deny tool calls by tool name."""

    def __init__(
        self,
        *,
        allow_tools: Iterable[str] | None = None,
        deny_tools: Iterable[str] = (),
        allow_internal_tools: bool = True,
    ) -> None:
        self.allow_tools = None if allow_tools is None else frozenset(allow_tools)
        self.deny_tools = frozenset(deny_tools)
        self.allow_internal_tools = allow_internal_tools

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Deny blocked tool calls before execution."""
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()
        if ctx.tool_is_internal and self.allow_internal_tools:
            return MiddlewareDecision.continue_()

        name = ctx.tool_call.tool_name
        if name in self.deny_tools:
            return MiddlewareDecision.deny_tool(
                "tool_denylisted",
                metadata={"tool_name": name},
            )
        if self.allow_tools is not None and name not in self.allow_tools:
            return MiddlewareDecision.deny_tool(
                "tool_not_allowlisted",
                metadata={"tool_name": name},
            )
        return MiddlewareDecision.continue_()


__all__ = ["ToolPolicyMiddleware"]

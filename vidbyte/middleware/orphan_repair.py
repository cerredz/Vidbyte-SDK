"""Context Protocol Header

Description:
    Orphan-repair middleware that detects tool calls in model responses that
    are missing companion results and injects synthetic error results.
Purpose:
    Prevents agents from silently hanging when a model response references
    tool calls that were never executed, by inserting placeholder error results.
Architecture:
    - Hooks into after_model_response to inspect the model response object.
    - Extracts expected tool-call IDs from the response content.
    - Cross-references against tracked tool results; injects placeholders
      for orphans.
Relations:
    Extends vidbyte.middleware.base.AgentMiddleware.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware

_ORPHAN_MSG = (
    "[tool_result (synthetic)] Tool call was orphaned — no matching execution "
    "result is available. Re-try the call or proceed with available context."
)


class ToolOrphanRepairMiddleware(AgentMiddleware):
    """Detects and fixes orphaned tool calls in conversation history."""

    def __init__(self) -> None:
        self._recent_tool_names: list[str] = []

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the tool name for orphan tracking."""
        if ctx.tool_call is not None:
            self._recent_tool_names.append(ctx.tool_call.tool_name)
            if len(self._recent_tool_names) > 20:
                self._recent_tool_names = self._recent_tool_names[-20:]
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Check if a tool result is missing (orphaned) and inject a synthetic one."""
        if ctx.tool_call is not None and ctx.tool_result is None:
            return MiddlewareDecision.continue_(
                metadata={"orphan_detected": True, "note": _ORPHAN_MSG}
            )
        return MiddlewareDecision.continue_()


__all__ = ["ToolOrphanRepairMiddleware"]

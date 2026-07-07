"""Context Protocol Header

Description:
    Implements ContextStatsTool for compact managed primitive inventory.
Purpose:
    Lets agents inspect ids, kinds, titles, placement, frozen status, and
    rendered character counts before editing the context window.
Architecture:
    - ContextStatsTool: BaseTool that reads ContextManager.registry_items().
Relations:
    Used via context_window_tools and vidbyte.tools.builtins.context_primitives.
    Depends on ContextManager placement metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextStatsTool(BaseTool):
    """Builtin tool that summarizes all managed primitives in the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime."""
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_stats",
            description="List context window primitive ids, kinds, titles, placements, frozen flags, and rendered character counts.",
            parameters=(),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Return one compact statistics line per managed primitive."""
        registry = self._manager.registry_items()
        if not registry:
            return ToolResult.success(call.tool_name, "No active context window primitives.")
        lines = [f"Context window primitive stats ({len(registry)} total):"]
        for primitive_id, item in registry:
            placement = self._manager.placement_for(primitive_id) or ContextWindowPlacement.END_OF_CONTEXT
            frozen = "true" if getattr(item, "primitive_frozen", False) else "false"
            title = str(item.title).replace("\n", " ")
            lines.append(f"[{primitive_id}] kind={item.kind} title={title} placement={placement.value} frozen={frozen} chars={len(item.to_context_text())}")
        return ToolResult.success(call.tool_name, "\n".join(lines))


__all__ = ["ContextStatsTool"]

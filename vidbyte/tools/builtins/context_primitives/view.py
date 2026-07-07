"""Context Protocol Header

Description:
    Implements ContextViewTool for reading one managed context primitive.
Purpose:
    Lets agents inspect the full rendered text for a specific primitive without
    dumping every registered primitive into the tool result.
Architecture:
    - ContextViewTool: BaseTool that reads ContextManager.get_by_id().
Relations:
    Used via context_window_tools and vidbyte.tools.builtins.context_primitives.
    Depends on ContextManager and primitive rendering helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.context.primitives.base import _truncate_text
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_MAX_VIEW_CHARS = 12000


class ContextViewTool(BaseTool):
    """Builtin tool that returns the rendered text for one managed primitive."""

    def __init__(self, context_manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime."""
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_view",
            description="View the rendered text for one context window primitive by id.",
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description="The id of the primitive to view, e.g. 'plan:current'.",
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Return bounded rendered text for one primitive or an actionable error."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        item = self._manager.get_by_id(primitive_id)
        if item is None:
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' does not exist. Use context_stats or context_list to inspect available ids.")
        output = _truncate_text(item.to_context_text(), _MAX_VIEW_CHARS)
        return ToolResult.success(call.tool_name, output, metadata={"primitive_id": primitive_id, "kind": item.kind})


__all__ = ["ContextViewTool"]

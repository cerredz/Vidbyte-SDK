"""Context Protocol Header

Description:
    Implements ContextMoveTool for changing managed primitive placement.
Purpose:
    Lets agents move non-frozen primitives between context and conversation
    placement slots without changing primitive content.
Architecture:
    - ContextMoveTool: BaseTool that routes to ContextManager.set_placement().
Relations:
    Used via context_window_tools and vidbyte.tools.builtins.context_primitives.
    Depends on ContextWindowPlacement and frozen primitive semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextMoveTool(BaseTool):
    """Builtin tool that updates the placement for one managed primitive."""

    def __init__(self, context_manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime."""
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_move",
            description="Move one non-frozen context window primitive to another placement without changing content.",
            parameters=(
                ToolParameter(name="primitive_id", type="string", description="The id of the primitive to move.", required=True),
                ToolParameter(name="placement", type="string", description="One of: top_of_context, end_of_context, top_of_conversation, end_of_conversation.", required=True),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Move the primitive to a new placement or return a steering error."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        item = self._manager.get_by_id(primitive_id)
        if item is None:
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' does not exist. Use context_stats or context_list to inspect available ids.")
        if getattr(item, "primitive_frozen", False):
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' is frozen; it cannot be moved. Create a new primitive with a different id instead.")
        placement_result = self._parse_placement(str(call.arguments.get("placement", "")).strip())
        if not isinstance(placement_result, ContextWindowPlacement):
            return ToolResult.error(call.tool_name, placement_result)
        self._manager.set_placement(primitive_id, placement_result)
        return ToolResult.success(call.tool_name, f"Primitive '{primitive_id}' moved to placement '{placement_result.value}'.", metadata={"primitive_id": primitive_id, "placement": placement_result.value})

    def _parse_placement(self, placement_raw: str) -> ContextWindowPlacement | str:
        """Return a normalized placement enum or an error message string."""
        try:
            return ContextWindowPlacement(placement_raw)
        except ValueError:
            allowed = ", ".join(placement.value for placement in ContextWindowPlacement)
            return f"Invalid placement '{placement_raw}'. Use one of: {allowed}."


__all__ = ["ContextMoveTool"]

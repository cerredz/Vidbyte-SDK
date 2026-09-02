"""Context Protocol Header

Description:
    Implements ContextMoveTool for changing managed primitive placement.
Purpose:
    Lets agents move non-frozen primitives between context and conversation
    placement slots without changing primitive content.
Architecture:
    - ContextMoveTool: BaseTool that routes to ContextManager.set_placement().
Relations:
    Used via ContextWindowFactory and vidbyte.tools.builtins.context_primitives.
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
            description=(
                "context_move is the management tool for reordering managed context window "
                "primitives without rewriting their content. context_move does change the "
                "placement of one non-frozen primitive among top_of_context, end_of_context, "
                "top_of_conversation, and end_of_conversation so the agent can prioritize what "
                "the model sees first on the next loop iteration."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description=(
                        "primitive_id is the registry key of the managed primitive to move. "
                        "primitive_id does select which slot's placement metadata is updated."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="placement",
                    type="string",
                    description=(
                        "placement is the new render position for the primitive. placement does "
                        "accept top_of_context, end_of_context, top_of_conversation, or "
                        "end_of_conversation and leaves content unchanged."
                    ),
                    required=True,
                ),
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
        try:
            self._manager.set_placement(primitive_id, placement_result)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(call.tool_name, f"Primitive '{primitive_id}' moved to placement '{placement_result.value}'.", metadata={"primitive_id": primitive_id, "placement": placement_result.value})

    def _parse_placement(self, placement_raw: str) -> ContextWindowPlacement | str:
        """Return a normalized placement enum or an error message string."""
        try:
            return ContextWindowPlacement(placement_raw)
        except ValueError:
            allowed = ", ".join(placement.value for placement in ContextWindowPlacement)
            return f"Invalid placement '{placement_raw}'. Use one of: {allowed}."


__all__ = ["ContextMoveTool"]

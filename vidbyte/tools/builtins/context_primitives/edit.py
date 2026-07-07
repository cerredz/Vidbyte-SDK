"""Context Protocol Header

Description:
    Implements ContextEditTool for exact-string edits on managed primitives.
Purpose:
    Lets agents update content-bearing primitives without replacing unrelated
    fields or silently patching ambiguous text.
Architecture:
    - ContextEditTool: BaseTool that dataclasses.replace()s the content field.
Relations:
    Used via context_window_tools and vidbyte.tools.builtins.context_primitives.
    Depends on ContextManager and frozen primitive semantics.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextEditTool(BaseTool):
    """Builtin tool that performs an exact unique replacement on primitive content."""

    def __init__(self, context_manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime."""
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_edit",
            description="Edit one non-frozen content-bearing context primitive by replacing one exact, unique old_string with new_string.",
            parameters=(
                ToolParameter(name="primitive_id", type="string", description="The id of the primitive to edit.", required=True),
                ToolParameter(name="old_string", type="string", description="Exact existing content string to replace. It must appear exactly once.", required=True),
                ToolParameter(name="new_string", type="string", description="Replacement string.", required=True),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Patch the primitive content field or return a steering error."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        item = self._manager.get_by_id(primitive_id)
        if item is None:
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' does not exist. Use context_stats or context_list to inspect available ids.")
        if getattr(item, "primitive_frozen", False):
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' is frozen; it cannot be modified. Create a new primitive with a different id instead.")
        content = getattr(item, "content", None)
        if not isinstance(content, str) or not dataclasses.is_dataclass(item):
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' has no editable string content field. Create a replacement primitive instead.")
        old_string = str(call.arguments.get("old_string", ""))
        new_string = str(call.arguments.get("new_string", ""))
        if not old_string:
            return ToolResult.error(call.tool_name, "old_string must be a non-empty exact string that appears once in the primitive content.")
        match_count = content.count(old_string)
        if match_count == 0:
            return ToolResult.error(call.tool_name, f"old_string was not found in primitive '{primitive_id}'. Use context_view first and pass an exact substring.")
        if match_count > 1:
            return ToolResult.error(call.tool_name, f"old_string appears {match_count} times in primitive '{primitive_id}'. Use a longer exact string that appears once.")
        try:
            updated = dataclasses.replace(item, content=content.replace(old_string, new_string, 1))
            placement = self._manager.placement_for(primitive_id) or ContextWindowPlacement.END_OF_CONTEXT
            self._manager.upsert(updated, placement=placement)
        except (TypeError, ValueError) as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(call.tool_name, f"Primitive '{primitive_id}' content edited successfully.", metadata={"primitive_id": primitive_id})


__all__ = ["ContextEditTool"]

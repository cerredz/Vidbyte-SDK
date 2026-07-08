"""Context Protocol Header

Description:
    Implements ContextEditTool for exact-string edits on managed primitives.
Purpose:
    Lets agents update content-bearing primitives without replacing unrelated
    fields or silently patching ambiguous text.
Architecture:
    - ContextEditTool: BaseTool that dataclasses.replace()s the content field.
Relations:
    Used via ContextWindowFactory and vidbyte.tools.builtins.context_primitives.
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
            description=(
                "context_edit is the management tool for surgical updates to content-bearing "
                "managed context window primitives. context_edit does replace exactly one unique "
                "occurrence of old_string with new_string on a non-frozen primitive that has a "
                "string content field, preserving placement and other fields; it refuses zero "
                "matches, multiple matches, frozen primitives, and primitives without editable content."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description=(
                        "primitive_id is the registry key of the managed primitive to edit. "
                        "primitive_id does select which slot is patched; use context_stats or "
                        "context_list if you need to discover available ids."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    description=(
                        "old_string is the exact existing substring to replace inside the primitive "
                        "content field. old_string does identify the patch target and must appear "
                        "exactly once — expand the substring if it is missing or ambiguous."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="new_string",
                    type="string",
                    description=(
                        "new_string is the replacement text written in place of the single old_string "
                        "match. new_string does become the updated content fragment after a successful edit."
                    ),
                    required=True,
                ),
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
            return ToolResult.error(
                call.tool_name,
                f"old_string was not found in primitive '{primitive_id}'. Read the primitive from the rendered context window zone and pass an exact substring that appears once.",
            )
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

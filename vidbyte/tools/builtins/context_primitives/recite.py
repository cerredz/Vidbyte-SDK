"""Context Protocol Header

Description:
    Implements ContextReciteTool for re-emitting managed primitives at end of conversation.
Purpose:
    Lets agents re-surface a named primitive into the model's most recent attention span
    via END_OF_CONVERSATION placement without removing the source primitive.
Architecture:
    - ContextReciteTool: BaseTool that routes to ContextManager.recite().
Relations:
    Used via ContextWindowFactory and vidbyte.tools.builtins.context_primitives.
    Depends on ContextManager conversation placement rendering in AgentRuntime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextReciteTool(BaseTool):
    """Builtin tool that copies a managed primitive to END_OF_CONVERSATION attention."""

    def __init__(self, context_manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime."""
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_recite",
            description=(
                "context_recite re-emits a named managed primitive at END_OF_CONVERSATION so it "
                "lands in the model's most recent attention span (Manus-style recitation). "
                "It upserts a copy (default id recite:{primitive_id}, or slot_id when provided) "
                "without removing or moving the source. Call again after editing the source to "
                "refresh the recitation copy."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description=(
                        "primitive_id is the registry key of the source managed primitive to recite. "
                        "Use context_list or context_stats to discover available ids."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="slot_id",
                    type="string",
                    description=(
                        "Optional fixed recitation slot id. Defaults to recite:{primitive_id}. "
                        "Use a stable slot like recite:active to overwrite a single sticky recitation."
                    ),
                    required=False,
                    default="",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Copy the source primitive to END_OF_CONVERSATION or return a steering error."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        if not primitive_id:
            return ToolResult.error(call.tool_name, "primitive_id is required.")
        slot_raw = str(call.arguments.get("slot_id", "") or "").strip()
        slot_id = slot_raw or None
        try:
            target_id = self._manager.recite(primitive_id, slot_id=slot_id)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(
            call.tool_name,
            f"Primitive '{primitive_id}' recited to END_OF_CONVERSATION as '{target_id}'.",
            metadata={"primitive_id": primitive_id, "recite_id": target_id},
        )


__all__ = ["ContextReciteTool"]

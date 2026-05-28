"""Context Protocol Header

Description:
    Implements ContextRemoveTool — an agent-facing builtin for removing managed
    primitives from the active ContextManager registry.
Purpose:
    Lets agents clean up window-resident context primitives they no longer need.
Architecture:
    - ContextRemoveTool: BaseTool that routes to ContextManager.remove_by_id().
Relations:
    Used via vidbyte.tools.builtins.context_primitives. Depends on
    vidbyte.context.manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextRemoveTool(BaseTool):
    """Builtin tool that removes a managed primitive from the context window registry."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores a reference to the live manager shared with AgentRuntime.
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_remove",
            description=(
                "Remove a named primitive from the context window. "
                "No-op if the primitive does not exist."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description="The id of the primitive to remove, e.g. 'plan:current'.",
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Remove the primitive with the given id from the manager."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        self._manager.remove_by_id(primitive_id)
        return ToolResult.success(
            call.tool_name,
            f"Primitive '{primitive_id}' removed from the context window.",
        )

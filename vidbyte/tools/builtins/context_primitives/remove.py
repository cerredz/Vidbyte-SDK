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
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

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
                "context_remove is the management tool for deleting managed context window "
                "primitives the agent no longer needs. context_remove does remove one "
                "non-frozen primitive by primitive_id from the shared ContextManager registry "
                "(no-op if the id is already absent) so the rendered context window zone "
                "stops including that entry on the next loop iteration."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description=(
                        "primitive_id is the registry key of the managed primitive to delete "
                        "(for example 'plan:current'). primitive_id does select the slot to "
                        "remove; frozen primitives cannot be deleted through this tool."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Remove the primitive with the given id from the manager."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        item = self._manager.get_by_id(primitive_id)
        if item is not None and getattr(item, "primitive_frozen", False):
            return ToolResult.error(
                call.tool_name,
                f"Primitive '{primitive_id}' is frozen; it cannot be removed. Create a new primitive with a different id instead.",
            )
        self._manager.remove_by_id(primitive_id)
        return ToolResult.success(
            call.tool_name,
            f"Primitive '{primitive_id}' removed from the context window.",
        )

"""Context Protocol Header

Description:
    Implements ContextListTool — an agent-facing builtin for listing all managed
    primitives currently registered in the active ContextManager.
Purpose:
    Lets agents inspect what is in the context window registry before deciding
    to create, update, or remove primitives.
Architecture:
    - ContextListTool: BaseTool that reads from ContextManager.registry_items().
Relations:
    Used via vidbyte.tools.builtins.context_primitives. Depends on
    vidbyte.context.manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextListTool(BaseTool):
    """Builtin tool that lists all managed primitives currently in the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores a reference to the live manager shared with AgentRuntime.
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_list",
            description=(
                "context_list is the management tool for enumerating managed context window "
                "primitives currently in the registry. context_list does return each primitive's "
                "id, kind, title, frozen marker, and rendered character count so the agent can "
                "inspect what is online before creating, editing, moving, or removing entries."
            ),
            parameters=(),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Return a summary of every primitive in the manager registry."""
        registry = self._manager.registry_items()
        if not registry:
            return ToolResult.success(call.tool_name, "No active context window primitives.")
        lines = [f"Active context window primitives ({len(registry)} total):"]
        for primitive_id, item in registry:
            frozen_marker = " [frozen]" if getattr(item, "primitive_frozen", False) else ""
            char_count = len(item.to_context_text())
            lines.append(f"  [{primitive_id}] ({item.kind}) {item.title}{frozen_marker} — {char_count} chars")
        return ToolResult.success(call.tool_name, "\n".join(lines))

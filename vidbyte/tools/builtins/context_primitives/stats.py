"""Context Protocol Header

Description:
    Implements ContextStatsTool for compact managed primitive inventory.
Purpose:
    Lets agents inspect ids, kinds, titles, placement, frozen status, and
    rendered character counts before editing the context window.
Architecture:
    - ContextStatsTool: BaseTool that reads ContextManager.registry_items().
Relations:
    Used via ContextWindowFactory and vidbyte.tools.builtins.context_primitives.
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
            description=(
                "context_stats is the management tool for a compact inventory of every managed "
                "context window primitive. context_stats does return one line per registry entry "
                "with id, kind, title, placement, frozen flag, and rendered character count so the "
                "agent can decide what to edit, move, or remove without dumping full primitive bodies."
            ),
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
            try:
                char_count = len(item.to_context_text())
            except Exception as exc:
                return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' could not be rendered for stats: {exc}")
            lines.append(f"[{primitive_id}] kind={item.kind} title={title} placement={placement.value} frozen={frozen} chars={char_count}")
        return ToolResult.success(call.tool_name, "\n".join(lines))


__all__ = ["ContextStatsTool"]

"""Context Protocol Header

Description:
    Implements ContextUpsertTool — an agent-facing builtin for creating and
    updating managed primitives in the active ContextManager registry.
Purpose:
    Lets agents add or update window-resident context primitives at runtime
    without leaving the agentic loop.
Architecture:
    - ContextUpsertTool: BaseTool that routes to ContextManager.upsert().
Relations:
    Used via vidbyte.tools.builtins.context_primitives. Depends on
    vidbyte.context.manager and vidbyte.context.primitives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_SUPPORTED_TYPES = ("text", "task", "plan", "document", "memory", "progress")


class ContextUpsertTool(BaseTool):
    """Builtin tool that creates or updates a managed primitive in the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores a reference to the live manager shared with AgentRuntime.
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_upsert",
            description=(
                "Create or update a named primitive in the context window. "
                f"Supported types: {', '.join(_SUPPORTED_TYPES)}. "
                "The primitive persists across all future turns."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description="Stable identifier for this primitive, e.g. 'plan:current' or 'file:auth.py'.",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="The text content to store in the primitive.",
                    required=True,
                ),
                ToolParameter(
                    name="primitive_type",
                    type="string",
                    description=f"Primitive kind. One of: {', '.join(_SUPPORTED_TYPES)}. Defaults to 'text'.",
                    required=False,
                    default="text",
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Optional display title shown in the context window.",
                    required=False,
                    default="",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Build the appropriate primitive and upsert it into the manager."""
        args = dict(call.arguments)
        primitive_id = str(args.get("primitive_id", "")).strip()
        content = str(args.get("content", ""))
        primitive_type = str(args.get("primitive_type", "text")).strip().lower()
        title = str(args.get("title", "")).strip()

        if primitive_type not in _SUPPORTED_TYPES:
            return ToolResult.error(
                call.tool_name,
                f"Unknown primitive_type '{primitive_type}'. Supported: {', '.join(_SUPPORTED_TYPES)}.",
            )

        item = self._build_primitive(primitive_id, primitive_type, content, title)
        if item is None:
            return ToolResult.error(call.tool_name, f"Failed to construct primitive of type '{primitive_type}'.")

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(
            call.tool_name,
            f"Primitive '{primitive_id}' (type={primitive_type}) upserted successfully.",
        )

    def _build_primitive(self, primitive_id: str, primitive_type: str, content: str, title: str) -> object | None:
        """Construct the concrete primitive instance for the given type."""
        from vidbyte.context.primitives import (
            DocumentContextItem,
            MemoryContextItem,
            PlanContextItem,
            ProgressContextItem,
            TaskContextItem,
            TextContextItem,
        )
        if primitive_type == "text":
            return TextContextItem(
                primitive_id=primitive_id,
                title=title or "Text",
                content=content,
            )
        if primitive_type == "task":
            return TaskContextItem(
                primitive_id=primitive_id,
                goal=content,
                title=title or "Task",
            )
        if primitive_type == "plan":
            steps = tuple(line.strip() for line in content.splitlines() if line.strip())
            return PlanContextItem(
                primitive_id=primitive_id,
                steps=steps,
                title=title or "Plan",
            )
        if primitive_type == "document":
            return DocumentContextItem(
                primitive_id=primitive_id,
                source="agent",
                content=content,
                title=title or "Document",
            )
        if primitive_type == "memory":
            return MemoryContextItem(
                primitive_id=primitive_id,
                content=content,
                title=title or "Memory",
            )
        if primitive_type == "progress":
            steps = tuple(line.strip() for line in content.splitlines() if line.strip())
            return ProgressContextItem(
                primitive_id=primitive_id,
                next_steps=steps,
                title=title or "Progress",
            )
        return None

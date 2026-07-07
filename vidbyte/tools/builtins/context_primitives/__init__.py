"""Context Protocol Header

Description:
    Exports the context primitive management builtin tools.
Purpose:
    Provides agent-accessible tools for creating, editing, moving, viewing,
    removing, and listing window-resident context primitives at runtime.
Architecture:
    - CreateContextPrimitiveTool: Registry-backed per-primitive create tool.
    - ContextUpsertTool: Creates or updates a managed primitive by id.
    - ContextRemoveTool: Removes a managed primitive by id.
    - ContextListTool: Lists all active managed primitives.
    - ContextViewTool / ContextStatsTool / ContextEditTool / ContextMoveTool:
      Management tools for agent-driven context editing.
Relations:
    Related to vidbyte.context.manager and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.context_primitives.create import CreateContextPrimitiveTool
from vidbyte.tools.builtins.context_primitives.edit import ContextEditTool
from vidbyte.tools.builtins.context_primitives.factory import context_window_tools
from vidbyte.tools.builtins.context_primitives.list_tool import ContextListTool
from vidbyte.tools.builtins.context_primitives.move import ContextMoveTool
from vidbyte.tools.builtins.context_primitives.registry import CREATE_TOOL_REGISTRY, PrimitiveToolDefinition
from vidbyte.tools.builtins.context_primitives.remove import ContextRemoveTool
from vidbyte.tools.builtins.context_primitives.stats import ContextStatsTool
from vidbyte.tools.builtins.context_primitives.upsert import ContextUpsertTool
from vidbyte.tools.builtins.context_primitives.view import ContextViewTool

__all__ = [
    "CREATE_TOOL_REGISTRY",
    "CreateContextPrimitiveTool",
    "ContextEditTool",
    "ContextListTool",
    "ContextMoveTool",
    "ContextRemoveTool",
    "ContextStatsTool",
    "ContextUpsertTool",
    "ContextViewTool",
    "PrimitiveToolDefinition",
    "context_window_tools",
]

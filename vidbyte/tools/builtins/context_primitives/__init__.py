"""Context Protocol Header

Description:
    Exports the context primitive management builtin tools.
Purpose:
    Provides agent-accessible tools for creating, editing, reciting, moving,
    removing, and listing window-resident context primitives at runtime.
Architecture:
    - CreateContextPrimitiveTool: Registry-backed per-primitive create tool.
    - ContextWindowFactory: Class interface for mounting the tool family.
    - ContextUpsertTool: Creates or updates a managed primitive by id.
    - ContextRemoveTool: Removes a managed primitive by id.
    - ContextListTool: Lists all active managed primitives.
    - ContextStatsTool / ContextEditTool / ContextMoveTool / ContextReciteTool:
      Management tools for agent-driven context editing and attention recitation.
Relations:
    Related to vidbyte.context.manager and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.context_primitives.create import CreateContextPrimitiveTool
from vidbyte.tools.builtins.context_primitives.edit import ContextEditTool
from vidbyte.tools.builtins.context_primitives.factory import ContextWindowFactory, context_window_tools
from vidbyte.tools.builtins.context_primitives.list_tool import ContextListTool
from vidbyte.tools.builtins.context_primitives.move import ContextMoveTool
from vidbyte.tools.builtins.context_primitives.recite import ContextReciteTool
from vidbyte.tools.builtins.context_primitives.registry import CREATE_TOOL_REGISTRY, PrimitiveToolDefinition
from vidbyte.tools.builtins.context_primitives.remove import ContextRemoveTool
from vidbyte.tools.builtins.context_primitives.stats import ContextStatsTool
from vidbyte.tools.builtins.context_primitives.upsert import ContextUpsertTool

__all__ = [
    "CREATE_TOOL_REGISTRY",
    "CreateContextPrimitiveTool",
    "ContextEditTool",
    "ContextListTool",
    "ContextMoveTool",
    "ContextReciteTool",
    "ContextRemoveTool",
    "ContextStatsTool",
    "ContextUpsertTool",
    "ContextWindowFactory",
    "PrimitiveToolDefinition",
    "context_window_tools",
]

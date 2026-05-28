"""Context Protocol Header

Description:
    Exports the context primitive management builtin tools.
Purpose:
    Provides agent-accessible tools for creating, updating, removing, and listing
    window-resident context primitives at runtime.
Architecture:
    - ContextUpsertTool: Creates or updates a managed primitive by id.
    - ContextRemoveTool: Removes a managed primitive by id.
    - ContextListTool: Lists all active managed primitives.
Relations:
    Related to vidbyte.context.manager and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.context_primitives.list_tool import ContextListTool
from vidbyte.tools.builtins.context_primitives.remove import ContextRemoveTool
from vidbyte.tools.builtins.context_primitives.upsert import ContextUpsertTool

__all__ = [
    "ContextListTool",
    "ContextRemoveTool",
    "ContextUpsertTool",
]

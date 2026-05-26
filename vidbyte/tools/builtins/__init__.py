"""Context Protocol Header

Description:
    Exports Vidbyte's built-in tool categories.
Purpose:
    Provides convenient imports for safe built-in tools without auto-registering
    environment-specific instances.
Architecture:
    - Code search tools from builtins.code_search.
    - Patch/edit tools from builtins.editing.
    - Context compaction tools from builtins.context.
    - MCP discovery tools from builtins.mcp.
Relations:
    Related to vidbyte.tools.client and vidbyte.tools.registry.
"""

from __future__ import annotations

from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.builtins.context import (
    CompactionMode,
    ContextCompactionTool,
    ContextMessage,
    ProgressLog,
)
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.mcp import AttachMcpServerTool, SearchMcpServersTool

__all__ = [
    "AttachMcpServerTool",
    "CompactionMode",
    "ContextCompactionTool",
    "ContextMessage",
    "GlobTool",
    "GrepTool",
    "PatchTool",
    "ProgressLog",
    "SearchMcpServersTool",
    "SemanticSearchTool",
]

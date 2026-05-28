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
    - Memory provider tools from builtins.memory.
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
from vidbyte.tools.builtins.context_primitives import ContextListTool, ContextRemoveTool, ContextUpsertTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.mcp import AttachMcpServerTool, SearchMcpServersTool
from vidbyte.tools.builtins.memory import (
    CogneeAddTool,
    CogneeCognifyTool,
    CogneeDeleteTool,
    CogneeSearchTool,
    LettaAddArchivalMemoryTool,
    LettaDeleteArchivalMemoryTool,
    LettaGetMemoryBlockTool,
    LettaSearchArchivalMemoryTool,
    Mem0AddMemoryTool,
    Mem0DeleteMemoryTool,
    Mem0GetMemoriesTool,
    Mem0SearchMemoryTool,
    SupermemoryAddMemoryTool,
    SupermemoryDeleteMemoryTool,
    SupermemorySearchMemoryTool,
    ZepAddMemoryTool,
    ZepDeleteSessionTool,
    ZepGetMemoryTool,
    ZepSearchMemoryTool,
)

__all__ = [
    "AttachMcpServerTool",
    "CompactionMode",
    "ContextCompactionTool",
    "ContextListTool",
    "ContextMessage",
    "ContextRemoveTool",
    "ContextUpsertTool",
    "GlobTool",
    "GrepTool",
    "PatchTool",
    "ProgressLog",
    "SearchMcpServersTool",
    "SemanticSearchTool",
    # Memory providers
    "CogneeAddTool",
    "CogneeCognifyTool",
    "CogneeDeleteTool",
    "CogneeSearchTool",
    "LettaAddArchivalMemoryTool",
    "LettaDeleteArchivalMemoryTool",
    "LettaGetMemoryBlockTool",
    "LettaSearchArchivalMemoryTool",
    "Mem0AddMemoryTool",
    "Mem0DeleteMemoryTool",
    "Mem0GetMemoriesTool",
    "Mem0SearchMemoryTool",
    "SupermemoryAddMemoryTool",
    "SupermemoryDeleteMemoryTool",
    "SupermemorySearchMemoryTool",
    "ZepAddMemoryTool",
    "ZepDeleteSessionTool",
    "ZepGetMemoryTool",
    "ZepSearchMemoryTool",
]

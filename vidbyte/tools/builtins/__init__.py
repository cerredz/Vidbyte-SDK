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
    - Context algorithm tools from builtins.trajectory_checkpoint and builtins.reflexion.
Relations:
    Related to vidbyte.tools.client and vidbyte.tools.registry.
"""

from __future__ import annotations

from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.builtins.output_schema import (
    AppendOutputTool,
    DeclareOutputSchemaTool,
    ExtendOutputSchemaTool,
    OutputSchemaBuilder,
    OutputSchemaField,
)
from vidbyte.tools.builtins.reflexion import ReflexionTool
from vidbyte.tools.builtins.trajectory_checkpoint import TrajectoryCheckpointTool
from vidbyte.tools.builtins.context import (
    CompactionMode,
    ContextCompactionTool,
    ContextMessage,
    ProgressLog,
)
from vidbyte.tools.builtins.context_primitives import ContextListTool, ContextRemoveTool, ContextUpsertTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.handoff import CreateHandoffTool
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
    "AppendOutputTool",
    "AttachMcpServerTool",
    "CodeExecutionTool",
    "CreateHandoffTool",
    "CompactionMode",
    "ContextCompactionTool",
    "ContextListTool",
    "ContextMessage",
    "ContextRemoveTool",
    "ContextUpsertTool",
    "DeclareOutputSchemaTool",
    "ExtendOutputSchemaTool",
    "GlobTool",
    "GrepTool",
    "OutputSchemaBuilder",
    "OutputSchemaField",
    "PatchTool",
    "ProgressLog",
    "ReflexionTool",
    "SearchMcpServersTool",
    "SemanticSearchTool",
    "TrajectoryCheckpointTool",
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

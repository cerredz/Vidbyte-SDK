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
    - Context primitive editing tools from builtins.context_primitives.
    - Context algorithm tools from builtins.trajectory_checkpoint and builtins.reflexion.
    - Deep CoT event tools from builtins.cot_events.
    - 182 deep reasoning trace tools from builtins.reasoning.
    - Sequential continuation tool from builtins.run_prompts_sequentially.
    - Cooperative pause tool from builtins.pause.
Relations:
    Related to vidbyte.tools.client and vidbyte.tools.registry.
"""

from __future__ import annotations

from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.builtins.context import (
    CompactionMode,
    ContextCompactionTool,
    ContextMessage,
    ProgressLog,
)
from vidbyte.tools.builtins.context_primitives import (
    CREATE_TOOL_REGISTRY,
    ContextEditTool,
    ContextListTool,
    ContextMoveTool,
    ContextReciteTool,
    ContextRemoveTool,
    ContextStatsTool,
    ContextUpsertTool,
    ContextWindowFactory,
    CreateContextPrimitiveTool,
    PrimitiveToolDefinition,
    context_window_tools,
)
from vidbyte.tools.builtins.cot_events import (
    AssumptionCheckTool,
    BacktrackTool,
    CotEventParser,
    DecisionTool,
    HypothesisTool,
    UncertaintyTool,
)
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.fork import ForkConversationTool
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
from vidbyte.tools.builtins.operations import (
    BraveSearchTool,
    BrowserbaseFetchTool,
    BrowserbaseSearchTool,
    DirectHttpFetchTool,
    ExaSearchTool,
    FirecrawlFetchTool,
    LinkupFetchTool,
    LinkupSearchTool,
    OpenAlexSearchTool,
    ParallelExtractTool,
    ParallelSearchTool,
    PricedOperationTool,
    SemanticScholarSearchTool,
    TavilyExtractTool,
    TavilySearchTool,
)
from vidbyte.tools.builtins.output_schema import (
    AppendOutputTool,
    DeclareOutputSchemaTool,
    ExtendOutputSchemaTool,
    OutputSchemaBuilder,
    OutputSchemaField,
)
from vidbyte.tools.builtins.pause import PauseAgentTool
from vidbyte.tools.builtins.providers import (
    MongoCreateCollectionTool,
    MongoCreateIndexTool,
    MongoDeleteDocumentsTool,
    MongoFindDocumentsTool,
    MongoInsertDocumentTool,
    MongoUpdateDocumentsTool,
    ProviderCreateSchemaTool,
    ProviderCreateTableTool,
    ProviderDeleteRowsTool,
    ProviderInsertRowTool,
    ProviderSelectRowsTool,
    ProviderUpdateRowsTool,
)
from vidbyte.tools.builtins.reasoning import (
    REASONING_TRACE_DEFINITIONS,
    REASONING_TRACE_TOOL_CLASSES,
    ReasoningTraceCatalog,
    ReasoningTraceDefinition,
    ReasoningTraceTool,
)
from vidbyte.tools.builtins.reflexion import ReflexionTool
from vidbyte.tools.builtins.run_prompts_sequentially import RunPromptsSequentiallyTool
from vidbyte.tools.builtins.sessions import (
    BatchForkTool,
    CheckpointTool,
    ForkTool,
    ResumeAppendTool,
    ResumeOutputTool,
    ResumeReplaceTool,
    RewindTool,
    SessionTool,
)
from vidbyte.tools.builtins.trajectory_checkpoint import TrajectoryCheckpointTool

for _reasoning_trace_class in REASONING_TRACE_TOOL_CLASSES.values():
    globals()[_reasoning_trace_class.__name__] = _reasoning_trace_class

__all__ = [
    "CREATE_TOOL_REGISTRY",
    "REASONING_TRACE_DEFINITIONS",
    "REASONING_TRACE_TOOL_CLASSES",
    "AppendOutputTool",
    "AssumptionCheckTool",
    "AttachMcpServerTool",
    "BacktrackTool",
    "BatchForkTool",
    "BraveSearchTool",
    "BrowserbaseFetchTool",
    "BrowserbaseSearchTool",
    "CheckpointTool",
    "CodeExecutionTool",
    # Memory providers
    "CogneeAddTool",
    "CogneeCognifyTool",
    "CogneeDeleteTool",
    "CogneeSearchTool",
    "CompactionMode",
    "ContextCompactionTool",
    "ContextEditTool",
    "ContextListTool",
    "ContextMessage",
    "ContextMoveTool",
    "ContextReciteTool",
    "ContextRemoveTool",
    "ContextStatsTool",
    "ContextUpsertTool",
    "ContextWindowFactory",
    "CotEventParser",
    "CreateContextPrimitiveTool",
    "CreateHandoffTool",
    "DecisionTool",
    "DeclareOutputSchemaTool",
    "DirectHttpFetchTool",
    "ExaSearchTool",
    "ExtendOutputSchemaTool",
    "FirecrawlFetchTool",
    "ForkConversationTool",
    "ForkTool",
    "GlobTool",
    "GrepTool",
    "HypothesisTool",
    "LettaAddArchivalMemoryTool",
    "LettaDeleteArchivalMemoryTool",
    "LettaGetMemoryBlockTool",
    "LettaSearchArchivalMemoryTool",
    "LinkupFetchTool",
    "LinkupSearchTool",
    "Mem0AddMemoryTool",
    "Mem0DeleteMemoryTool",
    "Mem0GetMemoriesTool",
    "Mem0SearchMemoryTool",
    "MongoCreateCollectionTool",
    "MongoCreateIndexTool",
    "MongoDeleteDocumentsTool",
    "MongoFindDocumentsTool",
    "MongoInsertDocumentTool",
    "MongoUpdateDocumentsTool",
    "OpenAlexSearchTool",
    "OutputSchemaBuilder",
    "OutputSchemaField",
    "ParallelExtractTool",
    "ParallelSearchTool",
    "PatchTool",
    "PauseAgentTool",
    "PricedOperationTool",
    "PrimitiveToolDefinition",
    "ProgressLog",
    "ProviderCreateSchemaTool",
    "ProviderCreateTableTool",
    "ProviderDeleteRowsTool",
    "ProviderInsertRowTool",
    "ProviderSelectRowsTool",
    "ProviderUpdateRowsTool",
    "ReasoningTraceCatalog",
    "ReasoningTraceDefinition",
    "ReasoningTraceTool",
    "ReflexionTool",
    "ResumeAppendTool",
    "ResumeOutputTool",
    "ResumeReplaceTool",
    "RewindTool",
    "RunPromptsSequentiallyTool",
    "SearchMcpServersTool",
    "SemanticScholarSearchTool",
    "SemanticSearchTool",
    "SessionTool",
    "SupermemoryAddMemoryTool",
    "SupermemoryDeleteMemoryTool",
    "SupermemorySearchMemoryTool",
    "TavilyExtractTool",
    "TavilySearchTool",
    "TrajectoryCheckpointTool",
    "UncertaintyTool",
    "ZepAddMemoryTool",
    "ZepDeleteSessionTool",
    "ZepGetMemoryTool",
    "ZepSearchMemoryTool",
    "context_window_tools",
]

__all__.extend(
    (
        *(_reasoning_trace_class.__name__ for _reasoning_trace_class in REASONING_TRACE_TOOL_CLASSES.values()),
    )
)

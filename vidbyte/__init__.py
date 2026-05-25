"""Context Protocol Header

Description:
    Exports the root Vidbyte SDK client and top-level public tool, agent, context, and strategy contracts.
Purpose:
    Keeps common SDK imports concise while leaving specialized built-in tools in
    their category packages.
Architecture:
    - VidbyteSDK: Root namespace client.
    - Agent exports: BaseAgent, AgentCard, AgentMessage, AgentRegistry, AgentRunnerConfig, AgentSpec.
    - Tool exports: BaseTool, ToolCall, ToolExecutor, ToolParameter, ToolPermission, ToolRegistry, ToolResult, ToolSpec, ToolStatus, ToolsFormatter.
    - MCP exports: McpServerConfig, McpServerHandle, McpToolPermission.
    - Context exports: BaseAgentContext, BaseContext, ContextBudget, ContextPermissions.
    - Preset exports: BudgetPreset, PermissionPreset.
    - Strategy exports: BaseStrategy, StrategyContext, StrategyResult.
    - Pipeline exports: BasePipeline, ConditionalPipeline, ParallelPipeline, PipelineNode, SequentialPipeline.
    - Error exports: McpError, McpConnectionError, McpInitializeError, McpToolDiscoveryError, McpToolExecutionError, McpAttachmentError, PipelineExecutionError.
Relations:
    Related to vidbyte.client, vidbyte.agents, vidbyte.tools, vidbyte.context, vidbyte.strategies, and vidbyte.pipelines.
"""

from __future__ import annotations

from vidbyte.agents import (
    Agent,
    AgentClient,
    AgentCard,
    AgentInput,
    AgentMessage,
    AgentRegistry,
    AgentRunnerConfig,
    AgentRuntimeConfig,
    AgentRuntimeStats,
    AgentSpec,
    AgentStopReason,
    BaseAgent,
)
from vidbyte.client import VidbyteSDK
from vidbyte.context import (
    ArtifactContextItem,
    BaseAgentContext,
    BaseContext,
    ContextBudget,
    ContextItem,
    ContextManager,
    ContextPermissions,
    ContextWindow,
    ContextWindowAlgorithm,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
    ToolResultAdmission,
)
from vidbyte.lib.enums import BudgetPreset, ModelModality, PermissionPreset, Prompt
from vidbyte.lib.errors import (
    McpAttachmentError,
    McpConnectionError,
    McpError,
    McpInitializeError,
    McpToolDiscoveryError,
    McpToolExecutionError,
    PipelineExecutionError,
)
from vidbyte.middleware import (
    AgentMiddleware,
    AuditLogMiddleware,
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
    MiddlewarePipeline,
    ModelRetryMiddleware,
    RuntimeLimitMiddleware,
    TokenRateLimitMiddleware,
    ToolPolicyMiddleware,
)
from vidbyte.pipelines import (
    BasePipeline,
    ConditionalPipeline,
    MapReducePipeline,
    ParallelPipeline,
    PipelineNode,
    SequentialPipeline,
)
from vidbyte.prompts import Prompts
from vidbyte.strategies import (
    BaseStrategy,
    BaseStrategyUtils,
    ChainOfDraftStrategy,
    ChainOfThoughtStrategy,
    PlanAndExecuteStrategy,
    ReActStrategy,
    ReflexionStrategy,
    SelfConsistencyStrategy,
    SelfRefinementStrategy,
    SkeletonOfThoughtStrategy,
    StepBackStrategy,
    StrategyContext,
    StrategyResult,
    TreeOfThoughtsStrategy,
)
from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy
from vidbyte.tools import (
    BaseTool,
    FunctionTool,
    ToolCall,
    ToolCallContext,
    ToolCallState,
    ToolExecutor,
    ToolMixin,
    ToolParameter,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolStatus,
    Tools,
    ToolsFormatter,
    tool,
    vidbyte_tool,
)
from vidbyte.tools.mcp import (
    McpServerConfig,
    McpServerHandle,
    McpToolPermission,
)

__all__ = [
    "Agent",
    "AgentCard",
    "AgentClient",
    "AgentInput",
    "AgentMiddleware",
    "AuditLogMiddleware",
    "AgentMessage",
    "AgentRegistry",
    "AgentRunnerConfig",
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentSpec",
    "AgentStopReason",
    "ArtifactContextItem",
    "BaseAgent",
    "BaseAgentContext",
    "BaseContext",
    "BasePipeline",
    "BaseStrategy",
    "BaseStrategyUtils",
    "BaseTool",
    "BudgetPreset",
    "ChainOfDraftStrategy",
    "ChainOfThoughtStrategy",
    "ContextBudget",
    "ContextItem",
    "ContextManager",
    "ContextPermissions",
    "ContextWindow",
    "ContextWindowAlgorithm",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "MemoryContextItem",
    "McpAttachmentError",
    "McpConnectionError",
    "McpError",
    "McpInitializeError",
    "McpServerConfig",
    "McpServerHandle",
    "McpToolDiscoveryError",
    "McpToolExecutionError",
    "McpToolPermission",
    "MiddlewareAction",
    "MiddlewareContext",
    "MiddlewareDecision",
    "MiddlewareEvent",
    "MiddlewareHook",
    "MiddlewarePipeline",
    "ModelRetryMiddleware",
    "MultiAgentConsensusStrategy",
    "ConditionalPipeline",
    "MapReducePipeline",
    "ModelModality",
    "ParallelPipeline",
    "PermissionPreset",
    "PipelineExecutionError",
    "PipelineNode",
    "PlanAndExecuteStrategy",
    "ProgressContextItem",
    "Prompt",
    "Prompts",
    "ReActStrategy",
    "ReflexionStrategy",
    "ResponseContextItem",
    "RuntimeLimitMiddleware",
    "SelfConsistencyStrategy",
    "SelfRefinementStrategy",
    "SkeletonOfThoughtStrategy",
    "StepBackStrategy",
    "StrategyContext",
    "SequentialPipeline",
    "StrategyResult",
    "TaskContextItem",
    "TextContextItem",
    "ToolCall",
    "ToolCallContext",
    "ToolCallContextItem",
    "ToolCallState",
    "ToolResultAdmission",
    "ToolExecutor",
    "ToolParameter",
    "ToolPermission",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "TokenRateLimitMiddleware",
    "ToolPolicyMiddleware",
    "Tools",
    "ToolsFormatter",
    "TreeOfThoughtsStrategy",
    "VidbyteSDK",
    "tool",
    "vidbyte_tool",
]

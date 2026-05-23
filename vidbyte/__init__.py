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
    - Error exports: McpError, McpConnectionError, McpInitializeError, McpToolDiscoveryError, McpToolExecutionError, McpAttachmentError.
Relations:
    Related to vidbyte.client, vidbyte.agents, vidbyte.tools, vidbyte.context, and vidbyte.strategies.
"""

from __future__ import annotations

from vidbyte.agents import (
    AgentCard,
    AgentMessage,
    AgentRegistry,
    AgentRunnerConfig,
    AgentSpec,
    BaseAgent,
)
from vidbyte.client import VidbyteSDK
from vidbyte.context import BaseAgentContext, BaseContext, ContextBudget, ContextPermissions
from vidbyte.lib.enums import BudgetPreset, PermissionPreset, Prompt
from vidbyte.lib.errors import (
    McpAttachmentError,
    McpConnectionError,
    McpError,
    McpInitializeError,
    McpToolDiscoveryError,
    McpToolExecutionError,
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
    ToolExecutor,
    ToolMixin,
    ToolParameter,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolStatus,
    ToolsFormatter,
    vidbyte_tool,
)
from vidbyte.tools.mcp import (
    McpServerConfig,
    McpServerHandle,
    McpToolPermission,
)

__all__ = [
    "AgentCard",
    "AgentMessage",
    "AgentRegistry",
    "AgentRunnerConfig",
    "AgentSpec",
    "BaseAgent",
    "BaseAgentContext",
    "BaseContext",
    "BaseStrategy",
    "BaseStrategyUtils",
    "BaseTool",
    "BudgetPreset",
    "ChainOfDraftStrategy",
    "ChainOfThoughtStrategy",
    "ContextBudget",
    "ContextPermissions",
    "McpAttachmentError",
    "McpConnectionError",
    "McpError",
    "McpInitializeError",
    "McpServerConfig",
    "McpServerHandle",
    "McpToolDiscoveryError",
    "McpToolExecutionError",
    "McpToolPermission",
    "MultiAgentConsensusStrategy",
    "PermissionPreset",
    "PlanAndExecuteStrategy",
    "Prompt",
    "Prompts",
    "ReActStrategy",
    "ReflexionStrategy",
    "SelfConsistencyStrategy",
    "SelfRefinementStrategy",
    "SkeletonOfThoughtStrategy",
    "StepBackStrategy",
    "StrategyContext",
    "StrategyResult",
    "ToolCall",
    "ToolExecutor",
    "ToolParameter",
    "ToolPermission",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "ToolsFormatter",
    "TreeOfThoughtsStrategy",
    "VidbyteSDK",
]

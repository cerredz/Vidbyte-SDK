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
    - Context exports: BaseContext, ContextBudget, ContextPermissions.
    - Preset exports: BudgetPreset, PermissionPreset.
    - Strategy exports: BaseStrategy, StrategyContext, StrategyResult.
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
from vidbyte.context import BaseContext, ContextBudget, ContextPermissions
from vidbyte.lib.enums import BudgetPreset, PermissionPreset
from vidbyte.strategies import BaseStrategy, StrategyContext, StrategyResult
from vidbyte.tools import (
    BaseTool,
    ToolCall,
    ToolExecutor,
    ToolParameter,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolStatus,
    ToolsFormatter,
)

__all__ = [
    "AgentCard",
    "AgentMessage",
    "AgentRegistry",
    "AgentRunnerConfig",
    "AgentSpec",
    "BaseAgent",
    "BaseContext",
    "BaseStrategy",
    "BaseTool",
    "BudgetPreset",
    "ContextBudget",
    "ContextPermissions",
    "PermissionPreset",
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
    "VidbyteSDK",
]

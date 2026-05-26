"""Context Protocol Header

Description:
    Exports SDK dataclass contracts from the central Vidbyte lib namespace.
Purpose:
    Keeps reusable immutable data contracts in one package while feature
    packages provide compatibility import shims.
Architecture:
    - Tool contracts from tools.
    - Context, MCP, security, sandbox, multi-agent, and strategies contracts.
Relations:
    Related to vidbyte.tools, vidbyte.agents, and vidbyte.strategies.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.agents import (
    AgentCard,
    AgentMessage,
    AgentRunnerConfig,
    AgentRuntimeConfig,
    AgentRuntimeStats,
    AgentSpec,
    AgentStopReason,
)
from vidbyte.lib.dataclasses.context import (
    BaseAgentContext,
    BaseContext,
    ContextArtifact,
    ContextBudget,
    ContextMessage,
    ContextPermissions,
    ContextResponse,
    ContextState,
    ContextToolCall,
    ProgressLog,
    StrategyContext,
    VMAOContext,
)
from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    ContextPrimitive,
    ContextPrimitivePlacement,
    ContextPrimitiveVisibility,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    IdentityContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.context.updates import ContextPrimitiveUpdate, ContextPrimitiveUpdateAction
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
)
from vidbyte.lib.dataclasses.tool_types import FileStat
from vidbyte.lib.dataclasses.multi_agent import CandidateFailure, CandidateResult, DagNode, EvaluationDecision, NodeState, Verification
from vidbyte.lib.dataclasses.sandbox import SandboxRequest, SandboxResult, SandboxTransport
from vidbyte.lib.dataclasses.security import PermissionDecision, PermissionPolicy
from vidbyte.lib.dataclasses.strategies import StrategyResult
from vidbyte.lib.dataclasses.tools import (
    ToolCall,
    ToolCallContext,
    ToolCallState,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "AgentCard",
    "AgentMessage",
    "AgentRunnerConfig",
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentSpec",
    "AgentStopReason",
    "ArtifactContextItem",
    "BaseAgentContext",
    "BaseContext",
    "CandidateFailure",
    "CandidateResult",
    "ContextArtifact",
    "ContextBudget",
    "ContextItem",
    "ContextMessage",
    "ContextPermissions",
    "ContextPrimitive",
    "ContextPrimitivePlacement",
    "ContextPrimitiveUpdate",
    "ContextPrimitiveUpdateAction",
    "ContextPrimitiveVisibility",
    "ContextResponse",
    "ContextState",
    "ContextToolCall",
    "DagNode",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "EvaluationDecision",
    "FileContextItem",
    "FileStat",
    "FileSystemToolConfig",
    "GitDiffContextItem",
    "IdentityContextItem",
    "MemoryContextItem",
    "McpToolDefinition",
    "MiddlewareAction",
    "MiddlewareContext",
    "MiddlewareDecision",
    "MiddlewareEvent",
    "MiddlewareHook",
    "NodeState",
    "PermissionDecision",
    "PermissionPolicy",
    "PlanContextItem",
    "ProgressContextItem",
    "ProgressLog",
    "ResponseContextItem",
    "SandboxRequest",
    "SandboxResult",
    "SandboxTransport",
    "StrategyContext",
    "StrategyResult",
    "TaskContextItem",
    "TextContextItem",
    "ToolCall",
    "ToolCallContext",
    "ToolCallState",
    "ToolCallContextItem",
    "ToolParameter",
    "ToolPermission",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "Verification",
    "VMAOContext",
]

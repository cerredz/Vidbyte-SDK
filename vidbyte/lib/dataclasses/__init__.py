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

from vidbyte.lib.dataclasses.agents import AgentCard, AgentMessage, AgentRunnerConfig, AgentSpec, AgentRole
from vidbyte.lib.dataclasses.context import (
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
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.dataclasses.model_configs import TextModelConfig
from vidbyte.lib.dataclasses.multi_agent import CandidateFailure, CandidateResult, DagNode, EvaluationDecision, NodeState, Verification
from vidbyte.lib.dataclasses.sandbox import SandboxRequest, SandboxResult, SandboxTransport
from vidbyte.lib.dataclasses.security import PermissionDecision, PermissionPolicy
from vidbyte.lib.dataclasses.strategies import StrategyResult
from vidbyte.lib.dataclasses.tools import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "AgentCard",
    "AgentMessage",
    "AgentRole",
    "AgentRunnerConfig",
    "AgentSpec",
    "BaseContext",
    "CandidateFailure",
    "CandidateResult",
    "ContextArtifact",
    "ContextBudget",
    "ContextMessage",
    "ContextPermissions",
    "ContextResponse",
    "ContextState",
    "ContextToolCall",
    "DagNode",
    "EvaluationDecision",
    "FileSystemToolConfig",
    "McpToolDefinition",
    "NodeState",
    "PermissionDecision",
    "PermissionPolicy",
    "ProgressLog",
    "SandboxRequest",
    "SandboxResult",
    "SandboxTransport",
    "StrategyContext",
    "StrategyResult",
    "TextModelConfig",
    "ToolCall",
    "ToolParameter",
    "ToolPermission",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "Verification",
    "VMAOContext",
]

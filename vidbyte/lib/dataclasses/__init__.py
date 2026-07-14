"""Context Protocol Header

Description:
    Exports SDK dataclass contracts from the central Vidbyte lib namespace.
Purpose:
    Keeps reusable immutable data contracts in one package while feature
    packages provide compatibility import shims.
Architecture:
    - Tool contracts from tools.
    - Context, MCP, security, sandbox, and multi-agent contracts.
    - Harness specification, run manifest, and trajectory-record contracts.
Relations:
    Related to vidbyte.tools, vidbyte.agents, and vidbyte.harnesses.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.agents import (
    AgentCard,
    AgentIterationSnapshot,
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
)
from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
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
    TrajectoryCheckpointContextItem,
)
from vidbyte.lib.dataclasses.filesystem import FileStat, FileSystemToolConfig
from vidbyte.lib.dataclasses.harnesses import (
    HARNESS_SCHEMA_VERSION,
    HarnessExecutionResult,
    HarnessRun,
    HarnessRunStatus,
    HarnessSpec,
    TrajectoryRecord,
)
from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
    MiddlewareTransform,
)
from vidbyte.lib.dataclasses.multi_agent import CandidateFailure, CandidateResult, DagNode, EvaluationDecision, NodeState, Verification
from vidbyte.lib.dataclasses.sandbox import SandboxRequest, SandboxResult, SandboxTransport
from vidbyte.lib.dataclasses.security import PermissionDecision, PermissionPolicy
from vidbyte.lib.dataclasses.sessions import (
    SESSION_SCHEMA_VERSION,
    AgentUsage,
    Checkpoint,
    CheckpointPolicy,
    RunState,
    SessionMeta,
    SessionStatus,
    TraceCapture,
    UsageRollup,
)
from vidbyte.lib.dataclasses.sources import (
    ArtifactRef,
    FetchResponse,
    LlmsTxtDocument,
    LlmsTxtLink,
    LlmsTxtSection,
    MarkdownDocument,
    Selection,
    SourceResult,
    SourceSnapshot,
)
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.trace import (
    TraceField,
    TraceFieldType,
    TraceMode,
    TraceOption,
    TraceSchema,
)
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
    "AgentIterationSnapshot",
    "AgentMessage",
    "AgentResult",
    "AgentRunnerConfig",
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentSpec",
    "AgentStopReason",
    "AgentUsage",
    "ArtifactRef",
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
    "ContextResponse",
    "ContextState",
    "ContextToolCall",
    "DagNode",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "EvaluationDecision",
    "FileContextItem",
    "FileStat",
    "FetchResponse",
    "FileSystemToolConfig",
    "GitDiffContextItem",
    "HARNESS_SCHEMA_VERSION",
    "HarnessExecutionResult",
    "HarnessRun",
    "HarnessRunStatus",
    "HarnessSpec",
    "TrajectoryRecord",
    "MemoryContextItem",
    "McpToolDefinition",
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtSection",
    "MarkdownDocument",
    "MiddlewareAction",
    "MiddlewareContext",
    "MiddlewareDecision",
    "MiddlewareEvent",
    "MiddlewareHook",
    "MiddlewareTransform",
    "NodeState",
    "PermissionDecision",
    "PermissionPolicy",
    "ProgressContextItem",
    "ProgressLog",
    "ResponseContextItem",
    "RunnerHandle",
    "SESSION_SCHEMA_VERSION",
    "SandboxRequest",
    "SandboxResult",
    "SandboxTransport",
    "Selection",
    "Checkpoint",
    "CheckpointPolicy",
    "RunState",
    "SessionMeta",
    "SessionStatus",
    "SourceResult",
    "SourceSnapshot",
    "TaskContextItem",
    "TextContextItem",
    "ToolCall",
    "ToolCallContext",
    "ToolCallState",
    "ToolCallContextItem",
    "TrajectoryCheckpointContextItem",
    "ToolParameter",
    "ToolPermission",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "TraceField",
    "TraceFieldType",
    "TraceMode",
    "TraceOption",
    "TraceCapture",
    "TraceSchema",
    "UsageRollup",
    "Verification",
]

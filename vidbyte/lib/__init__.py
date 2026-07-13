"""Context Protocol Header

Description:
    Re-exports central Vidbyte dataclasses, enums, errors, registries, runners, tools, and tracing protocols.
Purpose:
    Provides a stable internal/public contract boundary without moving feature implementations into `vidbyte.lib`.
Architecture:
    Imports shared contracts from focused subpackages, including multi-agent ledger, dispatch, report, and stop-state types.
Relations:
    Consumed by the root `vidbyte` namespace and feature packages throughout the SDK.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses import (
    AgentCard,
    AgentDispatch,
    AgentMessage,
    AgentReport,
    AgentRunnerConfig,
    AgentSpec,
    BaseAgentContext,
    BaseContext,
    CandidateFailure,
    CandidateResult,
    ContextArtifact,
    ContextBudget,
    ContextPermissions,
    ContextResponse,
    ContextToolCall,
    DagNode,
    EvaluationDecision,
    FinalizationContext,
    LedgerEvent,
    MultiAgentResult,
    MultiAgentSettings,
    NodeState,
    OrchestrationContext,
    OrchestratorDecision,
    OrchestratorPlan,
    TaskBlocker,
    TaskEvidence,
    TaskLedgerSnapshot,
    TaskRecord,
    TaskSpec,
    ToolSpec,
    Verification,
)
from vidbyte.lib.enums import BudgetPreset, MultiAgentStopReason, OrchestratorAction, PermissionPreset, TaskStatus

__all__ = [
    "AgentCard",
    "AgentDispatch",
    "AgentMessage",
    "AgentReport",
    "AgentRunnerConfig",
    "AgentSpec",
    "BaseAgentContext",
    "BaseContext",
    "BudgetPreset",
    "CandidateFailure",
    "CandidateResult",
    "ContextArtifact",
    "ContextBudget",
    "ContextPermissions",
    "ContextResponse",
    "ContextToolCall",
    "DagNode",
    "EvaluationDecision",
    "FinalizationContext",
    "LedgerEvent",
    "MultiAgentResult",
    "MultiAgentSettings",
    "MultiAgentStopReason",
    "NodeState",
    "OrchestrationContext",
    "OrchestratorAction",
    "OrchestratorDecision",
    "OrchestratorPlan",
    "PermissionPreset",
    "TaskBlocker",
    "TaskEvidence",
    "TaskLedgerSnapshot",
    "TaskRecord",
    "TaskSpec",
    "TaskStatus",
    "ToolSpec",
    "Verification",
]

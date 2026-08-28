"""Context Protocol Header

Description:
    Exposes agents, execution runtimes, aggregate actors, and ledger-driven team orchestration for Vidbyte SDK.
Purpose:
    Allows easy package-level import of BaseAgent, registries, client schemas,
    swappable execution runtimes, and multi-agent ledger/transfer contracts.
Architecture:
    - BaseAgent: Client-facing agent coordinator.
    - AgentRegistry: Local/shared memory storage registry.
    - Swappable Runtimes: LinearAgentRuntime, SearchTreeRuntimeComponent, PointToPointActorRuntime, BroadcastActorRuntime.
    - Multi-Agent Team: MultiAgent, MagenticOneOrchestrator, TaskLedger, AgentBinding, and AgentTransfer.
Relations:
    Imported by the root SDK client, evaluator harnesses, and user applications.
Similar Files:
    - vidbyte/agents/base.py: Agent controller core.
"""

from __future__ import annotations

from vidbyte.agents.aggregation import (
    AggregateAgent,
    AggregateResult,
    MultiProviderAggregator,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.client import AgentClient
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.continual_trace import ContinualTraceAgent
from vidbyte.agents.contracts import (
    MinCompactions,
    MinCostSpent,
    MinDistinctTools,
    MinElapsedSeconds,
    MinFinalOutputChars,
    MinFinalOutputTokens,
    MinIterations,
    MinSuccessfulToolCalls,
    MinTimeTaken,
    MinTokens,
    MinToolCalls,
    MinToolCallsById,
    OutputContract,
)
from vidbyte.agents.fallback import (
    AgentFallback,
    AgentFallbackConfig,
    CostBudgetPolicy,
    FallbackTransform,
    LatencyPolicy,
)
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.agents.multi import (
    AgentBinding,
    AgentDispatch,
    AgentReport,
    AgentTransfer,
    FinalizationContext,
    LedgerEvent,
    MagenticOneOrchestrator,
    MultiAgent,
    MultiAgentOrchestrator,
    MultiAgentResult,
    MultiAgentSettings,
    MultiAgentStopReason,
    OrchestrationContext,
    OrchestratorAction,
    OrchestratorDecision,
    OrchestratorPlan,
    TaskBlocker,
    TaskEvidence,
    TaskLedger,
    TaskLedgerSnapshot,
    TaskRecord,
    TaskSpec,
    TaskStatus,
)
from vidbyte.agents.pricing import ProviderUsage, UsageRecord, UsageRollup, UsageTracker
from vidbyte.agents.runtimes import (
    ActorRuntime,
    BroadcastActorRuntime,
    LinearRuntime,
    MctsSearchRuntime,
    PointToPointActorRuntime,
    SearchTreeRuntimeComponent,
)
from vidbyte.agents.runtimes import (
    LinearAgentRuntime as AgentRuntime,
)
from vidbyte.agents.settings import (
    AgentFallbackSettings,
    AgentLoopSettings,
    ToolErrorPolicy,
    ToolSettings,
    UnrecoverableAction,
)
from vidbyte.agents.types import (
    AgentCard,
    AgentForkSettings,
    AgentInput,
    AgentMessage,
    AgentSpec,
)
from vidbyte.lib.dataclasses.agents import (
    AgentRunnerConfig,
    AgentRuntimeConfig,
    AgentRuntimeStats,
    AgentStopReason,
    FallbackModel,
)
from vidbyte.lib.dataclasses.multi_agent import AggregateConfig, ProposerSpec
from vidbyte.lib.registries import AgentRegistry

Agent = BaseAgent

__all__ = [
    "ActorRuntime",
    "Agent",
    "AgentBinding",
    "AgentCard",
    "AgentClient",
    "AgentDispatch",
    "AgentFallback",
    "AgentFallbackConfig",
    "AgentFallbackSettings",
    "AgentForkSettings",
    "AgentInput",
    "AgentLoopSettings",
    "AgentMessage",
    "AgentRegistry",
    "AgentReport",
    "AgentRunnerConfig",
    "AgentRuntime",
    "AgentRuntimeConfig",
    "AgentRuntimeContextAlgorithms",
    "AgentRuntimeStats",
    "AgentSpec",
    "AgentStopReason",
    "AgentTransfer",
    "AggregateAgent",
    "AggregateConfig",
    "AggregateResult",
    "BaseAgent",
    "BroadcastActorRuntime",
    "ContinualTraceAgent",
    "CostBudgetPolicy",
    "FallbackModel",
    "FallbackTransform",
    "FinalizationContext",
    "HandoffAgent",
    "LatencyPolicy",
    "LedgerEvent",
    "LinearRuntime",
    "MagenticOneOrchestrator",
    "MctsSearchRuntime",
    "MinCompactions",
    "MinCostSpent",
    "MinDistinctTools",
    "MinElapsedSeconds",
    "MinFinalOutputChars",
    "MinFinalOutputTokens",
    "MinIterations",
    "MinSuccessfulToolCalls",
    "MinTimeTaken",
    "MinTokens",
    "MinToolCalls",
    "MinToolCallsById",
    "MultiAgent",
    "MultiAgentOrchestrator",
    "MultiAgentResult",
    "MultiAgentSettings",
    "MultiAgentStopReason",
    "MultiProviderAggregator",
    "OrchestrationContext",
    "OrchestratorAction",
    "OrchestratorDecision",
    "OrchestratorPlan",
    "OutputContract",
    "PointToPointActorRuntime",
    "ProposerSpec",
    "ProviderUsage",
    "SearchTreeRuntimeComponent",
    "TaskBlocker",
    "TaskEvidence",
    "TaskLedger",
    "TaskLedgerSnapshot",
    "TaskRecord",
    "TaskSpec",
    "TaskStatus",
    "ToolErrorPolicy",
    "ToolSettings",
    "UnrecoverableAction",
    "UsageRecord",
    "UsageRollup",
    "UsageTracker",
]

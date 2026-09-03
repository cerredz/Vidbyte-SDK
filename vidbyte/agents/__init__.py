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

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.aggregation import AggregateAgent, AggregateResult, MultiProviderAggregator
from vidbyte.agents.client import AgentClient
from vidbyte.agents.fallback import AgentFallback, FallbackTransform
from vidbyte.agents.continual_trace import ContinualTraceAgent
from vidbyte.agents.settings import AgentFallbackSettings, AgentLoopSettings, ToolErrorPolicy, ToolSettings, UnrecoverableAction
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
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.pricing import ProviderUsage, UsageRecord, UsageRollup, UsageTracker
from vidbyte.agents.speed import (
    AgentSpeedHistory,
    AgentSpeedRollup,
    AgentSpeedTracker,
    CallSpeedRecord,
    CallSpeedStats,
    ModelSpeedStats,
    RecordModelCallFailureInput,
    RecordModelCallInput,
    RecordRetryWaitInput,
    RecordStepInput,
    RecordStreamInput,
    RecordToolCallInput,
    RetryWaitSpeedRecord,
    RunSpeedSnapshot,
    RunSpeedStats,
    StepSpeedRecord,
    StepSpeedStats,
    StreamSpeedRecord,
    StreamSpeedStats,
    ToolCallSpeedRecord,
    ToolCallSpeedStats,
    ToolSpeedStats,
)
from vidbyte.lib.dataclasses.multi_agent import AggregateConfig, ProposerSpec
from vidbyte.lib.registries import AgentRegistry
from vidbyte.agents.runtimes import (
    LinearAgentRuntime as AgentRuntime,
    SearchTreeRuntimeComponent,
    PointToPointActorRuntime,
    BroadcastActorRuntime,
    LinearRuntime,
    MctsSearchRuntime,
    ActorRuntime,
)
from vidbyte.lib.dataclasses.agents import (
    AgentRunnerConfig,
    AgentRuntimeConfig,
    AgentRuntimeStats,
    AgentStopReason,
    FallbackModel,
)
from vidbyte.agents.types import AgentCard, AgentForkSettings, AgentInput, AgentMessage, AgentSpec

Agent = BaseAgent

__all__ = [
    "Agent",
    "AgentBinding",
    "AgentDispatch",
    "AgentReport",
    "AgentTransfer",
    "FinalizationContext",
    "LedgerEvent",
    "AggregateAgent",
    "AggregateConfig",
    "AggregateResult",
    "AgentClient",
    "AgentFallback",
    "AgentFallbackSettings",
    "AgentLoopSettings",
    "FallbackModel",
    "FallbackTransform",
    "ToolErrorPolicy",
    "ToolSettings",
    "UnrecoverableAction",
    "OutputContract",
    "MinToolCalls",
    "MinTokens",
    "MinIterations",
    "MinElapsedSeconds",
    "MinTimeTaken",
    "MinSuccessfulToolCalls",
    "MinDistinctTools",
    "MinFinalOutputChars",
    "MinFinalOutputTokens",
    "MinToolCallsById",
    "MinCompactions",
    "MinCostSpent",
    "AgentCard",
    "AgentForkSettings",
    "AgentInput",
    "AgentMessage",
    "MultiProviderAggregator",
    "ProposerSpec",
    "AgentRunnerConfig",
    "AgentRuntimeContextAlgorithms",
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentRegistry",
    "AgentSpec",
    "AgentStopReason",
    "BaseAgent",
    "ContinualTraceAgent",
    "HandoffAgent",
    "MagenticOneOrchestrator",
    "MultiAgent",
    "MultiAgentOrchestrator",
    "MultiAgentResult",
    "MultiAgentSettings",
    "MultiAgentStopReason",
    "OrchestrationContext",
    "OrchestratorAction",
    "OrchestratorDecision",
    "OrchestratorPlan",
    "TaskBlocker",
    "TaskEvidence",
    "TaskLedger",
    "TaskLedgerSnapshot",
    "TaskRecord",
    "TaskSpec",
    "TaskStatus",
    "AgentRuntime",
    "AgentSpeedRollup",
    "AgentSpeedHistory",
    "AgentSpeedTracker",
    "CallSpeedRecord",
    "CallSpeedStats",
    "ModelSpeedStats",
    "RecordModelCallFailureInput",
    "RecordModelCallInput",
    "RecordRetryWaitInput",
    "RecordStepInput",
    "RecordStreamInput",
    "RecordToolCallInput",
    "RetryWaitSpeedRecord",
    "RunSpeedSnapshot",
    "RunSpeedStats",
    "StepSpeedRecord",
    "StepSpeedStats",
    "StreamSpeedRecord",
    "StreamSpeedStats",
    "ToolCallSpeedRecord",
    "ToolCallSpeedStats",
    "ToolSpeedStats",
    "ProviderUsage",
    "UsageRecord",
    "UsageRollup",
    "UsageTracker",
    "SearchTreeRuntimeComponent",
    "PointToPointActorRuntime",
    "BroadcastActorRuntime",
    "LinearRuntime",
    "MctsSearchRuntime",
    "ActorRuntime",
]

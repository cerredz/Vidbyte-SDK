"""Context Protocol Header

Description:
    Exposes agents and orchestration primitives for Vidbyte SDK.
Purpose:
    Allows easy package-level import of BaseAgent, registries, client schemas,
    and swappable execution runtimes.
Architecture:
    - BaseAgent: Client-facing agent coordinator.
    - AgentRegistry: Local/shared memory storage registry.
    - Swappable Runtimes: LinearAgentRuntime, SearchTreeRuntimeComponent, PointToPointActorRuntime, BroadcastActorRuntime.
Relations:
    Imported by main client and evaluator harnesses.
Similar Files:
    - vidbyte/agents/base.py: Agent controller core.
"""

from __future__ import annotations

from vidbyte.agents.base import BaseAgent, ConfiguredAgentRunner
from vidbyte.agents.aggregation import AggregateAgent, AggregateResult, MultiProviderAggregator
from vidbyte.agents.client import AgentClient
from vidbyte.agents.continual_trace import ContinualTraceAgent
from vidbyte.agents.settings import AgentLoopSettings, ToolErrorPolicy, UnrecoverableAction
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
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
)
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage, AgentSpec, ModelModality

Agent = BaseAgent

__all__ = [
    "Agent",
    "AggregateAgent",
    "AggregateConfig",
    "AggregateResult",
    "AgentClient",
    "AgentLoopSettings",
    "ToolErrorPolicy",
    "UnrecoverableAction",
    "AgentCard",
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
    "ConfiguredAgentRunner",
    "ContinualTraceAgent",
    "HandoffAgent",
    "ModelModality",
    "AgentRuntime",
    "SearchTreeRuntimeComponent",
    "PointToPointActorRuntime",
    "BroadcastActorRuntime",
    "LinearRuntime",
    "MctsSearchRuntime",
    "ActorRuntime",
]

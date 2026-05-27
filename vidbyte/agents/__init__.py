"""Context Protocol Header

Description:
    Exposes agents and orchestration primitives for Vidbyte SDK.
Purpose:
    Allows easy package-level import of BaseAgent, registries, client schemas,
    and swappable execution runtimes.
Architecture:
    - BaseAgent: Client-facing agent coordinator.
    - AgentRegistry: Local/shared memory storage registry.
    - Swappable Runtimes: LinearAgentRuntime, SearchTreeRuntimeComponent, ActorRuntimeComponent.
Relations:
    Imported by main client and evaluator harnesses.
Similar Files:
    - vidbyte/agents/base.py: Agent controller core.
"""

from __future__ import annotations

from vidbyte.agents.base import BaseAgent, ConfiguredAgentRunner
from vidbyte.agents.client import AgentClient
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.registry import AgentRegistry
from vidbyte.agents.runtimes import (
    LinearAgentRuntime as AgentRuntime,
    SearchTreeRuntimeComponent,
    ActorRuntimeComponent,
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
    "AgentClient",
    "AgentCard",
    "AgentInput",
    "AgentMessage",
    "AgentRunnerConfig",
    "AgentRuntimeContextAlgorithms",
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentRegistry",
    "AgentSpec",
    "AgentStopReason",
    "BaseAgent",
    "ConfiguredAgentRunner",
    "ModelModality",
    "AgentRuntime",
    "SearchTreeRuntimeComponent",
    "ActorRuntimeComponent",
]

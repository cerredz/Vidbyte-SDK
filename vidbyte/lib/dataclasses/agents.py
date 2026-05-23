"""Context Protocol Header

Description:
    Defines immutable data contracts representing agent states, capabilities, and configurations.
Purpose:
    Exposes stable data structures like AgentCard and AgentMessage for registry and execution systems.
Architecture:
    - AgentRunnerConfig: Primitive backend configuration.
    - AgentCard: Local agent description, capabilities, and tools.
    - AgentMessage: Actor-to-actor message payload.
    - AgentSpec: Construction-friendly agent settings block.
Relations:
    Used by vidbyte.agents.base, vidbyte.agents.registry, and orchestration strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vidbyte.lib.enums import ModelModality


@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    """Primitive runner settings captured by an SDK agent."""

    api_key: str | None = None
    provider: str | None = None
    model_name: str | None = None
    modality: ModelModality | str = ModelModality.AUTO
    temperature: float | None = None
    run_id: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentInput:
    """Typed agent input for reliable modality routing."""

    prompt: str
    modality: ModelModality | str = ModelModality.AUTO
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Local capability declaration for an agent."""

    name: str
    description: str
    system_prompt: str
    capabilities: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    mcp_tool_names: tuple[str, ...] = ()
    mcp_server_names: tuple[str, ...] = ()
    modalities: tuple[ModelModality, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """In-process message passed between agents."""

    sender: str
    recipient: str
    content: str
    message_type: str = "response"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Construction-friendly agent description."""

    name: str
    system_prompt: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

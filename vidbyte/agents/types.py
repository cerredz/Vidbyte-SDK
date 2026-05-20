from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

AgentRole = Literal["worker", "service", "support", "evaluator"]


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Local capability declaration for an agent."""

    name: str
    role: AgentRole
    description: str
    capabilities: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """In-process message passed between agents."""

    sender: str
    recipient: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Construction-friendly agent description."""

    name: str
    role: AgentRole
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

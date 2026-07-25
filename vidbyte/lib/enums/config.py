"""Context Protocol Header

Description:
    Defines the type discriminators for YAML configuration documents.
Purpose:
    Gives the YamlLoader and descriptor dataclasses a single vocabulary for
    document kind (agent, harness, environment) and agent subtype (base, multi,
    aggregate, adversarial, handoff, continual_trace).
Architecture:
    - DocumentType: top-level YAML discriminator.
    - AgentType: polymorphic agent subtype within an agent document.
Relations:
    Used by vidbyte/lib/config/loader.py, vidbyte/lib/dataclasses/agent_descriptor.py.
"""

from __future__ import annotations

from enum import Enum


class DocumentType(str, Enum):
    """Top-level YAML document kind discriminator."""

    AGENT = "agent"
    HARNESS = "harness"
    ENVIRONMENT = "environment"


class AgentType(str, Enum):
    """Polymorphic agent subtype within an agent YAML document."""

    BASE = "base"
    MULTI = "multi"
    AGGREGATE = "aggregate"
    ADVERSARIAL = "adversarial"
    HANDOFF = "handoff"
    CONTINUAL_TRACE = "continual_trace"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        # Returns all valid agent type strings for error messages.
        return tuple(member.value for member in cls)


__all__ = [
    "AgentType",
    "DocumentType",
]

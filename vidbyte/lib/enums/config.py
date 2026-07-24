"""Context Protocol Header

Description:
    Enumerates the fixed vocabulary used by the public YAML configuration loader.
Purpose:
    Gives the agent ``type`` discriminator one authoritative, string-backed definition so
    an agent document selects a concrete agent settings class instead of a bare string.
Architecture:
    - AgentType: The agent kinds an agent document may declare, one per BaseAgent subclass.
Relations:
    Consumed by vidbyte.lib.dataclasses.config (settings dispatch) and vidbyte.config.loader.
Similar Files:
    - vidbyte/lib/enums/agent_runtime.py: Runtime enum used by the same agent settings.
    - vidbyte/lib/enums/model_provider.py: Provider enum validated by the same settings.
"""

from __future__ import annotations

from enum import Enum


class AgentType(str, Enum):
    """Supported ``type`` values for an agent document, one per concrete BaseAgent subclass.

    ``BASE`` is the plain :class:`vidbyte.agents.base.BaseAgent`. The remaining members name
    the composite and facade agents; the loader recognizes them but does not yet parse their
    full YAML shape, so requesting one raises a specific, actionable configuration error.
    """

    BASE = "base"
    AGGREGATE = "aggregate"
    CONTINUAL_TRACE = "continual_trace"
    HANDOFF = "handoff"
    MULTI = "multi"
    ADVERSARIAL = "adversarial"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        # Returns every accepted type string for building "must be one of ..." error messages.
        return tuple(member.value for member in cls)


__all__ = ["AgentType"]

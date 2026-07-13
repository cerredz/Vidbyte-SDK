"""Context Protocol Header

PURPOSE:
    Stable re-export surface for the agent-facing dataclasses (AgentCard,
    AgentForkSettings, AgentInput, AgentMessage, AgentSpec) so agent modules and
    callers import them from vidbyte.agents.types without depending on the
    internal vidbyte.lib.dataclasses layout.
ROLE IN CODEBASE:
    Imported across vidbyte.agents; forwards the canonical definitions that live
    in vidbyte.lib.dataclasses.agents.
ARCHITECTURE:
    - Pure re-export module: no types are defined here, only rebound and listed
      in __all__ to fix the public import path.
FUNCTION INVENTORY:
    - (module) re-exports the agent dataclasses; no callable logic lives here.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.agents import AgentCard, AgentForkSettings, AgentInput, AgentMessage, AgentSpec

__all__ = [
    "AgentCard",
    "AgentForkSettings",
    "AgentInput",
    "AgentMessage",
    "AgentSpec",
]

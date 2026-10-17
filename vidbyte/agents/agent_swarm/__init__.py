"""FILE: vidbyte/agents/agent_swarm/__init__.py

PURPOSE: Exposes AgentSwarm, its settings (AgentSwarmSettings), the three roles of one run (AgentSwarmRuntime, AgentSwarmEvents, and AgentSwarmWorkplace), and AgentSwarmMemberRuntime, the runtime that AgentRuntimeType.AGENT_SWARM_MEMBER resolves to.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents, by the runtime registry's lazy import, and by application code.
ARCHITECTURE NOTE: The member agent, the message tool, and the turn middleware stay internal to the package; the swarm's records and enums are public from vidbyte.lib.dataclasses.agent_swarm and vidbyte.lib.enums, and its toolset from vidbyte.tools.toolsets.
FUNCTION INVENTORY: None; this module only re-exports the six public names.
COMMON MODIFICATION PATTERNS: Export a new name here only when it becomes part of the supported AgentSwarm API, and mirror it in vidbyte/agents/__init__.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not export AgentSwarmMemberAgent, AgentSwarmMessageTool, or AgentSwarmTurnMiddleware; they are internal. 2. Do not add logic here.
KNOWN EDGE CASES: Importing this package builds nothing and touches no folder; the workplace is created when a run starts.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.5 and 9.2); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py
"""

from vidbyte.agents.agent_swarm.events import AgentSwarmEvents
from vidbyte.agents.agent_swarm.member import AgentSwarmMemberRuntime
from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime
from vidbyte.agents.agent_swarm.settings import AgentSwarmSettings
from vidbyte.agents.agent_swarm.swarm import AgentSwarm
from vidbyte.agents.agent_swarm.workplace import AgentSwarmWorkplace

__all__ = [
    "AgentSwarm",
    "AgentSwarmEvents",
    "AgentSwarmMemberRuntime",
    "AgentSwarmRuntime",
    "AgentSwarmSettings",
    "AgentSwarmWorkplace",
]

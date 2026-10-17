"""FILE: vidbyte/lib/enums/agent_swarm.py

PURPOSE: Defines the two closed vocabularies of AgentSwarm: the kind of one swarm event and the reason one swarm run ended.
ROLE IN CODEBASE: Typed fields of AgentSwarmEvent and AgentSwarmResult (vidbyte/lib/dataclasses/agent_swarm.py); recorded by AgentSwarmEvents and decided by AgentSwarmRuntime in vidbyte/agents/agent_swarm/. Re-exported from vidbyte/lib/enums/__init__.py and from the root vidbyte package, because a developer compares them against result.stop_reason and event.kind.
ARCHITECTURE NOTE: Every value is the member name in lowercase. The values are what a developer's on_event callback or log sees, so a value is a public contract as well as a name.
FUNCTION INVENTORY: No functions; two str Enums: AgentSwarmEventKind and AgentSwarmStopReason.
COMMON MODIFICATION PATTERNS: A new event kind is one more AgentSwarmEventKind member plus its row in AgentSwarmEvent's per-kind field rules and the place in AgentSwarmRuntime that records it. A new stop reason needs the end check in AgentSwarmRuntime to decide it.
WHAT NOT TO DO IN THIS FILE: 1. Do not change a value; developers' callbacks and logs compare against it. 2. Do not add behavior or methods. 3. Do not define a feature constant here; constants live in vidbyte/lib/constants/agent_swarm.py.
KNOWN EDGE CASES: TIMEOUT overrides the other three reasons only when the time limit is reached before the swarm decided to end; a swarm that had already decided keeps its reason.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.5 and 9.1); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py and the rest of tests/features/agent_swarm/
"""

from __future__ import annotations

from enum import Enum


class AgentSwarmEventKind(str, Enum):
    """What one swarm event records: a start, a tool call, a message sent or delivered, a turn ending or starting again, a failure, or the end."""

    AGENT_STARTED = "agent_started"
    TOOL_CALLED = "tool_called"
    MESSAGE_SENT = "message_sent"
    MESSAGE_DELIVERED = "message_delivered"
    AGENT_IDLE = "agent_idle"
    AGENT_WOKE = "agent_woke"
    AGENT_FAILED = "agent_failed"
    SWARM_ENDED = "swarm_ended"


class AgentSwarmStopReason(str, Enum):
    """Why a swarm run ended."""

    # No agent is working and no message waits for a running agent.
    QUIET = "quiet"
    # No agent is working, and the turn budget refused a wake.
    MAX_TURNS = "max_turns"
    # The time limit was reached before the swarm decided to end.
    TIMEOUT = "timeout"
    # Every agent failed.
    FAILED = "failed"


__all__ = ["AgentSwarmEventKind", "AgentSwarmStopReason"]

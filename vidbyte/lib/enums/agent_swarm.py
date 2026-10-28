"""FILE: vidbyte/lib/enums/agent_swarm.py

PURPOSE: Defines the six closed vocabularies of AgentSwarm: the kind of one swarm event, the reason one swarm run ended, the web-search provider a developer selects, why a compaction ran, what a cancelled agent was doing, and what the run found at the workplace path.
ROLE IN CODEBASE: Typed fields of AgentSwarmSettings, AgentSwarmEvent and AgentSwarmResult (vidbyte/lib/dataclasses/agent_swarm.py); recorded by AgentSwarmEvents and decided by AgentSwarmRuntime in vidbyte/agents/agent_swarm/. Re-exported from vidbyte/lib/enums/__init__.py; the event kind, the stop reason and the web-search provider are also root vidbyte exports, because a developer compares them against result.stop_reason and event.kind or passes one as a setting.
ARCHITECTURE NOTE: Every value is the member name in lowercase. The values are what a developer's on_event callback or log sees, so a value is a public contract as well as a name.
FUNCTION INVENTORY: No functions; six str Enums: AgentSwarmEventKind, AgentSwarmStopReason, AgentSwarmWebSearch, AgentSwarmCompactionTrigger, AgentSwarmAgentState and AgentSwarmFolderState.
COMMON MODIFICATION PATTERNS: A new event kind is one more AgentSwarmEventKind member plus its row in _KIND_FIELDS (vidbyte/lib/dataclasses/agent_swarm.py) and the block in AgentSwarmRuntime that records it. A new stop reason needs the block in AgentSwarmRuntime that decides it. A new web-search provider needs a client module and its row in AgentSwarmTools.search_tool_for.
WHAT NOT TO DO IN THIS FILE: 1. Do not change a value; developers' callbacks and logs compare against it. 2. Do not add behavior or methods. 3. Do not define a feature constant here; constants live in vidbyte/lib/constants/agent_swarm.py.
KNOWN EDGE CASES: TIMEOUT is decided only when the time limit is reached before the swarm decided to end; a swarm that had already decided keeps its reason. MAX_TOKENS can be decided by a compaction's summary call as well as by a loop call.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 8.1 D-5, D-7, D-18 and 8.5); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py and the rest of tests/features/agent_swarm/
"""

from __future__ import annotations

from enum import Enum


class AgentSwarmEventKind(str, Enum):
    """What one swarm event records: a run-level fact, a decision the runtime made, or a fact observed in one member's loop."""

    AGENT_STARTED = "agent_started"
    TOOL_CALLED = "tool_called"
    MESSAGE_SENT = "message_sent"
    MESSAGE_DELIVERED = "message_delivered"
    AGENT_IDLE = "agent_idle"
    AGENT_WOKE = "agent_woke"
    AGENT_FAILED = "agent_failed"
    SWARM_ENDED = "swarm_ended"
    WORKPLACE_PREPARED = "workplace_prepared"
    AGENT_CREATED = "agent_created"
    MESSAGE_REFUSED = "message_refused"
    WAKE_REFUSED = "wake_refused"
    MESSAGE_UNDELIVERED = "message_undelivered"
    SWARM_STOPPING = "swarm_stopping"
    AGENT_RELEASED = "agent_released"
    AGENT_CANCELLED = "agent_cancelled"
    AGENT_EXITED = "agent_exited"
    MODEL_CALLED = "model_called"
    MODEL_ERROR = "model_error"
    HISTORY_TRIMMED = "history_trimmed"
    TOOL_RESULT_TRUNCATED = "tool_result_truncated"
    FILE_CHANGED = "file_changed"
    COMMAND_FAILED = "command_failed"
    COMPACTION = "compaction"


class AgentSwarmStopReason(str, Enum):
    """Why a swarm run ended."""

    # No agent is working and no message waits for a running agent.
    QUIET = "quiet"
    # No agent is working, and the turn budget refused a wake.
    MAX_TURNS = "max_turns"
    # The time limit was reached before the swarm decided to end.
    TIMEOUT = "timeout"
    # Every agent failed or exited.
    FAILED = "failed"
    # The swarm-wide token budget was reached.
    MAX_TOKENS = "max_tokens"


class AgentSwarmWebSearch(str, Enum):
    """The web-search providers a developer can give every agent; each has a client module."""

    BRAVE = "brave"
    BROWSERBASE = "browserbase"
    EXA = "exa"
    PARALLEL = "parallel"
    TAVILY = "tavily"


class AgentSwarmCompactionTrigger(str, Enum):
    """Why a compaction ran: the agent called compact, or its measured context reached the trigger."""

    TOOL = "tool"
    AUTO = "auto"


class AgentSwarmAgentState(str, Enum):
    """What an agent was doing when the swarm cancelled it."""

    WORKING = "working"
    IDLE = "idle"


class AgentSwarmFolderState(str, Enum):
    """What preparing the workplace found at its path: it made the folder, or the folder was already there."""

    CREATED = "created"
    EXISTED = "existed"


__all__ = [
    "AgentSwarmAgentState",
    "AgentSwarmCompactionTrigger",
    "AgentSwarmEventKind",
    "AgentSwarmFolderState",
    "AgentSwarmStopReason",
    "AgentSwarmWebSearch",
]

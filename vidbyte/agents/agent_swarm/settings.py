"""FILE: vidbyte/agents/agent_swarm/settings.py

PURPOSE: Defines AgentSwarmSettings, the one public configuration object of AgentSwarm: the agents, the shared workplace folder, the API keys, the optional search tool, the optional on_event callback, the turn budget, and the time limit.
ROLE IN CODEBASE: Built by the developer and passed to AgentSwarm (swarm.py), which hands it to one AgentSwarmRuntime (runtime.py) per run. Exported by vidbyte/agents/agent_swarm/__init__.py, vidbyte/agents/__init__.py, and the root vidbyte package.
ARCHITECTURE NOTE: Settings objects live in the owning agent's settings.py (AGENTS.md Placement Rules, exception 1). Every check runs in __post_init__, so a constructed object is always valid and nothing downstream checks it again. Each field check is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter, and the key match is ProviderKeyMatcher's; only the rules that tie fields together (distinct names, a turn budget of at least one turn per agent, a search tool that takes no swarm tool's name) are written here. Checking settings never touches the disk: the workplace folder is created when a run starts.
FUNCTION INVENTORY: AgentSwarmSettings.__post_init__ is the narrated main function, with no private helpers.
COMMON MODIFICATION PATTERNS: A new setting adds one field, one RecordFieldValidator or RecordFieldConverter call in __post_init__, a named default in vidbyte/lib/constants/agent_swarm.py, and one row in the package README's limits table.
WHAT NOT TO DO IN THIS FILE: 1. Do not create the workplace folder or any file here; a refused setting must leave the disk unchanged. 2. Do not put api_keys in an error message or in repr. 3. Do not accept a bare string where a sequence is expected; it would split into characters.
KNOWN EDGE CASES: workplace="" is refused even though Path("") is the current folder, and a workplace that is an existing file is refused. True is refused for max_turns, although Python counts it as an int. Members on different providers share one api_keys list, matched once against every provider in member order. A refusal names the field as AgentSwarmSettings.<field> in the message and in details["field"].
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.5 and 9.3); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.constants.agent_swarm import (
    AGENT_SWARM_DEFAULT_MAX_TURNS,
    AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS,
    AGENT_SWARM_MAX_AGENTS,
    AGENT_SWARM_MAX_TIMEOUT_SECONDS,
    AGENT_SWARM_MIN_AGENTS,
    AGENT_SWARM_RESERVED_TOOL_NAMES,
)
from vidbyte.lib.dataclasses.agent_swarm import (
    AgentSwarmEventCallback,
    AgentSwarmMember,
)
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher
from vidbyte.tools.base import BaseTool


@dataclass(frozen=True, slots=True)
class AgentSwarmSettings:
    """Everything one swarm needs: its agents, the folder they share, their keys, an optional search tool and event callback, and the turn and time limits.

    agents and workplace keep their raw types until __post_init__ checks
    them, because a list is accepted and Path("") is the current folder.
    After __post_init__ agents is a tuple, workplace a resolved Path,
    and api_keys the matched ProviderKeys record.
    """

    agents: tuple[AgentSwarmMember, ...]
    workplace: str | Path
    api_keys: ProviderKeys | Iterable[str | None] | None = field(default_factory=ProviderKeys, repr=False)
    search_tool: BaseTool | None = None
    on_event: AgentSwarmEventCallback | None = None
    max_turns: int = AGENT_SWARM_DEFAULT_MAX_TURNS
    timeout_seconds: float = AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        # @intent one-closed-surface-for-the-whole-swarm
        # These settings configure every agent of every run, so a bad
        # value is refused here, before any folder, agent, or model call
        # exists, and the refusal names the field that must change. The
        # keys are matched once against every member's provider here.

        # The agents are members, kept as a tuple: at least two, so each
        # has someone to message, and at most the swarm cap.
        agents = RecordFieldConverter.to_tuple(self.agents, "AgentSwarmSettings.agents", item_type=AgentSwarmMember, max_items=AGENT_SWARM_MAX_AGENTS)
        if len(agents) < AGENT_SWARM_MIN_AGENTS:
            raise ConfigurationError(f"AgentSwarmSettings.agents must hold at least {AGENT_SWARM_MIN_AGENTS} members; got {len(agents)}.", details={"field": "AgentSwarmSettings.agents"})
        # Names are how agents address each other, so no two may share one.
        names = [member.name for member in agents]
        repeated = next((name for index, name in enumerate(names) if name in names[:index]), None)
        if repeated is not None:
            raise ConfigurationError(f"AgentSwarmSettings.agents must have distinct names, but {repeated!r} is used twice.", details={"field": "AgentSwarmSettings.agents"})
        object.__setattr__(self, "agents", agents)

        # Keep the workplace as an absolute path. It may not exist yet,
        # because the swarm creates it when a run starts, but it may
        # never be an existing file.
        object.__setattr__(self, "workplace", RecordFieldConverter.to_folder(self.workplace, "AgentSwarmSettings.workplace"))

        # @intent limits-live-in-code
        # The turn budget covers every agent's first turn, so it is at
        # least the number of agents; the time limit is a finite number
        # of seconds above zero and at most the ceiling. Neither appears
        # in any prompt.
        RecordFieldValidator.require_int(self.max_turns, "AgentSwarmSettings.max_turns", minimum=len(agents))
        RecordFieldValidator.require_number(self.timeout_seconds, "AgentSwarmSettings.timeout_seconds", maximum=AGENT_SWARM_MAX_TIMEOUT_SECONDS)

        # The callback is optional, and called once per event when given.
        if self.on_event is not None and not callable(self.on_event):
            raise ConfigurationError(f"AgentSwarmSettings.on_event must be None or a callable that takes one AgentSwarmEvent; got a value of type {type(self.on_event).__name__}.", details={"field": "AgentSwarmSettings.on_event"})

        # @intent the-search-tool-never-shadows-a-swarm-tool
        # Every agent holds the swarm's own tools, so a search tool that
        # took one of their names would leave the model unable to tell
        # which one it is calling.
        RecordFieldConverter.require_instance(self.search_tool, "AgentSwarmSettings.search_tool", BaseTool, optional=True)
        if self.search_tool is not None and self.search_tool.name in AGENT_SWARM_RESERVED_TOOL_NAMES:
            raise ConfigurationError(f"AgentSwarmSettings.search_tool must not take a swarm tool's name; got {self.search_tool.name!r}. Reserved: {', '.join(AGENT_SWARM_RESERVED_TOOL_NAMES)}.", details={"field": "AgentSwarmSettings.search_tool"})

        # Match the developer's keys once against every member's
        # provider, in member order; each agent carries this one record,
        # which is never shown.
        providers = tuple(dict.fromkeys(member.provider for member in agents))
        object.__setattr__(self, "api_keys", ProviderKeyMatcher.match(self.api_keys, primary=providers, field_name="AgentSwarmSettings.api_keys"))


__all__ = ["AgentSwarmSettings"]

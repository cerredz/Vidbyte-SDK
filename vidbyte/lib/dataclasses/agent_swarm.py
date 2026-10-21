"""FILE: vidbyte/lib/dataclasses/agent_swarm.py

PURPOSE: Defines the four validated records of AgentSwarm: AgentSwarmMember, one agent a developer puts in a swarm; AgentSwarmSettings, the one configuration object of a swarm; AgentSwarmEvent, one fact of a swarm run; and AgentSwarmResult, what one run returns. Also defines AgentSwarmEventCallback, the type of the developer's on_event callback.
ROLE IN CODEBASE: The lib home of every AgentSwarm record, so the settings sit in the bottom layer beside the records they hold (spec D-1, the user's choice over AGENTS.md exception 1). AgentSwarmMember and AgentSwarmSettings are built by the developer and passed to AgentSwarm (vidbyte/agents/agent_swarm/swarm.py), which hands the settings to one AgentSwarmRuntime per run; AgentSwarmEvent is built by AgentSwarmEvents and handed to on_event; AgentSwarmResult is built by AgentSwarmRuntime at the end of a run. AgentSwarmMember and AgentSwarmSettings are also exported from vidbyte.agents.agent_swarm, vidbyte.agents and the root vidbyte package.
ARCHITECTURE NOTE: Validation only. Every check runs in __post_init__, so a constructed record is always valid and its callers never check it again. Each field check is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py), the key match is ProviderKeyMatcher's, and the member's provider is coerced with ModelProvider itself and its model checked with ProviderModelRegistry, the two proofs lint rule C012 recognizes; only this feature's own rules (distinct names, a turn budget of at least one turn per agent, a web-search key that belongs to a selected provider, which fields each event kind carries, and how a result's events are numbered) are written here. Checking settings never touches the disk: the workplace folder is created when a run starts.
FUNCTION INVENTORY: Four frozen, slotted records, each with a narrated __post_init__ and no private helpers: AgentSwarmMember checks the name pattern, the provider, and the model; AgentSwarmSettings checks the agents, the workplace, the three limits, the callback, the web-search provider and key, and matches the model keys; AgentSwarmEvent checks the numbers, the kind, the agent, and the per-kind field table; AgentSwarmResult checks the stop reason, the event sequence with its one swarm_stopping, the replies, and the callback error names. AgentSwarmEventCallback is a type alias.
COMMON MODIFICATION PATTERNS: A new event kind adds its row to _KIND_FIELDS, and to _BLANK_ALLOWED when one of its text fields may be blank. A new event field adds one field, its name in _OPTIONAL_FIELDS, and its check in AgentSwarmEvent.__post_init__. A new setting adds one field, one RecordFieldValidator or RecordFieldConverter call in AgentSwarmSettings.__post_init__, a named default in vidbyte/lib/constants/agent_swarm.py, and one row in the package README's limits table.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents, vidbyte.tools, vidbyte.middleware, vidbyte.prompts, or any other layer above vidbyte/lib, not even inside a function. 2. Do not add to_dict or from_dict methods or dict[str, Any] signatures. 3. Do not quote message text, reply text, or a key in an error. 4. Do not create the workplace folder or any file in a record; a refused setting must leave the disk unchanged.
KNOWN EDGE CASES: AGENT_IDLE text may be empty, because a model may end its turn with an empty reply; compaction text is empty when compact was called without a focus or the trigger fired. elapsed_ms may be 0 and two events may share one value; order is carried by sequence. True is refused wherever a whole number is expected, although Python counts it as an int. workplace="" is refused even though Path("") is the current folder, and a workplace that is an existing file is refused. Members on different providers share one api_keys list, matched once against every provider in member order. The web-search provider is matched by its exact value, so "Tavily" is refused. A refusal names the field as Record.field in the message and in details["field"].
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 6.1 INV-16 to INV-21, 8.1 D-1, D-7, D-18, 8.5 and 9.1); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py, tests/features/agent_swarm/test_agent_swarm_settings.py and the rest of tests/features/agent_swarm/
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field, fields
from pathlib import Path

from vidbyte.lib.constants.agent_swarm import (
    AGENT_SWARM_DEFAULT_MAX_TOKENS,
    AGENT_SWARM_DEFAULT_MAX_TURNS,
    AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS,
    AGENT_SWARM_MAX_AGENTS,
    AGENT_SWARM_MAX_TIMEOUT_SECONDS,
    AGENT_SWARM_MIN_AGENTS,
    AGENT_SWARM_MIN_TOKENS,
    AGENT_SWARM_NAME_PATTERN,
)
from vidbyte.lib.dataclasses.agents import AgentMessage, ProviderKeys
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.agent_swarm import (
    AgentSwarmAgentState,
    AgentSwarmCompactionTrigger,
    AgentSwarmEventKind,
    AgentSwarmFolderState,
    AgentSwarmStopReason,
    AgentSwarmWebSearch,
)
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

# The optional fields each event kind carries (spec section 8.5); every
# other optional field must keep its default.
_KIND_FIELDS: dict[AgentSwarmEventKind, frozenset[str]] = {
    AgentSwarmEventKind.AGENT_STARTED: frozenset(),
    AgentSwarmEventKind.TOOL_CALLED: frozenset({"tool_name", "tool_status"}),
    AgentSwarmEventKind.MESSAGE_SENT: frozenset({"peer", "message_id", "text"}),
    AgentSwarmEventKind.MESSAGE_DELIVERED: frozenset({"peer", "message_id"}),
    AgentSwarmEventKind.AGENT_IDLE: frozenset({"text"}),
    AgentSwarmEventKind.AGENT_WOKE: frozenset(),
    AgentSwarmEventKind.AGENT_FAILED: frozenset({"text"}),
    AgentSwarmEventKind.SWARM_ENDED: frozenset({"stop_reason"}),
    AgentSwarmEventKind.WORKPLACE_PREPARED: frozenset({"path", "folder_state"}),
    AgentSwarmEventKind.AGENT_CREATED: frozenset(),
    AgentSwarmEventKind.MESSAGE_REFUSED: frozenset({"peer", "text"}),
    AgentSwarmEventKind.WAKE_REFUSED: frozenset({"peer", "message_id"}),
    AgentSwarmEventKind.MESSAGE_UNDELIVERED: frozenset({"peer", "message_id"}),
    AgentSwarmEventKind.SWARM_STOPPING: frozenset({"stop_reason"}),
    AgentSwarmEventKind.AGENT_RELEASED: frozenset(),
    AgentSwarmEventKind.AGENT_CANCELLED: frozenset({"agent_state"}),
    AgentSwarmEventKind.AGENT_EXITED: frozenset({"text"}),
    AgentSwarmEventKind.MODEL_CALLED: frozenset({"input_tokens", "output_tokens", "cached_tokens", "model_calls"}),
    AgentSwarmEventKind.MODEL_ERROR: frozenset({"text"}),
    AgentSwarmEventKind.HISTORY_TRIMMED: frozenset({"messages_dropped"}),
    AgentSwarmEventKind.TOOL_RESULT_TRUNCATED: frozenset({"tool_name", "omitted_chars"}),
    AgentSwarmEventKind.FILE_CHANGED: frozenset({"path", "peer"}),
    AgentSwarmEventKind.COMMAND_FAILED: frozenset({"text"}),
    AgentSwarmEventKind.COMPACTION: frozenset({"compaction_trigger", "text", "input_tokens", "messages_dropped"}),
}
# The optional fields by type: whole-number counts, texts, and enums.
_COUNT_FIELDS = ("input_tokens", "output_tokens", "cached_tokens", "model_calls", "messages_dropped", "omitted_chars")
_TEXT_FIELDS = ("peer", "text", "tool_name", "path")
_ENUM_FIELDS: dict[str, type[ToolStatus | AgentSwarmStopReason | AgentSwarmCompactionTrigger | AgentSwarmAgentState | AgentSwarmFolderState]] = {
    "tool_status": ToolStatus,
    "stop_reason": AgentSwarmStopReason,
    "compaction_trigger": AgentSwarmCompactionTrigger,
    "agent_state": AgentSwarmAgentState,
    "folder_state": AgentSwarmFolderState,
}
_OPTIONAL_FIELDS = ("message_id", *_COUNT_FIELDS, *_TEXT_FIELDS, *_ENUM_FIELDS)
# The kinds that belong to the swarm rather than to one agent, and the
# carried text fields a kind may leave blank; every other carried text
# field must hold text.
_SWARM_KINDS = frozenset({AgentSwarmEventKind.SWARM_ENDED, AgentSwarmEventKind.SWARM_STOPPING, AgentSwarmEventKind.WORKPLACE_PREPARED})
_BLANK_ALLOWED: dict[str, frozenset[AgentSwarmEventKind]] = {
    "peer": frozenset({AgentSwarmEventKind.MESSAGE_REFUSED, AgentSwarmEventKind.FILE_CHANGED}),
    "text": frozenset({AgentSwarmEventKind.AGENT_IDLE, AgentSwarmEventKind.COMPACTION}),
}
# The kinds whose message_id names an earlier message_sent event.
_EARLIER_MESSAGE_KINDS = frozenset({AgentSwarmEventKind.MESSAGE_DELIVERED, AgentSwarmEventKind.WAKE_REFUSED, AgentSwarmEventKind.MESSAGE_UNDELIVERED})


@dataclass(frozen=True, slots=True)
class AgentSwarmMember:
    """One agent of a swarm: its name and the model it runs on; every agent shares the swarm's one system prompt.

    provider keeps its raw type until __post_init__ checks it, so the
    developer may name it as text ("openai"); afterwards it is a
    ModelProvider.
    """

    name: str
    provider: ModelProvider | str
    model_name: str

    def __post_init__(self) -> None:
        # @intent member-names-are-recipient-names
        # The name is the agent's BaseAgent name, the value the other
        # agents pass to the message tool, and its name in every event,
        # so it is one short line of letters, digits, "_" and "-".
        RecordFieldValidator.require_text(self.name, "AgentSwarmMember.name", pattern=AGENT_SWARM_NAME_PATTERN, one_line=True)
        # Developers may name the provider as text; the enum is stored,
        # and a name the SDK does not know is refused with the known
        # ones.
        try:
            provider = ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"AgentSwarmMember.provider must be one of {', '.join(member.value for member in ModelProvider)}; got {self.provider!r}.", details={"field": "AgentSwarmMember.provider"}) from exc
        object.__setattr__(self, "provider", provider)
        RecordFieldValidator.require_text(self.model_name, "AgentSwarmMember.model_name")
        # A model the SDK cannot run under the provider is refused here,
        # before any swarm starts, not at the agent's first model call.
        try:
            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.model_name)
        except ConfigurationError as exc:
            raise ConfigurationError(f"AgentSwarmMember.model_name must be a model the SDK can run under the given provider; {exc.message}", details={"field": "AgentSwarmMember.model_name"}) from exc


@dataclass(frozen=True, slots=True)
class AgentSwarmEvent:
    """One fact of a swarm run, numbered by sequence; which optional fields it carries depends on its kind."""

    sequence: int
    kind: AgentSwarmEventKind
    agent: str
    elapsed_ms: int
    peer: str = ""
    message_id: int = 0
    text: str = ""
    tool_name: str = ""
    tool_status: ToolStatus | None = None
    stop_reason: AgentSwarmStopReason | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    model_calls: int = 0
    messages_dropped: int = 0
    omitted_chars: int = 0
    path: str = ""
    compaction_trigger: AgentSwarmCompactionTrigger | None = None
    agent_state: AgentSwarmAgentState | None = None
    folder_state: AgentSwarmFolderState | None = None

    def __post_init__(self) -> None:
        # Events are numbered from 1, and their time is whole
        # milliseconds since the run started.
        RecordFieldValidator.require_int(self.sequence, "AgentSwarmEvent.sequence", minimum=1)
        RecordFieldValidator.require_enum(self.kind, AgentSwarmEventKind, "AgentSwarmEvent.kind")
        RecordFieldValidator.require_int(self.elapsed_ms, "AgentSwarmEvent.elapsed_ms", minimum=0)
        kind = self.kind

        # Every event names its agent, except the three facts of the
        # swarm itself (its folder, its stop decision, and its end),
        # which belong to no agent.
        if kind in _SWARM_KINDS and self.agent != "":
            raise ConfigurationError(f"AgentSwarmEvent.agent must be empty for a {kind.value} event.", details={"field": "AgentSwarmEvent.agent"})
        RecordFieldValidator.require_text(self.agent, "AgentSwarmEvent.agent", allow_blank=kind in _SWARM_KINDS)

        # A field the kind does not carry must keep its default, so a
        # reader never mistakes a stray value for data. Type and value
        # are compared, so 0.0 or False never pass for 0.
        defaults = {item.name: item.default for item in fields(self)}
        for name in _OPTIONAL_FIELDS:
            value = getattr(self, name)
            if name not in _KIND_FIELDS[kind] and (type(value), value) != (type(defaults[name]), defaults[name]):
                raise ConfigurationError(f"AgentSwarmEvent.{name} must keep its default for a {kind.value} event.", details={"field": f"AgentSwarmEvent.{name}"})

        # @intent events-carry-what-their-kind-means
        # The fields the kind carries must hold what the kind means.
        # Counts are whole numbers from zero. Names, texts and paths are
        # present, except the few a kind may leave blank (a refusal with
        # no recipient, a file's first writer, an empty reply, a
        # compaction without focus), and every enum field the kind
        # carries holds a member. A sent message's id is its own
        # sequence, and a delivery, a refused wake, or an undelivered
        # message names an earlier one, so a reader can pair every
        # outcome with its send.
        carried = _KIND_FIELDS[kind]
        for name in sorted(carried.intersection(_COUNT_FIELDS)):
            RecordFieldValidator.require_int(getattr(self, name), f"AgentSwarmEvent.{name}", minimum=0)
        for name in sorted(carried.intersection(_TEXT_FIELDS)):
            RecordFieldValidator.require_text(getattr(self, name), f"AgentSwarmEvent.{name}", allow_blank=kind in _BLANK_ALLOWED.get(name, frozenset()))
        for name in sorted(carried.intersection(_ENUM_FIELDS)):
            RecordFieldValidator.require_enum(getattr(self, name), _ENUM_FIELDS[name], f"AgentSwarmEvent.{name}")
        if kind is AgentSwarmEventKind.MESSAGE_SENT:
            RecordFieldValidator.require_int(self.message_id, "AgentSwarmEvent.message_id", minimum=self.sequence, maximum=self.sequence)
        if kind in _EARLIER_MESSAGE_KINDS:
            RecordFieldValidator.require_int(self.message_id, "AgentSwarmEvent.message_id", minimum=1, maximum=self.sequence - 1)


AgentSwarmEventCallback = Callable[[AgentSwarmEvent], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AgentSwarmSettings:
    """Everything one swarm needs: its agents, the folder they share, their keys, an optional web-search provider and event callback, and the turn, token and time limits.

    agents, workplace and web_search keep their raw types until
    __post_init__ checks them, because a list is accepted, Path("") is
    the current folder, and a provider may be named as text. Afterwards
    agents is a tuple, workplace a resolved Path, api_keys the matched
    ProviderKeys record, and web_search an AgentSwarmWebSearch or None.
    """

    agents: tuple[AgentSwarmMember, ...]
    workplace: str | Path
    api_keys: ProviderKeys | Iterable[str | None] | None = field(default_factory=ProviderKeys, repr=False)
    web_search: AgentSwarmWebSearch | str | None = None
    web_search_api_key: str | None = field(default=None, repr=False)
    on_event: AgentSwarmEventCallback | None = None
    max_turns: int = AGENT_SWARM_DEFAULT_MAX_TURNS
    max_tokens: int = AGENT_SWARM_DEFAULT_MAX_TOKENS
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
        # Names are how agents address each other, so no two may share
        # one.
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
        # least the number of agents; the token budget is at least its
        # floor and has no ceiling; the time limit is a finite number of
        # seconds above zero and at most the ceiling. None of them
        # appears in any prompt.
        RecordFieldValidator.require_int(self.max_turns, "AgentSwarmSettings.max_turns", minimum=len(agents))
        RecordFieldValidator.require_int(self.max_tokens, "AgentSwarmSettings.max_tokens", minimum=AGENT_SWARM_MIN_TOKENS)
        RecordFieldValidator.require_number(self.timeout_seconds, "AgentSwarmSettings.timeout_seconds", maximum=AGENT_SWARM_MAX_TIMEOUT_SECONDS)

        # The callback is optional, and called once per event when
        # given.
        if self.on_event is not None and not callable(self.on_event):
            raise ConfigurationError(f"AgentSwarmSettings.on_event must be None or a callable that takes one AgentSwarmEvent; got a value of type {type(self.on_event).__name__}.", details={"field": "AgentSwarmSettings.on_event"})

        # @intent a-web-search-key-belongs-to-a-selected-provider
        # A selected provider is one of the providers with a client,
        # named by its exact value, and needs its key; a key with no
        # provider is almost always a forgotten provider, so it is
        # refused rather than ignored. The key is never quoted.
        if self.web_search is not None:
            object.__setattr__(self, "web_search", RecordFieldConverter.to_enum(self.web_search, AgentSwarmWebSearch, "AgentSwarmSettings.web_search"))
            RecordFieldValidator.require_text(self.web_search_api_key, "AgentSwarmSettings.web_search_api_key")
        elif self.web_search_api_key is not None:
            raise ConfigurationError("AgentSwarmSettings.web_search_api_key must be None unless AgentSwarmSettings.web_search selects the provider the key belongs to.", details={"field": "AgentSwarmSettings.web_search_api_key"})

        # Match the developer's keys once against every member's
        # provider, in member order; each agent carries this one record,
        # which is never shown.
        providers = tuple(dict.fromkeys(member.provider for member in agents))
        object.__setattr__(self, "api_keys", ProviderKeyMatcher.match(self.api_keys, primary=providers, field_name="AgentSwarmSettings.api_keys"))


@dataclass(frozen=True, slots=True)
class AgentSwarmResult:
    """What one swarm run returns: why it ended, every event in order, each released agent's last reply, and the type names of on_event errors.

    events and replies may be given as lists; after __post_init__ they
    are tuples.
    """

    stop_reason: AgentSwarmStopReason
    events: tuple[AgentSwarmEvent, ...]
    replies: tuple[AgentMessage, ...]
    event_error_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # @intent results-hold-one-complete-numbered-run
        # The events are the whole run numbered 1 to N with no gap or
        # repeat, ending in the run's one swarm_ended event, whose stop
        # reason is the result's, after exactly one swarm_stopping with
        # that same reason; a reader can then trust the record as the
        # full order of what happened.
        RecordFieldValidator.require_enum(self.stop_reason, AgentSwarmStopReason, "AgentSwarmResult.stop_reason")
        events = RecordFieldConverter.to_tuple(self.events, "AgentSwarmResult.events", item_type=AgentSwarmEvent)
        ended = [event for event in events if event.kind is AgentSwarmEventKind.SWARM_ENDED]
        if [event.sequence for event in events] != list(range(1, len(events) + 1)) or len(ended) != 1 or events[-1] is not ended[0]:
            raise ConfigurationError("AgentSwarmResult.events must be numbered 1 to N in order and end with its one swarm_ended event.", details={"field": "AgentSwarmResult.events"})
        stopping = [event for event in events if event.kind is AgentSwarmEventKind.SWARM_STOPPING]
        if len(stopping) != 1 or stopping[0].stop_reason is not ended[0].stop_reason:
            raise ConfigurationError("AgentSwarmResult.events must hold exactly one swarm_stopping event before swarm_ended, with the same stop reason.", details={"field": "AgentSwarmResult.events"})
        if ended[0].stop_reason is not self.stop_reason:
            raise ConfigurationError("AgentSwarmResult.stop_reason must equal the stop reason of its swarm_ended event.", details={"field": "AgentSwarmResult.stop_reason"})
        object.__setattr__(self, "events", events)
        # Each reply is the agent's own message record.
        object.__setattr__(self, "replies", RecordFieldConverter.to_tuple(self.replies, "AgentSwarmResult.replies", item_type=AgentMessage))
        # Each callback error is named by its exception type: one line.
        error_types = RecordFieldConverter.to_tuple(self.event_error_types, "AgentSwarmResult.event_error_types", item_type=str)
        for name in error_types:
            RecordFieldValidator.require_text(name, "AgentSwarmResult.event_error_types", one_line=True)
        object.__setattr__(self, "event_error_types", error_types)


__all__ = ["AgentSwarmEvent", "AgentSwarmEventCallback", "AgentSwarmMember", "AgentSwarmResult", "AgentSwarmSettings"]

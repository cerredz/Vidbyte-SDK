"""FILE: vidbyte/lib/dataclasses/agent_swarm.py

PURPOSE: Defines the three validated records of AgentSwarm: AgentSwarmMember, one agent a developer puts in a swarm; AgentSwarmEvent, one state change of a swarm run; and AgentSwarmResult, what one run returns. Also defines AgentSwarmEventCallback, the type of the developer's on_event callback.
ROLE IN CODEBASE: AgentSwarmMember is built by the developer and held by AgentSwarmSettings (vidbyte/agents/agent_swarm/settings.py); AgentSwarmEvent is built by AgentSwarmEvents and handed to on_event; AgentSwarmResult is built by AgentSwarmRuntime at the end of a run. AgentSwarmMember is also exported from the root vidbyte package.
ARCHITECTURE NOTE: Validation only. Every check runs in __post_init__, so a constructed record is always valid and its callers never check it again. Each field check is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py), except the member's provider, which is coerced with ModelProvider itself and its model checked with ProviderModelRegistry, the two proofs lint rule C012 recognizes; only this feature's own rules, which fields each event kind carries and how a result's events are numbered, are written here.
FUNCTION INVENTORY: Three frozen, slotted records, each with a __post_init__: AgentSwarmMember checks the name pattern, the prompt, the provider, and the model; AgentSwarmEvent checks the numbers, the kind, and the per-kind field table through _check_agent, _check_unlisted_fields, and _check_kind_fields; AgentSwarmResult checks the stop reason, the event sequence, the replies, and the callback error names. AgentSwarmEventCallback is a type alias.
COMMON MODIFICATION PATTERNS: A new event kind adds its row to _KIND_FIELDS and one case in AgentSwarmEvent._check_kind_fields. A new record field adds one field and one RecordFieldValidator or RecordFieldConverter call; its bound goes in vidbyte/lib/constants/agent_swarm.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents, vidbyte.tools, or any other layer above vidbyte/lib. 2. Do not add to_dict or from_dict methods or dict[str, Any] signatures. 3. Do not quote message text or reply text in an error; it can be long.
KNOWN EDGE CASES: AGENT_IDLE text may be empty, because a model may end its turn with an empty reply. elapsed_ms may be 0 and two events may share one value; order is carried by sequence. True is refused wherever a whole number is expected, although Python counts it as an int. A refusal names the field as Record.field in the message and in details["field"].
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.5 and 9.1); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py and the rest of tests/features/agent_swarm/
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields

from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_NAME_PATTERN
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.agent_swarm import AgentSwarmEventKind, AgentSwarmStopReason
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry

# The optional fields each event kind carries (spec section 9.1); every
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
}
_OPTIONAL_FIELDS = ("peer", "message_id", "text", "tool_name", "tool_status", "stop_reason")


@dataclass(frozen=True, slots=True)
class AgentSwarmMember:
    """One agent of a swarm: its name, its own system prompt, and the model it runs on.

    provider keeps its raw type until __post_init__ checks it, so the
    developer may name it as text ("openai"); afterwards it is a
    ModelProvider.
    """

    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str

    def __post_init__(self) -> None:
        # @intent member-names-are-recipient-names
        # The name is the agent's BaseAgent name, the value the other
        # agents pass to the message tool, and its name in every event,
        # so it is one short line of letters, digits, "_" and "-".
        RecordFieldValidator.require_text(self.name, "AgentSwarmMember.name", pattern=AGENT_SWARM_NAME_PATTERN, one_line=True)
        RecordFieldValidator.require_text(self.system_prompt, "AgentSwarmMember.system_prompt")
        # Developers may name the provider as text; the enum is stored,
        # and a name the SDK does not know is refused with the known ones.
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
    """One state change of a swarm run, numbered by sequence; which optional fields it carries depends on its kind."""

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

    def __post_init__(self) -> None:
        # Events are numbered from 1, and their time is whole
        # milliseconds since the run started.
        RecordFieldValidator.require_int(self.sequence, "AgentSwarmEvent.sequence", minimum=1)
        RecordFieldValidator.require_enum(self.kind, AgentSwarmEventKind, "AgentSwarmEvent.kind")
        RecordFieldValidator.require_int(self.elapsed_ms, "AgentSwarmEvent.elapsed_ms", minimum=0)
        # Every event names its agent, except the swarm's own end.
        self._check_agent()
        # A field the kind does not carry must keep its default, so a
        # reader never mistakes a stray value for data.
        self._check_unlisted_fields()
        # The fields the kind carries must hold what the kind means.
        self._check_kind_fields()

    def _check_agent(self) -> None:
        # The swarm's end belongs to no agent; every other event to one.
        if self.kind is AgentSwarmEventKind.SWARM_ENDED and self.agent != "":
            raise ConfigurationError("AgentSwarmEvent.agent must be empty for a swarm_ended event.", details={"field": "AgentSwarmEvent.agent"})
        RecordFieldValidator.require_text(self.agent, "AgentSwarmEvent.agent", allow_blank=self.kind is AgentSwarmEventKind.SWARM_ENDED)

    def _check_unlisted_fields(self) -> None:
        # Compare type and value, so 0.0 or False never pass for 0.
        defaults = {item.name: item.default for item in fields(self)}
        for name in _OPTIONAL_FIELDS:
            value = getattr(self, name)
            if name not in _KIND_FIELDS[self.kind] and (type(value), value) != (type(defaults[name]), defaults[name]):
                raise ConfigurationError(f"AgentSwarmEvent.{name} must keep its default for a {self.kind.value} event.", details={"field": f"AgentSwarmEvent.{name}"})

    def _check_kind_fields(self) -> None:
        # @intent events-carry-what-their-kind-means
        # A sent message's id is its own sequence, and a delivery names
        # an earlier one, so a reader can pair every delivery with its
        # send; the stop reason, a tool call's name and status, and a
        # failure's cause are always present.
        kind = self.kind
        if kind in (AgentSwarmEventKind.MESSAGE_SENT, AgentSwarmEventKind.MESSAGE_DELIVERED):
            RecordFieldValidator.require_text(self.peer, "AgentSwarmEvent.peer")
        if kind is AgentSwarmEventKind.MESSAGE_SENT:
            RecordFieldValidator.require_int(self.message_id, "AgentSwarmEvent.message_id", minimum=self.sequence, maximum=self.sequence)
        if kind is AgentSwarmEventKind.MESSAGE_DELIVERED:
            RecordFieldValidator.require_int(self.message_id, "AgentSwarmEvent.message_id", minimum=1, maximum=self.sequence - 1)
        if kind in (AgentSwarmEventKind.MESSAGE_SENT, AgentSwarmEventKind.AGENT_FAILED, AgentSwarmEventKind.AGENT_IDLE):
            RecordFieldValidator.require_text(self.text, "AgentSwarmEvent.text", allow_blank=kind is AgentSwarmEventKind.AGENT_IDLE)
        if kind is AgentSwarmEventKind.TOOL_CALLED:
            RecordFieldValidator.require_text(self.tool_name, "AgentSwarmEvent.tool_name", one_line=True)
            RecordFieldValidator.require_enum(self.tool_status, ToolStatus, "AgentSwarmEvent.tool_status")
        if kind is AgentSwarmEventKind.SWARM_ENDED:
            RecordFieldValidator.require_enum(self.stop_reason, AgentSwarmStopReason, "AgentSwarmEvent.stop_reason")


AgentSwarmEventCallback = Callable[[AgentSwarmEvent], None | Awaitable[None]]


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
        # reason is the result's; a reader can then trust the record as
        # the full order of what happened.
        RecordFieldValidator.require_enum(self.stop_reason, AgentSwarmStopReason, "AgentSwarmResult.stop_reason")
        events = RecordFieldConverter.to_tuple(self.events, "AgentSwarmResult.events", item_type=AgentSwarmEvent)
        ended = [event for event in events if event.kind is AgentSwarmEventKind.SWARM_ENDED]
        if [event.sequence for event in events] != list(range(1, len(events) + 1)) or len(ended) != 1 or events[-1] is not ended[0]:
            raise ConfigurationError("AgentSwarmResult.events must be numbered 1 to N in order and end with its one swarm_ended event.", details={"field": "AgentSwarmResult.events"})
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


__all__ = ["AgentSwarmEvent", "AgentSwarmEventCallback", "AgentSwarmMember", "AgentSwarmResult"]

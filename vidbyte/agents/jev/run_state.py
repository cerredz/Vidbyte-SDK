"""FILE: vidbyte/agents/jev/run_state.py

PURPOSE: Defines JevAgent's structured run state, the matching finish-attempt handoff, the run report, and the contract every setting-enabled section implements.
ROLE IN CODEBASE: builders.py fills JevRunState once before the loop and JevRunHandoff at each finish attempt; runtime.py reviews each active JevRunSection and attaches a JevRunReport to the result.
ARCHITECTURE NOTE: The base state (goal, objective, mission, what_not_to_do, constraints, proposed_plan) is shared by every done check; each JevAgentSettings flag contributes one JevRunSection that adds its own state, handoff, and review, so builders never special-case a check.
COMMON MODIFICATION PATTERNS: Add a done check by subclassing JevRunSection, adding a JevRunSectionKey member, and enabling it from a JevAgentSettings flag in runtime.py.
KNOWN EDGE CASES: Payload parsing raises AgentExecutionError on any shape mismatch so a malformed builder answer can never pass as an empty section; a section whose state is not ACTIVE is never reviewed.
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.lib.constants.jev import JEV_EVENT_ID_PREFIX
from vidbyte.lib.dataclasses.agents import FinishReviewAction
from vidbyte.lib.enums.jev_run_state import (
    JevRunEventKind,
    JevRunSectionKey,
    JevSectionStatus,
)
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.runners.decision import DecisionModelRunner

JsonSchema = dict[str, Any]
JsonPayload = Mapping[str, Any]


class JevPayload:
    """Strict readers for builder JSON; every mismatch names the offending field."""

    @staticmethod
    def error(where: str, expected: str, received: object) -> AgentExecutionError:
        # Builds one context-rich error so repair prompts and logs point at the exact field.
        return AgentExecutionError(
            f"{where} must be {expected}; received {type(received).__name__}.",
            details={"field": where, "expected": expected, "received_type": type(received).__name__},
        )

    @classmethod
    def mapping(cls, payload: JsonPayload, key: str, *, where: str) -> JsonPayload:
        # Reads a nested JSON object.
        value = payload.get(key)
        if not isinstance(value, Mapping):
            raise cls.error(f"{where}.{key}", "an object", value)
        return value

    @classmethod
    def text(cls, payload: JsonPayload, key: str, *, where: str) -> str:
        # Reads a string field, stripping surrounding whitespace.
        value = payload.get(key)
        if not isinstance(value, str):
            raise cls.error(f"{where}.{key}", "a string", value)
        return value.strip()

    @classmethod
    def texts(cls, payload: JsonPayload, key: str, *, where: str) -> tuple[str, ...]:
        # Reads a list of strings, dropping blank entries.
        value = payload.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise cls.error(f"{where}.{key}", "a list of strings", value)
        return tuple(item.strip() for item in value if item.strip())

    @classmethod
    def flag(cls, payload: JsonPayload, key: str, *, where: str) -> bool:
        # Reads a JSON boolean without accepting truthy stand-ins.
        value = payload.get(key)
        if type(value) is not bool:
            raise cls.error(f"{where}.{key}", "true or false", value)
        return value

    @classmethod
    def objects(cls, payload: JsonPayload, key: str, *, where: str) -> tuple[JsonPayload, ...]:
        # Reads a list of JSON objects.
        value = payload.get(key)
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise cls.error(f"{where}.{key}", "a list of objects", value)
        return tuple(value)


class JevSchema:
    """Small JSON-schema constructors shared by the base state, the handoff, and every section."""

    @staticmethod
    def string(description: str) -> JsonSchema:
        # One string property.
        return {"type": "string", "description": description}

    @staticmethod
    def strings(description: str) -> JsonSchema:
        # One list-of-strings property.
        return {"type": "array", "items": {"type": "string"}, "description": description}

    @staticmethod
    def boolean(description: str) -> JsonSchema:
        # One boolean property.
        return {"type": "boolean", "description": description}

    @staticmethod
    def closed_object(properties: Mapping[str, JsonSchema]) -> JsonSchema:
        # An object whose every property is required and which admits no extra keys.
        return {"type": "object", "properties": dict(properties), "required": list(properties), "additionalProperties": False}


@dataclass(frozen=True, slots=True)
class JevRunEvent:
    """One numbered event of the run as the handoff builder sees it."""

    event_id: str
    kind: JevRunEventKind
    iteration: int
    label: str
    text: str

    def render(self) -> str:
        """Render the event as one event-log line."""
        return f"{self.event_id} [{self.label}] {self.text}"

    @staticmethod
    def position(event_id: str) -> int:
        """Return the ordinal of an event ID such as 'E12' so code can compare event order."""
        return int(event_id.removeprefix(JEV_EVENT_ID_PREFIX))


@dataclass(frozen=True, slots=True)
class JevSectionState:
    """Base record for one section of the run state; subclasses add the section's fields."""

    status: JevSectionStatus
    reason: str = ""

    def is_active(self) -> bool:
        """Return whether this section gates the run."""
        return self.status is JevSectionStatus.ACTIVE

    def to_payload(self) -> dict[str, Any]:
        """Render the section for the handoff builder's input."""
        return {"status": self.status.value, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class JevSectionHandoff:
    """Base record for one section's validated handoff entry; subclasses add the section's fields."""


@dataclass(frozen=True, slots=True)
class JevSectionReview:
    """Outcome of reviewing one active section at a finish attempt."""

    section: JevRunSectionKey
    passed: bool
    feedback: str = ""
    jev_available: bool = True
    jev_usage: JevUsage | None = None


class JevRunSection(ABC):
    """Contract for a done check that a JevAgentSettings flag adds to the run state."""

    key: ClassVar[JevRunSectionKey]

    @abstractmethod
    def state_instructions(self) -> str:
        """Return the prompt text the run-state builder receives for this section."""

    @abstractmethod
    def state_schema(self) -> JsonSchema:
        """Return the JSON schema of this section inside the run state's `sections` object."""

    @abstractmethod
    def parse_state(self, payload: JsonPayload, *, request: str) -> JevSectionState:
        """Validate the builder's section payload against the request and return its state."""

    @abstractmethod
    def agent_instructions(self, state: JevSectionState) -> str:
        """Return the text appended to the main agent's system prompt while this section is active."""

    @abstractmethod
    def handoff_instructions(self) -> str:
        """Return the prompt text the handoff builder receives for this section."""

    @abstractmethod
    def handoff_schema(self, state: JevSectionState) -> JsonSchema:
        """Return the JSON schema of this section inside the handoff's `sections` object."""

    @abstractmethod
    def parse_handoff(self, payload: JsonPayload, *, state: JevSectionState, event_ids: frozenset[str]) -> JevSectionHandoff:
        """Validate the handoff builder's section payload against the state and the event log."""

    @abstractmethod
    async def areview(self, *, state: JevSectionState, handoff: JevSectionHandoff, decider: DecisionModelRunner | None) -> JevSectionReview:
        """Decide whether this section passes, asking Jev only the recognition questions code cannot answer."""


@dataclass(frozen=True, slots=True)
class JevRunState:
    """Structured description of what the request asks for, built once before the main loop."""

    request: str
    goal: str = ""
    objective: str = ""
    mission: str = ""
    what_not_to_do: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    proposed_plan: tuple[str, ...] = ()
    sections: Mapping[JevRunSectionKey, JevSectionState] = field(default_factory=dict)

    @staticmethod
    def schema(section_schemas: Mapping[JevRunSectionKey, JsonSchema]) -> JsonSchema:
        """Return the builder's output schema: the base fields plus one property per enabled section."""
        return JevSchema.closed_object(
            {
                "goal": JevSchema.string("The broad aim behind the request, in one sentence."),
                "objective": JevSchema.string("The concrete outcome the request asks for, in one sentence."),
                "mission": JevSchema.string("The purpose the request says should guide the work, or an empty string."),
                "what_not_to_do": JevSchema.strings("Every action or result the request forbids or rules out."),
                "constraints": JevSchema.strings("Every limit or qualification the request places on the work."),
                "proposed_plan": JevSchema.strings("One to seven suggested steps; never treated as requirements."),
                "sections": JevSchema.closed_object({key.value: schema for key, schema in section_schemas.items()}),
            }
        )

    @classmethod
    def from_payload(cls, payload: JsonPayload, *, request: str, sections: Sequence[JevRunSection]) -> JevRunState:
        """Validate the builder's answer and let each enabled section parse its own part."""
        # @intent strict-builder-payloads
        # Any shape mismatch raises instead of defaulting, so a malformed answer can never become an empty
        # section that silently disables a done check; the runtime records the failure instead.
        section_payloads = JevPayload.mapping(payload, "sections", where="run_state")
        return cls(
            request=request,
            goal=JevPayload.text(payload, "goal", where="run_state"),
            objective=JevPayload.text(payload, "objective", where="run_state"),
            mission=JevPayload.text(payload, "mission", where="run_state"),
            what_not_to_do=JevPayload.texts(payload, "what_not_to_do", where="run_state"),
            constraints=JevPayload.texts(payload, "constraints", where="run_state"),
            proposed_plan=JevPayload.texts(payload, "proposed_plan", where="run_state"),
            sections={
                section.key: section.parse_state(JevPayload.mapping(section_payloads, section.key.value, where="run_state.sections"), request=request)
                for section in sections
            },
        )

    @classmethod
    def unavailable(cls, request: str, sections: Sequence[JevRunSection], reason: str) -> JevRunState:
        """Return a state whose sections are all UNAVAILABLE, used when the builder itself fails."""
        # @intent builder-failure-is-recorded-not-hidden
        # A failed build leaves the run ungated, but every section keeps a reason in the report so the
        # missing check is visible to callers instead of looking like a request with no requirements.
        return cls(request=request, sections={section.key: JevSectionState(JevSectionStatus.UNAVAILABLE, reason) for section in sections})

    def active_section_keys(self) -> tuple[JevRunSectionKey, ...]:
        """Return the keys of the sections that gate this run, in insertion order."""
        return tuple(key for key, state in self.sections.items() if state.is_active())

    def to_payload(self) -> dict[str, Any]:
        """Render the state as JSON-ready data for the handoff builder."""
        return {
            "goal": self.goal,
            "objective": self.objective,
            "mission": self.mission,
            "what_not_to_do": list(self.what_not_to_do),
            "constraints": list(self.constraints),
            "proposed_plan": list(self.proposed_plan),
            "sections": {key.value: state.to_payload() for key, state in self.sections.items()},
        }


@dataclass(frozen=True, slots=True)
class JevRunHandoff:
    """Structured account of the agent's recorded work, built at one finish attempt."""

    through_event_id: str
    overall_outcome: str
    limitations: tuple[str, ...] = ()
    sections: Mapping[JevRunSectionKey, JevSectionHandoff] = field(default_factory=dict)

    @staticmethod
    def schema(section_schemas: Mapping[JevRunSectionKey, JsonSchema]) -> JsonSchema:
        """Return the handoff builder's output schema: the base fields plus one property per active section."""
        return JevSchema.closed_object(
            {
                "overall_outcome": JevSchema.string("One or two sentences on what the run delivered."),
                "limitations": JevSchema.strings("Anything that limits what the event log can show."),
                "sections": JevSchema.closed_object({key.value: schema for key, schema in section_schemas.items()}),
            }
        )

    @classmethod
    def from_payload(cls, payload: JsonPayload, *, run_state: JevRunState, sections: Sequence[JevRunSection], event_ids: frozenset[str], through_event_id: str) -> JevRunHandoff:
        """Validate the handoff builder's answer and let each active section check its own entry."""
        section_payloads = JevPayload.mapping(payload, "sections", where="handoff")
        return cls(
            through_event_id=through_event_id,
            overall_outcome=JevPayload.text(payload, "overall_outcome", where="handoff"),
            limitations=JevPayload.texts(payload, "limitations", where="handoff"),
            sections={
                section.key: section.parse_handoff(
                    JevPayload.mapping(section_payloads, section.key.value, where="handoff.sections"),
                    state=run_state.sections[section.key],
                    event_ids=event_ids,
                )
                for section in sections
            },
        )


@dataclass(frozen=True, slots=True)
class JevFinishReviewRecord:
    """What happened at one finish attempt: the handoff, each section's review, and the action taken."""

    through_event_id: str
    action: FinishReviewAction
    handoff: JevRunHandoff | None = None
    reviews: tuple[JevSectionReview, ...] = ()
    handoff_failure: str = ""


@dataclass(frozen=True, slots=True)
class JevRunReport:
    """Run-level record attached to the result metadata whenever a run-state section is enabled."""

    run_state: JevRunState
    finish_reviews: tuple[JevFinishReviewRecord, ...] = ()
    builder_usage: tuple[UsageRollup, ...] = ()


__all__ = [
    "JevFinishReviewRecord",
    "JevPayload",
    "JevRunEvent",
    "JevRunHandoff",
    "JevRunReport",
    "JevRunSection",
    "JevRunState",
    "JevSchema",
    "JevSectionHandoff",
    "JevSectionReview",
    "JevSectionState",
]

"""FILE: vidbyte/agents/jev/run_state.py

PURPOSE: Owns validated run-state, run-snapshot, handoff, and multipart completion-decision records shared by every Jev done check.
ROLE IN CODEBASE: The Jev state builder and handoff builder exchange these typed records with JevRuntime.
ARCHITECTURE NOTE: These records are feature-local and ephemeral; provider transport records remain in vidbyte.lib.
COMMON MODIFICATION PATTERNS: Change a record, its strict output schema, prompt instructions, and contract tests together.
KNOWN EDGE CASES: Empty deliverables are valid; handoff IDs must match the generated state IDs exactly; sections exist only for enabled presets.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-scope-coverage-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-multipart-done-criteria.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from vidbyte.agents.jev.evidence import JevEvidenceReference
from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.scope_coverage.handoff import JevScopeHandoff
from vidbyte.agents.jev.scope_coverage.state import JevScopeSection
from vidbyte.lib.errors import OutputSchemaViolationError
from vidbyte.tools.types import ToolCallContext


@dataclass(frozen=True, slots=True)
class JevDeliverable:
    """One distinct requested output and the observable condition that defines completion."""

    id: str
    description: str
    completion_signal: str


@dataclass(frozen=True, slots=True)
class JevRunState:
    """Stable request-shaped context generated once before the main agent loop."""

    goal: str
    objective: str
    mission: str
    what_not_to_do: tuple[str, ...]
    sections: Mapping[str, str]
    deliverables: tuple[JevDeliverable, ...]
    scope: JevScopeSection | None = None
    presets: tuple[JevPresets, ...] = (JevPresets.MultiPart,)

    def to_payload(self) -> dict[str, Any]:
        # Returns a detached, JSON-compatible initial state shared by the handoff builder and Jev policy.
        payload: dict[str, Any] = {
            "goal": self.goal,
            "objective": self.objective,
            "mission": self.mission,
            "what_not_to_do": list(self.what_not_to_do),
            "sections": dict(self.sections),
        }
        if JevPresets.MultiPart in self.presets:
            payload["multi_part"] = {
                "deliverables": [
                    {"id": item.id, "description": item.description, "completion_signal": item.completion_signal}
                    for item in self.deliverables
                ]
            }
        if self.scope is not None:
            payload["scope"] = self.scope.to_payload()
        return payload

    def with_scope(self, scope: JevScopeSection) -> JevRunState:
        # Returns a copy carrying a reviewed scope section; every other field is unchanged.
        return replace(self, scope=scope)

    @classmethod
    def from_payload(cls, payload: object, *, presets: tuple[JevPresets, ...] = (JevPresets.MultiPart,), original_request: str | None = None) -> JevRunState:
        # Validates the base fields plus the section of every enabled preset.
        # @intent sections-follow-enabled-presets
        # A section is required exactly when its preset is enabled, so a disabled check costs no generated tokens.
        if not isinstance(payload, Mapping):
            raise cls._violation(payload, "state must be a JSON object")
        try:
            goal = cls._required_text(payload.get("goal"), "goal")
            objective = cls._required_text(payload.get("objective"), "objective")
            mission = cls._required_text(payload.get("mission"), "mission")
            what_not_to_do = cls._text_tuple(payload.get("what_not_to_do"), "what_not_to_do")
            sections = cls._text_mapping(payload.get("sections"), "sections")
            deliverables = cls._deliverables(payload.get("multi_part")) if JevPresets.MultiPart in presets else ()
            scope = None
            if JevPresets.ScopeCoverage in presets:
                if original_request is None:
                    raise ValueError("the scope section is validated against the original request, which was not supplied")
                scope = JevScopeSection.from_payload(payload.get("scope"), original_request=original_request, deliverable_ids=[item.id for item in deliverables])
        except (TypeError, ValueError) as exc:
            raise cls._violation(payload, str(exc)) from exc
        return cls(goal, objective, mission, what_not_to_do, sections, deliverables, scope, tuple(presets))

    @classmethod
    def _deliverables(cls, multi_part: object) -> tuple[JevDeliverable, ...]:
        # Validates the multipart section's deliverable list, identifiers, and uniqueness.
        raw_deliverables = multi_part.get("deliverables") if isinstance(multi_part, Mapping) else None
        if not isinstance(raw_deliverables, Sequence) or isinstance(raw_deliverables, (str, bytes)):
            raise TypeError("multi_part.deliverables must be an array")
        deliverables = tuple(cls._deliverable(item) for item in raw_deliverables)
        identifiers = tuple(item.id for item in deliverables)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("multi_part.deliverables IDs must be unique")
        if any(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", identifier) is None for identifier in identifiers):
            raise ValueError("deliverable IDs must start with a lowercase letter and contain only lowercase letters, digits, or underscores")
        return deliverables

    @staticmethod
    def output_schema(presets: tuple[JevPresets, ...] = (JevPresets.MultiPart,)) -> dict[str, Any]:
        # Returns the strict structured-output schema for the one-time request decomposition.
        text = {"type": "string", "minLength": 1}
        properties: dict[str, Any] = {
            "goal": text,
            "objective": text,
            "mission": text,
            "what_not_to_do": {"type": "array", "items": text},
            "sections": {"type": "object", "additionalProperties": text},
        }
        required = ["goal", "objective", "mission", "what_not_to_do", "sections"]
        if JevPresets.MultiPart in presets:
            properties["multi_part"] = {
                "type": "object",
                "properties": {
                    "deliverables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"id": text, "description": text, "completion_signal": text},
                            "required": ["id", "description", "completion_signal"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["deliverables"],
                "additionalProperties": False,
            }
            required.append("multi_part")
        if JevPresets.ScopeCoverage in presets:
            properties["scope"] = JevScopeSection.output_schema()
            required.append("scope")
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}

    @classmethod
    def _deliverable(cls, value: object) -> JevDeliverable:
        # Converts one structured deliverable and rejects absent or blank identifying content.
        if not isinstance(value, Mapping):
            raise TypeError("each deliverable must be an object")
        return JevDeliverable(
            cls._required_text(value.get("id"), "deliverable.id"),
            cls._required_text(value.get("description"), "deliverable.description"),
            cls._required_text(value.get("completion_signal"), "deliverable.completion_signal"),
        )

    @staticmethod
    def _required_text(value: object, field_name: str) -> str:
        # Requires a non-blank string for each state or handoff field used in a decision.
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-blank string")
        return value.strip()

    @classmethod
    def _text_tuple(cls, value: object, field_name: str) -> tuple[str, ...]:
        # Validates a list of text entries and freezes it for run-local reuse.
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise TypeError(f"{field_name} must be an array of strings")
        return tuple(cls._required_text(item, field_name) for item in value)

    @classmethod
    def _text_mapping(cls, value: object, field_name: str) -> dict[str, str]:
        # Validates named section content and returns a detached mapping.
        if not isinstance(value, Mapping):
            raise TypeError(f"{field_name} must be an object of strings")
        return {cls._required_text(key, f"{field_name} key"): cls._required_text(item, field_name) for key, item in value.items()}

    @staticmethod
    def _violation(payload: object, reason: str) -> OutputSchemaViolationError:
        # Builds a safe typed error without exposing credentials or unrelated runtime context.
        raw = json.dumps(payload, ensure_ascii=False, default=str)[:4_000]
        return OutputSchemaViolationError("Jev run state did not satisfy its required structure.", raw_output=raw, validation_error=reason)


@dataclass(frozen=True, slots=True)
class JevRunSnapshot:
    """Bounded direct observations supplied to the end-of-attempt handoff builder."""

    original_request: str
    state: JevRunState
    iteration_outputs: tuple[str, ...]
    tool_calls: tuple[Mapping[str, Any], ...]
    final_output: str

    def evidence_sources(self) -> Mapping[str, str]:
        # Assigns deterministic IDs to exact text surfaces the handoff may cite as run evidence.
        sources = {f"iteration_{index}": value for index, value in enumerate(self.iteration_outputs, start=1) if value.strip()}
        for index, call in enumerate(self.tool_calls, start=1):
            sources[f"tool_call_{index}"] = "\n".join(
                (
                    f"Tool: {call['name']}",
                    "Arguments: " + json.dumps(dict(call["arguments"]), ensure_ascii=False, sort_keys=True, default=str),
                    f"State: {call['state']}",
                    f"Output: {call['output']}",
                )
            )
        if self.final_output.strip():
            sources["final_answer"] = self.final_output
        return sources

    @classmethod
    def from_runtime(cls, original_request: str, state: JevRunState, iteration_outputs: Sequence[str], tool_calls: Sequence[ToolCallContext], final_output: str) -> JevRunSnapshot:
        # Projects live loop observations into detached, JSON-safe tool-call records.
        # @intent snapshot-direct-observations
        # Stable evidence source IDs must point to the exact runtime text captured for this finish attempt.
        rendered_calls = tuple(
            {
                "name": call.name,
                "arguments": dict(call.arguments),
                "state": str(getattr(call.state, "value", call.state)),
                "output": call.output,
            }
            for call in tool_calls
        )
        return cls(original_request, state, tuple(iteration_outputs), rendered_calls, final_output)

    def render(self) -> str:
        # Serializes run observations and exact source IDs for grounded handoff generation.
        # @intent preserve-citable-run-source
        # Handoff citations are validated against these exact source strings before Jev receives them.
        payload = {
            "original_request": self.original_request,
            "initial_state": self.state.to_payload(),
            "iteration_outputs": list(self.iteration_outputs),
            "tool_calls": [dict(item) for item in self.tool_calls],
            "candidate_final_output": self.final_output,
            "evidence_sources": self.evidence_sources(),
        }
        if self.state.scope is not None:
            payload["checked_scope_dimension_ids"] = [item.id for item in self.state.scope.checked_dimensions()]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


@dataclass(frozen=True, slots=True)
class JevDeliverableHandoff:
    """Run-authored progress and direct evidence for one requested deliverable."""

    id: str
    status: str
    evidence: tuple[JevEvidenceReference, ...]
    remaining: str


@dataclass(frozen=True, slots=True)
class JevRunHandoff:
    """Structured handoff corresponding exactly to one generated JevRunState."""

    deliverables: tuple[JevDeliverableHandoff, ...]
    scope: JevScopeHandoff | None = None

    @staticmethod
    def needs_deliverables(state: JevRunState) -> bool:
        # Returns whether the multipart section of this handoff must be generated.
        return bool(state.deliverables)

    @staticmethod
    def needs_scope(state: JevRunState) -> bool:
        # Returns whether the scope section of this handoff must be generated.
        return state.scope is not None and bool(state.scope.checked_dimensions())

    @classmethod
    def from_payload(cls, payload: object, state: JevRunState, snapshot: JevRunSnapshot) -> JevRunHandoff:
        # Checks section coverage and every citation before classification can be requested.
        if not isinstance(payload, Mapping):
            raise JevRunState._violation(payload, "handoff must be a JSON object")
        sources = snapshot.evidence_sources()
        try:
            deliverables = cls._deliverables(payload.get("deliverables"), state, sources) if cls.needs_deliverables(state) else ()
            scope = JevScopeHandoff.from_payload(payload.get("scope"), state.scope, sources) if cls.needs_scope(state) and state.scope is not None else None
        except (TypeError, ValueError) as exc:
            raise JevRunState._violation(payload, str(exc)) from exc
        return cls(deliverables, scope)

    @classmethod
    def _deliverables(cls, raw_items: object, state: JevRunState, sources: Mapping[str, str]) -> tuple[JevDeliverableHandoff, ...]:
        # Parses one record per state deliverable and orders them by the state's identifiers.
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            raise TypeError("handoff.deliverables must be an array")
        items = tuple(cls._item(item, sources) for item in raw_items)
        actual = tuple(item.id for item in items)
        expected = tuple(item.id for item in state.deliverables)
        if len(set(actual)) != len(actual):
            raise ValueError("handoff deliverable IDs must be unique")
        if set(actual) != set(expected) or len(actual) != len(expected):
            raise ValueError(f"handoff IDs must exactly match state IDs; expected {sorted(expected)}, got {sorted(actual)}")
        by_id = {item.id: item for item in items}
        return tuple(by_id[item.id] for item in state.deliverables)

    @staticmethod
    def output_schema(state: JevRunState) -> dict[str, Any]:
        # Composes the handoff schema from the sections this run's state requires.
        properties: dict[str, Any] = {}
        if JevRunHandoff.needs_deliverables(state):
            properties["deliverables"] = JevRunHandoff._deliverables_schema(state)
        if JevRunHandoff.needs_scope(state) and state.scope is not None:
            properties["scope"] = JevScopeHandoff.output_schema(state.scope)
        return {"type": "object", "properties": properties, "required": sorted(properties), "additionalProperties": False}

    @staticmethod
    def _deliverables_schema(state: JevRunState) -> dict[str, Any]:
        # Constrains the model to one structured record per generated deliverable identifier.
        text = {"type": "string", "minLength": 1}
        evidence = JevEvidenceReference.schema()
        item = {
            "type": "object",
            "properties": {
                "id": text,
                "status": {"type": "string", "enum": ["complete", "incomplete", "unclear"]},
                "evidence": {"type": "array", "items": evidence},
                "remaining": text,
            },
            "required": ["id", "status", "evidence", "remaining"],
            "additionalProperties": False,
        }
        return {"type": "array", "items": item, "minItems": len(state.deliverables), "maxItems": len(state.deliverables)}

    @classmethod
    def _item(cls, value: object, sources: Mapping[str, str]) -> JevDeliverableHandoff:
        # Parses a handoff item and verifies every excerpt against a known run source.
        if not isinstance(value, Mapping):
            raise TypeError("each handoff deliverable must be an object")
        status = JevRunState._required_text(value.get("status"), "handoff.status")
        if status.casefold() not in {"complete", "incomplete", "unclear"}:
            raise ValueError("handoff.status must be complete, incomplete, or unclear")
        raw_evidence = value.get("evidence")
        if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, (str, bytes)):
            raise TypeError("handoff.evidence must be an array of source-linked excerpts")
        evidence_refs = tuple(cls._evidence(item, sources) for item in raw_evidence)
        return JevDeliverableHandoff(
            JevRunState._required_text(value.get("id"), "handoff.id"),
            status,
            evidence_refs,
            JevRunState._required_text(value.get("remaining"), "handoff.remaining"),
        )

    @staticmethod
    def _evidence(value: object, sources: Mapping[str, str]) -> JevEvidenceReference:
        # Rejects invented source IDs and excerpts not present exactly in the cited source.
        return JevEvidenceReference.parse(value, sources, field_name="handoff.evidence")

    def by_id(self) -> Mapping[str, JevDeliverableHandoff]:
        # Returns validated handoff records keyed by their state-matched deliverable IDs.
        return {item.id: item for item in self.deliverables}

    def to_payload(self) -> dict[str, Any]:
        # Produces a detached JSON-compatible shape of every generated section.
        payload: dict[str, Any] = {"deliverables": [{"id": item.id, "status": item.status, "evidence": [evidence.to_payload() for evidence in item.evidence], "remaining": item.remaining} for item in self.deliverables]}
        if self.scope is not None:
            payload["scope"] = self.scope.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class JevDeliverableDecision:
    """One calibrated classification result associated with its exact deliverable ID."""

    id: str
    complete: bool
    probability: float
    evidence_gap: str


@dataclass(frozen=True, slots=True)
class JevDoneCriteriaDecision:
    """Combined policy outcome after deterministic code joins individual Jev answers."""

    complete: bool
    deliverables: tuple[JevDeliverableDecision, ...]
    attempt: int

    def metadata(self) -> dict[str, Any]:
        # Returns public, credential-free evaluation details for AgentResult metadata.
        # @intent expose-final-check-only
        # Report the latest decision without serializing prompts, provider bodies, or credentials.
        return {
            "complete": self.complete,
            "deliverables": {item.id: {"complete": item.complete, "probability": item.probability, "evidence_gap": item.evidence_gap} for item in self.deliverables},
        }

    def continuation_feedback(self) -> str:
        # Names only incomplete deliverables and includes their structured handoff gap for the main agent.
        incomplete = [item for item in self.deliverables if not item.complete]
        lines = ["The multipart completion check found requested work that is not yet clearly complete."]
        lines.extend(f"- {item.id}: {item.evidence_gap}" for item in incomplete)
        lines.append("Continue the existing task and address these specific gaps before giving a final answer.")
        return "\n".join(lines)


__all__ = [
    "JevDeliverable",
    "JevDeliverableDecision",
    "JevDeliverableHandoff",
    "JevDoneCriteriaDecision",
    "JevEvidenceReference",
    "JevRunHandoff",
    "JevRunSnapshot",
    "JevRunState",
]

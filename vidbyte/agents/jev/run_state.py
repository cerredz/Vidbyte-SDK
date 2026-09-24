"""FILE: vidbyte/agents/jev/run_state.py

PURPOSE: Owns validated multipart run-state, run-snapshot, handoff, and completion-decision records.
ROLE IN CODEBASE: The Jev state builder and handoff builder exchange these typed records with JevRuntime.
ARCHITECTURE NOTE: These records are feature-local and ephemeral; provider transport records remain in vidbyte.lib.
COMMON MODIFICATION PATTERNS: Change a record, its strict output schema, prompt instructions, and contract tests together.
KNOWN EDGE CASES: Empty deliverables are valid; handoff IDs must match the generated state IDs exactly.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-multipart-done-criteria.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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

    def to_payload(self) -> dict[str, Any]:
        # Returns a detached, JSON-compatible initial state shared by the handoff builder and Jev policy.
        return {
            "goal": self.goal,
            "objective": self.objective,
            "mission": self.mission,
            "what_not_to_do": list(self.what_not_to_do),
            "sections": dict(self.sections),
            "multi_part": {
                "deliverables": [
                    {"id": item.id, "description": item.description, "completion_signal": item.completion_signal}
                    for item in self.deliverables
                ]
            },
        }

    @classmethod
    def from_payload(cls, payload: object) -> JevRunState:
        # Validates required state fields and creates immutable nested deliverable records.
        if not isinstance(payload, Mapping):
            raise cls._violation(payload, "state must be a JSON object")
        try:
            goal = cls._required_text(payload.get("goal"), "goal")
            objective = cls._required_text(payload.get("objective"), "objective")
            mission = cls._required_text(payload.get("mission"), "mission")
            what_not_to_do = cls._text_tuple(payload.get("what_not_to_do"), "what_not_to_do")
            sections = cls._text_mapping(payload.get("sections"), "sections")
            multi_part = payload.get("multi_part")
            raw_deliverables = multi_part.get("deliverables") if isinstance(multi_part, Mapping) else None
            if not isinstance(raw_deliverables, Sequence) or isinstance(raw_deliverables, (str, bytes)):
                raise TypeError("multi_part.deliverables must be an array")
            deliverables = tuple(cls._deliverable(item) for item in raw_deliverables)
            identifiers = tuple(item.id for item in deliverables)
            if len(set(identifiers)) != len(identifiers):
                raise ValueError("multi_part.deliverables IDs must be unique")
            if any(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", identifier) is None for identifier in identifiers):
                raise ValueError("deliverable IDs must start with a lowercase letter and contain only lowercase letters, digits, or underscores")
        except (TypeError, ValueError) as exc:
            raise cls._violation(payload, str(exc)) from exc
        return cls(goal, objective, mission, what_not_to_do, sections, deliverables)

    @staticmethod
    def output_schema() -> dict[str, Any]:
        # Returns the strict structured-output schema for the one-time request decomposition.
        text = {"type": "string", "minLength": 1}
        return {
            "type": "object",
            "properties": {
                "goal": text,
                "objective": text,
                "mission": text,
                "what_not_to_do": {"type": "array", "items": text},
                "sections": {"type": "object", "additionalProperties": text},
                "multi_part": {
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
                },
            },
            "required": ["goal", "objective", "mission", "what_not_to_do", "sections", "multi_part"],
            "additionalProperties": False,
        }

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
        return OutputSchemaViolationError("Jev multipart state did not satisfy its required structure.", raw_output=raw, validation_error=reason)


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
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


@dataclass(frozen=True, slots=True)
class JevDeliverableHandoff:
    """Run-authored progress and direct evidence for one requested deliverable."""

    id: str
    status: str
    evidence: tuple[JevEvidenceReference, ...]
    remaining: str


@dataclass(frozen=True, slots=True)
class JevEvidenceReference:
    """One exact excerpt tied to a known iteration, tool call, or final-answer source."""

    source_id: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class JevRunHandoff:
    """Structured handoff corresponding exactly to one generated JevRunState."""

    deliverables: tuple[JevDeliverableHandoff, ...]

    @classmethod
    def from_payload(cls, payload: object, state: JevRunState, snapshot: JevRunSnapshot) -> JevRunHandoff:
        # Checks deliverable coverage and every citation before classification can be requested.
        raw_items = payload.get("deliverables") if isinstance(payload, Mapping) else None
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            raise JevRunState._violation(payload, "handoff.deliverables must be an array")
        sources = snapshot.evidence_sources()
        try:
            items = tuple(cls._item(item, sources) for item in raw_items)
            actual = tuple(item.id for item in items)
            expected = tuple(item.id for item in state.deliverables)
            if len(set(actual)) != len(actual):
                raise ValueError("handoff deliverable IDs must be unique")
            if set(actual) != set(expected) or len(actual) != len(expected):
                raise ValueError(f"handoff IDs must exactly match state IDs; expected {sorted(expected)}, got {sorted(actual)}")
        except (TypeError, ValueError) as exc:
            raise JevRunState._violation(payload, str(exc)) from exc
        by_id = {item.id: item for item in items}
        return cls(tuple(by_id[item.id] for item in state.deliverables))

    @staticmethod
    def output_schema(state: JevRunState) -> dict[str, Any]:
        # Constrains the model to one structured record per generated deliverable identifier.
        text = {"type": "string", "minLength": 1}
        evidence = {"type": "object", "properties": {"source_id": text, "excerpt": text}, "required": ["source_id", "excerpt"], "additionalProperties": False}
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
        return {
            "type": "object",
            "properties": {"deliverables": {"type": "array", "items": item, "minItems": len(state.deliverables), "maxItems": len(state.deliverables)}},
            "required": ["deliverables"],
            "additionalProperties": False,
        }

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
        if not isinstance(value, Mapping):
            raise TypeError("each evidence reference must be an object")
        source_id = JevRunState._required_text(value.get("source_id"), "handoff.evidence.source_id")
        excerpt = JevRunState._required_text(value.get("excerpt"), "handoff.evidence.excerpt")
        source = sources.get(source_id)
        if source is None:
            raise ValueError(f"unknown evidence source ID {source_id!r}")
        if excerpt not in source:
            raise ValueError(f"evidence excerpt is not present in source {source_id!r}")
        return JevEvidenceReference(source_id, excerpt)

    def by_id(self) -> Mapping[str, JevDeliverableHandoff]:
        # Returns validated handoff records keyed by their state-matched deliverable IDs.
        return {item.id: item for item in self.deliverables}

    def to_payload(self) -> dict[str, Any]:
        # Produces a detached JSON-compatible shape for Jev's single-item classification state.
        return {"deliverables": [{"id": item.id, "status": item.status, "evidence": [{"source_id": evidence.source_id, "excerpt": evidence.excerpt} for evidence in item.evidence], "remaining": item.remaining} for item in self.deliverables]}


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
            "preset": "multi_part",
            "attempts": self.attempt,
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

"""FILE: vidbyte/agents/jev/motivating_case/state.py

PURPOSE: Owns the validated run state for the motivating-case done check: the boundary scenarios a request is about.
ROLE IN CODEBASE: MotivatingCaseStateBuilderAgent parses its output through MotivatingCaseState.from_payload; the handoff builder, checker, and Jev questions all read these records.
ARCHITECTURE NOTE: The state is built once per run from the request; every field that a Jev question uses as a definition (condition, near_miss, ordinary_flow) is written here, not by Jev.
COMMON MODIFICATION PATTERNS: Change a field, its output schema, the state-builder prompt, and tests/test_jev_motivating_case.py together.
KNOWN EDGE CASES: An empty scenario list is valid and disables the check; quotes must be verbatim request text after whitespace normalization.
RELATED DOCS: docs/design/jev-motivating-case.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_MOTIVATING_CASE_MAX_MOTIVATING,
    JEV_MOTIVATING_CASE_MAX_SCENARIOS,
)
from vidbyte.lib.enums import JevBoundaryKind, JevExerciseMode, JevScenarioRole
from vidbyte.lib.errors import OutputSchemaViolationError

_SCENARIO_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")
_WHITESPACE = re.compile(r"\s+")


class VerbatimText:
    """Whitespace-insensitive verbatim matching shared by state and handoff validation."""

    @staticmethod
    def normalize(text: str) -> str:
        # Collapses every whitespace run so line wrapping and JSON escaping cannot break a verbatim match.
        return _WHITESPACE.sub(" ", text).strip()

    @classmethod
    def contains(cls, haystack: str, needle: str) -> bool:
        # Reports whether needle appears in haystack after both are normalized; blank needles never match.
        normalized = cls.normalize(needle)
        return bool(normalized) and normalized in cls.normalize(haystack)


@dataclass(frozen=True, slots=True)
class MotivatingScenario:
    """One boundary condition the request is about, with the definitions Jev will match against."""

    id: str
    role: JevScenarioRole
    kind: JevBoundaryKind
    source_quote: str
    target: str
    condition: str
    near_miss: str
    expected_behavior: str | None
    literal_inputs: tuple[str, ...]
    exercise_mode: JevExerciseMode

    def blocks_finish(self) -> bool:
        # Only scenarios the user named can hold a run open; implied ones are reported, never enforced.
        return self.role is not JevScenarioRole.IMPLIED

    def to_payload(self) -> dict[str, Any]:
        # Returns the JSON shape shared with the handoff builder and run metadata.
        return {
            "id": self.id,
            "role": self.role.value,
            "kind": self.kind.value,
            "source_quote": self.source_quote,
            "target": self.target,
            "condition": self.condition,
            "near_miss": self.near_miss,
            "expected_behavior": self.expected_behavior or "",
            "literal_inputs": list(self.literal_inputs),
            "exercise_mode": self.exercise_mode.value,
        }


@dataclass(frozen=True, slots=True)
class MotivatingCaseState:
    """Request-derived state for the motivating-case check, generated once before the main loop."""

    ordinary_flow: str
    testing_restriction_quote: str | None
    scenarios: tuple[MotivatingScenario, ...]

    def is_empty(self) -> bool:
        # An empty state means the request names no boundary condition, so no finish check runs.
        return not self.scenarios

    def to_payload(self) -> dict[str, Any]:
        # Returns a detached JSON-compatible copy for prompts and metadata.
        return {
            "ordinary_flow": self.ordinary_flow,
            "testing_restriction_quote": self.testing_restriction_quote or "",
            "scenarios": [scenario.to_payload() for scenario in self.scenarios],
        }

    @classmethod
    def from_payload(cls, payload: object, request: str) -> MotivatingCaseState:
        # Validates builder output against the schema rules and the request's own wording.
        # @intent builder-output-is-untrusted
        # The state defines every later Jev question, so a paraphrased quote or invented restriction is rejected rather than repaired.
        if not isinstance(payload, Mapping):
            raise cls.violation(payload, "state must be a JSON object")
        try:
            ordinary_flow = cls._text(payload.get("ordinary_flow"), "ordinary_flow")
            restriction = cls._optional_text(payload.get("testing_restriction_quote"), "testing_restriction_quote")
            if restriction is not None and not VerbatimText.contains(request, restriction):
                raise ValueError("testing_restriction_quote must be verbatim request text")
            raw = payload.get("scenarios")
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                raise ValueError("scenarios must be an array")
            scenarios = tuple(cls._scenario(item, request) for item in raw)
            cls._check_scenario_set(scenarios)
        except (TypeError, ValueError) as exc:
            raise cls.violation(payload, str(exc)) from exc
        return cls(ordinary_flow, restriction, scenarios)

    @staticmethod
    def output_schema() -> dict[str, Any]:
        # Returns the strict structured-output schema; absent optional text is the empty string for portability.
        text = {"type": "string", "minLength": 1}
        optional = {"type": "string"}
        scenario = {
            "type": "object",
            "properties": {
                "id": text,
                "role": {"type": "string", "enum": [member.value for member in JevScenarioRole]},
                "kind": {"type": "string", "enum": [member.value for member in JevBoundaryKind]},
                "source_quote": text,
                "target": text,
                "condition": text,
                "near_miss": text,
                "expected_behavior": optional,
                "literal_inputs": {"type": "array", "items": text},
                "exercise_mode": {"type": "string", "enum": [member.value for member in JevExerciseMode]},
            },
            "required": ["id", "role", "kind", "source_quote", "target", "condition", "near_miss", "expected_behavior", "literal_inputs", "exercise_mode"],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {
                "ordinary_flow": text,
                "testing_restriction_quote": optional,
                "scenarios": {"type": "array", "items": scenario, "maxItems": JEV_MOTIVATING_CASE_MAX_SCENARIOS},
            },
            "required": ["ordinary_flow", "testing_restriction_quote", "scenarios"],
            "additionalProperties": False,
        }

    @classmethod
    def _scenario(cls, value: object, request: str) -> MotivatingScenario:
        # Converts one scenario and proves its quote came from the request rather than the builder.
        # @intent quote-proves-user-origin
        # A verbatim quote is the only proof a scenario came from the user and not from the builder's own brainstorming.
        if not isinstance(value, Mapping):
            raise ValueError("each scenario must be an object")
        scenario_id = cls._text(value.get("id"), "scenario.id")
        if _SCENARIO_ID.fullmatch(scenario_id) is None:
            raise ValueError(f"scenario id {scenario_id!r} must be lowercase snake_case starting with a letter")
        quote = cls._text(value.get("source_quote"), "scenario.source_quote")
        if not VerbatimText.contains(request, quote):
            raise ValueError(f"scenario {scenario_id!r} source_quote is not verbatim request text")
        literals = value.get("literal_inputs")
        if not isinstance(literals, Sequence) or isinstance(literals, (str, bytes)):
            raise ValueError(f"scenario {scenario_id!r} literal_inputs must be an array")
        return MotivatingScenario(
            id=scenario_id,
            role=JevScenarioRole(cls._text(value.get("role"), "scenario.role")),
            kind=JevBoundaryKind(cls._text(value.get("kind"), "scenario.kind")),
            source_quote=quote,
            target=cls._text(value.get("target"), "scenario.target"),
            condition=cls._text(value.get("condition"), "scenario.condition"),
            near_miss=cls._text(value.get("near_miss"), "scenario.near_miss"),
            expected_behavior=cls._optional_text(value.get("expected_behavior"), "scenario.expected_behavior"),
            literal_inputs=tuple(cls._text(item, "scenario.literal_inputs") for item in literals),
            exercise_mode=JevExerciseMode(cls._text(value.get("exercise_mode"), "scenario.exercise_mode")),
        )

    @staticmethod
    def _check_scenario_set(scenarios: tuple[MotivatingScenario, ...]) -> None:
        # Enforces unique IDs and the caps that keep the check bounded and focused on what the user asked.
        identifiers = [scenario.id for scenario in scenarios]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("scenario ids must be unique")
        if len(scenarios) > JEV_MOTIVATING_CASE_MAX_SCENARIOS:
            raise ValueError(f"at most {JEV_MOTIVATING_CASE_MAX_SCENARIOS} scenarios are allowed")
        motivating = sum(1 for scenario in scenarios if scenario.role is JevScenarioRole.MOTIVATING)
        if motivating > JEV_MOTIVATING_CASE_MAX_MOTIVATING:
            raise ValueError(f"at most {JEV_MOTIVATING_CASE_MAX_MOTIVATING} motivating scenarios are allowed")

    @staticmethod
    def _text(value: object, field_name: str) -> str:
        # Requires a non-blank string for every field a decision depends on.
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-blank string")
        return value.strip()

    @staticmethod
    def _optional_text(value: object, field_name: str) -> str | None:
        # Maps the schema's empty-string convention back to None.
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string")
        return value.strip() or None

    @staticmethod
    def violation(payload: object, reason: str) -> OutputSchemaViolationError:
        # Builds a bounded typed error that names the broken rule without leaking unrelated context.
        raw = json.dumps(payload, ensure_ascii=False, default=str)[:4_000]
        return OutputSchemaViolationError(f"Jev motivating-case output did not satisfy its required structure: {reason}.", raw_output=raw, validation_error=reason)


__all__ = ["MotivatingCaseState", "MotivatingScenario", "VerbatimText"]

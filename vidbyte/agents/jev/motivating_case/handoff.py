"""FILE: vidbyte/agents/jev/motivating_case/handoff.py

PURPOSE: Owns the finish-attempt handoff for the motivating-case check: per-scenario event refs and verbatim quotes.
ROLE IN CODEBASE: MotivatingCaseHandoffBuilderAgent parses its output here; ScenarioEvidenceChecker verifies every ref and quote before Jev sees any of it.
ARCHITECTURE NOTE: The handoff links evidence across turns but carries no verdict field, so the generative builder can never decide the check.
COMMON MODIFICATION PATTERNS: Change a field, its output schema, the handoff-builder prompt, the checker, and tests together.
KNOWN EDGE CASES: Blank strings mean absent; the handoff must cover exactly the state's scenario ids, in any order.
RELATED DOCS: docs/design/jev-motivating-case.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.jev.motivating_case.state import MotivatingCaseState
from vidbyte.lib.constants.jev import JEV_MOTIVATING_CASE_EXCERPT_CHARS
from vidbyte.lib.errors import OutputSchemaViolationError

_FIELDS: tuple[str, ...] = (
    "case_name",
    "setup_ref",
    "setup_quote",
    "outcome_ref",
    "outcome_quote",
    "inspection_ref",
    "inspection_quote",
    "blocker_ref",
    "blocker_quote",
)


@dataclass(frozen=True, slots=True)
class ScenarioExercise:
    """Where the run built, ran, inspected, or was blocked on one scenario, as claimed by the handoff builder."""

    scenario_id: str
    case_name: str | None = None
    setup_ref: str | None = None
    setup_quote: str | None = None
    outcome_ref: str | None = None
    outcome_quote: str | None = None
    inspection_ref: str | None = None
    inspection_quote: str | None = None
    blocker_ref: str | None = None
    blocker_quote: str | None = None


@dataclass(frozen=True, slots=True)
class MotivatingCaseHandoff:
    """Handoff with exactly one ScenarioExercise per state scenario, in state order."""

    exercises: tuple[ScenarioExercise, ...]

    def by_id(self) -> Mapping[str, ScenarioExercise]:
        # Returns exercises keyed by their scenario id.
        return {exercise.scenario_id: exercise for exercise in self.exercises}

    @classmethod
    def empty(cls, state: MotivatingCaseState) -> MotivatingCaseHandoff:
        # Builds a handoff that claims nothing, used when only code-side recovery can find evidence.
        return cls(tuple(ScenarioExercise(scenario.id) for scenario in state.scenarios))

    @classmethod
    def from_payload(cls, payload: object, state: MotivatingCaseState) -> MotivatingCaseHandoff:
        # Parses builder output and rejects any handoff that does not cover exactly the state's scenarios.
        raw = payload.get("scenarios") if isinstance(payload, Mapping) else None
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise cls._violation(payload, "handoff.scenarios must be an array")
        try:
            exercises = tuple(cls._exercise(item) for item in raw)
            actual = [exercise.scenario_id for exercise in exercises]
            expected = [scenario.id for scenario in state.scenarios]
            if len(set(actual)) != len(actual):
                raise ValueError("handoff scenario ids must be unique")
            if sorted(actual) != sorted(expected):
                raise ValueError(f"handoff ids must exactly match state ids; expected {sorted(expected)}, got {sorted(actual)}")
        except (TypeError, ValueError) as exc:
            raise cls._violation(payload, str(exc)) from exc
        by_id = {exercise.scenario_id: exercise for exercise in exercises}
        return cls(tuple(by_id[scenario.id] for scenario in state.scenarios))

    @staticmethod
    def output_schema(state: MotivatingCaseState) -> dict[str, Any]:
        # Constrains the builder to one entry per scenario id, with every field present and blank meaning absent.
        text = {"type": "string"}
        item = {
            "type": "object",
            "properties": {"scenario_id": {"type": "string", "enum": [scenario.id for scenario in state.scenarios]}, **{name: text for name in _FIELDS}},
            "required": ["scenario_id", *_FIELDS],
            "additionalProperties": False,
        }
        count = len(state.scenarios)
        return {
            "type": "object",
            "properties": {"scenarios": {"type": "array", "items": item, "minItems": count, "maxItems": count}},
            "required": ["scenarios"],
            "additionalProperties": False,
        }

    @classmethod
    def _exercise(cls, value: object) -> ScenarioExercise:
        # Converts one entry, mapping blank strings to None and bounding quote length.
        if not isinstance(value, Mapping):
            raise ValueError("each handoff scenario must be an object")
        scenario_id = value.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError("handoff scenario_id must be a non-blank string")
        fields = {name: cls._optional(value.get(name), name) for name in _FIELDS}
        return ScenarioExercise(scenario_id.strip(), **fields)

    @staticmethod
    def _optional(value: object, field_name: str) -> str | None:
        # Treats missing and blank values as absent and rejects non-string content.
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"handoff.{field_name} must be a string")
        stripped = value.strip()
        if not stripped:
            return None
        return stripped[:JEV_MOTIVATING_CASE_EXCERPT_CHARS]

    @staticmethod
    def _violation(payload: object, reason: str) -> OutputSchemaViolationError:
        # Reuses the state's bounded error shape for handoff failures.
        return MotivatingCaseState.violation(payload, reason)


__all__ = ["MotivatingCaseHandoff", "ScenarioExercise"]

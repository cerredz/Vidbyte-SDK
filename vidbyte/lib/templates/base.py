"""Context Protocol Header

Description:
    Implements ContextWindowTemplate and TemplateViolation for slot-sequence
    validation against a ContextWindowRecorder.
Purpose:
    Allows algorithm test harnesses to assert that a recorded slot sequence
    matches an expected structural pattern exactly, position by position.
Architecture:
    - TemplateViolation: Immutable record of one positional mismatch.
    - ContextWindowTemplate: Validates a RecorderBase against an expected
      ordered list of slot name strings.
Relations:
    Consumes RecorderBase from vidbyte.context.templates. Subclassed by
    algorithm-specific templates such as ReflexionContextWindowTemplate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.context.templates.recorder import RecorderBase


@dataclass(frozen=True)
class TemplateViolation:
    """Immutable description of one positional mismatch in a slot sequence comparison."""

    position: int
    expected: str
    actual: str | None
    message: str


class ContextWindowTemplate:
    """Validates a recorder's slot sequence against an expected ordered list of slot names."""

    def __init__(self, slots: list[str]) -> None:
        # Store the expected slot sequence as an immutable tuple.
        self._slots = tuple(slots)

    @property
    def expected_slots(self) -> tuple[str, ...]:
        # Return the expected slot sequence this template will validate against.
        return self._slots

    def validate(self, recorder: RecorderBase) -> list[TemplateViolation]:
        # Compare the recorder's slot sequence to expected slots and return all violations.
        actual = recorder.slots()
        violations: list[TemplateViolation] = []
        length = max(len(self._slots), len(actual))
        for i in range(length):
            expected_slot = self._slots[i] if i < len(self._slots) else None
            actual_slot = actual[i] if i < len(actual) else None
            if expected_slot is None and actual_slot is not None:
                violations.append(self._extra_slot_violation(i, actual_slot))
            elif expected_slot is not None and actual_slot is None:
                violations.append(self._missing_slot_violation(i, expected_slot))
            elif expected_slot != actual_slot:
                violations.append(self._mismatch_violation(i, expected_slot, actual_slot))  # type: ignore[arg-type]
        return violations

    def passes(self, recorder: RecorderBase) -> bool:
        # Return True if the recorder's slot sequence exactly matches this template.
        return len(self.validate(recorder)) == 0

    @staticmethod
    def _mismatch_violation(position: int, expected: str, actual: str) -> TemplateViolation:
        # Build a violation for a slot type mismatch at a known position.
        return TemplateViolation(
            position=position,
            expected=expected,
            actual=actual,
            message=f"position {position}: expected {expected!r}, got {actual!r}",
        )

    @staticmethod
    def _missing_slot_violation(position: int, expected: str) -> TemplateViolation:
        # Build a violation for a slot that was expected but the trace ended early.
        return TemplateViolation(
            position=position,
            expected=expected,
            actual=None,
            message=f"position {position}: expected {expected!r} but trace ended",
        )

    @staticmethod
    def _extra_slot_violation(position: int, actual: str) -> TemplateViolation:
        # Build a violation for an unexpected extra slot beyond the template length.
        return TemplateViolation(
            position=position,
            expected="<end>",
            actual=actual,
            message=f"position {position}: unexpected extra slot {actual!r}",
        )


__all__ = [
    "ContextWindowTemplate",
    "TemplateViolation",
]

"""FILE: vidbyte/agents/jev/done_criteria/criteria.py

PURPOSE: Implements Jev's deterministic minimum-run-duration completion criterion.
ROLE IN CODEBASE: JevPreset constructs MinimumTime; JevDoneCriteria evaluates it using runtime elapsed seconds.
ARCHITECTURE NOTE: The criterion is pure policy and never sleeps, reads wall-clock time, or completes a task by itself.
FUNCTION INVENTORY: MinimumTime.__init__ validates and normalizes one duration; evaluate returns threshold status and metadata.
COMMON MODIFICATION PATTERNS: Add new named criteria here as JevDoneCriterion subclasses and export them from package __init__.py.
WHAT NOT TO DO: Do not measure runtime or append prompts here; the runtime clock and message history belong to JevRuntime.
KNOWN EDGE CASES: Booleans are rejected despite being Python integers; conversion overflow is rejected as non-finite.
RELATED DOCS: docs/design/jev-done-criteria.md.
TESTS: tests/test_jev_done_criteria.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.jev.done_criteria.base import (
    JevDoneCriterion,
    JevDoneCriterionResult,
)
from vidbyte.lib.errors import ConfigurationError

_DURATION_MULTIPLIERS = {"seconds": 1.0, "minutes": 60.0, "hours": 3_600.0, "days": 86_400.0}


@dataclass(frozen=True, slots=True, init=False)
class MinimumTime(JevDoneCriterion):
    """Requires the run's monotonic elapsed duration to reach one configured threshold."""

    duration_seconds: float = field()

    def __init__(self, *, seconds: float | None = None, minutes: float | None = None, hours: float | None = None, days: float | None = None) -> None:
        # Validates one unit and stores its finite positive duration in canonical seconds.
        value, unit = self._configured_duration(seconds=seconds, minutes=minutes, hours=hours, days=days)
        normalized_seconds = value * _DURATION_MULTIPLIERS[unit]
        if not math.isfinite(normalized_seconds):
            raise ConfigurationError("MinimumTime duration must normalize to a finite number of seconds.")
        object.__setattr__(self, "duration_seconds", normalized_seconds)

    def evaluate(self, *, elapsed_seconds: float) -> JevDoneCriterionResult:
        # Rejects premature completion while reporting whether this configured floor has elapsed.
        met = elapsed_seconds >= self.duration_seconds
        prompt = "" if met else self._continuation_prompt(elapsed_seconds)
        return JevDoneCriterionResult(met, prompt, {"minimum_duration_met": met})

    @staticmethod
    def _configured_duration(*, seconds: float | None, minutes: float | None, hours: float | None, days: float | None) -> tuple[float, str]:
        # Returns the single supplied duration after rejecting ambiguous or invalid unit input.
        values = {"seconds": seconds, "minutes": minutes, "hours": hours, "days": days}
        supplied = tuple((unit, value) for unit, value in values.items() if value is not None)
        if len(supplied) != 1:
            raise ConfigurationError("MinimumTime requires exactly one of seconds, minutes, hours, or days.")
        unit, value = supplied[0]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ConfigurationError(f"MinimumTime.{unit} must be a finite number greater than zero.")
        try:
            normalized_value = float(value)
        except OverflowError as exc:
            raise ConfigurationError(f"MinimumTime.{unit} must be representable as a finite number.") from exc
        if not math.isfinite(normalized_value):
            raise ConfigurationError(f"MinimumTime.{unit} must be a finite number greater than zero.")
        return normalized_value, unit

    def _continuation_prompt(self, elapsed_seconds: float) -> str:
        # Gives the model the measured and required durations while leaving task completion to the model.
        return (
            f"The configured minimum run duration has not elapsed ({elapsed_seconds:.3f} of "
            f"{self.duration_seconds:.3f} seconds). Continue useful work on the task; do not wait idly. "
            "You may finish only after the minimum duration has elapsed and the task is complete."
        )


__all__ = ["MinimumTime"]

"""Context Protocol Header

Description:
    Implements ReflexionContextWindowTemplate, the canonical template for
    validating the structural slot sequence produced by the Reflexion
    context-window algorithm.
Purpose:
    Gives test harnesses and AI-assisted implementation loops a concrete
    acceptance criterion for Reflexion runs: the slot sequence must contain
    exactly one system_prompt, alternating reflexion_trial and
    reflexion_reflection slots for each failing trial, and a final
    reflexion_trial for the last attempt.
Architecture:
    - ReflexionContextWindowTemplate: ContextWindowTemplate subclass that
      builds the correct slot list from max_trials and failing_trials.
Relations:
    Subclasses ContextWindowTemplate from vidbyte.lib.templates.base.
    Validates recorders produced by ReflexionRuntimeAlgorithm instrumentation.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class ReflexionContextWindowTemplate(ContextWindowTemplate):
    """Template for the structural slot sequence of a Reflexion algorithm run."""

    def __init__(self, *, max_trials: int = 3, failing_trials: int | None = None) -> None:
        # Build the expected slot list from trial and failure counts, then initialize.
        actual_failing = failing_trials if failing_trials is not None else max_trials - 1
        super().__init__(self._build_slots(max_trials=max_trials, failing_trials=actual_failing))

    @staticmethod
    def _build_slots(*, max_trials: int, failing_trials: int) -> list[str]:
        # Construct the canonical Reflexion slot sequence for the given trial configuration.
        slots: list[str] = ["system_prompt"]
        for _ in range(failing_trials):
            slots.extend(["reflexion_trial", "reflexion_reflection"])
        slots.append("reflexion_trial")
        return slots


__all__ = [
    "ReflexionContextWindowTemplate",
]

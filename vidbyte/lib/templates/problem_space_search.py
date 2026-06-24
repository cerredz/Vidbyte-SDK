"""Context Protocol Header

Description:
    Defines template validation for problem-space search context-window runs.
Purpose:
    Provides deterministic slot sequences for explorer cadence tests.
Architecture:
    - ProblemSpaceSearchContextWindowTemplate: Expected note slot builder.
Relations:
    Used by tests and verification scripts for the problem-space search algorithm.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class ProblemSpaceSearchContextWindowTemplate(ContextWindowTemplate):
    """Template for problem-space search runtime slot sequences."""

    def __init__(self, *, iterations: int, interval: int = 5, max_notes: int | None = None) -> None:
        # Builds the expected slot list for completed non-final iterations.
        super().__init__(self._build_slots(iterations=iterations, interval=interval, max_notes=max_notes))

    @staticmethod
    def _build_slots(*, iterations: int, interval: int, max_notes: int | None) -> list[str]:
        # Constructs the canonical slot sequence for problem-space search runs.
        if iterations < 0:
            raise ValueError("iterations must be greater than or equal to zero.")
        if interval <= 0:
            raise ValueError("interval must be greater than zero.")
        slots = ["system_prompt"]
        injections = 0
        for iteration in range(1, iterations + 1):
            slots.append("problem_space_search_iteration")
            if iteration % interval == 0 and (max_notes is None or injections < max_notes):
                slots.append("problem_space_search_injection")
                injections += 1
        return slots


__all__ = [
    "ProblemSpaceSearchContextWindowTemplate",
]

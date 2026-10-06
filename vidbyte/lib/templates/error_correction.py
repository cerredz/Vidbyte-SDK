"""Context Protocol Header

Description:
    Defines template validation for error-correction context-window runs.
Purpose:
    Provides deterministic slot sequences for audit cadence tests.
Architecture:
    - ErrorCorrectionContextWindowTemplate: Expected audit-pass slot builder.
Relations:
    Used by tests and verification scripts for the error-correction algorithm.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class ErrorCorrectionContextWindowTemplate(ContextWindowTemplate):
    """Template for error-correction runtime slot sequences."""

    def __init__(self, *, iterations: int, interval: int = 4, max_passes: int | None = None) -> None:
        # Builds the expected slot list for completed non-final iterations.
        super().__init__(self._build_slots(iterations=iterations, interval=interval, max_passes=max_passes))

    @staticmethod
    def _build_slots(*, iterations: int, interval: int, max_passes: int | None) -> list[str]:
        # Constructs the canonical slot sequence for error-correction runs.
        if iterations < 0:
            raise ValueError("iterations must be greater than or equal to zero.")
        if interval <= 0:
            raise ValueError("interval must be greater than zero.")
        slots = ["system_prompt"]
        passes = 0
        for iteration in range(1, iterations + 1):
            slots.append("error_correction_iteration")
            if iteration % interval == 0 and (max_passes is None or passes < max_passes):
                slots.append("error_correction_pass")
                passes += 1
        return slots


__all__ = [
    "ErrorCorrectionContextWindowTemplate",
]

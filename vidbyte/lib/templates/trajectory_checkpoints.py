"""Context Protocol Header

Description:
    Defines template validation for trajectory checkpoint context-window runs.
Purpose:
    Provides deterministic slot sequences for checkpoint cadence tests.
Architecture:
    - TrajectoryCheckpointContextWindowTemplate: Expected checkpoint slot builder.
Relations:
    Used by tests and verification scripts for trajectory checkpoint algorithms.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class TrajectoryCheckpointContextWindowTemplate(ContextWindowTemplate):
    """Template for trajectory checkpoint runtime slot sequences."""

    def __init__(self, *, iterations: int, interval: int = 3, max_checkpoints: int | None = None) -> None:
        # Builds the expected slot list for completed non-final iterations.
        super().__init__(self._build_slots(iterations=iterations, interval=interval, max_checkpoints=max_checkpoints))

    @staticmethod
    def _build_slots(*, iterations: int, interval: int, max_checkpoints: int | None) -> list[str]:
        # Constructs the canonical slot sequence for trajectory checkpoint runs.
        if iterations < 0:
            raise ValueError("iterations must be greater than or equal to zero.")
        if interval <= 0:
            raise ValueError("interval must be greater than zero.")
        slots = ["system_prompt"]
        injections = 0
        for iteration in range(1, iterations + 1):
            slots.append("trajectory_checkpoint_iteration")
            if iteration % interval == 0 and (max_checkpoints is None or injections < max_checkpoints):
                slots.append("trajectory_checkpoint_injection")
                injections += 1
        return slots


__all__ = [
    "TrajectoryCheckpointContextWindowTemplate",
]

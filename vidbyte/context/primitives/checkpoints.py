"""Context Protocol Header

Description:
    Defines the trajectory checkpoint context primitive.
Purpose:
    Gives the trajectory checkpoint algorithm a typed, bounded context unit that
    renders observable runtime progress for the next model call.
Architecture:
    - TrajectoryCheckpointContextItem: Ordered checkpoint sections with bounding.
Relations:
    Written by TrajectoryCheckpointAlgorithm and re-exported through
    vidbyte.context.primitives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _truncate_text


@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointContextItem:
    """Structured runtime checkpoint context for trajectory algorithms."""

    primitive_id: str
    iteration: int
    checkpoint_index: int
    reasoning_summary: str
    trajectory: str
    output: str
    score: float | None
    feedback: str
    title: str = "Runtime Checkpoint"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "trajectory_checkpoint"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders required checkpoint sections in deterministic order.
        score_text = "N/A" if self.score is None else f"{self.score:.2f}"
        text = "\n".join(
            (
                f"Iteration: {self.iteration}",
                f"Checkpoint: {self.checkpoint_index}",
                "",
                "### Reasoning Summary",
                self.reasoning_summary,
                "",
                "### Trajectory",
                self.trajectory,
                "",
                "### Output",
                self.output,
                "",
                "### Score",
                score_text,
                "",
                "### Feedback",
                self.feedback,
            )
        )
        return _truncate_text(text, self.max_chars)


__all__ = [
    "TrajectoryCheckpointContextItem",
]

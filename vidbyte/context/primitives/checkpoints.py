"""FILE: vidbyte/context/primitives/checkpoints.py

PURPOSE:
    Defines bounded trajectory-checkpoint and reflexion records for model-visible
    progress and correction context.
ROLE IN CODEBASE:
    Written by context algorithms, rendered by ContextManager, and re-exported
    through vidbyte.context.primitives for callers that compose context windows.
ARCHITECTURE NOTE:
    Frozen slotted dataclasses own deterministic field rendering while shared
    truncation preserves the managed-context boundary and character limit.
FUNCTION INVENTORY:
    TrajectoryCheckpointContextItem.to_context_text() renders runtime progress.
    ReflexionContextItem.to_context_text() renders critique and correction plan.
COMMON MODIFICATION PATTERNS:
    Add checkpoint fields before the metadata tail, render them in stable order,
    and preserve the existing truncation helper and optional failed attempt.
WHAT NOT TO DO IN THIS FILE:
    Do not execute trajectory steps, evaluate scores, or control context placement;
    those responsibilities belong to the calling algorithms and ContextManager.
KNOWN EDGE CASES:
    Scores may be absent and failed attempts are optional; oversized text remains
    stored but is bounded only when rendered.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/tree/main/vidbyte/context/primitives
TESTS:
    Existing context algorithm tests, package compilation, and source/package
    smoke gates cover importability and rendering behavior.
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
        lines = [
            "This primitive carries a bounded runtime checkpoint from an agent's trajectory. Iteration and checkpoint index locate the snapshot, while reasoning summary and trajectory show how the state was reached. Output, score, and feedback record the observed result and evaluation at that point. Use it to continue or audit progress without treating the checkpoint as a live execution state.",
            "",
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
        ]
        text = "\n".join(lines)
        return _truncate_text(text, self.max_chars)


@dataclass(frozen=True, slots=True)
class ReflexionContextItem:
    """Structured self-critique written by the model when it detects a reasoning failure."""

    primitive_id: str
    critique: str
    correction_plan: str
    failed_attempt: str | None = None
    title: str = "Reflexion Note"
    max_chars: int = 1200
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "reflexion"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders critique, correction plan, and optional failed attempt, bounded by max_chars.
        lines = [
            "This primitive carries a self-critique produced after a reasoning attempt needs review. The critique identifies the perceived failure, and the correction plan describes how the next attempt should change. An optional failed-attempt section preserves the concrete work that motivated the reflection. Use this note to guide revision while checking its claims against the surrounding context.",
            "",
            "### Critique",
            self.critique,
            "",
            "### Correction Plan",
            self.correction_plan,
        ]
        if self.failed_attempt is not None:
            lines.extend(("", "### Failed Attempt", self.failed_attempt))
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "ReflexionContextItem",
    "TrajectoryCheckpointContextItem",
]

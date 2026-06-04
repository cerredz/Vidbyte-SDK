"""Context Protocol Header

Description:
    Defines task-, progress-, and plan-style context primitives.
Purpose:
    Gives developers and algorithms immutable units of goal, progress, and
    multi-step plan context.
Architecture:
    - Task/Progress/Plan context primitives.
Relations:
    Re-exported through vidbyte.context.primitives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section


@dataclass(frozen=True, slots=True)
class TaskContextItem:
    """Structured task context for goal, progress, and deterministic checks."""

    goal: str
    status: str = "pending"
    progress: str | None = None
    completed: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    deterministic_checks: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "task"
    title: str = "Task"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders goal, status, optional progress, and bullet sections.
        lines = [f"Task goal: {self.goal}", f"Status: {self.status}"]
        if self.progress:
            lines.append(f"Progress: {self.progress}")
        _extend_section(lines, "Completed", self.completed)
        _extend_section(lines, "Next steps", self.next_steps)
        _extend_section(lines, "Deterministic checks", self.deterministic_checks)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ProgressContextItem:
    """Structured progress context mirroring ProgressLog fields."""

    completed_tasks: tuple[str, ...] = ()
    touched_files: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "progress"
    title: str = "Progress"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders all progress sections as bullet lists.
        lines: list[str] = ["Progress:"]
        _extend_section(lines, "Completed tasks", self.completed_tasks)
        _extend_section(lines, "Touched files", self.touched_files)
        _extend_section(lines, "Decisions", self.decisions)
        _extend_section(lines, "Errors", self.errors)
        _extend_section(lines, "Next steps", self.next_steps)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PlanContextItem:
    """Structured plan context for algorithm-owned multi-step execution plans."""

    steps: tuple[str, ...] = ()
    current_step: int = 0
    status: str = "planning"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "plan"
    title: str = "Plan"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders numbered steps with an arrow marker on the current step.
        lines = [f"Plan (status: {self.status}):"]
        for i, step in enumerate(self.steps):
            marker = "→" if i == self.current_step else " "
            lines.append(f"{marker} {i + 1}. {step}")
        if not self.steps:
            lines.append("No steps defined.")
        return "\n".join(lines)


__all__ = [
    "PlanContextItem",
    "ProgressContextItem",
    "TaskContextItem",
]

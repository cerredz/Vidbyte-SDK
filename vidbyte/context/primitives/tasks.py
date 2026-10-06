"""FILE: vidbyte/context/primitives/tasks.py

PURPOSE:
    Defines immutable task, progress, and plan records for keeping execution
    goals, completed work, and next actions visible in context windows.
ROLE IN CODEBASE:
    ContextManager renders these records, create-tool registry builders construct
    the create-enabled types, and vidbyte.context.primitives re-exports them.
ARCHITECTURE NOTE:
    Dataclasses own stable task-oriented rendering while shared helpers format
    sections and add the managed-context boundary.
FUNCTION INVENTORY:
    TaskContextItem, ProgressContextItem, and PlanContextItem each render one
    execution record through to_context_text() -> str.
COMMON MODIFICATION PATTERNS:
    Add fields before metadata, render them in semantic order, and keep plan step
    numbering and active-step marking stable for downstream agents.
WHAT NOT TO DO IN THIS FILE:
    Do not advance tasks, validate checks, or mutate the registry; callers and
    ContextManager own lifecycle, placement, and replacement behavior.
KNOWN EDGE CASES:
    Progress sections may be empty, plans may contain no steps, and current_step
    may not identify a displayed step without changing the stored plan.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/tree/main/vidbyte/context/primitives
TESTS:
    Existing context primitive registry and built-in context-tool tests plus source
    and package smoke gates cover task rendering and integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from vidbyte.context.primitives.base import _extend_section, _with_context_intro


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

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "task",
        "tool_name": "context_create_task",
        "default_title": "Task",
        "description": (
            "context_create_task is the typed create tool for TaskContextItem goal-tracking entries "
            "in the managed context window registry. context_create_task does insert or overwrite a "
            "task primitive by primitive_id with goal, status, progress, completed work, next steps, "
            "and deterministic checks so the agent can keep an explicit execution contract visible "
            "while working and verify completion criteria before finishing."
        ),
        "fields": {
            "goal": {
                "type": "string",
                "required": True,
                "description": (
                    "goal is the primary outcome the agent is trying to achieve for this task. goal "
                    "does define success criteria in plain language and should stay stable while "
                    "status/progress fields evolve."
                ),
            },
            "status": {
                "type": "string",
                "required": False,
                "description": (
                    "status is the lifecycle label for the task (for example pending, active, blocked, "
                    "done). status does communicate whether the agent is still working, waiting, or "
                    "finished; defaults to 'pending' when omitted."
                ),
            },
            "progress": {
                "type": "string",
                "required": False,
                "description": (
                    "progress is an optional free-form summary of how far the task has advanced. "
                    "progress does capture narrative state that does not fit cleanly into completed "
                    "or next_steps lists."
                ),
            },
            "completed": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "completed is the list of work items already finished for this task. completed "
                    "does prevent the agent from redoing finished sub-work and documents forward "
                    "motion across iterations."
                ),
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "next_steps is the ordered list of remaining actions needed to finish the goal. "
                    "next_steps does tell the model what to do next without re-deriving the plan "
                    "from scratch each turn."
                ),
            },
            "deterministic_checks": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "deterministic_checks is the list of verifiable pass/fail checks that prove the "
                    "task is done (commands, assertions, expected outputs). deterministic_checks does "
                    "ground completion in evidence instead of self-reported status alone."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders goal, status, optional progress, and bullet sections.
        lines = [
            "This primitive carries an explicit work goal and its current execution state. The status and progress summarize where the work stands, while completed and next-step sections preserve the execution trail. Deterministic checks identify observable conditions that can support a completion claim. Use this record to continue the task from recorded state instead of reconstructing it from conversation alone.",
            "",
            f"Task goal: {self.goal}",
            f"Status: {self.status}",
        ]
        if self.progress:
            lines.append(f"Progress: {self.progress}")
        _extend_section(lines, "Completed", self.completed)
        _extend_section(lines, "Next steps", self.next_steps)
        _extend_section(lines, "Deterministic checks", self.deterministic_checks)
        return _with_context_intro("\n".join(lines))


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

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "progress",
        "tool_name": "context_create_progress",
        "default_title": "Progress",
        "description": (
            "context_create_progress is the typed create tool for ProgressContextItem run journals "
            "in the managed context window registry. context_create_progress does insert or overwrite "
            "a progress primitive by primitive_id that catalogs completed tasks, touched files, "
            "decisions, errors, and next steps so the agent can keep a compact working log of what "
            "has already happened in the run."
        ),
        "fields": {
            "completed_tasks": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "completed_tasks is the list of finished work items in this progress log. "
                    "completed_tasks does prevent duplicate effort by recording what already shipped."
                ),
            },
            "touched_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "touched_files is the list of file paths the agent has read or modified so far. "
                    "touched_files does keep a lightweight inventory of the blast radius of the run."
                ),
            },
            "decisions": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "decisions is the list of important choices already made. decisions does preserve "
                    "rationale and direction so later steps stay consistent with earlier judgment calls."
                ),
            },
            "errors": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "errors is the list of failures, blockers, or surprises encountered. errors does "
                    "surface unresolved problems so the agent does not silently retry the same dead end."
                ),
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "next_steps is the remaining action queue for this progress log. next_steps does "
                    "tell the model the immediate follow-ups after the current iteration."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders all progress sections as bullet lists.
        lines: list[str] = [
            "This primitive carries a compact journal of work already performed during a run. Completed tasks, touched files, and decisions show the path taken so far. Errors and next steps expose unresolved work and guide the next iteration. Use it as a progress snapshot rather than as a replacement for the underlying artifacts.",
            "",
            "Progress:",
        ]
        _extend_section(lines, "Completed tasks", self.completed_tasks)
        _extend_section(lines, "Touched files", self.touched_files)
        _extend_section(lines, "Decisions", self.decisions)
        _extend_section(lines, "Errors", self.errors)
        _extend_section(lines, "Next steps", self.next_steps)
        return _with_context_intro("\n".join(lines))


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

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "plan",
        "tool_name": "context_create_plan",
        "default_title": "Plan",
        "description": (
            "context_create_plan is the typed create tool for PlanContextItem multi-step execution "
            "plans in the managed context window registry. context_create_plan does insert or "
            "overwrite a plan primitive by primitive_id with ordered steps, a current-step index, "
            "and status so the agent can track multi-step work that re-renders with the active step "
            "highlighted on every loop iteration."
        ),
        "fields": {
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "required": True,
                "description": (
                    "steps is the ordered list of plan step descriptions. steps does define the full "
                    "sequence of work the agent intends to follow; each entry should be a concrete, "
                    "actionable step rather than a vague goal."
                ),
            },
            "current_step": {
                "type": "integer",
                "required": False,
                "description": (
                    "current_step is the zero-based index of the step currently being executed. "
                    "current_step does mark which step is active when the plan renders (shown with "
                    "an arrow); defaults to 0 when omitted."
                ),
            },
            "status": {
                "type": "string",
                "required": False,
                "description": (
                    "status is the plan lifecycle label (for example planning, executing, blocked, "
                    "done). status does communicate overall plan state independent of which step is "
                    "current; defaults to 'planning' when omitted."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders numbered steps with an arrow marker on the current step.
        lines = [
            "This primitive carries an ordered plan for multi-step execution. Each numbered step represents work in sequence, and the arrow marks the step currently considered active. The plan status describes the overall lifecycle without proving that any step is complete. Follow the listed steps while checking their real outcomes in the surrounding context.",
            "",
            f"Plan (status: {self.status}):",
        ]
        for i, step in enumerate(self.steps):
            marker = "→" if i == self.current_step else " "
            lines.append(f"{marker} {i + 1}. {step}")
        if not self.steps:
            lines.append("No steps defined.")
        return _with_context_intro("\n".join(lines))


__all__ = [
    "PlanContextItem",
    "ProgressContextItem",
    "TaskContextItem",
]

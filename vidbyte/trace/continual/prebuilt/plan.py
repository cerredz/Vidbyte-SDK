"""Context Protocol Header

Description:
    Defines the plan-oriented continual trace schema (planning lens).
Purpose:
    Gives developers a ready-made typed schema for recording an agent's intended
    plan, the status of each step, deviations, and what remains.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class PlanTraceModel(BaseModel):
    """Plan-oriented continual trace describing intended structure and execution progress."""

    goal: str = Field(
        description=(
            "The overall objective the plan is meant to achieve, with success criteria when known. "
            "Capture the developer's intent as precisely as the context allows. Keep this stable unless "
            "the context clearly redefines the objective."
        ),
    )
    plan_summary: str = Field(
        default="",
        description=(
            "A short narrative of the agent's current overall plan or strategy. Overwrite this with the "
            "single most-current description of how the agent intends to reach the goal."
        ),
    )
    plan_steps: list[str] = Field(
        default_factory=list,
        description=(
            "The ordered steps of the plan as the agent has laid them out, each a concrete action. Append "
            "new steps as the plan is elaborated; do not rewrite the whole list, so the plan's evolution "
            "stays visible."
        ),
    )
    current_step: str = Field(
        default="",
        description=(
            "The single step the agent is actively working on right now. Overwrite this each update to "
            "point at the present step."
        ),
    )
    current_step_index: int = Field(
        default=0,
        description=(
            "The zero-based index of the current step within plan_steps. Overwrite with the latest index; "
            "use it to show how far through the plan the agent is."
        ),
    )
    completed_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Plan steps that are finished. Append each step as it completes and never remove completed "
            "steps on later updates."
        ),
    )
    remaining_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Plan steps not yet started. Append newly identified remaining steps; an item here may later "
            "also appear under completed_steps as the plan executes."
        ),
    )
    skipped_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Steps the agent deliberately skipped, with the reason when visible. Append each skipped step "
            "so a successor understands gaps in execution."
        ),
    )
    blocked_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Steps that cannot proceed because of a blocker, paired with the blocking cause when known. "
            "Append blocked steps as they arise."
        ),
    )
    step_dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "Ordering or prerequisite relationships between steps, phrased like 'step B depends on step A'. "
            "Append each dependency the context reveals so a successor preserves correct ordering."
        ),
    )
    milestones: list[str] = Field(
        default_factory=list,
        description=(
            "Significant checkpoints in the plan that mark meaningful progress. Append milestones as they "
            "are defined; keep them stable once recorded."
        ),
    )
    milestones_reached: list[str] = Field(
        default_factory=list,
        description=(
            "Milestones the agent has actually achieved. Append each milestone when the context confirms "
            "it was reached."
        ),
    )
    deviations: list[str] = Field(
        default_factory=list,
        description=(
            "Places where execution diverged from the stated plan, with the reason. Append each deviation; "
            "this is high-value because it explains why the actual run differs from the intended plan."
        ),
    )
    replans: list[str] = Field(
        default_factory=list,
        description=(
            "Points where the agent revised its plan, noting what changed and why. Append each replanning "
            "event to preserve the strategy's history."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Assumptions the plan depends on that are not yet confirmed. Append each so a reviewer can "
            "check whether the plan still holds if an assumption fails."
        ),
    )
    risks: list[str] = Field(
        default_factory=list,
        description=(
            "Things that could cause the plan to fail or need rework. Append each identified risk; keep "
            "prior risks unless the context shows they no longer apply."
        ),
    )
    contingencies: list[str] = Field(
        default_factory=list,
        description=(
            "Fallback plans or alternative approaches the agent has prepared if the primary plan fails. "
            "Append each contingency as it is considered."
        ),
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete conditions that would mean the plan succeeded. Append newly discovered criteria; keep "
            "prior ones unless clearly superseded."
        ),
    )
    estimated_remaining_effort: str = Field(
        default="",
        description=(
            "A qualitative estimate of how much work is left (for example 'roughly two more steps' or "
            "'most of the work remains'). Overwrite with the latest estimate."
        ),
    )
    blockers: list[str] = Field(
        default_factory=list,
        description=(
            "Active conditions preventing the plan from advancing. Append each blocker; reflect resolution "
            "in status rather than deleting entries."
        ),
    )
    next_action: str = Field(
        default="",
        description=(
            "The immediate next action the plan calls for. Overwrite with the single most-current next "
            "action as execution proceeds."
        ),
    )
    plan_confidence: str = Field(
        default="",
        description=(
            "A brief qualitative read on how likely the current plan is to succeed (low/medium/high with a "
            "one-line reason). Overwrite with the latest assessment."
        ),
    )
    status: str = Field(
        default="",
        description=(
            "The overall status of the plan right now: how far along, what is in progress, and what blocks "
            "completion. Overwrite each update to reflect the most recent reality."
        ),
    )


PlanTrace = TraceSchema.from_model(
    PlanTraceModel,
    name="plan_trace",
    description="Tracks the agent's plan, step status, deviations, and remaining work.",
)

__all__ = [
    "PlanTrace",
    "PlanTraceModel",
]

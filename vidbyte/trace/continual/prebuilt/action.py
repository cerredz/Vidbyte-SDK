"""Context Protocol Header

Description:
    Defines the action-oriented continual trace schema (execution lens).
Purpose:
    Gives developers a ready-made typed schema for recording what an agent is
    trying to do, the work it has performed, mistakes, and its current status.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class ActionTraceModel(BaseModel):
    """Action-oriented continual trace describing goal, work, mistakes, and status."""

    goal: str = Field(
        description=(
            "The original or current high-level goal the main agent is working toward. Capture the "
            "developer's intent as precisely as the context allows, including any explicit success "
            "criteria or constraints. If the goal is refined or narrowed during the run, record the "
            "most current understanding rather than the first phrasing. Keep this stable across "
            "updates unless the context clearly redefines the objective."
        ),
    )
    subgoals: list[str] = Field(
        default_factory=list,
        description=(
            "The intermediate objectives the agent is pursuing on the way to the main goal, whether "
            "stated explicitly or inferable from its behavior. Each entry should be a short, concrete "
            "subgoal. Append new subgoals as they emerge and do not restate ones already captured."
        ),
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description=(
            "The concrete conditions that would mean the task is done correctly. Record measurable or "
            "checkable criteria visible in the context, such as tests passing or a specific output "
            "existing. Append newly discovered criteria; keep prior ones unless clearly superseded."
        ),
    )
    constraints: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit limits, requirements, or rules the agent must respect (allowed tools, scope "
            "boundaries, style rules, forbidden actions). Append each constraint as it appears in the "
            "context. These matter for a later handoff because they explain why some paths were avoided."
        ),
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description=(
            "An ordered list of the important actions, tool calls, decisions, or steps the agent has "
            "already performed. Each entry should be a short, concrete statement of what happened and, "
            "when useful, why it mattered. Append new meaningful actions rather than rewriting history; "
            "omit trivial or repetitive steps that add no value."
        ),
    )
    current_action: str = Field(
        default="",
        description=(
            "What the agent is doing right now, as of the latest snapshot. This is a single most-current "
            "value, not a log; overwrite it each update to reflect the present step or pending tool call."
        ),
    )
    next_action: str = Field(
        default="",
        description=(
            "The immediate next step the agent appears about to take, inferred from the latest context. "
            "Write the single most likely next action and overwrite it as the situation evolves."
        ),
    )
    completed_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Steps that are finished and verified as done in the context. Append each step as it "
            "completes; do not remove completed steps on later updates."
        ),
    )
    pending_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Steps that still remain to reach the goal. Append newly identified pending steps. It is "
            "acceptable for an item here to later also appear under completed_steps as work progresses."
        ),
    )
    mistakes: list[str] = Field(
        default_factory=list,
        description=(
            "Mistakes, failed attempts, incorrect assumptions, dead ends, or recoveries observed so far. "
            "Record what went wrong and, where the context reveals it, the correction that followed. This "
            "is one of the most valuable fields for a handoff because it stops a future agent from "
            "repeating the same error. Keep prior entries unless the context shows they were not mistakes."
        ),
    )
    recoveries: list[str] = Field(
        default_factory=list,
        description=(
            "How the agent corrected or worked around each mistake or blocker. Pair the recovery with the "
            "problem it resolved when possible. Append new recoveries as they occur."
        ),
    )
    blockers: list[str] = Field(
        default_factory=list,
        description=(
            "Conditions currently preventing progress (missing input, failing dependency, awaited result). "
            "Append each blocker as it appears; a blocker that is later resolved should be reflected in the "
            "current_status rather than deleted here."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Assumptions the agent is relying on that are not yet confirmed (input shape, environment "
            "state, user intent). Append each assumption so a reviewer can later check whether it held."
        ),
    )
    decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Notable choices the agent committed to, with brief reasoning when visible. Append each "
            "decision; this preserves the reasoning trail behind the actions taken."
        ),
    )
    inputs_received: list[str] = Field(
        default_factory=list,
        description=(
            "The inputs, parameters, files, or user messages the agent was given or fetched. Append each "
            "distinct input so the run can be reproduced or understood."
        ),
    )
    outputs_produced: list[str] = Field(
        default_factory=list,
        description=(
            "The concrete outputs the agent has produced so far (answers, files, artifacts, side effects). "
            "Append each output as it is created."
        ),
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description=(
            "The tools or capabilities the agent has invoked during the run. Append each tool name the "
            "first time it is used; do not duplicate names already present."
        ),
    )
    external_resources: list[str] = Field(
        default_factory=list,
        description=(
            "External systems the agent touched: files, APIs, services, URLs, or databases. Append each "
            "resource so the run's external footprint is visible to a later reader."
        ),
    )
    progress_summary: str = Field(
        default="",
        description=(
            "A short narrative of how far the agent has come overall. Overwrite this each update with the "
            "single most-current summary of progress against the goal."
        ),
    )
    current_status: str = Field(
        default="",
        description=(
            "The latest known state of the task and what still remains unresolved. Summarize how far the "
            "agent has progressed and what the immediate next step appears to be, including any blocking "
            "condition or pending result. This should always reflect the most recent context and is "
            "expected to change on nearly every update."
        ),
    )
    iteration_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Brief per-iteration observations worth keeping, keyed loosely to where in the run they "
            "happened. Append one short note per meaningful iteration; do not rewrite earlier notes."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Unresolved questions that would matter to a later handoff or a human reviewer. Phrase each as "
            "a concrete question. Append new questions and keep them until the context answers them."
        ),
    )
    confidence: str = Field(
        default="",
        description=(
            "A brief qualitative assessment of how likely the agent is to succeed given current progress "
            "(for example low, medium, or high with a one-line reason). Overwrite with the latest read."
        ),
    )
    time_sensitive_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Anything time-bound a successor must know quickly: expiring sessions, rate limits hit, "
            "deadlines, or stale state. Append each note as it becomes relevant."
        ),
    )


ActionTrace = TraceSchema.from_model(
    ActionTraceModel,
    name="action_trace",
    description="Tracks the agent goal, work performed, mistakes, and current status.",
)

__all__ = [
    "ActionTrace",
    "ActionTraceModel",
]

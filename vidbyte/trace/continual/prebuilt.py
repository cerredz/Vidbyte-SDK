"""Context Protocol Header

Description:
    Defines the default action-oriented continual trace schema.
Purpose:
    Gives developers a ready-made typed schema for summarizing an agent's goal,
    actions, mistakes, and current status during execution.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual and vidbyte.trace.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class ActionTraceModel(BaseModel):
    """Action-oriented continual trace describing goal, work, mistakes, and status."""

    goal: str = Field(
        description=(
            "The original or current high-level goal the main agent is working toward. "
            "Capture the developer's intent as precisely as the context allows, including any "
            "explicit success criteria or constraints. If the goal is refined or narrowed during "
            "the run, record the most current understanding rather than the first phrasing. Keep "
            "this stable across updates unless the context clearly redefines the objective."
        ),
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description=(
            "An ordered list of the important actions, tool calls, decisions, or steps the main "
            "agent has already performed. Each entry should be a short, concrete statement of what "
            "happened and, when useful, why it mattered. Append new meaningful actions rather than "
            "rewriting history so the trace reads as a running log. Omit trivial or repetitive steps "
            "that add no value to a later handoff."
        ),
    )
    mistakes: list[str] = Field(
        default_factory=list,
        description=(
            "Mistakes, failed attempts, incorrect assumptions, dead ends, or recoveries observed so "
            "far. Record what went wrong and, where the context reveals it, the correction that "
            "followed. This field is one of the most valuable parts of a handoff because it stops a "
            "future agent from repeating the same error. Keep prior entries unless the context shows "
            "they were not actually mistakes."
        ),
    )
    current_status: str = Field(
        description=(
            "The latest known state of the task and what still remains unresolved. Summarize how far "
            "the agent has progressed and what the immediate next step appears to be. Note any blocking "
            "conditions, pending tool results, or waiting states that affect progress. This field "
            "should always reflect the most recent context and is expected to change on nearly every "
            "update."
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

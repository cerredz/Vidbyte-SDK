"""Context Protocol Header

Description:
    Defines the default action-oriented continual trace schema.
Purpose:
    Gives developers a ready-made schema for summarizing an agent's goal,
    actions, mistakes, and current status during execution.
Architecture:
    Module-level TraceSchema constant.
Relations:
    Re-exported by vidbyte.trace.prebuilt.
"""

from __future__ import annotations

from vidbyte.trace.options import TraceSchema


ActionTrace = TraceSchema(
    name="action_trace",
    description="Tracks the agent goal, work performed, mistakes, and current status.",
    fields={
        "goal": "The original or current goal the main agent is working toward.",
        "actions_taken": "Important actions, tool calls, decisions, or steps the main agent has taken.",
        "mistakes": "Mistakes, failed attempts, incorrect assumptions, or recoveries observed so far.",
        "current_status": "The latest known state of the task and what remains unresolved.",
    },
)

__all__ = [
    "ActionTrace",
]

"""Context Protocol Header

Description:
    Defines a debugging-oriented continual trace schema.
Purpose:
    Gives developers a ready-made schema for recording blockers, mistakes,
    decisions, and open questions during an agent run.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.prebuilt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.trace.options import TraceSchema


class DebugTraceModel(BaseModel):
    """Debugging-oriented continual trace describing decisions, mistakes, blockers, and open questions."""

    goal: str = Field(
        description=(
            "The debugging or implementation goal the main agent is pursuing. Describe the "
            "bug, failing behavior, or feature under investigation as concretely as the "
            "context allows. Include the expected versus actual behavior when it is known, "
            "since that framing anchors every later decision. Update this only when the "
            "investigation reveals the real problem is different from the original report."
        ),
    )
    decisions: list[str] = Field(
        description=(
            "Important choices the main agent made and the reasoning behind them. Each entry "
            "should pair the decision with the evidence or assumption that motivated it so a "
            "later reader can judge whether it still holds. Capture both the path taken and "
            "any deliberately rejected alternatives that are worth remembering. Append new "
            "decisions rather than overwriting earlier ones to preserve the reasoning trail."
        ),
    )
    mistakes: list[str] = Field(
        description=(
            "Errors, failed hypotheses, broken commands, or fixes applied after a mistake. "
            "Record what was tried, why it failed, and what was learned from the failure. "
            "This is the highest-value field for debugging handoffs because it prevents a "
            "future agent from re-running known dead ends. Preserve prior entries unless the "
            "context proves an earlier note was incorrect."
        ),
    )
    blockers: list[str] = Field(
        description=(
            "Current blockers or external conditions preventing progress right now. Describe "
            "the blocker, what is needed to clear it, and who or what the agent is waiting on "
            "when that is visible in the context. Distinguish hard blockers that stop work "
            "entirely from soft ones that merely slow it down. Remove a blocker from the "
            "active set once the context shows it has been resolved."
        ),
    )
    open_questions: list[str] = Field(
        description=(
            "Unresolved questions that would matter to a later handoff or a human reviewer. "
            "Capture uncertainties about root cause, missing information, or ambiguous "
            "requirements that still need an answer. Phrase each item as a concrete question "
            "so the next agent knows exactly what to investigate. Keep questions here until "
            "the context provides a clear answer, then move the resolution into decisions."
        ),
    )


DebugTrace = TraceSchema.from_model(
    DebugTraceModel,
    name="debug_trace",
    description="Tracks debugging-relevant decisions, mistakes, blockers, and open questions.",
)

__all__ = [
    "DebugTrace",
    "DebugTraceModel",
]

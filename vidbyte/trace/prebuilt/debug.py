"""Context Protocol Header

Description:
    Defines a debugging-oriented continual trace schema.
Purpose:
    Gives developers a ready-made schema for recording blockers, mistakes,
    decisions, and open questions during an agent run.
Architecture:
    Module-level TraceSchema constant.
Relations:
    Re-exported by vidbyte.trace.prebuilt.
"""

from __future__ import annotations

from vidbyte.trace.options import TraceSchema


DebugTrace = TraceSchema(
    name="debug_trace",
    description="Tracks debugging-relevant decisions, mistakes, blockers, and open questions.",
    fields={
        "goal": "The debugging or implementation goal the main agent is pursuing.",
        "decisions": "Important choices the main agent made and the reasoning behind them.",
        "mistakes": "Errors, failed hypotheses, broken commands, or fixes made after mistakes.",
        "blockers": "Current blockers or external conditions preventing progress.",
        "open_questions": "Unresolved questions that would matter to a later handoff.",
    },
)

__all__ = [
    "DebugTrace",
]

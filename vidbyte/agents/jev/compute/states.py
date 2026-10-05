"""FILE: vidbyte/agents/jev/compute/states.py

PURPOSE: Build bounded situation states from the verified run brief, exact live facts, request, and recent numbered events.
ROLE IN CODEBASE: JevComputeRecognizer sends each enabled situation's state with its fixed sign questions.
ARCHITECTURE NOTE: Event numbering comes from the current JevRunEventLog; recent context is clipped here without a separate brief event module.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_ATTEMPTS_FIELD,
    JEV_COMPUTE_BRIEF_FIELD,
    JEV_COMPUTE_FAILURES_FIELD,
    JEV_COMPUTE_GROUP_FIELD,
    JEV_COMPUTE_NEXT_STEP_FIELD,
    JEV_COMPUTE_PLAN_FIELD,
    JEV_COMPUTE_PROBLEM_FIELD,
    JEV_COMPUTE_RECENT_EVENT_MAX_CHARS,
    JEV_COMPUTE_RECENT_EVENTS,
    JEV_COMPUTE_RECENT_FIELD,
    JEV_COMPUTE_REQUEST_FIELD,
    JEV_RUN_BRIEF_CLIP_HEAD_SHARE,
    JEV_RUN_BRIEF_GOAL_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import JevRunBrief, JevRunFacts
from vidbyte.lib.enums.jev import JevComputeSituation

ComputeState = Mapping[str, object]


class JevComputeStates:
    """Build each situation's state from #512's verified note brief and current run evidence."""

    @classmethod
    def build(
        cls,
        situation: JevComputeSituation,
        request: str,
        brief: JevRunBrief,
        facts: JevRunFacts,
        events: JevRunEventLog,
    ) -> ComputeState | None:
        """Return bounded state for one situation, or None when the run has no recent work events."""
        recent = cls._recent(events.lines, facts)
        if not recent:
            return None
        common = {
            JEV_COMPUTE_REQUEST_FIELD: cls._clip(request, JEV_RUN_BRIEF_GOAL_MAX_CHARS),
            JEV_COMPUTE_RECENT_FIELD: recent,
        }
        notes = tuple(f"{note.event}: {note.text}" for note in brief.notes)
        match situation:
            case JevComputeSituation.REPEATING:
                specific = {
                    JEV_COMPUTE_PROBLEM_FIELD: brief.goal,
                    JEV_COMPUTE_ATTEMPTS_FIELD: notes,
                    JEV_COMPUTE_FAILURES_FIELD: facts.error_streak,
                }
            case JevComputeSituation.EACH_OF_SEVERAL:
                specific = {
                    JEV_COMPUTE_GROUP_FIELD: {"goal": brief.goal, "verified_notes": notes},
                    JEV_COMPUTE_PLAN_FIELD: recent,
                }
            case JevComputeSituation.SELF_CONTAINED_STEP:
                specific = {
                    JEV_COMPUTE_NEXT_STEP_FIELD: cls._latest_assistant(events.lines),
                    JEV_COMPUTE_BRIEF_FIELD: brief.render(),
                }
            case _:
                return None
        return {**common, **specific}

    @classmethod
    def _recent(cls, lines: Sequence[str], facts: JevRunFacts) -> str:
        """Render exact run counts followed by the newest bounded, numbered events."""
        recent = [line for line in lines if not line.partition(" ")[2].startswith("USER: ")][-JEV_COMPUTE_RECENT_EVENTS:]
        if not recent:
            return ""
        fact_line = (
            f"RUN FACTS iteration={facts.iteration} tool_calls={facts.tool_calls} "
            f"error_streak={facts.error_streak} tokens_used={facts.tokens_used}"
        )
        return "\n".join((fact_line, *(cls._clip(line, JEV_COMPUTE_RECENT_EVENT_MAX_CHARS) for line in recent)))

    @staticmethod
    def _latest_assistant(lines: Sequence[str]) -> str:
        """Return the latest assistant event verbatim, or an empty string if none exists."""
        return next((line for line in reversed(lines) if " ASSISTANT " in line), "")

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        """Keep a bounded head and tail with an explicit count for omitted characters."""
        if len(text) <= limit:
            return text
        available = max(0, limit - 32)
        head = int(available * JEV_RUN_BRIEF_CLIP_HEAD_SHARE)
        tail = available - head
        while True:
            marker = f" [...] {len(text) - head - tail} chars omitted [...] "
            overflow = head + tail + len(marker) - limit
            if overflow <= 0:
                return f"{text[:head]}{marker}{text[-tail:] if tail else ''}"
            reduction = min(overflow, tail)
            tail -= reduction
            head -= overflow - reduction


__all__ = ["JevComputeStates"]

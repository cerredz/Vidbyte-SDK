"""FILE: vidbyte/agents/jev/compute/states.py

PURPOSE: Builds the state each compute situation's sign questions read from the verified run brief and the newest run events, or returns None when code finds the situation's preconditions absent and Jev need not be asked.
ROLE IN CODEBASE: JevComputeRecognizer calls `build` once per enabled situation at each recognition; the field names and the descriptions in vidbyte/lib/jev/compute/ must match what is built here.
ARCHITECTURE NOTE: Following the question-writing house style, code does every lookup and count: it picks the group with the most pending items, the problem a failed approach left unsolved, and the soonest next step, so each question judges one subject instead of searching the brief for it.
COMMON MODIFICATION PATTERNS: Add a situation's builder here, with a precondition that asks Jev nothing when the brief cannot show the situation, and describe every field it builds in that situation's state text.
KNOWN EDGE CASES: A group needs JEV_COMPUTE_EACH_OF_SEVERAL_MIN_PENDING pending items; a problem counts only when a failed approach targets it and no approach that worked does. Quotes are passed as "E14: text" so each keeps its event id.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_ATTEMPTS_FIELD,
    JEV_COMPUTE_BRIEF_FIELD,
    JEV_COMPUTE_EACH_OF_SEVERAL_MIN_PENDING,
    JEV_COMPUTE_FAILURES_FIELD,
    JEV_COMPUTE_GROUP_FIELD,
    JEV_COMPUTE_NEXT_STEP_FIELD,
    JEV_COMPUTE_PLAN_FIELD,
    JEV_COMPUTE_PROBLEM_FIELD,
    JEV_COMPUTE_RECENT_EVENT_MAX_CHARS,
    JEV_COMPUTE_RECENT_EVENTS,
    JEV_COMPUTE_RECENT_FIELD,
    JEV_COMPUTE_REQUEST_FIELD,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefApproach,
    JevRunBriefQuote,
)
from vidbyte.lib.enums.jev import (
    JevComputeSituation,
    JevRunBriefItemStatus,
    JevRunBriefOutcome,
)

ComputeState = Mapping[str, object]


class JevComputeStates:
    """Builds each compute situation's question state from the run brief, or None when the situation cannot apply."""

    @classmethod
    def build(cls, situation: JevComputeSituation, request: str, brief: JevRunBrief, events: JevRunBriefEvents) -> ComputeState | None:
        """Return the state one situation's questions read, or None when its preconditions are absent."""
        # @intent code-asks-only-where-the-brief-shows-a-subject
        # Each situation's questions judge one subject the brief already records. When there is none, a Jev call
        # could only recognize nothing, so code asks nothing and the situation is recorded as not eligible.
        common = {
            JEV_COMPUTE_REQUEST_FIELD: JevRunBriefEvents.clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS),
            JEV_COMPUTE_RECENT_FIELD: events.tail(JEV_COMPUTE_RECENT_EVENTS, event_chars=JEV_COMPUTE_RECENT_EVENT_MAX_CHARS),
        }
        match situation:
            case JevComputeSituation.REPEATING:
                specific = cls._repeating(brief)
            case JevComputeSituation.EACH_OF_SEVERAL:
                specific = cls._each_of_several(brief)
            case JevComputeSituation.SELF_CONTAINED_STEP:
                specific = cls._self_contained_step(brief)
        return None if specific is None else {**common, **specific}

    @staticmethod
    def stuck_problem(brief: JevRunBrief) -> tuple[str, tuple[JevRunBriefApproach, ...]] | None:
        """Return the first problem a failed approach targeted that no approach has solved, with every approach taken on it."""
        solved = {approach.target for approach in brief.approaches if approach.outcome is JevRunBriefOutcome.WORKED}
        problem = next((approach.target for approach in brief.approaches if approach.outcome is JevRunBriefOutcome.FAILED and approach.target not in solved), None)
        if problem is None:
            return None
        return problem, tuple(approach for approach in brief.approaches if approach.target == problem)

    @classmethod
    def _repeating(cls, brief: JevRunBrief) -> ComputeState | None:
        # Describes the stuck problem, every attempt on it, and the open failures.
        stuck = cls.stuck_problem(brief)
        if stuck is None:
            return None
        problem, approaches = stuck
        attempts = tuple(
            {"approach": approach.approach, "outcome": approach.outcome.value, "evidence": tuple(cls.quote(quote) for quote in approach.evidence)}
            for approach in approaches
        )
        return {
            JEV_COMPUTE_PROBLEM_FIELD: problem,
            JEV_COMPUTE_ATTEMPTS_FIELD: attempts,
            JEV_COMPUTE_FAILURES_FIELD: tuple(cls.quote(quote) for quote in brief.open_failures),
        }

    @classmethod
    def _each_of_several(cls, brief: JevRunBrief) -> ComputeState | None:
        # Picks the group with the most pending items, and quotes the agent's current and next steps as its plan.
        pending = Counter(item.group for item in brief.items if item.status is JevRunBriefItemStatus.PENDING)
        if not pending:
            return None
        group, count = pending.most_common(1)[0]
        if count < JEV_COMPUTE_EACH_OF_SEVERAL_MIN_PENDING:
            return None
        steps = ((brief.current_step,) if brief.current_step is not None else ()) + brief.next_steps
        return {
            JEV_COMPUTE_GROUP_FIELD: {"name": group, "items": tuple({"name": item.name, "status": item.status.value} for item in brief.items if item.group == group)},
            JEV_COMPUTE_PLAN_FIELD: tuple(cls.quote(quote) for quote in steps),
        }

    @classmethod
    def _self_contained_step(cls, brief: JevRunBrief) -> ComputeState | None:
        # Picks the soonest stated next step, with the whole brief so references to the run can be recognized.
        if not brief.next_steps:
            return None
        return {JEV_COMPUTE_NEXT_STEP_FIELD: cls.quote(brief.next_steps[0]), JEV_COMPUTE_BRIEF_FIELD: brief.render()}

    @staticmethod
    def quote(quote: JevRunBriefQuote) -> str:
        """Return a brief quote with its event id beside its text, as the state descriptions and helper prompts show it."""
        return f"{quote.event}: {quote.quote}"


__all__ = ["JevComputeStates"]

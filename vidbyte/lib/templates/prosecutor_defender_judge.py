"""Context Protocol Header

FILE: vidbyte/lib/templates/prosecutor_defender_judge.py
PURPOSE: Defines canonical recorder-slot sequences for successful and failed
prosecutor/defender/judge context-window runs.
ROLE IN CODEBASE: Test harnesses and manual verification compare an algorithm
recorder against this ContextWindowTemplate subclass.
ARCHITECTURE NOTE: Failure sequences contain only a canonical completed-stage
prefix followed by one failure slot; preflight uses an empty prefix.
FUNCTION INVENTORY: The template constructor validates stage prefixes and builds
the exact expected slot list.
WHAT NOT TO DO: Do not accept reordered, duplicated, or skipped completed roles.
KNOWN EDGE CASES: A judge failure has prosecutor and defender slots but no judge
slot; a successful run cannot specify failed_stage.
RELATED DOCS: docs/design/context-window-prosecutor-defender-judge.md.
TEST FILES: No new tests are authorized by the approved no-tests design.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate

_CANONICAL_STAGES = ("prosecutor", "defender", "judge")
_STAGE_SLOTS = {
    "prosecutor": "prosecutor_defender_judge_prosecutor",
    "defender": "prosecutor_defender_judge_defender",
    "judge": "prosecutor_defender_judge_judge",
}


class ProsecutorDefenderJudgeContextWindowTemplate(ContextWindowTemplate):
    """Template for a successful run or one stage-labelled failure."""

    def __init__(self, *, completed_stages: tuple[str, ...] = _CANONICAL_STAGES, failed_stage: str | None = None) -> None:
        # Validates the canonical prefix and builds the deterministic slot sequence.
        if completed_stages != _CANONICAL_STAGES[: len(completed_stages)]:
            raise ValueError("completed_stages must be a canonical prosecutor/defender/judge prefix.")
        if failed_stage is None and completed_stages != _CANONICAL_STAGES:
            raise ValueError("Successful template requires all three completed stages.")
        if failed_stage is not None:
            if failed_stage not in _CANONICAL_STAGES:
                raise ValueError(f"Unknown failed_stage: {failed_stage!r}.")
            if failed_stage in completed_stages:
                raise ValueError("failed_stage cannot also appear in completed_stages.")
            if completed_stages and failed_stage != _CANONICAL_STAGES[len(completed_stages)]:
                raise ValueError("failed_stage must immediately follow completed_stages.")
        slots = ["system_prompt", "prosecutor_defender_judge_candidate"]
        slots.extend(_STAGE_SLOTS[stage] for stage in completed_stages)
        if failed_stage is not None:
            slots.append("prosecutor_defender_judge_failure")
        super().__init__(slots)


__all__ = ["ProsecutorDefenderJudgeContextWindowTemplate"]

"""FILE: vidbyte/lib/enums/jev_run_state.py

PURPOSE: Defines the closed value sets used by JevAgent's run state, event log, and required-sequence done check.
ROLE IN CODEBASE: vidbyte/agents/jev/run_state.py, event_log.py, and required_sequence.py key records and verdicts on these members.
ARCHITECTURE NOTE: Kept apart from vidbyte/lib/enums/jev.py, which mirrors TypeSafe's wire vocabulary; these values are SDK policy, not provider protocol.
COMMON MODIFICATION PATTERNS: Add a JevRunSectionKey member together with its JevRunSection implementation and JevAgentSettings flag.
KNOWN EDGE CASES: Values appear in result metadata, so renaming one is a breaking change for callers that read the run report.
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

from enum import Enum


class JevRunSectionKey(str, Enum):
    """Named run-state sections a JevAgent setting can enable."""

    REQUIRED_SEQUENCE = "required_sequence"


class JevSectionStatus(str, Enum):
    """Whether a run-state section gates this run."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    UNAVAILABLE = "unavailable"


class JevRunEventKind(str, Enum):
    """Source of one numbered event in the run's event log."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FINISH_REVIEW = "finish_review"


class JevStageFailure(str, Enum):
    """First reason a required stage failed its finish review."""

    NO_WORK = "no_work"
    OUT_OF_ORDER = "out_of_order"
    WORK_NOT_SHOWN = "work_not_shown"
    PREVIOUS_OUTPUT_NOT_USED = "previous_output_not_used"


__all__ = ["JevRunEventKind", "JevRunSectionKey", "JevSectionStatus", "JevStageFailure"]

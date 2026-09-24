"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed TypeSafe Jev question types plus the closed vocabularies of JevAgent's motivating-case done check.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members and `vidbyte/providers/typesafe.py` serializes their values onto the wire.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change. Motivating-case members also appear in the state builder's JSON schema and prompt, so change all three together.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-motivating-case.md, and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_motivating_case.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from enum import Enum


class JevQuestionType(str, Enum):
    """TypeSafe System One question types."""

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class JevBoundaryKind(str, Enum):
    """Kinds of boundary condition a request can be motivated by; each has what/not_for text in the builder prompt."""

    EMPTY_OR_MISSING = "empty_or_missing"
    SIZE_OR_LIMIT = "size_or_limit"
    REPEAT_OR_RETRY = "repeat_or_retry"
    FAILURE_PATH = "failure_path"
    CONFLICTING_STATE = "conflicting_state"
    ORDERING_OR_TIMING = "ordering_or_timing"
    ACCESS = "access"
    FORMAT = "format"
    OTHER = "other"


class JevScenarioRole(str, Enum):
    """Why a scenario is in the run state, which decides whether it can block finishing."""

    MOTIVATING = "motivating"
    REQUESTED = "requested"
    IMPLIED = "implied"


class JevExerciseMode(str, Enum):
    """Which kind of evidence can satisfy a scenario."""

    RUN = "run"
    RUN_OR_INSPECT = "run_or_inspect"
    INSPECT_ONLY = "inspect_only"


class JevScenarioOutcome(str, Enum):
    """Code-combined result for one scenario at one finish attempt."""

    EXERCISED = "exercised"
    INSPECTED = "inspected"
    BLOCKED = "blocked"
    NOT_EXERCISED = "not_exercised"


__all__ = ["JevBoundaryKind", "JevExerciseMode", "JevQuestionType", "JevScenarioOutcome", "JevScenarioRole"]

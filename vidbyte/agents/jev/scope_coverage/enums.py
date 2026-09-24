"""FILE: vidbyte/agents/jev/scope_coverage/enums.py

PURPOSE: Defines the closed vocabularies of the scope-coverage done check.
ROLE IN CODEBASE: The state and handoff sections validate generated labels against these members; the check and decision records report them.
ARCHITECTURE NOTE: Feature-local like JevPresets; serialized values are the exact strings the builder schemas allow.
COMMON MODIFICATION PATTERNS: Change a member together with its builder prompt asset, schema enum, and policy branch.
KNOWN EDGE CASES: Only EVERY_MEMBER and NAMED_LIST breadths are checked; the other two are recorded and skipped.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from enum import Enum


class JevScopeBreadth(str, Enum):
    """How much of a group the request asks the change to reach."""

    EVERY_MEMBER = "every_member"
    NAMED_LIST = "named_list"
    ONE_EXAMPLE = "one_example"
    SINGLE_TARGET = "single_target"

    @classmethod
    def values(cls) -> list[str]:
        """Return the serialized values in declaration order."""
        return [member.value for member in cls]

    def is_checked(self) -> bool:
        """Return whether this breadth promises coverage of more than one member."""
        return self in (JevScopeBreadth.EVERY_MEMBER, JevScopeBreadth.NAMED_LIST)


class JevScopeUniverse(str, Enum):
    """Where the full list of members comes from."""

    NAMED_IN_REQUEST = "named_in_request"
    FOUND_IN_WORKSPACE = "found_in_workspace"
    OPEN_ENDED = "open_ended"

    @classmethod
    def values(cls) -> list[str]:
        """Return the serialized values in declaration order."""
        return [member.value for member in cls]


class JevScopeUnitSource(str, Enum):
    """Why a unit appears in a handoff dimension; recomputed in code after generation."""

    NAMED_IN_REQUEST = "named_in_request"
    FOUND_BY_RUN = "found_by_run"
    MENTIONED_BY_AGENT = "mentioned_by_agent"

    @classmethod
    def values(cls) -> list[str]:
        """Return the serialized values in declaration order."""
        return [member.value for member in cls]


class JevScopeCoverageOutcome(str, Enum):
    """What the scope check decided at one finish attempt."""

    COMPLETE = "complete"
    NOT_CHECKED = "not_checked"
    CONTINUED = "continued"
    DISCLOSURE_REQUESTED = "disclosure_requested"
    PARTIAL_DISCLOSED = "partial_disclosed"
    PARTIAL_UNDISCLOSED = "partial_undisclosed"


__all__ = ["JevScopeBreadth", "JevScopeCoverageOutcome", "JevScopeUnitSource", "JevScopeUniverse"]

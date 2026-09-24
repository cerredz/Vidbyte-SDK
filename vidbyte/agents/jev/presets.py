"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Defines the closed user-facing Jev capability presets and normalizes the done_criteria argument.
ROLE IN CODEBASE: JevAgent validates its done_criteria through normalize_done_criteria; JevRuntime owns each preset's fixed implementation.
ARCHITECTURE NOTE: Presets name product behavior; internal questions and thresholds stay private.
COMMON MODIFICATION PATTERNS: Add a preset only with its complete JevDoneCheck subclass, state/handoff sections, docs, and tests.
KNOWN EDGE CASES: Raw strings are not accepted by JevAgent even though this enum subclasses str; empty and duplicate tuples are rejected.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-scope-coverage-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from enum import Enum

from vidbyte.lib.errors import ConfigurationError


class JevPresets(str, Enum):
    """Closed named policies supported by JevAgent."""

    MultiPart = "multi_part"
    ScopeCoverage = "scope_coverage"


def normalize_done_criteria(value: object) -> tuple[JevPresets, ...]:
    """Return the enabled presets in declaration order from one preset, a tuple of presets, or None."""
    # @intent closed-done-criteria-surface
    # Only JevPresets members reach the runtime, so a typo or raw string cannot silently disable a check.
    if value is None:
        return ()
    if isinstance(value, JevPresets):
        return (value,)
    if not isinstance(value, tuple) or not value:
        raise ConfigurationError(
            "JevAgent.done_criteria must be a JevPresets member, a non-empty tuple of JevPresets members, or None.",
            details={"received_type": type(value).__name__},
        )
    if not all(isinstance(item, JevPresets) for item in value):
        raise ConfigurationError(
            "Every JevAgent.done_criteria entry must be a JevPresets member; raw strings are not accepted.",
            details={"received_types": [type(item).__name__ for item in value]},
        )
    if len(set(value)) != len(value):
        raise ConfigurationError("JevAgent.done_criteria must not repeat a preset.", details={"received": [item.value for item in value]})
    return tuple(member for member in JevPresets if member in value)


__all__ = ["JevPresets", "normalize_done_criteria"]

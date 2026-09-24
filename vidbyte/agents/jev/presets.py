"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Defines the closed user-facing Jev capability presets.
ROLE IN CODEBASE: JevAgent accepts these named choices and JevRuntime owns their fixed implementation.
ARCHITECTURE NOTE: Presets name product behavior; internal questions and thresholds stay private.
COMMON MODIFICATION PATTERNS: Add a preset only with its complete settings validation, runtime policy, docs, and tests.
KNOWN EDGE CASES: Raw strings are not accepted by JevAgent even though this enum subclasses str.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py.
"""

from enum import Enum


class JevPresets(str, Enum):
    """Closed named policies supported by JevAgent."""

    MultiPart = "multi_part"


__all__ = ["JevPresets"]

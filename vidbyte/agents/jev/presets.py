"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Defines the closed, named done-criteria presets a caller can enable on JevAgent.
ROLE IN CODEBASE: JevAgent(settings, done_criteria=JevPresets.MotivatingCase) passes the member to JevRuntime, which owns the fixed policy behind it.
ARCHITECTURE NOTE: A preset names product behavior; its questions, thresholds, and actions stay private to vidbyte/agents/jev/.
COMMON MODIFICATION PATTERNS: Add a member only together with its runtime policy, prompts, docs, and tests.
KNOWN EDGE CASES: Raw strings are refused by JevAgent even though this StrEnum compares equal to its values.
RELATED DOCS: docs/design/jev-motivating-case.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from enum import StrEnum


class JevPresets(StrEnum):
    """Named done-criteria policies supported by JevAgent."""

    MotivatingCase = "motivating_case"


__all__ = ["JevPresets"]

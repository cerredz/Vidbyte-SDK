"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed set of TypeSafe Jev question types the SDK can send to the System One endpoint.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members and `vidbyte/providers/typesafe.py` serializes their values onto the wire.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a member only when TypeSafe documents a new question type, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it.
RELATED DOCS: docs/design/jev-agent-scaffold.md and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
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


__all__ = ["JevQuestionType"]

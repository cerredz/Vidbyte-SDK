"""FILE: vidbyte/lib/enums/integrations.py

PURPOSE: Defines the categorical vocabulary for external source integrations.
ROLE IN CODEBASE: SourceConfig coerces the public provider string into SourceProvider so downstream code matches on an enum.
ARCHITECTURE NOTE: The enum gains a member per supported provider; raw strings never flow past the validated config boundary.
COMMON MODIFICATION PATTERNS: Add a member here and a factory branch in vidbyte/integrations/providers.py together.
KNOWN EDGE CASES: Coercion is case-insensitive but the resource address always keeps its original case.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

from enum import Enum


class SourceProvider(str, Enum):
    """External provider a source integration reads from."""

    GITHUB = "github"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return every accepted provider name as plain strings."""
        return tuple(member.value for member in cls)


class SourceKind(str, Enum):
    """Shape of resource a validated source address points at."""

    PULL_REQUEST = "pull_request"
    REPOSITORY = "repository"


__all__ = [
    "SourceKind",
    "SourceProvider",
]

"""FILE: vidbyte/lib/enums/integrations.py

PURPOSE: Defines the categorical vocabularies used by the Sources access layer.
ROLE IN CODEBASE: Every mode, operation, authorization state, and outcome the integrations layer reports comes from here.
ARCHITECTURE NOTE: All vocabularies subclass IntegrationEnum so parser choices derive from members rather than duplicated literals.
COMMON MODIFICATION PATTERNS: Add a member with a semantically distinct meaning; never add a member that restates an existing one.
KNOWN EDGE CASES: Raw strings are coerced to members in Sources.__init__, never inside a frozen dataclass field.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

from enum import Enum


class IntegrationEnum(str, Enum):
    """Base enum exposing canonical serialized values for integration vocabularies."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class LoadMode(IntegrationEnum):
    """Decides whether a selection is fetched before the run, exposed as tools, or both."""

    LOAD = "load"
    TOOLS = "tools"
    HYBRID = "hybrid"


class ProviderOperation(IntegrationEnum):
    """One read capability a provider adapter can expose to an agent as a scoped tool."""

    LIST = "list"
    SEARCH = "search"
    READ = "read"


class AccessState(IntegrationEnum):
    """Outcome of authorizing one selection against its connection and credentials."""

    GRANTED = "granted"
    AUTH_REQUIRED = "auth_required"
    REAUTH_REQUIRED = "reauth_required"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    RATE_LIMITED = "rate_limited"
    TRANSPORT_FAILED = "transport_failed"


class LoadOutcome(IntegrationEnum):
    """What actually happened to one selection's content during resolution."""

    LOADED = "loaded"
    TRUNCATED = "truncated"
    SKIPPED = "skipped"
    FAILED = "failed"
    TOOLS_ONLY = "tools_only"


class FailurePolicy(IntegrationEnum):
    """Decides whether a failed selection aborts resolution or is recorded and survived."""

    REPORT = "report"
    REQUIRE_ALL = "require_all"


__all__ = [
    "AccessState",
    "FailurePolicy",
    "IntegrationEnum",
    "LoadMode",
    "LoadOutcome",
    "ProviderOperation",
]

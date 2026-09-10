"""FILE: vidbyte/lib/dataclasses/integrations.py

PURPOSE: Defines every validated value type the Sources access layer passes between its components.
ROLE IN CODEBASE: Connections, credentials, selections, scopes, budgets, and report entries are all constructed here and are provably valid once built.
ARCHITECTURE NOTE: Each dataclass is frozen and slotted and owns its own rules in __post_init__, so no consumer re-checks a shape it was handed.
COMMON MODIFICATION PATTERNS: Add a field with its validation in the same __post_init__; coerce loose caller types before construction, never inside the dataclass.
KNOWN EDGE CASES: A credential with no expiry is not expired, an empty required-scope tuple is always covered, and filters are frozen into an immutable mapping.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from vidbyte.lib.constants.integrations import (
    INTEGRATIONS_MAX_TOKENS_CEILING,
    INTEGRATIONS_MAX_TOOL_BYTES_CEILING,
    INTEGRATIONS_MAX_TOOL_CALLS_CEILING,
)
from vidbyte.lib.enums.integrations import AccessState, LoadMode, LoadOutcome
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Connection:
    """One authenticated provider account, addressed by a non-secret identifier."""

    connection_id: str
    provider: str
    account_label: str = ""

    def __post_init__(self) -> None:
        """Reject a connection that cannot be addressed or attributed to a provider."""
        if not self.connection_id.strip():
            raise ConfigurationError("Connection.connection_id cannot be empty.")
        if not self.provider.strip():
            raise ConfigurationError("Connection.provider cannot be empty.")


@dataclass(frozen=True, slots=True)
class Credentials:
    """A resolved provider secret with its granted scopes and optional expiry."""

    connection_id: str
    token: str
    scopes: tuple[str, ...] = ()
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        """Reject an unusable credential and require any expiry to be timezone-aware."""
        # @intent redaction
        # Only the presence of the token is validated here. Its value is never
        # logged, rendered into a report entry, or copied into an exception
        # message anywhere in this layer.
        if not self.connection_id.strip():
            raise ConfigurationError("Credentials.connection_id cannot be empty.")
        if not self.token.strip():
            raise ConfigurationError("Credentials.token cannot be empty.")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ConfigurationError("Credentials.expires_at must be timezone-aware.")

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return True only when an expiry is set and has already passed."""
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or datetime.now(timezone.utc))

    def covers(self, required: tuple[str, ...]) -> bool:
        """Return True when every required scope was granted to this credential."""
        return all(scope in self.scopes for scope in required)


@dataclass(frozen=True, slots=True)
class ResourceSelection:
    """One external resource a run may read, with the mode and bounds that govern it."""

    provider: str
    resource_id: str
    connection: str
    mode: LoadMode = LoadMode.LOAD
    filters: Mapping[str, Any] = field(default_factory=dict)
    limit: int | None = None
    required_scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject an unaddressable selection and freeze its filter mapping."""
        if not self.provider.strip():
            raise ConfigurationError("ResourceSelection.provider cannot be empty.")
        if not self.resource_id.strip():
            raise ConfigurationError("ResourceSelection.resource_id cannot be empty.")
        if not self.connection.strip():
            raise ConfigurationError("ResourceSelection.connection cannot be empty.")
        if self.limit is not None and self.limit <= 0:
            raise ConfigurationError("ResourceSelection.limit must be a positive integer when set.")
        object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))

    @property
    def loads(self) -> bool:
        """Return True when this selection contributes content to the context window."""
        return self.mode in (LoadMode.LOAD, LoadMode.HYBRID)

    @property
    def exposes_tools(self) -> bool:
        """Return True when this selection contributes scoped tools to the agent."""
        return self.mode in (LoadMode.TOOLS, LoadMode.HYBRID)

    def identity(self) -> tuple[str, str, str]:
        """Return the tuple that makes two selections duplicates of one another."""
        return (self.provider, self.resource_id, self.mode.value)


@dataclass(frozen=True, slots=True)
class ResourceScope:
    """The immutable resource boundary a scoped tool is permanently bound to."""

    provider: str
    resource_id: str
    connection_id: str

    def __post_init__(self) -> None:
        """Reject a scope that cannot identify the resource it is meant to bound."""
        if not self.provider.strip():
            raise ConfigurationError("ResourceScope.provider cannot be empty.")
        if not self.resource_id.strip():
            raise ConfigurationError("ResourceScope.resource_id cannot be empty.")
        if not self.connection_id.strip():
            raise ConfigurationError("ResourceScope.connection_id cannot be empty.")

    def qualified_id(self) -> str:
        """Return the single string a scope policy compares against its granted set."""
        return f"{self.provider}:{self.resource_id}"


@dataclass(frozen=True, slots=True)
class LoadRequest:
    """Everything an adapter needs to fetch one selection's content."""

    selection: ResourceSelection
    connection: Connection
    credentials: Credentials


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """The verdict on one selection's connection, carrying credentials only when granted."""

    state: AccessState
    connection: Connection | None = None
    credentials: Credentials | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        """Guarantee that a denied authorization can never carry a usable credential."""
        # @intent permissions
        # A non-granted result must be structurally incapable of leaking a
        # credential, so callers cannot accidentally read one off a denial.
        if self.state is not AccessState.GRANTED and (self.connection is not None or self.credentials is not None):
            raise ConfigurationError("AuthorizationResult may only carry a connection and credentials when granted.")
        if self.state is AccessState.GRANTED and (self.connection is None or self.credentials is None):
            raise ConfigurationError("A granted AuthorizationResult requires both a connection and credentials.")

    @property
    def granted(self) -> bool:
        """Return True when this selection may proceed to the provider."""
        return self.state is AccessState.GRANTED

    def require_connection(self) -> Connection:
        """Return the granted connection, raising rather than yielding None to a caller."""
        if self.connection is None:
            raise ConfigurationError(f"No connection is available on a '{self.state.value}' authorization result.")
        return self.connection

    def require_credentials(self) -> Credentials:
        """Return the granted credentials, raising rather than yielding None to a caller."""
        if self.credentials is None:
            raise ConfigurationError(f"No credentials are available on a '{self.state.value}' authorization result.")
        return self.credentials


@dataclass(frozen=True, slots=True)
class SelectionReportEntry:
    """What actually happened to one selection, including why it failed."""

    selection: ResourceSelection
    outcome: LoadOutcome
    state: AccessState
    item_count: int = 0
    tokens_loaded: int = 0
    tokens_original: int = 0
    detail: str = ""

    def describe(self) -> str:
        """Render one human-readable report line for this selection."""
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.selection.provider}:{self.selection.resource_id} -> {self.outcome.value}/{self.state.value}{suffix}"


@dataclass(frozen=True, slots=True)
class ContextBudgetPlan:
    """The validated numeric ceilings one Sources resolution runs under."""

    max_tokens: int
    max_tool_calls: int
    max_tool_bytes: int

    def __post_init__(self) -> None:
        """Reject negative budgets and any ceiling above the documented maximum."""
        self._require_within("max_tokens", self.max_tokens, INTEGRATIONS_MAX_TOKENS_CEILING)
        self._require_within("max_tool_calls", self.max_tool_calls, INTEGRATIONS_MAX_TOOL_CALLS_CEILING)
        self._require_within("max_tool_bytes", self.max_tool_bytes, INTEGRATIONS_MAX_TOOL_BYTES_CEILING)

    @staticmethod
    def _require_within(name: str, value: int, ceiling: int) -> None:
        """Raise when one budget field is negative, non-integer, or above its ceiling."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError(f"ContextBudgetPlan.{name} must be an integer.")
        if value < 0:
            raise ConfigurationError(f"ContextBudgetPlan.{name} cannot be negative.")
        if value > ceiling:
            raise ConfigurationError(f"ContextBudgetPlan.{name} cannot exceed {ceiling}.")


__all__ = [
    "AuthorizationResult",
    "Connection",
    "ContextBudgetPlan",
    "Credentials",
    "LoadRequest",
    "ResourceScope",
    "ResourceSelection",
    "SelectionReportEntry",
]

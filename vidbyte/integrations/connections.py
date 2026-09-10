"""FILE: vidbyte/integrations/connections.py

PURPOSE: Resolves a developer-facing connection name into an authenticated, scope-checked provider connection.
ROLE IN CODEBASE: The only place the Sources layer decides whether a selection may reach its provider at all.
ARCHITECTURE NOTE: CredentialResolver is a protocol so a CLI keyring or a hosted backend can supply secrets without the SDK importing either.
COMMON MODIFICATION PATTERNS: Add an authorization check as one more ordered step in ConnectionBroker.authorize, returning a typed AccessState rather than raising.
KNOWN EDGE CASES: A resolver that raises degrades to TRANSPORT_FAILED, and a denied result is structurally unable to carry credentials.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vidbyte.lib.dataclasses.integrations import (
    AuthorizationResult,
    Connection,
    Credentials,
    ResourceSelection,
)
from vidbyte.lib.enums.integrations import AccessState
from vidbyte.lib.errors import ConfigurationError


@runtime_checkable
class CredentialResolver(Protocol):
    """Supplies the secret for one connection, or None when the account is not linked."""

    async def resolve(self, connection: Connection) -> Credentials | None:
        """Return valid credentials for a connection, or None when none are available."""
        ...


class ConnectionRegistry:
    """Maps the connection names developers write in selections to immutable connections."""

    def __init__(self) -> None:
        # Names are developer-chosen labels; the connection carries the stable identifier.
        self._connections: dict[str, Connection] = {}

    def register(self, name: str, connection: Connection) -> ConnectionRegistry:
        """Register one named connection and return this registry for chaining."""
        if not name.strip():
            raise ConfigurationError("A connection name cannot be empty.")
        self._connections[name] = connection
        return self

    def resolve(self, name: str) -> Connection | None:
        """Return the connection registered under a name, or None when absent."""
        return self._connections.get(name)

    def names(self) -> tuple[str, ...]:
        """Return every registered connection name in sorted order."""
        return tuple(sorted(self._connections))


class InMemoryCredentialResolver:
    """Credential resolver backed by an in-process map, used for tests and embedding."""

    def __init__(self) -> None:
        # @intent redaction
        # Secrets live only for the lifetime of this object and are never written
        # to disk, logged, or copied into a report entry by this layer.
        self._credentials: dict[str, Credentials] = {}

    def add(self, connection_id: str, credentials: Credentials) -> InMemoryCredentialResolver:
        """Store credentials under a connection id and return this resolver for chaining."""
        self._credentials[connection_id] = credentials
        return self

    async def resolve(self, connection: Connection) -> Credentials | None:
        """Return stored credentials for a connection, or None when none were added."""
        return self._credentials.get(connection.connection_id)


class ConnectionBroker:
    """Decides whether one selection is authorized, and returns the verdict as a typed state."""

    def __init__(self, *, connections: ConnectionRegistry, resolver: CredentialResolver) -> None:
        # Both collaborators are injected so hosted and local credential sources are interchangeable.
        self._connections = connections
        self._resolver = resolver

    async def authorize(self, selection: ResourceSelection) -> AuthorizationResult:
        """Run every authorization check for one selection and return the first failing state."""
        # @intent permissions
        # Each step returns a distinct AccessState so a caller can tell an unlinked
        # account from an expired token from a missing scope, and can act on it.
        connection = self._connections.resolve(selection.connection)
        if connection is None:
            return AuthorizationResult(state=AccessState.AUTH_REQUIRED, detail=f"No connection named '{selection.connection}' is registered.")
        if connection.provider != selection.provider:
            return AuthorizationResult(state=AccessState.INSUFFICIENT_SCOPE, detail=f"Connection '{selection.connection}' is for {connection.provider}, not {selection.provider}.")
        try:
            credentials = await self._resolve_credentials(connection)
        except Exception as exc:
            return AuthorizationResult(state=AccessState.TRANSPORT_FAILED, detail=f"Credential resolution failed with {type(exc).__name__}.")
        if credentials is None:
            return AuthorizationResult(state=AccessState.AUTH_REQUIRED, detail=f"No credentials are available for connection '{selection.connection}'.")
        return self._verify_credentials(selection, connection, credentials)

    async def _resolve_credentials(self, connection: Connection) -> Credentials | None:
        """Await the injected resolver for one connection's secret."""
        # @intent external boundaries
        # The resolver may reach an OS keyring or a remote service. Its failure is
        # caught by the caller and reported as one selection's transport failure so
        # a broken secret store cannot cancel every sibling selection in the run.
        return await self._resolver.resolve(connection)

    def _verify_credentials(self, selection: ResourceSelection, connection: Connection, credentials: Credentials) -> AuthorizationResult:
        """Check expiry and granted scopes, returning a granted result only when both pass."""
        if credentials.is_expired():
            return AuthorizationResult(state=AccessState.REAUTH_REQUIRED, detail=f"Credentials for '{selection.connection}' have expired.")
        if not credentials.covers(selection.required_scopes):
            return AuthorizationResult(state=AccessState.INSUFFICIENT_SCOPE, detail=f"Connection '{selection.connection}' is missing a required scope.")
        return AuthorizationResult(state=AccessState.GRANTED, connection=connection, credentials=credentials)


__all__ = [
    "ConnectionBroker",
    "ConnectionRegistry",
    "CredentialResolver",
    "InMemoryCredentialResolver",
]

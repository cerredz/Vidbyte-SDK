"""FILE: vidbyte/lib/dataclasses/tool_catalogs.py

PURPOSE: Defines the typed records every public tool catalog is normalized into: an entry, the ways it can be installed, the secrets it needs, its tools, and the credentials a catalog needs.
ROLE IN CODEBASE: vidbyte/providers/tool_catalogs/ adapters return these records; JevAgentAlignment's tool alignment filters, judges, and attaches from them without knowing which catalog an entry came from.
ARCHITECTURE NOTE: Catalog payload dictionaries never leave the provider layer. Only these frozen records cross into the agents layer, so a new catalog changes one adapter, not the alignment logic.
COMMON MODIFICATION PATTERNS: Add a field here only when two or more catalogs report it; catalog-only details stay inside the adapter that reads them.
KNOWN EDGE CASES: Secrets and credentials are excluded from repr so a logged entry or settings object never prints a key.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py and tests/test_jev_tool_alignment.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from vidbyte.lib.enums.tool_catalogs import (
    ToolCatalogName,
    ToolInstallKind,
    ToolSecretLocation,
)
from vidbyte.lib.errors import ConfigurationError

VALUE_PLACEHOLDER = "{value}"


@dataclass(frozen=True, slots=True)
class ToolCatalogCredentials:
    """Owner credentials for one keyed catalog; which fields are needed depends on the catalog."""

    api_key: str | None = field(default=None, repr=False)
    client_id: str | None = None
    client_secret: str | None = field(default=None, repr=False)
    project_id: str | None = None
    environment: str | None = None

    def __post_init__(self) -> None:
        # Rejects blank strings so a missing credential is always None, never an empty header value.
        for name in ("api_key", "client_id", "client_secret", "project_id", "environment"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ConfigurationError(f"ToolCatalogCredentials.{name} must be a non-blank string or None.")


@dataclass(frozen=True, slots=True)
class ToolSecretRequirement:
    """One secret or config value an install needs, and where it is sent."""

    name: str  # the key the owner supplies it under, such as BRAVE_API_KEY
    location: ToolSecretLocation
    target: str  # the header name, query key, or environment variable it is sent as
    template: str = VALUE_PLACEHOLDER  # how the value is rendered, such as "Bearer {value}"
    required: bool = True
    description: str = ""

    def render(self, value: str) -> str:
        """Return the value formatted the way the install expects it."""
        return self.template.replace(VALUE_PLACEHOLDER, value)


@dataclass(frozen=True, slots=True)
class ToolInstall:
    """One way to run an entry's tools: a remote endpoint, a managed platform, a local process, or an API description."""

    kind: ToolInstallKind
    url: str | None = None  # REMOTE_HTTP endpoint, or the OpenAPI document for OPENAPI
    command: tuple[str, ...] = ()  # CONTAINER or PACKAGE stdio command
    static_headers: Mapping[str, str] = field(default_factory=dict)  # non-secret headers every request carries
    secrets: tuple[ToolSecretRequirement, ...] = ()
    pinned: bool = True  # False when a PACKAGE names no version, so a later publish could change what runs
    reference: str | None = None  # MANAGED platform reference, such as a toolkit or app slug

    def __post_init__(self) -> None:
        # Freezes header mappings and requires the field each kind is run from.
        object.__setattr__(self, "static_headers", MappingProxyType(dict(self.static_headers)))
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "secrets", tuple(self.secrets))
        if self.kind in (ToolInstallKind.REMOTE_HTTP, ToolInstallKind.OPENAPI) and not self.url:
            raise ConfigurationError(f"A {self.kind.value} install needs a url.")
        if self.kind in (ToolInstallKind.CONTAINER, ToolInstallKind.PACKAGE) and not self.command:
            raise ConfigurationError(f"A {self.kind.value} install needs a command.")
        if self.kind is ToolInstallKind.MANAGED and not self.reference:
            raise ConfigurationError("A managed install needs a platform reference.")

    @property
    def location(self) -> str:
        """Return the URL, command, or platform reference a user can recognize the install by."""
        if self.url:
            return self.url
        if self.command:
            return " ".join(self.command)
        return self.reference or ""

    @property
    def required_secrets(self) -> tuple[ToolSecretRequirement, ...]:
        """Return the secrets the install cannot run without."""
        return tuple(secret for secret in self.secrets if secret.required)


@dataclass(frozen=True, slots=True)
class CatalogTool:
    """One tool an entry exposes, with the safety hints its catalog or server declares."""

    name: str
    description: str
    input_schema: Mapping[str, object] = field(default_factory=dict)
    read_only: bool | None = None  # the declared read-only hint, when the catalog reports one
    destructive: bool | None = None  # the declared destructive hint, when the catalog reports one

    def __post_init__(self) -> None:
        # Freezes the schema so a shared entry cannot be edited by one consumer.
        object.__setattr__(self, "input_schema", MappingProxyType(dict(self.input_schema)))


@dataclass(frozen=True, slots=True)
class ToolCatalogEntry:
    """One server, toolkit, or app a catalog lists, normalized across catalogs."""

    catalog: ToolCatalogName
    entry_id: str
    name: str
    description: str
    installs: tuple[ToolInstall, ...] = ()
    tools: tuple[CatalogTool, ...] = ()
    version: str | None = None
    publisher: str | None = None
    verified: bool = False
    repository_url: str | None = None

    def __post_init__(self) -> None:
        # Requires an id and a name, and freezes the tuples so entries can be shared across passes.
        if not self.entry_id or not self.name:
            raise ConfigurationError("A ToolCatalogEntry needs an entry_id and a name.")
        object.__setattr__(self, "installs", tuple(self.installs))
        object.__setattr__(self, "tools", tuple(self.tools))

    @property
    def key(self) -> str:
        """Return the id that is unique across catalogs, such as mcp_registry:io.github.github/github-mcp-server."""
        return f"{self.catalog.value}:{self.entry_id}"


@dataclass(frozen=True, slots=True)
class ToolConnection:
    """A connectable endpoint an install resolves to: the MCP URL and the headers every request carries."""

    url: str
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Freezes the headers, which usually carry a credential.
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class ToolCatalogSearch:
    """The merged result of one query across catalogs, with each failed catalog's safe error text."""

    entries: tuple[ToolCatalogEntry, ...] = ()
    errors: Mapping[ToolCatalogName, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freezes the merged result so the scout cannot mutate what later steps read.
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(self, "errors", MappingProxyType(dict(self.errors)))


__all__ = [
    "VALUE_PLACEHOLDER",
    "CatalogTool",
    "ToolCatalogCredentials",
    "ToolCatalogEntry",
    "ToolCatalogSearch",
    "ToolConnection",
    "ToolInstall",
    "ToolSecretRequirement",
]

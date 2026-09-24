"""FILE: vidbyte/providers/tool_catalogs/toolsdk.py

PURPOSE: Adapts ToolSDK's MCP registry (a JSON index published from GitHub, keyed by npm package name) into ToolCatalogEntry records.
ROLE IN CODEBASE: ToolCatalogs builds ToolSdkCatalog for ToolCatalogName.TOOLSDK; JevAgentAlignment searches the cached index and describes entries through it.
ARCHITECTURE NOTE: The index (`packages-list.json`) holds each package's category, validation flag, and tool names and descriptions; describe() reads the package's own JSON file for its description, runtime, environment variables, and remotes.
COMMON MODIFICATION PATTERNS: Map a new `runtime` value in _package_install; keep remotes whose environment variables have no declared header mapping unattachable.
KNOWN EDGE CASES: Packages name no version, so their npx/uvx installs are unpinned and the fact filter rejects them unless the owner allows unpinned packages; the SDK never runs a package whose next publish could change what runs. The index is ~2.7 MB and is cached per adapter instance.
RELATED DOCS: https://github.com/toolsdk-ai/toolsdk-mcp-registry and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import (
    TOOLSDK_INDEX_URL,
    TOOLSDK_PACKAGE_BASE_URL,
)
from vidbyte.lib.dataclasses.tool_catalogs import (
    CatalogTool,
    ToolCatalogCredentials,
    ToolCatalogEntry,
    ToolInstall,
    ToolSecretRequirement,
)
from vidbyte.lib.enums.tool_catalogs import (
    ToolCatalogName,
    ToolInstallKind,
    ToolSecretLocation,
)
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.providers.tool_catalogs.base import (
    IndexedToolCatalogProvider,
    items,
    mapping,
    text,
    tool_text,
)

_STREAMABLE_HTTP = "streamable-http"
_NODE = "node"
_PYTHON = "python"


class ToolSdkCatalog(IndexedToolCatalogProvider):
    """ToolSDK's registry of MCP packages and remotes."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.TOOLSDK
    index_url: ClassVar[str] = TOOLSDK_INDEX_URL

    def __init__(self, *, credentials: ToolCatalogCredentials | None = None, transport: HttpTransport | None = None) -> None:
        # Adds a map from package name to its package-file path, filled while the index is parsed.
        # @intent package-paths-come-from-the-index
        # describe() reads only package files the index points to, never a path built from a package name.
        super().__init__(credentials=credentials, transport=transport)
        self._paths: dict[str, str] = {}

    def parse_index(self, body: str) -> Iterable[ToolCatalogEntry]:
        """Parse the package index into entries whose tools come from the index's tool map."""
        paths: dict[str, str] = {}
        entries: list[ToolCatalogEntry] = []
        for package_name, raw in mapping(self.load_json(body)).items():
            item = mapping(raw)
            name = text(package_name)
            if not name:
                continue
            tools = tuple(
                CatalogTool(name=text(mapping(tool).get("name")) or text(key), description=tool_text(mapping(tool).get("description")))
                for key, tool in mapping(item.get("tools")).items()
                if text(mapping(tool).get("name")) or text(key)
            )
            entries.append(ToolCatalogEntry(catalog=self.name, entry_id=name, name=name, description=text(item.get("category")), tools=tools, verified=item.get("validated") is True))
            if text(item.get("path")):
                paths[name] = text(item.get("path"))
        self._paths = paths
        return entries

    async def describe(self, entry: ToolCatalogEntry) -> ToolCatalogEntry:
        """Read the package file and return the entry with its description and installs."""
        await self.entries()
        path = self._paths.get(entry.entry_id)
        if not path:
            return entry
        package = mapping(await self.get_json(f"{TOOLSDK_PACKAGE_BASE_URL}{path}"))
        secrets = tuple(_env_requirement(text(name), mapping(spec)) for name, spec in mapping(package.get("env")).items() if text(name))
        installs = [install for install in (_remote_install(remote, secrets) for remote in items(package.get("remotes"))) if install is not None]
        package_install = _package_install(text(package.get("packageName")) or entry.entry_id, text(package.get("runtime")), secrets)
        if package_install is not None:
            installs.append(package_install)
        return ToolCatalogEntry(
            catalog=entry.catalog,
            entry_id=entry.entry_id,
            name=text(package.get("name")) or entry.name,
            description=text(package.get("description")) or entry.description,
            installs=tuple(installs),
            tools=entry.tools,
            verified=entry.verified,
            repository_url=text(package.get("url")) or None,
        )


def _remote_install(raw: object, secrets: tuple[ToolSecretRequirement, ...]) -> ToolInstall | None:
    # A remote is attachable only when it needs no environment values, since the file never says which header carries them.
    # @intent no-guessed-secret-headers
    # Guessing which header carries an env value could send a secret to the wrong place, so such remotes are skipped.
    remote = mapping(raw)
    url = text(remote.get("url"))
    if text(remote.get("type")) != _STREAMABLE_HTTP or not url or any(secret.required for secret in secrets):
        return None
    return ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url=url)


def _package_install(package_name: str, runtime: str, secrets: tuple[ToolSecretRequirement, ...]) -> ToolInstall | None:
    # Builds an unpinned npx or uvx command; the missing version is recorded, not hidden.
    if runtime == _NODE:
        return ToolInstall(kind=ToolInstallKind.PACKAGE, command=("npx", "-y", package_name), secrets=secrets, pinned=False)
    if runtime == _PYTHON:
        return ToolInstall(kind=ToolInstallKind.PACKAGE, command=("uvx", package_name), secrets=secrets, pinned=False)
    return None


def _env_requirement(name: str, spec: Mapping[str, object]) -> ToolSecretRequirement:
    # Declares one environment variable the package reads.
    return ToolSecretRequirement(name=name, location=ToolSecretLocation.ENV, target=name, required=spec.get("required") is True, description=text(spec.get("description")))


__all__ = ["ToolSdkCatalog"]

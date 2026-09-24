"""FILE: vidbyte/providers/tool_catalogs/mcp_registry.py

PURPOSE: Adapts the official MCP Registry and GitHub's MCP Registry, which both publish the MCP `server.json` shape, into ToolCatalogEntry records.
ROLE IN CODEBASE: ToolCatalogs builds McpRegistryCatalog for ToolCatalogName.MCP_REGISTRY and GitHubMcpRegistryCatalog for ToolCatalogName.GITHUB_MCP_REGISTRY; JevAgentAlignment searches both through the ToolCatalogProvider contract.
ARCHITECTURE NOTE: parse_server_json is the single translation of `server.json` (remotes, packages, header templates, environment variables) into installs, so both registries normalize identically.
COMMON MODIFICATION PATTERNS: Support a new package registryType by adding one branch to _package_install; support a new remote transport only after vidbyte/tools/mcp has a matching transport.
KNOWN EDGE CASES: The official registry matches `search` against server names only, so a multi-word query is also searched word by word and re-ranked locally. GitHub's registry ignores `search`, so its ~300 servers are paged into a cached local index. Remotes whose URL still contains a `{variable}`, legacy SSE remotes, and packages that need an argument with no value are skipped because they cannot be connected as published.
RELATED DOCS: https://registry.modelcontextprotocol.io/docs, https://github.com/modelcontextprotocol/registry, and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable, Mapping
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import (
    GITHUB_MCP_REGISTRY_BASE_URL,
    MCP_REGISTRY_BASE_URL,
    MCP_REGISTRY_SERVERS_PATH,
    TOOL_CATALOG_INDEX_TTL_SECONDS,
)
from vidbyte.lib.dataclasses.tool_catalogs import (
    VALUE_PLACEHOLDER,
    ToolCatalogEntry,
    ToolInstall,
    ToolSecretRequirement,
)
from vidbyte.lib.enums.tool_catalogs import (
    ToolCatalogName,
    ToolInstallKind,
    ToolSecretLocation,
)
from vidbyte.providers.tool_catalogs.base import (
    IndexedToolCatalogProvider,
    ToolCatalogProvider,
    items,
    mapping,
    query_terms,
    rank_entries,
    text,
)

REGISTRY_PAGE_LIMIT = 100
REGISTRY_MAX_PAGES = 5
REGISTRY_MAX_TERM_SEARCHES = 3
_TEMPLATE_VARIABLE = re.compile(r"\{([A-Za-z0-9_.\-]+)\}")
_STREAMABLE_HTTP = "streamable-http"
_STDIO = "stdio"


class McpRegistryCatalog(ToolCatalogProvider):
    """The official MCP Registry at registry.modelcontextprotocol.io."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.MCP_REGISTRY
    base_url: ClassVar[str] = MCP_REGISTRY_BASE_URL

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Search by the whole query, then word by word when that is not enough, and rank the union locally."""
        found: dict[str, ToolCatalogEntry] = {entry.entry_id: entry for entry in await self._search_once(query, limit)}
        if len(found) < limit:
            for term in sorted(query_terms(query), key=len, reverse=True)[:REGISTRY_MAX_TERM_SEARCHES]:
                for entry in await self._search_once(term, limit):
                    found.setdefault(entry.entry_id, entry)
        return rank_entries(found.values(), query, limit=limit)

    async def _search_once(self, query: str, limit: int) -> tuple[ToolCatalogEntry, ...]:
        # Asks the registry for the latest version of each server whose name contains the query.
        payload = await self.get_json(f"{self.base_url}{MCP_REGISTRY_SERVERS_PATH}", params={"search": query, "limit": limit, "version": "latest"})
        return tuple(parse_server_list(self.name, payload))


class GitHubMcpRegistryCatalog(IndexedToolCatalogProvider):
    """GitHub's curated MCP Registry at api.mcp.github.com, cached as a local index because it ignores `search`."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.GITHUB_MCP_REGISTRY
    index_url: ClassVar[str] = f"{GITHUB_MCP_REGISTRY_BASE_URL}{MCP_REGISTRY_SERVERS_PATH}"

    async def entries(self) -> tuple[ToolCatalogEntry, ...]:
        """Return the cached index, paging through the whole registry when the cache is empty or older than the TTL."""
        now = time.monotonic()
        if self._loaded_at is not None and now - self._loaded_at <= TOOL_CATALOG_INDEX_TTL_SECONDS:
            return self._entries
        collected: list[ToolCatalogEntry] = []
        cursor: str | None = None
        for _ in range(REGISTRY_MAX_PAGES):
            payload = await self.get_json(self.index_url, params={"limit": REGISTRY_PAGE_LIMIT, "cursor": cursor}, index=True)
            collected.extend(parse_server_list(self.name, payload))
            cursor = text(mapping(mapping(payload).get("metadata")).get("nextCursor")) or None
            if cursor is None:
                break
        self._entries = tuple(collected)
        self._loaded_at = now
        return self._entries

    def parse_index(self, body: str) -> Iterable[ToolCatalogEntry]:
        """Parse one registry page body; entries() pages with get_json instead, so this serves single-page callers."""
        return parse_server_list(self.name, self.load_json(body))


def parse_server_list(catalog: ToolCatalogName, payload: object) -> list[ToolCatalogEntry]:
    """Parse a `GET /v0.1/servers` page into entries, skipping servers that are not active."""
    entries: list[ToolCatalogEntry] = []
    for raw in items(mapping(payload).get("servers")):
        wrapper = mapping(raw)
        official = mapping(mapping(wrapper.get("_meta")).get("io.modelcontextprotocol.registry/official"))
        if official and text(official.get("status")) not in ("", "active"):
            continue
        entry = parse_server_json(catalog, mapping(wrapper.get("server")) or wrapper)
        if entry is not None:
            entries.append(entry)
    return entries


def parse_server_json(catalog: ToolCatalogName, server: Mapping[str, object]) -> ToolCatalogEntry | None:
    """Translate one `server.json` object into an entry, or None when it has no name."""
    name = text(server.get("name"))
    if not name:
        return None
    installs = [install for install in (_remote_install(remote) for remote in items(server.get("remotes"))) if install is not None]
    installs.extend(install for install in (_package_install(package) for package in items(server.get("packages"))) if install is not None)
    return ToolCatalogEntry(
        catalog=catalog,
        entry_id=name,
        name=text(server.get("title")) or name,
        description=text(server.get("description")),
        installs=tuple(installs),
        version=text(server.get("version")) or None,
        publisher=name.split("/", 1)[0],
        # Both registries only list names whose publisher proved the namespace (GitHub login or DNS).
        verified=True,
        repository_url=text(mapping(server.get("repository")).get("url")) or None,
    )


def _remote_install(raw: object) -> ToolInstall | None:
    # Converts one streamable-http remote into a REMOTE_HTTP install; other transports cannot be connected.
    remote = mapping(raw)
    url = text(remote.get("url"))
    if text(remote.get("type")) != _STREAMABLE_HTTP or not url or _TEMPLATE_VARIABLE.search(url):
        return None
    static_headers: dict[str, str] = {}
    secrets: list[ToolSecretRequirement] = []
    for header in (mapping(item) for item in items(remote.get("headers"))):
        header_name = text(header.get("name"))
        if not header_name:
            continue
        requirement = _header_requirement(header_name, header)
        if requirement is None:
            static_headers[header_name] = text(header.get("value"))
        else:
            secrets.append(requirement)
    return ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url=url, static_headers=static_headers, secrets=tuple(secrets))


def _header_requirement(header_name: str, header: Mapping[str, object]) -> ToolSecretRequirement | None:
    # Returns the requirement a header needs, or None for a fixed header value that needs nothing from the owner.
    value = text(header.get("value"))
    variables = _TEMPLATE_VARIABLE.findall(value)
    secret = header.get("isSecret") is True
    if value and not variables and not secret:
        return None
    single = len(variables) == 1
    return ToolSecretRequirement(
        # A single-variable template ("Bearer {TOKEN}") is supplied as TOKEN; anything else as the whole header value.
        name=variables[0] if single else header_name,
        location=ToolSecretLocation.HEADER,
        target=header_name,
        template=value.replace(f"{{{variables[0]}}}", VALUE_PLACEHOLDER) if single else VALUE_PLACEHOLDER,
        required=header.get("isRequired") is True,
        description=text(header.get("description")),
    )


def _package_install(raw: object) -> ToolInstall | None:
    # Converts one stdio package into a PACKAGE (npm, PyPI) or CONTAINER (OCI) install with its environment secrets.
    package = mapping(raw)
    identifier = text(package.get("identifier"))
    registry_type = text(package.get("registryType"))
    version = text(package.get("version"))
    transport = text(mapping(package.get("transport")).get("type")) or _STDIO
    if not identifier or transport != _STDIO or _needs_missing_argument(package):
        return None
    secrets = tuple(_env_requirement(mapping(variable)) for variable in items(package.get("environmentVariables")) if text(mapping(variable).get("name")))
    pinned = bool(version) and version != "latest"
    if registry_type == "npm":
        command: tuple[str, ...] = ("npx", "-y", f"{identifier}@{version}" if pinned else identifier)
        return ToolInstall(kind=ToolInstallKind.PACKAGE, command=command, secrets=secrets, pinned=pinned)
    if registry_type == "pypi":
        command = ("uvx", f"{identifier}=={version}" if pinned else identifier)
        return ToolInstall(kind=ToolInstallKind.PACKAGE, command=command, secrets=secrets, pinned=pinned)
    if registry_type == "oci":
        # An identifier that already carries a tag or digest is used as published; otherwise the version becomes the tag.
        tagged = "@" in identifier or ":" in identifier.rsplit("/", 1)[-1]
        image = f"{identifier}:{version}" if pinned and not tagged else identifier
        pinned = pinned or (tagged and not image.endswith(":latest"))
        env_flags = tuple(flag for secret in secrets for flag in ("-e", secret.target))
        return ToolInstall(kind=ToolInstallKind.CONTAINER, command=("docker", "run", "-i", "--rm", *env_flags, image), secrets=secrets, pinned=pinned)
    return None


def _env_requirement(variable: Mapping[str, object]) -> ToolSecretRequirement:
    # Declares one environment variable the local process reads.
    name = text(variable.get("name"))
    return ToolSecretRequirement(
        name=name,
        location=ToolSecretLocation.ENV,
        target=name,
        required=variable.get("isRequired") is True and not text(variable.get("default")),
        description=text(variable.get("description")),
    )


def _needs_missing_argument(package: Mapping[str, object]) -> bool:
    # True when a package or runtime argument is required but has no value, so the published command cannot run.
    arguments = (*items(package.get("packageArguments")), *items(package.get("runtimeArguments")))
    return any(mapping(argument).get("isRequired") is True and not text(mapping(argument).get("value")) for argument in arguments)


__all__ = ["GitHubMcpRegistryCatalog", "McpRegistryCatalog", "parse_server_json", "parse_server_list"]

"""FILE: vidbyte/providers/tool_catalogs/docker.py

PURPOSE: Adapts Docker's MCP Catalog (catalog.yaml, the curated list behind Docker's MCP Toolkit) into ToolCatalogEntry records with container and remote installs.
ROLE IN CODEBASE: ToolCatalogs builds DockerMcpCatalog for ToolCatalogName.DOCKER_MCP_CATALOG; JevAgentAlignment searches the cached index and describes entries through it.
ARCHITECTURE NOTE: The catalog has no search API, so the YAML file is downloaded once per TTL, parsed with yaml.safe_load, and ranked locally. describe() fetches an entry's `toolsUrl` for tool descriptions, arguments, and annotations.
COMMON MODIFICATION PATTERNS: Support a new entry `type` in _entry; keep entries that need Docker MCP Toolkit templating (`config`, `volumes`, templated env) unattachable, because only the Toolkit can fill those templates.
KNOWN EDGE CASES: Images are pinned by digest in the catalog, so container installs are pinned. Remote entries using legacy SSE are skipped. OAuth-only entries without a secret fallback have no install. `toolsUrl` is published as http:// and is fetched over https://. The tools URLs are remembered while the index is parsed, so describe() never re-reads the YAML.
RELATED DOCS: https://docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/ and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import DOCKER_MCP_CATALOG_URL
from vidbyte.lib.dataclasses.tool_catalogs import (
    VALUE_PLACEHOLDER,
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
    optional_bool,
    schema_from_parameters,
    text,
    tool_text,
)

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
_TOOLKIT_TEMPLATE = "{{"
_SERVER = "server"
_REMOTE = "remote"
_STREAMABLE_HTTP = "streamable-http"


class DockerMcpCatalog(IndexedToolCatalogProvider):
    """Docker's curated MCP catalog of signed images and remote endpoints."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.DOCKER_MCP_CATALOG
    index_url: ClassVar[str] = DOCKER_MCP_CATALOG_URL

    def __init__(self, *, credentials: ToolCatalogCredentials | None = None, transport: HttpTransport | None = None) -> None:
        # Adds a map from entry id to its tools JSON URL, filled while the index is parsed.
        super().__init__(credentials=credentials, transport=transport)
        self._tools_urls: dict[str, str] = {}

    def parse_index(self, body: str) -> Iterable[ToolCatalogEntry]:
        """Parse catalog.yaml into entries, one per registry key, remembering each entry's tools JSON URL."""
        registry = mapping(mapping(self.load_yaml(body)).get("registry"))
        tools_urls: dict[str, str] = {}
        entries: list[ToolCatalogEntry] = []
        for key, raw in registry.items():
            item = mapping(raw)
            entry = _entry(self.name, str(key), item)
            if entry is None:
                continue
            entries.append(entry)
            if text(item.get("toolsUrl")):
                # The catalog publishes these URLs as http://; the same host serves them over https://.
                tools_urls[entry.entry_id] = text(item.get("toolsUrl")).replace("http://", "https://", 1)
        self._tools_urls = tools_urls
        return entries

    async def describe(self, entry: ToolCatalogEntry) -> ToolCatalogEntry:
        """Fetch the entry's tools JSON and return the entry with full tool descriptions, arguments, and annotations."""
        await self.entries()
        tools_url = self._tools_urls.get(entry.entry_id)
        if not tools_url:
            return entry
        payload = await self.get_json(tools_url)
        tools = tuple(tool for tool in (_catalog_tool(item) for item in items(payload)) if tool is not None)
        return ToolCatalogEntry(
            catalog=entry.catalog,
            entry_id=entry.entry_id,
            name=entry.name,
            description=entry.description,
            installs=entry.installs,
            tools=tools or entry.tools,
            version=entry.version,
            publisher=entry.publisher,
            verified=entry.verified,
            repository_url=entry.repository_url,
        )


def _entry(catalog: ToolCatalogName, key: str, raw: Mapping[str, object]) -> ToolCatalogEntry | None:
    # Builds one entry; entries whose type is neither a server image nor a remote are skipped.
    kind = text(raw.get("type"))
    if kind not in (_SERVER, _REMOTE):
        return None
    metadata = mapping(raw.get("metadata"))
    install = _server_install(raw) if kind == _SERVER else _remote_install(raw)
    return ToolCatalogEntry(
        catalog=catalog,
        entry_id=key,
        name=text(raw.get("title")) or key,
        description=text(raw.get("description")),
        installs=(install,) if install is not None else (),
        tools=tuple(CatalogTool(name=text(mapping(tool).get("name")), description="") for tool in items(raw.get("tools")) if text(mapping(tool).get("name"))),
        publisher=text(metadata.get("owner")) or None,
        # Docker reviews and signs every catalog entry.
        verified=True,
        repository_url=text(raw.get("upstream") or raw.get("source")) or None,
    )


def _server_install(raw: Mapping[str, object]) -> ToolInstall | None:
    # Converts a server image into `docker run -i --rm` with its fixed env values and secret env names.
    image = text(raw.get("image"))
    if not image or _needs_toolkit(raw):
        return None
    secrets = tuple(_env_secret(mapping(secret)) for secret in items(raw.get("secrets")) if text(mapping(secret).get("env")))
    fixed_env = tuple(flag for variable in items(raw.get("env")) for flag in ("-e", f"{text(mapping(variable).get('name'))}={text(mapping(variable).get('value'))}"))
    secret_env = tuple(flag for secret in secrets for flag in ("-e", secret.target))
    return ToolInstall(kind=ToolInstallKind.CONTAINER, command=("docker", "run", "-i", "--rm", *fixed_env, *secret_env, image), secrets=secrets, pinned="@sha256:" in image)


def _remote_install(raw: Mapping[str, object]) -> ToolInstall | None:
    # Converts a streamable-http remote into a REMOTE_HTTP install whose `${ENV}` headers become secrets.
    remote = mapping(raw.get("remote"))
    url = text(remote.get("url"))
    if text(remote.get("transport_type")) != _STREAMABLE_HTTP or not url:
        return None
    static_headers: dict[str, str] = {}
    secrets: list[ToolSecretRequirement] = []
    for header_name, value in mapping(remote.get("headers")).items():
        header_value = text(value)
        reference = _ENV_REFERENCE.search(header_value)
        if reference is None:
            static_headers[str(header_name)] = header_value
            continue
        secrets.append(
            ToolSecretRequirement(
                name=reference.group(1),
                location=ToolSecretLocation.HEADER,
                target=str(header_name),
                template=header_value.replace(reference.group(0), VALUE_PLACEHOLDER),
            )
        )
    return ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url=url, static_headers=static_headers, secrets=tuple(secrets))


def _needs_toolkit(raw: Mapping[str, object]) -> bool:
    # True when running the image needs Docker MCP Toolkit templating that plain `docker run` cannot fill.
    templated_env = any(_TOOLKIT_TEMPLATE in text(mapping(variable).get("value")) for variable in items(raw.get("env")))
    oauth_only = bool(raw.get("oauth")) and not items(raw.get("secrets"))
    return bool(raw.get("config")) or bool(raw.get("volumes")) or bool(raw.get("command")) or templated_env or oauth_only


def _env_secret(secret: Mapping[str, object]) -> ToolSecretRequirement:
    # Declares one secret the container reads from its environment.
    env = text(secret.get("env"))
    return ToolSecretRequirement(name=env, location=ToolSecretLocation.ENV, target=env, description=text(secret.get("description")))


def _catalog_tool(raw: object) -> CatalogTool | None:
    # Converts one tools-JSON item (name, description, arguments, annotations).
    tool = mapping(raw)
    name = text(tool.get("name"))
    if not name:
        return None
    annotations = mapping(tool.get("annotations"))
    return CatalogTool(
        name=name,
        description=tool_text(tool.get("description")),
        input_schema=schema_from_parameters(items(tool.get("arguments"))),
        read_only=optional_bool(annotations.get("readOnlyHint")),
        destructive=optional_bool(annotations.get("destructiveHint")),
    )


__all__ = ["DockerMcpCatalog"]

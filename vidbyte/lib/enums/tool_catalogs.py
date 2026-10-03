"""FILE: vidbyte/lib/enums/tool_catalogs.py

PURPOSE: Declares the closed vocabularies for public tool catalogs: which catalog an entry came from, how its tools can be installed, and where a required secret is sent.
ROLE IN CODEBASE: vidbyte/lib/dataclasses/tool_catalogs.py records use these values, vidbyte/providers/tool_catalogs/ adapters produce them, and JevAgentAlignment's tool alignment filters on them.
ARCHITECTURE NOTE: The values live in vidbyte.lib so the provider layer (below agents) and the agents layer share one vocabulary without an upward import.
COMMON MODIFICATION PATTERNS: Adding a catalog means one ToolCatalogName member plus one adapter registered in vidbyte/providers/tool_catalogs/__init__.py; adding an install kind also needs attach support in JevAgentAlignment.
KNOWN EDGE CASES: OPENAPI entries are discoverable but never attachable until an OpenAPI tool bridge exists; MANAGED installs need a platform credential and an end-user id.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py and tests/test_jev_tool_alignment.py.
"""

from __future__ import annotations

from enum import StrEnum


class ToolCatalogName(StrEnum):
    """Public catalogs the SDK can search for existing tools."""

    MCP_REGISTRY = "mcp_registry"  # registry.modelcontextprotocol.io, the upstream MCP registry
    GITHUB_MCP_REGISTRY = "github_mcp_registry"  # api.mcp.github.com, GitHub's curated registry
    SMITHERY = "smithery"  # registry.smithery.ai, mostly Smithery-hosted remote servers
    GLAMA = "glama"  # glama.ai connectors, needs an API key
    DOCKER_MCP_CATALOG = "docker_mcp_catalog"  # Docker's curated catalog of images and remotes
    TOOLSDK = "toolsdk"  # ToolSDK's JSON registry published from GitHub
    COMPOSIO = "composio"  # managed platform, needs an API key and an end-user id
    PIPEDREAM = "pipedream"  # managed platform, needs an OAuth client and an end-user id
    ARCADE = "arcade"  # managed platform, needs an API key and an end-user id
    APIS_GURU = "apis_guru"  # OpenAPI directory; discovery only

    @property
    def needs_credentials(self) -> bool:
        """Return True when the catalog cannot be searched without an owner credential."""
        return self in _KEYED_CATALOGS


_KEYED_CATALOGS = frozenset({ToolCatalogName.GLAMA, ToolCatalogName.COMPOSIO, ToolCatalogName.PIPEDREAM, ToolCatalogName.ARCADE})


class ToolInstallKind(StrEnum):
    """How the tools of one catalog entry reach an agent."""

    REMOTE_HTTP = "remote_http"  # a Streamable HTTP MCP endpoint; no local code runs
    MANAGED = "managed"  # a platform (Composio, Pipedream, Arcade) hosts and runs the tools for an end user
    CONTAINER = "container"  # a Docker image run locally over stdio
    PACKAGE = "package"  # an npm or PyPI package run locally over stdio
    OPENAPI = "openapi"  # an OpenAPI description; not attachable yet


class ToolSecretLocation(StrEnum):
    """Where a required secret or config value is sent when connecting."""

    HEADER = "header"  # an HTTP header on every MCP request
    QUERY = "query"  # a query parameter on the MCP endpoint URL
    ENV = "env"  # an environment variable of a local process


__all__ = ["ToolCatalogName", "ToolInstallKind", "ToolSecretLocation"]

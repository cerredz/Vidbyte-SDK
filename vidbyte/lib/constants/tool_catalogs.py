"""FILE: vidbyte/lib/constants/tool_catalogs.py

PURPOSE: Declares the endpoints, size ceilings, timeouts, and search limits shared by the public tool-catalog adapters.
ROLE IN CODEBASE: vidbyte/providers/tool_catalogs/ adapters read the endpoints and ceilings; JevAgentAlignment reads the search limits when it fans out a scout query.
ARCHITECTURE NOTE: Every value is declared once here so the adapters, their tests, and the README External Contract cannot drift apart.
COMMON MODIFICATION PATTERNS: Change an endpoint only after the catalog documents the move; raise a byte ceiling only when a catalog's published index grows past it.
KNOWN EDGE CASES: The Docker, ToolSDK, and APIs.guru catalogs are whole-file indexes (0.6 MB, 2.7 MB, and 8.9 MB when retrieved), so they use the larger index ceiling and are cached per adapter instance.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

# Endpoints, retrieved 2026-09-23. Each one is documented in vidbyte/providers/tool_catalogs/README.md.
MCP_REGISTRY_BASE_URL: str = "https://registry.modelcontextprotocol.io"
GITHUB_MCP_REGISTRY_BASE_URL: str = "https://api.mcp.github.com"
MCP_REGISTRY_SERVERS_PATH: str = "/v0.1/servers"
SMITHERY_REGISTRY_BASE_URL: str = "https://registry.smithery.ai"
GLAMA_API_BASE_URL: str = "https://glama.ai/api/mcp"
DOCKER_MCP_CATALOG_URL: str = "https://desktop.docker.com/mcp/catalog/v3/catalog.yaml"
TOOLSDK_INDEX_URL: str = "https://toolsdk-ai.github.io/toolsdk-mcp-registry/indexes/packages-list.json"
TOOLSDK_PACKAGE_BASE_URL: str = "https://raw.githubusercontent.com/toolsdk-ai/toolsdk-mcp-registry/main/packages/"
COMPOSIO_API_BASE_URL: str = "https://backend.composio.dev"
PIPEDREAM_API_BASE_URL: str = "https://api.pipedream.com"
PIPEDREAM_MCP_URL: str = "https://remote.mcp.pipedream.net/v3"
ARCADE_API_BASE_URL: str = "https://api.arcade.dev"
APIS_GURU_LIST_URL: str = "https://api.apis.guru/v2/list.json"

# Transport policy for catalog calls. Searches are small JSON pages; indexes are whole catalog files.
TOOL_CATALOG_TIMEOUT_SECONDS: float = 10.0
TOOL_CATALOG_INDEX_TIMEOUT_SECONDS: float = 30.0
TOOL_CATALOG_RETRY_COUNT: int = 1
TOOL_CATALOG_MAX_RESPONSE_BYTES: int = 2_000_000
TOOL_CATALOG_INDEX_MAX_RESPONSE_BYTES: int = 16_000_000
TOOL_CATALOG_INDEX_TTL_SECONDS: float = 3_600.0
TOOL_CATALOG_HTTP_OK: int = 200
TOOL_CATALOG_HTTP_CREATED: int = 201
TOOL_CATALOG_HTTP_MULTIPLE_CHOICES: int = 300

# Search shaping: how many entries each catalog returns per query, and how many survive the merge.
TOOL_CATALOG_SEARCH_LIMIT: int = 8
TOOL_CATALOG_MERGED_LIMIT: int = 12
TOOL_CATALOG_DESCRIPTION_CHARS: int = 600
TOOL_CATALOG_TOOL_DESCRIPTION_CHARS: int = 1_200

__all__ = [
    "APIS_GURU_LIST_URL",
    "ARCADE_API_BASE_URL",
    "COMPOSIO_API_BASE_URL",
    "DOCKER_MCP_CATALOG_URL",
    "GITHUB_MCP_REGISTRY_BASE_URL",
    "GLAMA_API_BASE_URL",
    "MCP_REGISTRY_BASE_URL",
    "MCP_REGISTRY_SERVERS_PATH",
    "PIPEDREAM_API_BASE_URL",
    "PIPEDREAM_MCP_URL",
    "SMITHERY_REGISTRY_BASE_URL",
    "TOOLSDK_INDEX_URL",
    "TOOLSDK_PACKAGE_BASE_URL",
    "TOOL_CATALOG_DESCRIPTION_CHARS",
    "TOOL_CATALOG_HTTP_CREATED",
    "TOOL_CATALOG_HTTP_MULTIPLE_CHOICES",
    "TOOL_CATALOG_HTTP_OK",
    "TOOL_CATALOG_INDEX_MAX_RESPONSE_BYTES",
    "TOOL_CATALOG_INDEX_TIMEOUT_SECONDS",
    "TOOL_CATALOG_INDEX_TTL_SECONDS",
    "TOOL_CATALOG_MAX_RESPONSE_BYTES",
    "TOOL_CATALOG_MERGED_LIMIT",
    "TOOL_CATALOG_RETRY_COUNT",
    "TOOL_CATALOG_SEARCH_LIMIT",
    "TOOL_CATALOG_TIMEOUT_SECONDS",
    "TOOL_CATALOG_TOOL_DESCRIPTION_CHARS",
]

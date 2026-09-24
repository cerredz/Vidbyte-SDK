"""FILE: vidbyte/providers/tool_catalogs/composio.py

PURPOSE: Adapts Composio's tool catalog and tool-router sessions: search returns toolkits with their matching tools, and connect() opens a session whose MCP endpoint exposes exactly the chosen tools for one end user.
ROLE IN CODEBASE: ToolCatalogs builds ComposioCatalog for ToolCatalogName.COMPOSIO when the owner supplies an API key; JevAgentAlignment searches it and calls connect() for a MANAGED install before judging and bridging tools.
ARCHITECTURE NOTE: Search is `GET /api/v3.1/tools?query=` grouped by toolkit. connect() is `POST /api/v3.1/tool_router/session` with the toolkit and tool allowlists, preloaded tools, search off, and connection management off, so the session exposes only the chosen tools.
COMMON MODIFICATION PATTERNS: Keep the session allowlist in step with the tools JevAgentAlignment judged; never enable Composio's own search meta-tool, which would let the main model pull in unjudged tools.
KNOWN EDGE CASES: Composio runs tools with the end user's connected account, so `user_id` is required and a tool whose account is not connected fails at call time with Composio's own message. The session POST is never retried, because a retry could create a second session.
RELATED DOCS: https://docs.composio.dev/reference/api-reference/tools/getTools, https://docs.composio.dev/reference/api-reference/tool-router, and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import COMPOSIO_API_BASE_URL
from vidbyte.lib.dataclasses.tool_catalogs import (
    CatalogTool,
    ToolCatalogEntry,
    ToolConnection,
    ToolInstall,
)
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.providers.tool_catalogs.base import (
    ToolCatalogProvider,
    items,
    mapping,
    text,
    tool_text,
)

COMPOSIO_TOOLS_PER_TOOLKIT_FACTOR = 4
_READ_ONLY_TAG = "readOnlyHint"
_DESTRUCTIVE_TAG = "destructiveHint"


class ComposioCatalog(ToolCatalogProvider):
    """Composio's managed toolkits, run for one end user through a tool-router session."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.COMPOSIO
    base_url: ClassVar[str] = COMPOSIO_API_BASE_URL

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Search tools by text and group them into one entry per toolkit, in the order toolkits first appear."""
        payload = await self.get_json(f"{self.base_url}/api/v3.1/tools", params={"query": query, "limit": limit * COMPOSIO_TOOLS_PER_TOOLKIT_FACTOR}, headers=self._headers())
        grouped: dict[str, list[CatalogTool]] = {}
        toolkit_names: dict[str, str] = {}
        for raw in items(mapping(payload).get("items")):
            tool = mapping(raw)
            toolkit = mapping(tool.get("toolkit"))
            slug, tool_slug = text(toolkit.get("slug")), text(tool.get("slug"))
            if not slug or not tool_slug or tool.get("is_deprecated") is True:
                continue
            toolkit_names.setdefault(slug, text(toolkit.get("name")) or slug)
            grouped.setdefault(slug, []).append(_catalog_tool(tool_slug, tool))
        return tuple(
            ToolCatalogEntry(
                catalog=self.name,
                entry_id=slug,
                name=toolkit_names[slug],
                description=f"Composio {toolkit_names[slug]} toolkit, run with the end user's connected account.",
                installs=(ToolInstall(kind=ToolInstallKind.MANAGED, reference=slug),),
                tools=tuple(tools),
                publisher="composio",
                verified=True,
            )
            for slug, tools in list(grouped.items())[:limit]
        )

    async def connect(self, entry: ToolCatalogEntry, install: ToolInstall, *, tool_names: Sequence[str], user_id: str | None) -> ToolConnection:
        """Open a tool-router session that exposes only `tool_names` from this toolkit for `user_id`."""
        # @intent composio-session-exposes-only-judged-tools
        # The allowlist, preload list, and disabled search keep the session from offering any tool Jev did not judge.
        if not user_id:
            raise ProviderConfigurationError("Composio runs tools for an end user; set JevToolAlignmentSettings.user_id.", provider=self.name.value)
        toolkit = install.reference or entry.entry_id
        body: Mapping[str, object] = {
            "user_id": user_id,
            "toolkits": {"enable": [toolkit]},
            "tools": {toolkit: {"enable": list(tool_names)}},
            "preload": {"tools": list(tool_names)},
            "search": {"enable": False},
            "manage_connections": {"enable": False},
        }
        payload = mapping(await self.send_json("POST", f"{self.base_url}/api/v3.1/tool_router/session", body, headers=self._headers()))
        url = text(mapping(payload.get("mcp")).get("url"))
        if not url:
            raise ProviderResponseError("Composio created a session without an MCP URL.", provider=self.name.value)
        return ToolConnection(url=url, headers=self._headers())

    def _headers(self) -> Mapping[str, str]:
        # Composio authenticates every call, including the session's MCP endpoint, with the project API key.
        return {"x-api-key": self.require_credentials("api_key").api_key or ""}


def _catalog_tool(slug: str, tool: Mapping[str, object]) -> CatalogTool:
    # Converts one Composio tool; its tags carry the MCP-style read-only and destructive hints.
    tags = {text(tag) for tag in items(tool.get("tags"))}
    return CatalogTool(
        name=slug,
        description=tool_text(tool.get("description") or tool.get("human_description")),
        input_schema=mapping(tool.get("input_parameters")),
        read_only=True if _READ_ONLY_TAG in tags else None,
        destructive=True if _DESTRUCTIVE_TAG in tags else None,
    )


__all__ = ["ComposioCatalog"]

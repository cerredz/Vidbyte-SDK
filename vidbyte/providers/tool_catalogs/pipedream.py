"""FILE: vidbyte/providers/tool_catalogs/pipedream.py

PURPOSE: Adapts Pipedream Connect: search lists apps that have actions, and connect() resolves an app to Pipedream's remote MCP server with the headers that scope it to one project, environment, end user, and app.
ROLE IN CODEBASE: ToolCatalogs builds PipedreamCatalog for ToolCatalogName.PIPEDREAM when the owner supplies an OAuth client, project id, and environment; JevAgentAlignment connects to read an app's live tool list, then judges and bridges it.
ARCHITECTURE NOTE: Access tokens come from the OAuth client-credentials grant (`POST /v1/oauth/token`) and are cached until shortly before they expire. Apps come from `GET /v1/connect/apps?q=&has_actions=true`. The MCP endpoint is `https://remote.mcp.pipedream.net/v3` with `x-pd-*` headers.
COMMON MODIFICATION PATTERNS: Add an optional `x-pd-*` header in connect() only after Pipedream documents it; keep the token exchange the only POST this adapter sends.
KNOWN EDGE CASES: Search results carry no tool list; tools are read from the live MCP connection. An app whose end-user account is not connected returns Pipedream's own connect message when a tool runs. The token POST is not retried.
RELATED DOCS: https://pipedream.com/docs/connect/mcp/developers, https://pipedream.com/docs/connect/api-reference/list-apps, and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import (
    PIPEDREAM_API_BASE_URL,
    PIPEDREAM_MCP_URL,
)
from vidbyte.lib.dataclasses.tool_catalogs import (
    ToolCatalogCredentials,
    ToolCatalogEntry,
    ToolConnection,
    ToolInstall,
)
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.providers.tool_catalogs.base import (
    ToolCatalogProvider,
    items,
    mapping,
    text,
)

PIPEDREAM_TOKEN_REFRESH_MARGIN_SECONDS = 60.0
PIPEDREAM_DEFAULT_TOKEN_SECONDS = 3_600.0


class PipedreamCatalog(ToolCatalogProvider):
    """Pipedream Connect apps, run for one end user through Pipedream's remote MCP server."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.PIPEDREAM
    base_url: ClassVar[str] = PIPEDREAM_API_BASE_URL

    def __init__(self, *, credentials: ToolCatalogCredentials | None = None, transport: HttpTransport | None = None) -> None:
        # Starts with no cached access token.
        super().__init__(credentials=credentials, transport=transport)
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Search apps that have actions; each app becomes one MANAGED entry without a tool list."""
        payload = await self.get_json(f"{self.base_url}/v1/connect/apps", params={"q": query, "limit": limit, "has_actions": "true"}, headers=await self._auth_headers())
        entries: list[ToolCatalogEntry] = []
        for raw in items(mapping(payload).get("data")):
            app = mapping(raw)
            slug = text(app.get("name_slug"))
            if not slug:
                continue
            entries.append(
                ToolCatalogEntry(
                    catalog=self.name,
                    entry_id=slug,
                    name=text(app.get("name")) or slug,
                    description=text(app.get("description")),
                    installs=(ToolInstall(kind=ToolInstallKind.MANAGED, reference=slug),),
                    publisher="pipedream",
                    verified=True,
                )
            )
        return tuple(entries[:limit])

    async def connect(self, entry: ToolCatalogEntry, install: ToolInstall, *, tool_names: Sequence[str], user_id: str | None) -> ToolConnection:
        """Return the remote MCP endpoint scoped to this project, environment, end user, and app."""
        # @intent pipedream-scope-headers
        # Every header narrows what the endpoint can reach: one project, one environment, one end user, one app.
        del tool_names
        if not user_id:
            raise ProviderConfigurationError("Pipedream runs tools for an end user; set JevToolAlignmentSettings.user_id.", provider=self.name.value)
        credentials = self.require_credentials("project_id", "environment")
        headers = {
            **await self._auth_headers(),
            "x-pd-project-id": credentials.project_id or "",
            "x-pd-environment": credentials.environment or "",
            "x-pd-external-user-id": user_id,
            "x-pd-app-slug": install.reference or entry.entry_id,
        }
        return ToolConnection(url=PIPEDREAM_MCP_URL, headers=headers)

    async def _auth_headers(self) -> dict[str, str]:
        # Returns a bearer header, exchanging the OAuth client for a new token when the cached one is near expiry.
        # @intent pipedream-token-cache
        # One token serves every search and connection until it is about to expire, so a run makes one token request.
        if self._token is None or time.monotonic() >= self._token_expires_at:
            credentials = self.require_credentials("client_id", "client_secret")
            body = {"grant_type": "client_credentials", "client_id": credentials.client_id or "", "client_secret": credentials.client_secret or ""}
            payload = mapping(await self.send_json("POST", f"{self.base_url}/v1/oauth/token", body))
            token = text(payload.get("access_token"))
            if not token:
                raise ProviderResponseError("Pipedream returned no access token.", provider=self.name.value)
            expires_in = payload.get("expires_in")
            lifetime = float(expires_in) if isinstance(expires_in, (int, float)) else PIPEDREAM_DEFAULT_TOKEN_SECONDS
            self._token = token
            self._token_expires_at = time.monotonic() + max(0.0, lifetime - PIPEDREAM_TOKEN_REFRESH_MARGIN_SECONDS)
        return {"Authorization": f"Bearer {self._token}"}


__all__ = ["PipedreamCatalog"]

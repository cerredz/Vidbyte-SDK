"""FILE: vidbyte/agents/browser/tools.py

PURPOSE: Defines BrowserAgentTools, which gives every configured MCP server of a BrowserAgent a role name (browser-<role>-<n>) and, once the servers are live, returns the bridged tools of one role: action tools for the episode workers, search and fetch tools for the orchestrator.
ROLE IN CODEBASE: BrowserAgent (vidbyte/agents/browser/agent.py) queues each server under the name named_servers gives it, through the MCP mixin's own builders; BrowserAgentRuntime (runtime.py) calls tools() with the agent's live handles at the start of each run to split the catalog by role.
ARCHITECTURE NOTE: It builds no McpServerConfig and keeps no key: the mixin's with_preset_mcp_server and with_mcp_server build and queue the configs (AGENTS.md principle 5), and this class holds only the map from server name to role. A live handle is matched to its role by handle.name, which is the name the server was queued under. The class lives in the agent package rather than in vidbyte.tools.toolsets because its input, BrowserAgentSettings, sits in the agents layer (spec D-6).
FUNCTION INVENTORY: named_servers names every server in role order; tools returns the bridged tools of one role's live servers.
COMMON MODIFICATION PATTERNS: A fourth role adds a BrowserToolRole member, a settings field, and one entry in the role order below.
WHAT NOT TO DO IN THIS FILE: 1. Do not read os.environ or keep a server's env here. 2. Do not build or start a server; the mixin does both. 3. Do not match a handle to a role by its tool names; the server chooses those, so only the queued name is reliable.
KNOWN EDGE CASES: A handle whose name is not one of the role names (a server attached by other means) belongs to no role and its tools reach no agent through this class. Servers are numbered from one within each role, in the order the settings list them.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 8.1 D-6 and D-7, and 8.5); vidbyte/agents/mixins.py
TESTS: tests/features/browser_agent/test_browser_agent_episode.py and tests/features/browser_agent/test_browser_agent_observability.py
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.browser.settings import BrowserAgentSettings, BrowserServerSettings
from vidbyte.lib.constants.browser import (
    BROWSER_FIRST_INDEX,
    BROWSER_SERVER_NAME_TEMPLATE,
)
from vidbyte.lib.enums.browser import BrowserToolRole
from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp import McpServerHandle


class BrowserAgentTools:
    """Names each configured server by its role and returns the live tools of one role; it holds role names only, never a key."""

    def __init__(self, settings: BrowserAgentSettings) -> None:
        # Keep only which role each server name belongs to.
        self._roles = {name: role for name, role, _ in self.named_servers(settings)}

    @staticmethod
    def named_servers(settings: BrowserAgentSettings) -> tuple[tuple[str, BrowserToolRole, BrowserServerSettings], ...]:
        """Return (name, role, server) for every configured server, action servers first, each named browser-<role>-<n>."""
        roles = ((BrowserToolRole.ACTION, settings.action_servers), (BrowserToolRole.SEARCH, settings.search_servers), (BrowserToolRole.FETCH, settings.fetch_servers))
        return tuple((BROWSER_SERVER_NAME_TEMPLATE.format(role=role.value, index=index), role, server) for role, servers in roles for index, server in enumerate(servers, start=BROWSER_FIRST_INDEX))

    def tools(self, servers: Sequence[McpServerHandle], role: BrowserToolRole) -> tuple[BaseTool, ...]:
        """Return the bridged tools of the live servers that belong to `role`, in server order."""
        # @intent catalogs-split-by-server-role
        # Each agent's catalog comes from the servers of its own roles:
        # workers act through the action servers, and the orchestrator
        # reads through search and fetch, so no action tool reaches it.
        return tuple(tool for handle in servers if self._roles.get(handle.name) is role for tool in handle.bridged_tools)


__all__ = ["BrowserAgentTools"]

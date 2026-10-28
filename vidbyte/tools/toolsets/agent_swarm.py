"""FILE: vidbyte/tools/toolsets/agent_swarm.py

PURPOSE: Defines AgentSwarmTools, the catalog of the five file and shell tools every agent of an AgentSwarm holds over the one shared workplace folder (bash, grep, read_lines, write_text, and patch_file), and the builder of the web-search tool a developer selects for every agent.
ROLE IN CODEBASE: Built by AgentSwarmRuntime (vidbyte/agents/agent_swarm/runtime.py) for every member agent of a run, which also calls search_tool_for once per run when AgentSwarmSettings.web_search is set; exported by vidbyte/tools/toolsets/__init__.py. Composes vidbyte/tools/builtins/bash.py, vidbyte/tools/builtins/code_search/grep.py, vidbyte/tools/filesystem/read_lines.py, vidbyte/tools/filesystem/write_text.py, vidbyte/tools/builtins/editing/patch.py, and the priced search tools and provider clients of vidbyte/tools/builtins/operations/.
ARCHITECTURE NOTE: A Tools subclass that holds only the five tools. The run-bound message and compact tools live in vidbyte/agents/agent_swarm/ because they need the running swarm, and this layer may not import vidbyte.agents; the swarm runtime appends them, and the selected search tool after them. read_lines and write_text share one configuration that allows writing, so both see the same root folder. search_tool_for reads a table of (provider, tool class, client class), the CodingAgentTools.authenticate_tools pattern, and builds the tool around a client that holds the key.
FUNCTION INVENTORY: AgentSwarmTools.__init__ is the narrated main function; get_tools returns bash, grep, read_lines, write_text, and patch_file in that order; search_tool_for returns the selected provider's search tool with the key inside its client.
COMMON MODIFICATION PATTERNS: A tool every swarm agent should hold is added to get_tools and to the package README together. A new web-search provider adds one AgentSwarmWebSearch member and one row to _SEARCH_PROVIDERS, and needs a client module.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents; the message and compact tools stay in the agent package. 2. Do not keep a key on the catalog or read one from the environment; a key lives only in its provider client. 3. Do not root two tools at different folders; every agent shares the one workplace.
KNOWN EDGE CASES: The file tools refuse a path outside the root, but bash is not confined and runs with the inherited environment. Two agents writing one file at the same time is not guarded; the last write wins. A key the provider rejects is found only at the first search, which returns an error result.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 8.1 D-18, 8.5 and 9.2); vidbyte/agents/agent_swarm/README.md; vidbyte/tools/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py, tests/features/agent_swarm/test_agent_swarm_settings.py and tests/features/agent_swarm/test_agent_swarm_workplace.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.enums.agent_swarm import AgentSwarmWebSearch
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.builtins.editing.patch import PatchTool
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.builtins.operations.clients import (
    BraveClient,
    BrowserbaseClient,
    ExaClient,
    ParallelClient,
    TavilyClient,
    WebOperationClient,
)
from vidbyte.tools.builtins.operations.search import (
    BraveSearchTool,
    BrowserbaseSearchTool,
    ExaSearchTool,
    ParallelSearchTool,
    TavilySearchTool,
)
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem.read_lines import ReadLinesTool
from vidbyte.tools.filesystem.write_text import WriteTextTool

# Each selectable web-search provider's tool class and the client class
# that holds its key.
_SEARCH_PROVIDERS: dict[AgentSwarmWebSearch, tuple[type[PricedOperationTool], Callable[[str], WebOperationClient]]] = {
    AgentSwarmWebSearch.BRAVE: (BraveSearchTool, BraveClient),
    AgentSwarmWebSearch.BROWSERBASE: (BrowserbaseSearchTool, BrowserbaseClient),
    AgentSwarmWebSearch.EXA: (ExaSearchTool, ExaClient),
    AgentSwarmWebSearch.PARALLEL: (ParallelSearchTool, ParallelClient),
    AgentSwarmWebSearch.TAVILY: (TavilySearchTool, TavilyClient),
}


class AgentSwarmTools(Tools):
    """Catalog of bash, grep, read_lines, write_text, and patch_file over one shared workplace folder."""

    def __init__(self, root: Path) -> None:
        # Give every agent the same five tools over the shared folder:
        # the shell first, then search, read, write, and patch.
        super().__init__(self.get_tools(root))

    @staticmethod
    def get_tools(root: Path) -> tuple[BaseTool, ...]:
        """Return bash, grep, read_lines, write_text, and patch_file over root."""
        # Reading and writing share one configuration that allows
        # writing, so both resolve paths against the same folder and
        # refuse any path outside it.
        file_config = FileSystemToolConfig(root=root, allow_write=True)
        return (BashTool(root), GrepTool(root), ReadLinesTool(file_config), WriteTextTool(file_config), PatchTool(root))

    @staticmethod
    def search_tool_for(web_search: AgentSwarmWebSearch, api_key: str) -> BaseTool:
        """Return a new web-search tool of the selected provider, with the key inside its client."""
        # @intent the-selected-provider-picks-one-search-tool
        # Only the provider the developer selected picks the tool, never
        # an environment variable, and the key lives only inside that
        # provider's client. AgentSwarmSettings has already made sure
        # the provider is one of these and the key is non-blank text.
        tool_class, client_class = _SEARCH_PROVIDERS[web_search]
        return tool_class(client=client_class(api_key))


__all__ = ["AgentSwarmTools"]

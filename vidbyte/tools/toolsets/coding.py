"""FILE: vidbyte/tools/toolsets/coding.py

PURPOSE: Defines CodingAgentTools, the catalog of the seven tools a CodingAgent starts with over one root folder (bash, read_lines, write_text, replace_text, glob, grep, and one web-fetch tool), and the private _FetchedPagesView that lets the model read the pages a keyed fetch tool returned.
ROLE IN CODEBASE: Built by vidbyte/agents/coding.py (CodingAgent) from a validated CodingAgentSettings (vidbyte/lib/dataclasses/coding.py); exported by vidbyte/tools/toolsets/__init__.py and the root vidbyte package. Composes vidbyte/tools/builtins/bash.py, the filesystem and code-search tools, and the priced fetch tools in vidbyte/tools/builtins/operations/fetch.py with their provider clients.
ARCHITECTURE NOTE: CodingAgentTools is a Tools subclass that holds only the seven tools. The agent appends the caller's own tools when it hands everything to BaseAgent, because BaseAgent skips caller items that are not tools while a Tools catalog would reject them. The settings record has already checked the root and the keys, so this module only builds. _FetchedPagesView is a _ToolWrapper around a keyed fetch tool that appends each fetched page's text to a successful result's output; spec, validation, permission, metadata, and pricing stay the wrapped tool's, and the runtime unwraps it before pricing.
FUNCTION INVENTORY: CodingAgentTools.__init__ is the narrated main function; authenticate_tools gives the one supplied key to its provider client and fetch tool, or returns DirectHttpFetchTool; get_tools returns the seven tools in order over a root folder, with the given fetch tool last. _FetchedPagesView delegates spec, validate_call, and execute, and adds page text to a successful execute result.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one row to the table in authenticate_tools and one key field on CodingAgentSettings; a tool swap changes get_tools and the agents README together.
WHAT NOT TO DO IN THIS FILE: 1. Do not read fetch keys from environment variables. 2. Do not keep the settings record or a key on the catalog; a key lives only inside its provider client. 3. Do not edit the wrapped fetch tools to change their output; the view is the only place page text is added.
KNOWN EDGE CASES: fork() keeps the same _FetchedPagesView object, and _rewrap puts a new view around a fork clone of the fetch tool. Bash is not confined to the root folder.
RELATED DOCS: docs/spec/coding-agent/spec.md; vidbyte/agents/README.md (Coding Agent); vidbyte/tools/README.md
TESTS: tests/features/coding_agent/test_coding_agent_web_fetch.py, tests/features/coding_agent/test_coding_agent_contract.py, and tests/features/coding_agent/test_coding_agent_acceptance.py
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from vidbyte.lib.dataclasses.coding import CodingAgentSettings
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.operations import FetchPayload
from vidbyte.tools.base import BaseTool, _ToolWrapper
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.builtins.code_search.glob import GlobTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.builtins.operations.clients import WebOperationClient
from vidbyte.tools.builtins.operations.clients.browserbase import BrowserbaseClient
from vidbyte.tools.builtins.operations.clients.firecrawl import FirecrawlClient
from vidbyte.tools.builtins.operations.clients.parallel import ParallelClient
from vidbyte.tools.builtins.operations.clients.tavily import TavilyClient
from vidbyte.tools.builtins.operations.fetch import (
    BrowserbaseFetchTool,
    DirectHttpFetchTool,
    FirecrawlFetchTool,
    ParallelExtractTool,
    TavilyExtractTool,
)
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem.read_lines import ReadLinesTool
from vidbyte.tools.filesystem.replace_text import ReplaceTextTool
from vidbyte.tools.filesystem.write_text import WriteTextTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec, ToolStatus


class CodingAgentTools(Tools):
    """Catalog of the seven tools a CodingAgent starts with, all over one root folder."""

    def __init__(self, settings: CodingAgentSettings) -> None:
        # Give the one supplied key to its fetch provider, or use the
        # keyless direct HTTP fetch when the caller supplied no key.
        fetch_tool = self.authenticate_tools(settings)

        # Put bash and the five file and search tools over the root
        # folder first, and the fetch tool last.
        super().__init__(self.get_tools(Path(settings.root_dir), fetch_tool))

    @staticmethod
    def authenticate_tools(settings: CodingAgentSettings) -> BaseTool:
        """Return the fetch tool holding the one supplied key, or DirectHttpFetchTool when no key was supplied."""
        # @intent the-supplied-key-picks-one-fetch-provider
        # Only the key parameter the caller set picks the provider,
        # never an environment variable, and the key lives only inside
        # its provider client. CodingAgentSettings has already made sure
        # at most one key is set and that it is non-blank text. A keyed
        # tool is wrapped so the model can read fetched pages.
        providers: tuple[tuple[str | None, type[PricedOperationTool], Callable[[str], WebOperationClient]], ...] = (
            (settings.firecrawl_api_key, FirecrawlFetchTool, FirecrawlClient),
            (settings.browserbase_api_key, BrowserbaseFetchTool, BrowserbaseClient),
            (settings.parallel_api_key, ParallelExtractTool, ParallelClient),
            (settings.tavily_api_key, TavilyExtractTool, TavilyClient),
        )
        for key, tool_class, client_class in providers:
            if key is not None:
                return _FetchedPagesView(tool_class(client=client_class(key)))
        return DirectHttpFetchTool()

    @staticmethod
    def get_tools(root_dir: Path, fetch_tool: BaseTool) -> tuple[BaseTool, ...]:
        """Return the seven coding tools over root_dir in order, with fetch_tool last."""
        # Read, write, and edit share one configuration that allows
        # writing, so all three see the same root folder.
        file_config = FileSystemToolConfig(root=root_dir, allow_write=True)
        return (BashTool(root_dir), ReadLinesTool(file_config), WriteTextTool(file_config), ReplaceTextTool(file_config), GlobTool(root_dir), GrepTool(root_dir), fetch_tool)


class _FetchedPagesView(_ToolWrapper):
    """Private view over a keyed fetch tool that also shows the model the text of every page it fetched."""

    def __init__(self, tool: BaseTool) -> None:
        # Keeps the priced fetch tool whose spec, validation,
        # permission, metadata, and billing this view preserves.
        self._tool = tool

    @property
    def wrapped_tool(self) -> BaseTool:
        """Return the priced fetch tool behind this view."""
        return self._tool

    def _rewrap(self, tool: BaseTool) -> BaseTool:
        # Puts the same view around another copy of the fetch tool, such
        # as a fork clone.
        return _FetchedPagesView(tool)

    def spec(self) -> ToolSpec:
        """Return the wrapped tool's spec unchanged."""
        return self._tool.spec()

    def validate_call(self, call: ToolCall) -> str | None:
        """Delegate call validation without changing arguments or errors."""
        return self._tool.validate_call(call)

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the fetch, then follow a successful result's summary with each page's final URL and full text."""
        # @intent keyed-fetch-pages-reach-the-model
        # The keyed fetch tools show the model only a one-line summary
        # per page and keep the text in metadata, so without this view
        # the model could fetch a page but never read it. Run the priced
        # fetch exactly as the bare tool would.
        result = await self._tool.execute(call)

        # A failure, or a result without fetched pages, reaches the
        # model exactly as the wrapped tool built it.
        payload = result.metadata.get(PricedOperationTool._PAYLOAD_KEY)
        if result.status is not ToolStatus.SUCCESS or not isinstance(payload, FetchPayload):
            return result

        # Keep the provider's summary first, then add each page's final
        # URL and full text in fetch order. Only output changes:
        # metadata, including the operation-usage annotation the runtime
        # prices from, passes through untouched.
        pages ="\n\n".join(f"{index}. {page.final_url}\n{page.content}" for index, page in enumerate(payload.pages, start=1))
        return dataclasses.replace(result, output=f"{result.output}\n\n{pages}")


__all__ = ["CodingAgentTools"]

"""FILE: vidbyte/agents/coding.py

PURPOSE: Defines CodingAgent, a BaseAgent that takes every BaseAgent keyword unchanged plus a required root_dir and four optional fetch keys, and preloads seven tools over one root folder: bash, read_lines, write_text, replace_text, glob, grep, and one web-fetch tool picked by the key passed.
ROLE IN CODEBASE: Exported by vidbyte/agents/__init__.py and the root vidbyte package; builds on vidbyte/agents/base.py (BaseAgent), vidbyte/tools/builtins/bash.py (BashTool), the filesystem and code-search tools, and the priced fetch tools in vidbyte/tools/builtins/operations/fetch.py with their provider clients.
ARCHITECTURE NOTE: CodingAgent only assembles constructor arguments and then hands everything to BaseAgent.__init__; it overrides no BaseAgent method, so runs, forks, sessions, and JevAgent specialist checks behave exactly as for a BaseAgent holding the same tools and policy. The private _FetchedPagesView is a _ToolWrapper around a keyed fetch tool that appends each fetched page's text to a successful result's output; spec, validation, permission, metadata, and pricing stay the wrapped tool's, and the runtime unwraps it before pricing.
FUNCTION INVENTORY: CodingAgent.__init__ is the narrated main function; _resolve_root validates and resolves root_dir; _web_fetch_tool validates the four keys and builds the one fetch tool. _FetchedPagesView delegates spec, validate_call, and execute, and adds page text to a successful execute result.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one row to the ordered table in _web_fetch_tool and one key parameter on __init__; a tool swap changes the coding_tools tuple and the README together. Keep validation ahead of super().__init__ so a bad argument fails before BaseAgent builds anything.
WHAT NOT TO DO IN THIS FILE: 1. Do not override generate_reply or any other BaseAgent method (JevAgent rejects specialists that replace generate_reply). 2. Do not read fetch keys from environment variables. 3. Do not supply a default system prompt or name. 4. Do not edit the wrapped fetch tools to change their output; the view is the only place page text is added.
KNOWN EDGE CASES: CodingAgent.restore(state) raises TypeError for the missing root_dir; use BaseAgent.restore(state, tools=CodingAgent(...).tools.all()). fork() returns a plain BaseAgent with the same tools, including the same _FetchedPagesView object, and the same policy. The default allow-all policy also covers caller tools with WRITE or EXECUTE permission. Bash is not confined to root_dir.
RELATED DOCS: docs/spec/coding-agent/spec.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_acceptance.py, tests/features/coding_agent/test_coding_agent_contract.py, and tests/features/coding_agent/test_coding_agent_web_fetch.py
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.operations import FetchPayload
from vidbyte.lib.errors import ConfigurationError
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
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec, ToolStatus


class CodingAgent(BaseAgent):
    """BaseAgent preloaded with bash, read, write, edit, glob, grep, and one web-fetch tool over one root folder."""

    def __init__(
        self,
        *,
        root_dir: str | Path,
        firecrawl_api_key: str | None = None,
        browserbase_api_key: str | None = None,
        parallel_api_key: str | None = None,
        tavily_api_key: str | None = None,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        **kwargs: Any,
    ) -> None:
        # @intent coding-tools-run-by-default
        # BaseAgent's default policy allows only SAFE and READ, so bash, write_text, and replace_text would come back
        # DENIED on every call and three of the seven tools would never run. Allow-all is therefore the default here,
        # while a policy the caller passes is used as that exact object, so a caller can still make the agent read-only.
        # BaseAgent's own default stays SAFE+READ; only this class opts in.

        # Resolve the root folder once, so a later change of the process working directory never moves the tools.
        root = self._resolve_root(root_dir)

        # Pick the web-fetch tool from the one key the caller passed, or the key-free direct HTTP fetch.
        fetch_tool = self._web_fetch_tool(
            firecrawl_api_key=firecrawl_api_key,
            browserbase_api_key=browserbase_api_key,
            parallel_api_key=parallel_api_key,
            tavily_api_key=tavily_api_key,
        )

        # Build the seven tools over that one root; read, write, and edit share a configuration that allows writing.
        file_config = FileSystemToolConfig(root=root, allow_write=True)
        coding_tools = (BashTool(root), ReadLinesTool(file_config), WriteTextTool(file_config), ReplaceTextTool(file_config), GlobTool(root), GrepTool(root), fetch_tool)

        # The caller's own tools follow the seven in the caller's order; a clashing name fails in BaseAgent's catalog.
        caller_tools = tools.all() if isinstance(tools, Tools) else tuple(tools)
        self.root_dir = root

        # Everything else is BaseAgent's, passed through unchanged; only the default permission policy differs.
        super().__init__(
            tools=(*coding_tools, *caller_tools),
            permission_policy=permission_policy if permission_policy is not None else PermissionPolicy.allow_all(),
            **kwargs,
        )

    @staticmethod
    def _resolve_root(root_dir: str | Path) -> Path:
        """Return root_dir as an absolute path, or raise ConfigurationError when it is not an existing directory."""
        # os.path.isdir, not Path.is_dir: Path("") is the current folder, so an empty string would pass (FR-3, D-8).
        if not isinstance(root_dir, (str, os.PathLike)) or not os.path.isdir(root_dir):
            raise ConfigurationError("CodingAgent root_dir must be an existing directory.", details={"root_dir": str(root_dir)})
        return Path(root_dir).resolve()

    @staticmethod
    def _web_fetch_tool(*, firecrawl_api_key: str | None, browserbase_api_key: str | None, parallel_api_key: str | None, tavily_api_key: str | None) -> BaseTool:
        """Return the fetch tool for the one supplied key, or DirectHttpFetchTool when no key was supplied."""
        # @intent the-supplied-key-picks-one-fetch-provider
        # The provider is chosen only by which key parameter the caller set, never by environment variables, and the
        # key lives only inside its provider client. A blank or non-string key would turn every fetch into a 401, and two
        # keys would silently bill one vendor while ignoring the other, so both fail here. Errors name the parameter,
        # never the value, so a key cannot leak through an exception message or its details.
        providers: tuple[tuple[str, str | None, type[PricedOperationTool], Callable[[str], WebOperationClient]], ...] = (
            ("firecrawl_api_key", firecrawl_api_key, FirecrawlFetchTool, FirecrawlClient),
            ("browserbase_api_key", browserbase_api_key, BrowserbaseFetchTool, BrowserbaseClient),
            ("parallel_api_key", parallel_api_key, ParallelExtractTool, ParallelClient),
            ("tavily_api_key", tavily_api_key, TavilyExtractTool, TavilyClient),
        )
        supplied = [(name, key, tool_class, client_class) for name, key, tool_class, client_class in providers if key is not None]
        blank = [name for name, key, _, _ in supplied if not isinstance(key, str) or not key.strip()]
        if blank:
            raise ConfigurationError(f"CodingAgent {', '.join(blank)} must be a non-blank string.", details={"parameters": blank})
        if len(supplied) > 1:
            names = [name for name, _, _, _ in supplied]
            raise ConfigurationError(f"CodingAgent accepts at most one fetch key, but got {', '.join(names)}.", details={"parameters": names})
        if not supplied:
            return DirectHttpFetchTool()
        _, key, tool_class, client_class = supplied[0]
        return _FetchedPagesView(tool_class(client=client_class(key)))


class _FetchedPagesView(_ToolWrapper):
    """Private view over a keyed fetch tool that also shows the model the text of every page it fetched."""

    def __init__(self, tool: BaseTool) -> None:
        # Keeps the priced fetch tool whose spec, validation, permission, metadata, and billing this view preserves.
        self._tool = tool

    @property
    def wrapped_tool(self) -> BaseTool:
        """Return the priced fetch tool behind this view."""
        return self._tool

    def _rewrap(self, tool: BaseTool) -> BaseTool:
        # Puts the same view around another copy of the fetch tool, such as a fork clone.
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
        # The keyed fetch tools show the model only a one-line summary per page and keep the text in metadata, so the
        # model of a CodingAgent could fetch a page but never read it. Only output changes: metadata, including the
        # operation-usage annotation the runtime prices from, passes through untouched, and any non-success result is
        # returned exactly as the wrapped tool built it.

        # Run the priced fetch exactly as the bare tool would.
        result = await self._tool.execute(call)

        # A failure, or a result without fetched pages, reaches the model unchanged.
        payload = result.metadata.get(PricedOperationTool._PAYLOAD_KEY)
        if result.status is not ToolStatus.SUCCESS or not isinstance(payload, FetchPayload):
            return result

        # Keep the provider's summary first, then add each page's final URL and full text in the order fetched.
        pages = "\n\n".join(f"{index}. {page.final_url}\n{page.content}" for index, page in enumerate(payload.pages, start=1))
        return dataclasses.replace(result, output=f"{result.output}\n\n{pages}")


__all__ = ["CodingAgent"]

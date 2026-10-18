"""FILE: vidbyte/lib/registries/browser_tools.py

PURPOSE: Holds the 13 pinned browser tool rows the harness thread functions can mount and resolves a caller's tool strings and keys into BrowserToolSelection records: which tool, which of its tools are allowed and denied, which server flag values turn extra tools on, and which key it gets.
ROLE IN CODEBASE: NativeBrowserRun (vidbyte/harnesses/native/hostkit/browser.py) calls BrowserToolRegistry.select once per browser call, right after the request records are built; the per-harness mount compilers read the selections it returns. BrowserToolRegistry.definition gives one row by tool.
ARCHITECTURE NOTE: A static lookup class in the lib layer, in the shape of runtimes.py and provider_keys.py: the rows are a class-held table built from vidbyte/lib/constants/browser_tools.py, one source comment per row, and select and definition are class methods. It imports only vidbyte.lib and the standard library, reads no environment, starts nothing and touches no file. Every refusal is a ConfigurationError whose details["field"] names tools[<i>], tool_keys[<registry name>] or, through the request record, tool_keys entry <i>, and whose text holds only registry-owned words (a suggested name, the mountable tools, a capability list or an exclusion's reason), never the caller's item, because a key pasted into tools is never registered as a secret (spec D-28, T-1).
FUNCTION INVENTORY: select is the narrated main function; _resolved turns one lower-cased item into its row and named capabilities; _checked_keys applies the key rules; _selection works out one selection's allowed, denied and server flag tools. definition returns one row.
COMMON MODIFICATION PATTERNS: A new mountable tool adds its constants, one BrowserTool member and one row in ROWS with its source comment, and a section in vidbyte/lib/registries/README.md ("Browser Tool Sources"). A pin bump changes the constants only.
WHAT NOT TO DO IN THIS FILE: 1. Do not quote the caller's item, a part of it, a tool_keys name that is not a registry name, or any key in a refusal. 2. Do not import from vidbyte.harnesses or any layer above vidbyte.lib. 3. Do not resolve a tool string without lower-casing it first; the grammar is case-insensitive. 4. Do not let a narrowed selection fall back to a wildcard; what is not allowed is denied (spec D-10, D-24).
KNOWN EDGE CASES: A capability with a server_value (Playwright's devtools, storage, network, pdf and vision) is additive: naming it keeps the defaults and adds its tools, and denies nothing. A capability without one is a base capability: naming it replaces the defaults, and the tool's other base tools are denied in registry order. A capability named twice in one item counts once. fetch is both an excluded tool name and a capability name; before a colon it is the excluded tool. Two items naming one tool are refused at the later index, whatever their capabilities.
RELATED DOCS: vidbyte/lib/registries/README.md; vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_registry.py, tests/features/harness_threads/test_harness_threads_browser_contract.py
"""

from __future__ import annotations

import difflib
from types import MappingProxyType
from typing import ClassVar

from vidbyte.lib.constants import browser_tools as tools_data
from vidbyte.lib.constants.native_threads import NATIVE_FIELD_DETAIL_KEY
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserCapabilityDefinition,
    BrowserToolDefinition,
    BrowserToolRequest,
    BrowserToolSelection,
)
from vidbyte.lib.enums.browser_tools import (
    BrowserCapability,
    BrowserKeyRequirement,
    BrowserTool,
    BrowserToolExclusion,
    BrowserToolTransport,
    BrowserToolVariable,
)
from vidbyte.lib.errors import ConfigurationError


class BrowserToolRegistry:
    """The pinned browser tool rows and the resolution of tool strings and keys into selections."""

    # One row per mountable tool, in BrowserTool order. Package pins,
    # entries and tool lists come from `npm install` on Node 22.12.0 and
    # `tools/list` probes of the pinned packages (vendor facts section
    # 4); the remote rows from the vendors' own docs.
    ROWS: ClassVar[tuple[BrowserToolDefinition, ...]] = (
        # @playwright/mcp@0.0.83: its installed README (`--caps`) and a
        # `tools/list` probe without and with each --caps group.
        BrowserToolDefinition(
            tool=BrowserTool.PLAYWRIGHT, transport=BrowserToolTransport.STDIO, package=tools_data.PLAYWRIGHT_PACKAGE, version=tools_data.PLAYWRIGHT_VERSION,
            entry=tools_data.PLAYWRIGHT_ENTRY, url=None, key_rule=BrowserKeyRequirement.NONE, key_variable=None, arguments=tools_data.PLAYWRIGHT_ARGUMENTS,
            environment={}, profile_option=tools_data.PLAYWRIGHT_PROFILE_OPTION, output_option=tools_data.PLAYWRIGHT_OUTPUT_OPTION,
            caps_option=tools_data.PLAYWRIGHT_CAPS_OPTION, needs_chrome=True,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.CORE, tools=tools_data.PLAYWRIGHT_CORE_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.DEVTOOLS, tools=tools_data.PLAYWRIGHT_DEVTOOLS_TOOLS, server_value=BrowserCapability.DEVTOOLS.value),
                BrowserCapabilityDefinition(name=BrowserCapability.STORAGE, tools=tools_data.PLAYWRIGHT_STORAGE_TOOLS, server_value=BrowserCapability.STORAGE.value),
                BrowserCapabilityDefinition(name=BrowserCapability.NETWORK, tools=tools_data.PLAYWRIGHT_NETWORK_TOOLS, server_value=BrowserCapability.NETWORK.value),
                BrowserCapabilityDefinition(name=BrowserCapability.PDF, tools=tools_data.PLAYWRIGHT_PDF_TOOLS, server_value=BrowserCapability.PDF.value),
                BrowserCapabilityDefinition(name=BrowserCapability.VISION, tools=tools_data.PLAYWRIGHT_VISION_TOOLS, server_value=BrowserCapability.VISION.value),
            ),
            default_capabilities=(BrowserCapability.CORE,),
        ),
        # chrome-devtools-mcp@1.11.0: its installed README
        # (CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS) and a `tools/list`
        # probe.
        BrowserToolDefinition(
            tool=BrowserTool.CHROMEDEVTOOLS, transport=BrowserToolTransport.STDIO, package=tools_data.CHROMEDEVTOOLS_PACKAGE, version=tools_data.CHROMEDEVTOOLS_VERSION,
            entry=tools_data.CHROMEDEVTOOLS_ENTRY, url=None, key_rule=BrowserKeyRequirement.NONE, key_variable=None, arguments=tools_data.CHROMEDEVTOOLS_ARGUMENTS,
            environment={BrowserToolVariable.CHROME_DEVTOOLS_UPDATE_CHECKS.value: tools_data.CHROMEDEVTOOLS_QUIET_SWITCH},
            profile_option=tools_data.CHROMEDEVTOOLS_PROFILE_OPTION, output_option=None, caps_option=None, needs_chrome=True,
            capabilities=(BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.CHROMEDEVTOOLS_ALL_TOOLS),),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # firecrawl-mcp@3.30.2: its installed README (README.md:40-72)
        # and a `tools/list` probe; it starts without a key.
        BrowserToolDefinition(
            tool=BrowserTool.FIRECRAWL, transport=BrowserToolTransport.STDIO, package=tools_data.FIRECRAWL_PACKAGE, version=tools_data.FIRECRAWL_VERSION,
            entry=tools_data.FIRECRAWL_ENTRY, url=None, key_rule=BrowserKeyRequirement.OPTIONAL, key_variable=BrowserToolVariable.FIRECRAWL, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.FIRECRAWL_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.FIRECRAWL_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SCRAPE, tools=tools_data.FIRECRAWL_SCRAPE_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.MAP, tools=tools_data.FIRECRAWL_MAP_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.CRAWL, tools=tools_data.FIRECRAWL_CRAWL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.INTERACT, tools=tools_data.FIRECRAWL_INTERACT_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # exa-mcp-server@3.4.2: its installed README (README:25-30,
        # 105-130) and a `tools/list` probe; it starts without a key.
        BrowserToolDefinition(
            tool=BrowserTool.EXA, transport=BrowserToolTransport.STDIO, package=tools_data.EXA_PACKAGE, version=tools_data.EXA_VERSION,
            entry=tools_data.EXA_ENTRY, url=None, key_rule=BrowserKeyRequirement.OPTIONAL, key_variable=BrowserToolVariable.EXA, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.EXA_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.EXA_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.FETCH, tools=tools_data.EXA_FETCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # tavily-mcp@0.2.22: its installed README and a `tools/list`
        # probe; it starts without TAVILY_API_KEY but answers no call
        # without one (spec A-10).
        BrowserToolDefinition(
            tool=BrowserTool.TAVILY, transport=BrowserToolTransport.STDIO, package=tools_data.TAVILY_PACKAGE, version=tools_data.TAVILY_VERSION,
            entry=tools_data.TAVILY_ENTRY, url=None, key_rule=BrowserKeyRequirement.REQUIRED, key_variable=BrowserToolVariable.TAVILY, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.TAVILY_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.TAVILY_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.EXTRACT, tools=tools_data.TAVILY_EXTRACT_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.CRAWL, tools=tools_data.TAVILY_CRAWL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.MAP, tools=tools_data.TAVILY_MAP_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.RESEARCH, tools=tools_data.TAVILY_RESEARCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # @brave/brave-search-mcp-server@2.1.4: its installed README and
        # a `tools/list` probe.
        BrowserToolDefinition(
            tool=BrowserTool.BRAVE, transport=BrowserToolTransport.STDIO, package=tools_data.BRAVE_PACKAGE, version=tools_data.BRAVE_VERSION,
            entry=tools_data.BRAVE_ENTRY, url=None, key_rule=BrowserKeyRequirement.REQUIRED, key_variable=BrowserToolVariable.BRAVE, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.BRAVE_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.BRAVE_SEARCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # @perplexity-ai/mcp-server@1.3.0: its installed README and a
        # `tools/list` probe.
        BrowserToolDefinition(
            tool=BrowserTool.PERPLEXITY, transport=BrowserToolTransport.STDIO, package=tools_data.PERPLEXITY_PACKAGE, version=tools_data.PERPLEXITY_VERSION,
            entry=tools_data.PERPLEXITY_ENTRY, url=None, key_rule=BrowserKeyRequirement.REQUIRED, key_variable=BrowserToolVariable.PERPLEXITY, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.PERPLEXITY_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.PERPLEXITY_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.RESEARCH, tools=tools_data.PERPLEXITY_RESEARCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # @brightdata/mcp@3.1.0: its installed README (API_TOKEN) and a
        # `tools/list` probe (the 14 scraping_browser_* tools).
        BrowserToolDefinition(
            tool=BrowserTool.BRIGHTDATA, transport=BrowserToolTransport.STDIO, package=tools_data.BRIGHTDATA_PACKAGE, version=tools_data.BRIGHTDATA_VERSION,
            entry=tools_data.BRIGHTDATA_ENTRY, url=None, key_rule=BrowserKeyRequirement.REQUIRED, key_variable=BrowserToolVariable.BRIGHTDATA, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.BRIGHTDATA_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.BRIGHTDATA_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SCRAPE, tools=tools_data.BRIGHTDATA_SCRAPE_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.BROWSER, tools=tools_data.BRIGHTDATA_BROWSER_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # @apify/actors-mcp-server@0.18.4: its installed README
        # (APIFY_TOKEN) and a `tools/list` probe (spec EC-34).
        BrowserToolDefinition(
            tool=BrowserTool.APIFY, transport=BrowserToolTransport.STDIO, package=tools_data.APIFY_PACKAGE, version=tools_data.APIFY_VERSION,
            entry=tools_data.APIFY_ENTRY, url=None, key_rule=BrowserKeyRequirement.REQUIRED, key_variable=BrowserToolVariable.APIFY, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.APIFY_ALL_TOOLS),),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # linkup-mcp-server@3.4.0: its installed README (README:44-50,
        # 72-80) and a `tools/list` probe.
        BrowserToolDefinition(
            tool=BrowserTool.LINKUP, transport=BrowserToolTransport.STDIO, package=tools_data.LINKUP_PACKAGE, version=tools_data.LINKUP_VERSION,
            entry=tools_data.LINKUP_ENTRY, url=None, key_rule=BrowserKeyRequirement.REQUIRED, key_variable=BrowserToolVariable.LINKUP, arguments=(),
            environment={}, profile_option=None, output_option=None, caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.LINKUP_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.LINKUP_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.FETCH, tools=tools_data.LINKUP_FETCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.RESEARCH, tools=tools_data.LINKUP_RESEARCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # Browserbase's hosted server: its README (README.md:15-47,
        # 66-85), six tools, a Bearer key (spec A-12).
        BrowserToolDefinition(
            tool=BrowserTool.BROWSERBASE, transport=BrowserToolTransport.REMOTE, package=None, version=None, entry=(), url=tools_data.BROWSERBASE_URL,
            key_rule=BrowserKeyRequirement.REQUIRED, key_variable=None, arguments=(), environment={}, profile_option=None, output_option=None,
            caps_option=None, needs_chrome=False,
            capabilities=(BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.BROWSERBASE_ALL_TOOLS),),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # Jina's hosted server: its README (README.md:15-17, 64-80,
        # 122-136), an optional Bearer key (spec A-12).
        BrowserToolDefinition(
            tool=BrowserTool.JINA, transport=BrowserToolTransport.REMOTE, package=None, version=None, entry=(), url=tools_data.JINA_URL,
            key_rule=BrowserKeyRequirement.OPTIONAL, key_variable=None, arguments=(), environment={}, profile_option=None, output_option=None,
            caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.JINA_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.JINA_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.FETCH, tools=tools_data.JINA_FETCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
        # Parallel's hosted search server:
        # docs.parallel.ai/integrations/mcp/search-mcp, free without a
        # key, a Bearer key for paid use (spec A-12).
        BrowserToolDefinition(
            tool=BrowserTool.PARALLEL, transport=BrowserToolTransport.REMOTE, package=None, version=None, entry=(), url=tools_data.PARALLEL_URL,
            key_rule=BrowserKeyRequirement.OPTIONAL, key_variable=None, arguments=(), environment={}, profile_option=None, output_option=None,
            caps_option=None, needs_chrome=False,
            capabilities=(
                BrowserCapabilityDefinition(name=BrowserCapability.ALL, tools=tools_data.PARALLEL_ALL_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.SEARCH, tools=tools_data.PARALLEL_SEARCH_TOOLS),
                BrowserCapabilityDefinition(name=BrowserCapability.FETCH, tools=tools_data.PARALLEL_FETCH_TOOLS),
            ),
            default_capabilities=(BrowserCapability.ALL,),
        ),
    )
    DEFINITIONS: ClassVar[MappingProxyType[BrowserTool, BrowserToolDefinition]] = MappingProxyType({row.tool: row for row in ROWS})

    @classmethod
    def definition(cls, tool: BrowserTool) -> BrowserToolDefinition:
        """Return the pinned row of one mountable tool."""
        return cls.DEFINITIONS[tool]

    @classmethod
    def select(cls, request: BrowserToolRequest) -> tuple[BrowserToolSelection, ...]:
        """Resolve each tool string of a checked request into one selection, in request order, with its key."""
        # @intent browser-registry-never-quotes-the-item
        # The request record already checked the shape; every refusal
        # here names tools[<i>] or tool_keys[<registry name>] and holds
        # only registry-owned words, because the item may be a key.

        # Resolve each item to its row and the capabilities it names,
        # and refuse a tool that an earlier item already named.
        resolved: list[tuple[BrowserToolDefinition, tuple[BrowserCapability, ...]]] = []
        first_index: dict[BrowserTool, int] = {}
        for index, item in enumerate(request.tools):
            field = tools_data.BROWSER_TOOL_ITEM_FIELD.format(index=index)
            definition, named = cls._resolved(item.lower(), field)
            if definition.tool in first_index:
                raise ConfigurationError(tools_data.BROWSER_DUPLICATE_TEXT.format(first=first_index[definition.tool]), details={NATIVE_FIELD_DETAIL_KEY: field})
            first_index[definition.tool] = index
            resolved.append((definition, named))

        # Each key must belong to a selected tool that takes one, and
        # each selected tool that cannot answer a call without a key
        # needs one.
        cls._checked_keys(request, [definition for definition, _ in resolved])

        # Work out what each selection allows, denies and turns on.
        return tuple(cls._selection(definition, named, request.tool_keys.get(definition.tool.value)) for definition, named in resolved)

    @classmethod
    def _resolved(cls, item: str, field: str) -> tuple[BrowserToolDefinition, tuple[BrowserCapability, ...]]:
        # The tool name before the colon, the capability names after it;
        # a host after @ is reserved for a later release.
        named_tool, _, host = item.partition(tools_data.BROWSER_HOST_SEPARATOR)
        if host:
            raise ConfigurationError(tools_data.BROWSER_HOST_TEXT, details={NATIVE_FIELD_DETAIL_KEY: field})
        name, _, capability_text = named_tool.partition(tools_data.BROWSER_CAPABILITY_SEPARATOR)
        excluded = {member.value: member for member in BrowserToolExclusion}
        if name in excluded:
            raise ConfigurationError(tools_data.BROWSER_EXCLUDED_TEXT.format(reason=tools_data.BROWSER_TOOL_EXCLUSION_REASONS[excluded[name]]), details={NATIVE_FIELD_DETAIL_KEY: field})
        mountable = [member.value for member in BrowserTool]
        if name not in mountable:
            close = difflib.get_close_matches(name, [*mountable, *excluded], n=tools_data.BROWSER_SUGGESTION_COUNT, cutoff=tools_data.BROWSER_SUGGESTION_CUTOFF)
            text = (tools_data.BROWSER_TOOL_SUGGESTION_TEXT if close else tools_data.BROWSER_TOOL_UNKNOWN_TEXT).format(suggestion=close[0] if close else None, tools=tools_data.BROWSER_LIST_SEPARATOR.join(mountable))
            raise ConfigurationError(text, details={NATIVE_FIELD_DETAIL_KEY: field})
        definition = cls.DEFINITIONS[BrowserTool(name)]
        known = [capability.name.value for capability in definition.capabilities]
        requested = list(dict.fromkeys(capability_text.split(tools_data.BROWSER_CAPABILITY_LIST_SEPARATOR))) if capability_text else []
        for capability in requested:
            if capability not in known:
                close = difflib.get_close_matches(capability, known, n=tools_data.BROWSER_SUGGESTION_COUNT, cutoff=tools_data.BROWSER_SUGGESTION_CUTOFF)
                text = (tools_data.BROWSER_CAPABILITY_SUGGESTION_TEXT if close else tools_data.BROWSER_CAPABILITY_UNKNOWN_TEXT).format(tool=name, suggestion=close[0] if close else None, capabilities=tools_data.BROWSER_LIST_SEPARATOR.join(known))
                raise ConfigurationError(text, details={NATIVE_FIELD_DETAIL_KEY: field})
        return definition, tuple(BrowserCapability(capability) for capability in requested)

    @classmethod
    def _checked_keys(cls, request: BrowserToolRequest, definitions: list[BrowserToolDefinition]) -> None:
        # The record already refused a name that is not a registry name,
        # so every name shown here is registry-owned text.
        selected = {definition.tool.value: definition for definition in definitions}
        for name in request.tool_keys:
            field = tools_data.BROWSER_TOOL_KEY_NAME_FIELD.format(name=name)
            if name not in selected:
                raise ConfigurationError(tools_data.BROWSER_KEY_UNSELECTED_TEXT, details={NATIVE_FIELD_DETAIL_KEY: field})
            if selected[name].key_rule is BrowserKeyRequirement.NONE:
                raise ConfigurationError(tools_data.BROWSER_KEY_REFUSED_TEXT.format(tool=name), details={NATIVE_FIELD_DETAIL_KEY: field})
        for name, definition in selected.items():
            if definition.key_rule is BrowserKeyRequirement.REQUIRED and name not in request.tool_keys:
                raise ConfigurationError(tools_data.BROWSER_KEY_MISSING_TEXT.format(tool=name), details={NATIVE_FIELD_DETAIL_KEY: tools_data.BROWSER_TOOL_KEY_NAME_FIELD.format(name=name)})

    @classmethod
    def _selection(cls, definition: BrowserToolDefinition, named: tuple[BrowserCapability, ...], key: str | None) -> BrowserToolSelection:
        # A capability with a server flag value adds tools on top of the
        # base; naming a base capability replaces the defaults.
        additive = {capability.name for capability in definition.capabilities if capability.server_value is not None and capability.name in named}
        base = {capability.name for capability in definition.capabilities if capability.server_value is None and capability.name in named} or set(definition.default_capabilities)
        chosen = base | additive
        allowed = tuple(dict.fromkeys(tool for capability in definition.capabilities if capability.name in chosen for tool in capability.tools))

        # Every base tool the server exposes, plus what the named
        # server flags turn on, that is not allowed is denied, in
        # registry order.
        exposed = dict.fromkeys(tool for capability in definition.capabilities if capability.server_value is None or capability.name in additive for tool in capability.tools)
        denied = tuple(tool for tool in exposed if tool not in allowed)
        server_capabilities = tuple(capability.server_value for capability in definition.capabilities if capability.server_value is not None and capability.name in additive)
        capabilities = tuple(capability.name for capability in definition.capabilities if capability.name in chosen)
        return BrowserToolSelection(definition=definition, capabilities=capabilities, allowed=allowed, denied=denied, server_capabilities=server_capabilities, key=key)


__all__ = ["BrowserToolRegistry"]

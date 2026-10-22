"""FILE: vidbyte/lib/enums/browser_tools.py

PURPOSE: Defines the closed vocabularies of the browser tools the harness thread functions can mount: the mountable tools (BrowserTool), the names answered with a recorded reason instead (BrowserToolExclusion), the named tool subsets (BrowserCapability), how a tool is reached (BrowserToolTransport), whether it takes a key (BrowserKeyRequirement), how a vendor reported one call (BrowserToolCallStatus) and the environment variable each keyed stdio tool reads its key from (BrowserToolVariable).
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/browser_tools.py, the registry in vidbyte/lib/registries/browser_tools.py, the texts in vidbyte/lib/constants/browser_tools.py and the browser modules under vidbyte/harnesses/native/. Exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Every enum here is a StrEnum, so str(member) and an f-string give the value; the values are the strings a caller passes in `tools` and the names the vendors use for servers and variables. Tool values contain no underscore, so a vendor tool name splits unambiguously at its first `_` (opencode) or `__` (Grok, Muse).
FUNCTION INVENTORY: No functions. BrowserTool, BrowserToolExclusion, BrowserCapability, BrowserToolTransport, BrowserKeyRequirement, BrowserToolCallStatus and BrowserToolVariable.
COMMON MODIFICATION PATTERNS: A new mountable tool appends one BrowserTool member and adds its registry row (vidbyte/lib/registries/browser_tools.py) and constants in the same change; a keyed stdio tool also appends its BrowserToolVariable member. A tool that cannot be mounted appends a BrowserToolExclusion member and its reason in BROWSER_TOOL_EXCLUSION_REASONS.
WHAT NOT TO DO IN THIS FILE: 1. Do not name a member with a credential word (password, pass, pwd, token, secret, key) and bind it to a string (lint S054); BrowserToolVariable members are named after the tool. 2. Do not import anything from vidbyte; enums sit at the bottom layer. 3. Do not reorder members; append.
KNOWN EDGE CASES: `fetch` is both a BrowserCapability value (exa, jina, parallel) and a BrowserToolExclusion value (the Python fetch server); the two never meet, because a capability is only read after the `:` of a tool string. BrowserToolVariable.BRIGHTDATA is the bare API_TOKEN that Bright Data's server reads.
RELATED DOCS: vidbyte/harnesses/README.md; vidbyte/lib/registries/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_contract.py, tests/features/harness_threads/test_harness_threads_browser_registry.py
"""

from __future__ import annotations

from enum import StrEnum


class BrowserTool(StrEnum):
    """A browser tool the harness thread functions can mount, by the name a caller passes in tools."""

    PLAYWRIGHT = "playwright"
    CHROMEDEVTOOLS = "chromedevtools"
    FIRECRAWL = "firecrawl"
    EXA = "exa"
    TAVILY = "tavily"
    BRAVE = "brave"
    PERPLEXITY = "perplexity"
    BRIGHTDATA = "brightdata"
    APIFY = "apify"
    LINKUP = "linkup"
    BROWSERBASE = "browserbase"
    JINA = "jina"
    PARALLEL = "parallel"


class BrowserToolExclusion(StrEnum):
    """A well-known tool name the registry answers with its recorded reason instead of mounting it."""

    BROWSERSTACK = "browserstack"
    SEARXNG = "searxng"
    WDIO = "wdio"
    FETCH = "fetch"
    DUCKDUCKGO = "duckduckgo"
    AGENTBROWSER = "agentbrowser"
    PLAYWRIGHTCLI = "playwrightcli"
    MIDSCENE = "midscene"
    DEVBROWSER = "devbrowser"
    CRAWL4AI = "crawl4ai"
    BROWSERUSE = "browseruse"
    SCRAPLING = "scrapling"
    KERNEL = "kernel"
    CLOUDFLARE = "cloudflare"
    PUPPETEER = "puppeteer"
    HYPERBROWSER = "hyperbrowser"
    STEEL = "steel"
    BROWSERLESS = "browserless"


class BrowserCapability(StrEnum):
    """A named subset of one tool's own tools, written after the colon of a tool string."""

    ALL = "all"
    CORE = "core"
    DEVTOOLS = "devtools"
    STORAGE = "storage"
    NETWORK = "network"
    PDF = "pdf"
    VISION = "vision"
    SEARCH = "search"
    SCRAPE = "scrape"
    MAP = "map"
    CRAWL = "crawl"
    INTERACT = "interact"
    FETCH = "fetch"
    EXTRACT = "extract"
    RESEARCH = "research"
    BROWSER = "browser"


class BrowserToolTransport(StrEnum):
    """How a harness reaches a tool's server: a pinned local process over stdio, or a remote URL."""

    STDIO = "stdio"
    REMOTE = "remote"


class BrowserKeyRequirement(StrEnum):
    """Whether a tool needs a key in tool_keys, may take one, or takes none."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"


class BrowserToolCallStatus(StrEnum):
    """How the vendor reported one call to a mounted tool."""

    COMPLETED = "completed"
    FAILED = "failed"


class BrowserToolVariable(StrEnum):
    """The environment variable a stdio tool reads (a key, or a non-secret switch); members are named after the tool."""

    FIRECRAWL = "FIRECRAWL_API_KEY"
    EXA = "EXA_API_KEY"
    TAVILY = "TAVILY_API_KEY"
    BRAVE = "BRAVE_API_KEY"
    PERPLEXITY = "PERPLEXITY_API_KEY"
    BRIGHTDATA = "API_TOKEN"
    APIFY = "APIFY_TOKEN"
    LINKUP = "LINKUP_API_KEY"
    CHROME_DEVTOOLS_UPDATE_CHECKS = "CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS"


__all__ = [
    "BrowserCapability",
    "BrowserKeyRequirement",
    "BrowserTool",
    "BrowserToolCallStatus",
    "BrowserToolExclusion",
    "BrowserToolTransport",
    "BrowserToolVariable",
]

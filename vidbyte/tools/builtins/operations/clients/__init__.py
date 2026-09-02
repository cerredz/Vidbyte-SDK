"""Context Protocol Header

Description:
    Exports the executing provider clients backing the priced operation tools.
Purpose:
    Gives applications one import path for credentialed search and fetch clients
    plus the retry policy that governs how many attempts they may bill for.
Architecture:
    - WebOperationClient / RetryPolicy: Shared transport policy and base.
    - Brave / Browserbase / Exa / Firecrawl / Parallel / Tavily: Vendor clients
      returning typed payloads.
Relations:
    Re-exported by vidbyte.tools.builtins.operations; injected into the priced
    tools in that package.
"""

from __future__ import annotations

from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient
from vidbyte.tools.builtins.operations.clients.brave import BraveClient
from vidbyte.tools.builtins.operations.clients.browserbase import BrowserbaseClient
from vidbyte.tools.builtins.operations.clients.exa import ExaClient
from vidbyte.tools.builtins.operations.clients.firecrawl import FirecrawlClient
from vidbyte.tools.builtins.operations.clients.parallel import ParallelClient
from vidbyte.tools.builtins.operations.clients.tavily import TavilyClient

__all__ = [
    "BraveClient",
    "BrowserbaseClient",
    "ExaClient",
    "FirecrawlClient",
    "ParallelClient",
    "RetryPolicy",
    "TavilyClient",
    "WebOperationClient",
]

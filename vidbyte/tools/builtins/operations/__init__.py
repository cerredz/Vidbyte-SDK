"""Context Protocol Header

Description:
    Exports the pre-built priced search/fetch operation tools.
Purpose:
    Provides convenient imports for the operation tools and their shared base
    without auto-registering instances.
Architecture:
    - PricedOperationTool: Shared base carrying (operation, provider) identity.
    - Search tools: Brave/Browserbase/Exa/Tavily/Linkup/Parallel/OpenAlex/SemanticScholar.
    - Fetch tools: Firecrawl/Browserbase/Parallel/Tavily/Linkup/DirectHttp.
Relations:
    Re-exported by vidbyte.tools.builtins; priced via UsageTracker.record_operation.
"""

from __future__ import annotations

from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.builtins.operations.clients import (
    BraveClient,
    BrowserbaseClient,
    ExaClient,
    FirecrawlClient,
    ParallelClient,
    RetryPolicy,
    TavilyClient,
    WebOperationClient,
)
from vidbyte.tools.builtins.operations.fetch import (
    BrowserbaseFetchTool,
    DirectHttpFetchTool,
    FirecrawlFetchTool,
    LinkupFetchTool,
    ParallelExtractTool,
    TavilyExtractTool,
)
from vidbyte.tools.builtins.operations.search import (
    BraveSearchTool,
    BrowserbaseSearchTool,
    ExaSearchTool,
    LinkupSearchTool,
    OpenAlexSearchTool,
    ParallelSearchTool,
    SemanticScholarSearchTool,
    TavilySearchTool,
)

__all__ = [
    "BraveClient",
    "BraveSearchTool",
    "BrowserbaseClient",
    "BrowserbaseFetchTool",
    "BrowserbaseSearchTool",
    "DirectHttpFetchTool",
    "ExaClient",
    "ExaSearchTool",
    "FirecrawlClient",
    "FirecrawlFetchTool",
    "LinkupFetchTool",
    "LinkupSearchTool",
    "OpenAlexSearchTool",
    "ParallelClient",
    "ParallelExtractTool",
    "ParallelSearchTool",
    "PricedOperationTool",
    "RetryPolicy",
    "SemanticScholarSearchTool",
    "TavilyClient",
    "TavilyExtractTool",
    "TavilySearchTool",
    "WebOperationClient",
]

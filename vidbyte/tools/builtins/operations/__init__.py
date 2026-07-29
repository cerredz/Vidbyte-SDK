"""Context Protocol Header

Description:
    Exports the pre-built priced search/fetch operation tools.
Purpose:
    Provides convenient imports for the operation tools and their shared base
    without auto-registering instances.
Architecture:
    - PricedOperationTool: Shared base carrying (operation, provider) identity.
    - Search tools: Brave/Exa/Tavily/Linkup/Parallel/OpenAlex/SemanticScholar.
    - Fetch tools: Firecrawl/Parallel/Tavily/Linkup/DirectHttp.
Relations:
    Re-exported by vidbyte.tools.builtins; priced via UsageTracker.record_operation.
"""

from __future__ import annotations

from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.builtins.operations.api import ProviderApiTool
from vidbyte.tools.builtins.operations.clients import (
    BrowserbaseClient,
    BraveClient,
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
    ExaContentsTool,
    FirecrawlFetchTool,
    LinkupFetchTool,
    ParallelExtractTool,
    TavilyExtractTool,
)
from vidbyte.tools.builtins.operations.search import (
    BrowserbaseSearchTool,
    BraveSearchTool,
    ExaSearchTool,
    LinkupSearchTool,
    OpenAlexSearchTool,
    ParallelSearchTool,
    SemanticScholarSearchTool,
    TavilySearchTool,
)
from vidbyte.tools.builtins.operations.providers import (
    BrowserbaseContextTool,
    BrowserbaseSessionTool,
    ExaAnswerTool,
    ExaMonitorTool,
    ExaWebsetTool,
    ParallelChatTool,
    ParallelFindAllTool,
    ParallelMonitorTool,
    ParallelResponseTool,
    ParallelTaskTool,
    TavilyCrawlTool,
    TavilyMapTool,
    TavilyResearchTool,
)

__all__ = [
    "BraveClient",
    "BrowserbaseClient",
    "BrowserbaseContextTool",
    "BrowserbaseFetchTool",
    "BrowserbaseSearchTool",
    "BrowserbaseSessionTool",
    "BraveSearchTool",
    "DirectHttpFetchTool",
    "ExaSearchTool",
    "ExaAnswerTool",
    "ExaContentsTool",
    "ExaClient",
    "FirecrawlClient",
    "FirecrawlFetchTool",
    "LinkupFetchTool",
    "LinkupSearchTool",
    "OpenAlexSearchTool",
    "ParallelChatTool",
    "ParallelFindAllTool",
    "ParallelMonitorTool",
    "ParallelResponseTool",
    "ParallelTaskTool",
    "ParallelExtractTool",
    "ParallelSearchTool",
    "PricedOperationTool",
    "RetryPolicy",
    "SemanticScholarSearchTool",
    "TavilyExtractTool",
    "TavilyCrawlTool",
    "TavilyMapTool",
    "TavilyResearchTool",
    "TavilySearchTool",
    "ExaMonitorTool",
    "ExaWebsetTool",
    "ParallelClient",
    "ProviderApiTool",
    "TavilyClient",
    "WebOperationClient",
]

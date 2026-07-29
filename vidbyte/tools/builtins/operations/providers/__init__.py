"""Context Protocol Header

Description:
    Exports provider-specific operation tools beyond common search and fetch.
Purpose:
    Keeps the operation package import surface explicit as provider APIs grow.
Architecture:
    Browserbase, Exa, Tavily, and Parallel modules contain endpoint adapters over
    ProviderApiTool and injected provider clients.
Relations:
    Re-exported by vidbyte.tools.builtins.operations.
"""

from __future__ import annotations

from vidbyte.tools.builtins.operations.providers.browserbase import BrowserbaseContextTool, BrowserbaseSessionTool
from vidbyte.tools.builtins.operations.providers.exa import ExaAnswerTool, ExaMonitorTool, ExaWebsetTool
from vidbyte.tools.builtins.operations.providers.parallel import ParallelChatTool, ParallelFindAllTool, ParallelMonitorTool, ParallelTaskTool
from vidbyte.tools.builtins.operations.providers.tavily import TavilyCrawlTool, TavilyMapTool, TavilyResearchTool

__all__ = [
    "BrowserbaseContextTool",
    "BrowserbaseSessionTool",
    "ExaAnswerTool",
    "ExaMonitorTool",
    "ExaWebsetTool",
    "ParallelChatTool",
    "ParallelFindAllTool",
    "ParallelMonitorTool",
    "ParallelTaskTool",
    "TavilyCrawlTool",
    "TavilyMapTool",
    "TavilyResearchTool",
]

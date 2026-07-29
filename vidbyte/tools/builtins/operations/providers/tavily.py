"""Context Protocol Header

Description:
    Tavily map, crawl, and research endpoint tools.
Purpose:
    Exposes Tavily's graph-navigation and deep-research APIs with explicit limits
    and the provider's successful-page/credit usage dimensions.
Architecture:
    Tools delegate to TavilyClient methods so dynamic charges come from response
    usage rather than assumptions in the model-facing adapter.
Relations:
    Consumed through vidbyte.tools.builtins.operations exports.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.tools.builtins.operations.api import ProviderApiTool
from vidbyte.tools.types import ToolCall, ToolParameter


class TavilyMapTool(ProviderApiTool):
    """Map a website's navigable link graph."""

    operation = "map"
    provider = "tavily"
    tool_name = "tavily_map"
    description = "Maps a website with bounded depth, breadth, path filters, and optional natural-language instructions."
    charge_operation = None
    parameters = (ToolParameter("url", "string", "Root URL to map."), ToolParameter("instructions", "string", "Optional semantic mapping instructions.", required=False), ToolParameter("max_depth", "int", "Maximum traversal depth from 1 to 5.", required=False, default=1), ToolParameter("max_breadth", "int", "Maximum links per page from 1 to 500.", required=False, default=20), ToolParameter("limit", "int", "Maximum pages to return.", required=False, default=50), ToolParameter("options", "object", "Additional documented Tavily Map fields such as path/domain selectors.", required=False))

    async def _request(self, call: ToolCall):
        # Maps the site through TavilyClient so successful-page pricing is accurate.
        options = call.arguments.get("options")
        options = options if isinstance(options, Mapping) else None
        return await self._client.map(str(call.arguments["url"]), instructions=call.arguments.get("instructions"), max_depth=int(call.arguments.get("max_depth", 1)), max_breadth=int(call.arguments.get("max_breadth", 20)), limit=int(call.arguments.get("limit", 50)), options=options)


class TavilyCrawlTool(ProviderApiTool):
    """Crawl and extract a bounded website tree."""

    operation = "crawl"
    provider = "tavily"
    tool_name = "tavily_crawl"
    description = "Crawls and extracts a bounded website tree with path/domain filters and basic or advanced extraction."
    charge_operation = None
    parameters = (ToolParameter("url", "string", "Root URL to crawl."), ToolParameter("instructions", "string", "Optional semantic crawl instructions.", required=False), ToolParameter("max_depth", "int", "Maximum traversal depth from 1 to 5.", required=False, default=1), ToolParameter("max_breadth", "int", "Maximum links per page from 1 to 500.", required=False, default=20), ToolParameter("limit", "int", "Maximum pages to process.", required=False, default=50), ToolParameter("extract_depth", "string", "basic or advanced extraction.", required=False, default="basic"), ToolParameter("format", "string", "markdown or text.", required=False, default="markdown"), ToolParameter("options", "object", "Additional documented Tavily Crawl fields such as path/domain selectors or images.", required=False))

    async def _request(self, call: ToolCall):
        # Crawls through TavilyClient so map and extraction charges remain separate.
        options = call.arguments.get("options")
        options = options if isinstance(options, Mapping) else None
        return await self._client.crawl(str(call.arguments["url"]), instructions=call.arguments.get("instructions"), max_depth=int(call.arguments.get("max_depth", 1)), max_breadth=int(call.arguments.get("max_breadth", 20)), limit=int(call.arguments.get("limit", 50)), extract_depth=str(call.arguments.get("extract_depth", "basic")), format=str(call.arguments.get("format", "markdown")), options=options)


class TavilyResearchTool(ProviderApiTool):
    """Start Tavily deep research with bounded output controls."""

    operation = "research"
    provider = "tavily"
    tool_name = "tavily_research"
    description = "Starts or resumes Tavily Research for deep, cited analysis with optional structured output."
    charge_operation = None
    parameters = (ToolParameter("action", "string", "start or status.", required=False, default="start"), ToolParameter("input", "string", "Research objective for start.", required=False), ToolParameter("research_id", "string", "Research ID for status.", required=False), ToolParameter("model", "string", "mini or pro research model.", required=False, default="mini"), ToolParameter("output_schema", "object", "Optional structured output schema.", required=False), ToolParameter("stream", "bool", "Request provider streaming semantics.", required=False, default=False))

    async def _request(self, call: ToolCall):
        # Starts or resumes Tavily research and meters only the billable start response.
        if str(call.arguments.get("action", "start")) == "status":
            research_id = str(call.arguments.get("research_id", ""))
            if not research_id:
                raise ValueError("research_id is required for status")
            return await self._client.api("research_status", method="GET", path=f"research/{research_id}", charges=())
        input_text = str(call.arguments.get("input", ""))
        if not input_text.strip():
            raise ValueError("input is required to start research")
        return await self._client.research(input_text, model=str(call.arguments.get("model", "mini")), output_schema=call.arguments.get("output_schema"), stream=bool(call.arguments.get("stream", False)))


__all__ = ["TavilyCrawlTool", "TavilyMapTool", "TavilyResearchTool"]

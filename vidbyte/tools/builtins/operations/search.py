"""Context Protocol Header

Description:
    Pre-built priced search tools for the supported web-search providers.
Purpose:
    Give agents first-class search tools whose calls the runtime prices as
    search operations, each declaring its (operation, provider) and deriving its
    billing mode and units from the call arguments.
Architecture:
    - Brave/Browserbase/OpenAlex/SemanticScholar: flat per-request search (units = 1).
    - Exa/Parallel: per-result search (units = returned result count, floored at 1).
      Exa also suffixes its billing mode with "+highlights" when the bound client
      requested the contents block, because that bills a second vendor meter.
    - Tavily/Linkup: depth-tiered search selecting a billing mode.
Relations:
    Subclass PricedOperationTool (this package's base) and are exported through
    vidbyte/tools/builtins/operations/__init__.py.
Similar Files:
    - vidbyte/tools/builtins/operations/fetch.py
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.operations import SearchPayload
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.builtins.operations.clients import ExaClient
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


def _int_arg(call: ToolCall, name: str, default: int) -> int:
    # Reads a positive integer argument, falling back to default for missing/invalid values.
    value = call.arguments.get(name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _mode_arg(call: ToolCall, name: str, allowed: tuple[str, ...], default: str) -> str:
    # Reads a mode argument, clamping anything outside the allowed set to default.
    value = call.arguments.get(name)
    return value if isinstance(value, str) and value in allowed else default


def _render_search_results(label: str, payload: SearchPayload) -> str:
    # Renders a compact numbered result list for the model's context window.
    if not payload.hits:
        return f"{label}: no results for {payload.query!r}."
    lines = [f"{index}. {hit.title} — {hit.url}" + (f"\n   {hit.snippet[:300]}" if hit.snippet else "") for index, hit in enumerate(payload.hits, start=1)]
    return f"{label}: {len(payload.hits)} results for {payload.query!r}.\n" + "\n".join(lines)


_EXA_SEARCH_TYPES = ("auto", "fast", "deep-lite", "deep", "deep-reasoning")
_HIGHLIGHTS_MODE_SUFFIX = "+highlights"


class BraveSearchTool(PricedOperationTool):
    """Brave web search — flat per-request billing."""

    operation = "search"
    provider = "brave"

    def spec(self) -> ToolSpec:
        # Declares the Brave search tool with a query and an optional result count.
        return ToolSpec(
            name="brave_search",
            description="Runs a privacy-focused Brave web search and returns ranked result snippets.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="count", type="int", description="Maximum results to return (max 20).", required=False, default=10),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs the query through the injected BraveClient, or prices a contract stub without one.
        query = str(call.arguments.get("query", ""))
        if self._client is None:
            return self._contract_result(f"brave search: {query}", units=1)
        try:
            payload = await self._client.search(query, count=_int_arg(call, "count", 10))
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("brave search failed.", units=1, mode="default", attempts=self._client.max_attempts, error="search_failed")
        return self._executed_result(self._render(payload), payload, units=payload.billable_units, mode="default", attempts=payload.attempts)

    def _render(self, payload: SearchPayload) -> str:
        # Renders a compact numbered result list for the model's context window.
        return _render_search_results("brave search", payload)


class BrowserbaseSearchTool(PricedOperationTool):
    """Browserbase web search — flat per-request billing."""

    operation = "search"
    provider = "browserbase"

    def spec(self) -> ToolSpec:
        # Declares the Browserbase search tool with a query and an optional result count.
        return ToolSpec(
            name="browserbase_search",
            description="Runs a Browserbase web search and returns ranked result snippets.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="num_results", type="int", description="Maximum results to return (max 25).", required=False, default=10),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs the query through the injected BrowserbaseClient, or prices a contract stub without one.
        query = str(call.arguments.get("query", ""))
        if self._client is None:
            return self._contract_result(f"browserbase search: {query}", units=1)
        try:
            payload = await self._client.search(query, num_results=_int_arg(call, "num_results", 10))
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("browserbase search failed.", units=1, mode="default", attempts=self._client.max_attempts, error="search_failed")
        return self._executed_result(_render_search_results("browserbase search", payload), payload, units=payload.billable_units, mode="default", attempts=payload.attempts)


class ExaSearchTool(PricedOperationTool):
    """Exa neural search — per-result billing over a 10-result bundle."""

    operation = "search"
    provider = "exa"

    def spec(self) -> ToolSpec:
        # Declares the Exa search tool with query, result count, and search type.
        return ToolSpec(
            name="exa_search",
            description="Runs an Exa neural search returning hyper-relevant ranked results.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="num_results", type="int", description="Number of results to return.", required=False, default=10),
                ToolParameter(name="type", type="string", description="Search mode: 'auto', 'fast', 'deep-lite', 'deep', or 'deep-reasoning'.", required=False, default="auto"),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs the query through the injected ExaClient, or prices a contract stub without one.
        query = str(call.arguments.get("query", ""))
        search_type = _mode_arg(call, "type", _EXA_SEARCH_TYPES, "auto")
        mode = self._billing_mode(search_type)
        if self._client is None:
            return self._contract_result(f"exa search: {query}", units=_int_arg(call, "num_results", 10), mode=mode)
        try:
            payload = await self._client.search(query, num_results=_int_arg(call, "num_results", 10), search_type=search_type)
        except (ProviderRequestError, ProviderResponseError) as exc:
            return self._failed_result(
                "exa search failed.",
                units=1,
                mode=mode,
                attempts=self._client.max_attempts,
                error="search_failed",
                error_type=type(exc).__name__,
                error_status_code=getattr(exc, "status_code", None),
            )
        return self._executed_result(_render_search_results("exa search", payload), payload, units=payload.billable_units, mode=mode, attempts=payload.attempts)

    def _billing_mode(self, search_type: str) -> str:
        # Suffixes the search type when the bound client also requested billable highlights.
        # @intent a-rename-here-must-break-the-build-not-the-invoice
        # An untyped probe for the attribute would fall back to False if the client
        # ever renamed it, silently resolving to the cheaper non-highlights tariff
        # through the pricebook's "default" mode fallback. The isinstance check
        # makes that a type error instead of an under-billed search.
        if isinstance(self._client, ExaClient) and self._client.includes_highlights:
            return f"{search_type}{_HIGHLIGHTS_MODE_SUFFIX}"
        return search_type


class TavilySearchTool(PricedOperationTool):
    """Tavily agentic search — depth tier selects the billing mode."""

    operation = "search"
    provider = "tavily"

    def spec(self) -> ToolSpec:
        # Declares the Tavily search tool with query and search depth.
        return ToolSpec(
            name="tavily_search",
            description="Runs an LLM-optimized Tavily web search returning ready-to-consume snippets.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="search_depth", type="string", description="Search depth: 'basic' or 'advanced'.", required=False, default="basic"),
                ToolParameter(name="max_results", type="int", description="Maximum results to return.", required=False, default=5),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs the query through the injected TavilyClient, or prices a contract stub without one.
        query = str(call.arguments.get("query", ""))
        mode = _mode_arg(call, "search_depth", ("basic", "advanced"), "basic")
        if self._client is None:
            return self._contract_result(f"tavily search: {query}", units=1, mode=mode)
        try:
            payload = await self._client.search(query, max_results=_int_arg(call, "max_results", 5), search_depth=mode)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("tavily search failed.", units=1, mode=mode, attempts=self._client.max_attempts, error="search_failed")
        return self._executed_result(_render_search_results("tavily search", payload), payload, units=payload.billable_units, mode=mode, attempts=payload.attempts)


class LinkupSearchTool(PricedOperationTool):
    """Linkup search — standard vs deep depth selects the billing mode."""

    operation = "search"
    provider = "linkup"

    def spec(self) -> ToolSpec:
        # Declares the Linkup search tool with query and depth.
        return ToolSpec(
            name="linkup_search",
            description="Runs a Linkup web search returning sourced results or answers.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="depth", type="string", description="Search depth: 'standard' or 'deep'.", required=False, default="standard"),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one Linkup search per request at the standard/deep tier.
        mode = _mode_arg(call, "depth", ("standard", "deep"), "standard")
        return self._contract_result(f"linkup search: {call.arguments.get('query', '')}", units=1, mode=mode)


class ParallelSearchTool(PricedOperationTool):
    """Parallel search — per-result billing under a processor tier."""

    operation = "search"
    provider = "parallel"

    def spec(self) -> ToolSpec:
        # Declares the Parallel search tool with objective, processor, and result count.
        return ToolSpec(
            name="parallel_search",
            description="Runs a Parallel web search for an objective and returns matched results.",
            parameters=(
                ToolParameter(name="objective", type="string", description="Natural-language search objective.", required=True),
                ToolParameter(name="processor", type="string", description="Processor tier: 'turbo' or 'pro'.", required=False, default="turbo"),
                ToolParameter(name="max_results", type="int", description="Maximum results to return.", required=False, default=10),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs the objective through the injected ParallelClient, or prices a contract stub without one.
        objective = str(call.arguments.get("objective", ""))
        mode = _mode_arg(call, "processor", ("turbo", "pro"), "turbo")
        if self._client is None:
            return self._contract_result(f"parallel search: {objective}", units=_int_arg(call, "max_results", 10), mode=mode)
        try:
            payload = await self._client.search(objective, max_results=_int_arg(call, "max_results", 10), processor=mode)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("parallel search failed.", units=1, mode=mode, attempts=self._client.max_attempts, error="search_failed")
        return self._executed_result(_render_search_results("parallel search", payload), payload, units=payload.billable_units, mode=mode, attempts=payload.attempts)


class OpenAlexSearchTool(PricedOperationTool):
    """OpenAlex scholarly search — flat per-request billing."""

    operation = "search"
    provider = "openalex"

    def spec(self) -> ToolSpec:
        # Declares the OpenAlex works search tool with query and page size.
        return ToolSpec(
            name="openalex_search",
            description="Searches OpenAlex scholarly works and returns matching records.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="per_page", type="int", description="Results per page (max 200).", required=False, default=25),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one OpenAlex search call at the flat per-request rate.
        return self._contract_result(f"openalex search: {call.arguments.get('query', '')}", units=1)


class SemanticScholarSearchTool(PricedOperationTool):
    """Semantic Scholar paper search — free per-request operation."""

    operation = "search"
    provider = "semantic_scholar"

    def spec(self) -> ToolSpec:
        # Declares the Semantic Scholar paper search tool with query and limit.
        return ToolSpec(
            name="semantic_scholar_search",
            description="Searches Semantic Scholar papers and returns matching records.",
            parameters=(
                ToolParameter(name="query", type="string", description="The search query.", required=True),
                ToolParameter(name="limit", type="int", description="Maximum papers to return (max 100).", required=False, default=10),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one Semantic Scholar search call at the free rate.
        return self._contract_result(f"semantic_scholar search: {call.arguments.get('query', '')}", units=1)


__all__ = [
    "BraveSearchTool",
    "BrowserbaseSearchTool",
    "ExaSearchTool",
    "LinkupSearchTool",
    "OpenAlexSearchTool",
    "ParallelSearchTool",
    "SemanticScholarSearchTool",
    "TavilySearchTool",
]

# Priced Web Provider Tools

Vidbyte's built-in web tools use injected provider clients. The application owns API keys, provider plan selection, and tool registration; the SDK owns request normalization and usage accounting.

```python
from vidbyte.tools.builtins import ExaClient, ExaSearchTool

exa = ExaClient(api_key="exa-...")
search = ExaSearchTool(client=exa)
```

The same pattern is available for `BrowserbaseClient`, `TavilyClient`, and `ParallelClient`. Reuse one client per provider when connection pooling and shared retry policy matter.

## Provider surfaces

| Provider | Built-in tools |
| --- | --- |
| Browserbase | `browserbase_search`, `browserbase_fetch`, `browserbase_session`, `browserbase_context` |
| Exa | `exa_search`, `exa_contents`, `exa_answer`, `exa_webset`, `exa_monitor` |
| Tavily | `tavily_search`, `tavily_extract`, `tavily_map`, `tavily_crawl`, `tavily_research` |
| Parallel | `parallel_search`, `parallel_extract`, `parallel_chat`, `parallel_response`, `parallel_task`, `parallel_find_all`, `parallel_monitor` |

Async provider operations return a bounded result containing the provider task or resource ID. Polling and cancellation should be performed by an application-specific lifecycle adapter so a long-running research job can resume after process restart.

## Usage tracking and pricebook

The source of truth for SDK-computed cost is `vidbyte.lib.registries.operation_pricing.OPERATION_PRICING`. Provider responses may include credits or dollar estimates, but these are stored as reconciliation metadata and never override the configured pricebook.

```python
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.registries import OperationPricingRegistry

tracker = UsageTracker(operation_pricing=OperationPricingRegistry.default())
rollup = tracker.rollup()
print(rollup.operation_count, rollup.cost_usd, rollup.cost_complete)
```

Composed calls create multiple ledger records. For example, Exa Search can record a request, extra results, and page summaries separately. Tavily Crawl records mapping and extraction components. This preserves the provider billing basis without placing rate constants in tools.

Account plans can override the pricebook explicitly:

```python
from vidbyte.lib.registries import OperationPricing, OperationPricingRegistry

pricing = OperationPricingRegistry.default()
pricing.register("fetch", "browserbase", "default", OperationPricing(usd_per_unit=0.001))
```

If a provider endpoint has no reviewed tariff, the operation is still executable but its record has `cost_usd=None` and the rollup reports `cost_complete=False`.

## Safety defaults

- Set `max_results`, crawl `limit`, research model/processor, and response size bounds explicitly for production agent loops.
- Do not pass Browserbase context IDs or connection URLs to untrusted model prompts. Lifecycle renderers redact connection capabilities.
- Keep API keys in application configuration and pass them only to client constructors.
- Use a custom `RetryPolicy` for provider-specific rate limits; retry attempts are retained in usage metadata.

## Official references

- Browserbase pricing: https://www.browserbase.com/pricing
- Browserbase Search: https://docs.browserbase.com/platform/search/overview
- Browserbase Fetch: https://docs.browserbase.com/platform/fetch/overview
- Exa API pricing: https://exa.ai/pricing?tab=api
- Exa Search: https://exa.ai/docs/reference/search
- Exa Contents: https://exa.ai/docs/reference/contents-retrieval
- Tavily credits and pricing: https://docs.tavily.com/documentation/api-credits
- Tavily API overview: https://docs.tavily.com/documentation/api-reference/introduction
- Parallel pricing: https://docs.parallel.ai/getting-started/pricing
- Parallel Search: https://docs.parallel.ai/api-reference/search/search
- Parallel Extract: https://docs.parallel.ai/api-reference/extract/extract

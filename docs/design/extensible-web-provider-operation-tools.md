# Design: Extensible Web-Provider Operation Tools

## Original User Request

> `$talk look at the brave and firecrawl tools that we created inside of the vidbyte-sdk/ (in the tools folder), what are some other search/fetch providers that we can create just like these (other third party providers that provide this in thier api)`

> `$talk can you think through how to add browserbase, exa, tavily, and parallel (need to think about pricebook in lib folder, tool integration, and usage tracking in general), explain everything that we have to think about, also make sure to include small code snippets from descriptions (find api pricing in this request via web search AND everything that we can do with the apis)`

> `$design-doc-no-tests decide all of these things during implementation. Important thing to note is that the pricebook is the source of truth with pricing, we incorperate this addition to the pricebook into the sdk's usage tracking, and the tools are extensible with anything that you can do in the api's fo the providers. After implementing go over everything for a second time, and cross reference implementation with orignal task/intent`

## Repository Audit

### Current Architecture

The SDK already has the right initial seam for this feature:

1. `PricedOperationTool` gives a tool a stable `(operation, provider)` identity and places per-call usage metadata on `ToolResult`.
2. `search.py` and `fetch.py` expose pre-built tools. Brave and Firecrawl have executing clients; several other providers currently remain contract stubs.
3. `vidbyte/tools/builtins/operations/clients/_base.py` owns bounded JSON transport, API-key injection, retries, and attempt counts. Provider clients normalize vendor JSON into `SearchPayload` and `FetchPayload`.
4. `AgentRuntime._record_operation_usage` sends operation metadata to `UsageTracker` after tool execution.
5. `UsageTracker` records operation usage in the same run rollup as model-token usage.
6. `vidbyte/lib/registries/operation_pricing.py` is the pricebook and must remain the only source of SDK-computed operation cost.

The implementation will build on the existing client-injection model:

```python
client = ExaClient(api_key="...")
tool = ExaSearchTool(client=client)
```

No client will read a secret from an environment variable implicitly. Applications will construct clients, choose timeouts/retry limits, and inject them into tools. This keeps credentials out of tool schemas and makes tests, proxies, and multi-account deployments possible.

### Relevant Files

| Area | Existing path | Role in this change |
| --- | --- | --- |
| Tool identity/usage | `vidbyte/tools/builtins/operations/base.py` | Extend usage metadata from one tariff to a list of pricebook charge components and non-billable lifecycle calls. |
| Search/fetch tools | `vidbyte/tools/builtins/operations/search.py`, `fetch.py` | Replace provider stubs with executing Browserbase, Exa, Tavily, and Parallel tools and expose their provider-specific controls. |
| Provider clients | `vidbyte/tools/builtins/operations/clients/` | Add four credentialed clients and preserve Brave/Firecrawl behavior. |
| Normalized data | `vidbyte/lib/dataclasses/operations.py` | Carry normalized hits/pages, raw vendor data, provider request IDs, and pricebook charge dimensions. |
| Pricebook | `vidbyte/lib/registries/operation_pricing.py` | Add every supported billable meter and mode. This remains the billing authority. |
| Usage ledger | `vidbyte/agents/pricing/records.py`, `tracker.py` | Record each charge component, meter, retries, and provider-reported cost as audit data without allowing vendor-reported cost to override the pricebook. |
| Runtime | `vidbyte/agents/runtime.py` | Record all declared billable charges exactly once per provider attempt and skip explicitly non-billable polling/management calls. |
| Transport | `vidbyte/lib/http/transport.py` | Reuse bounded async JSON transport; add any missing response/header/request-id support needed by the clients. |
| Exports | `vidbyte/tools/builtins/operations/__init__.py`, `vidbyte/tools/builtins/__init__.py`, dataclass/client package exports | Make the tools discoverable without auto-instantiating provider clients. |

### Existing Conventions

- Python 3.11+, `pydantic` v2, and `httpx` are already available; no new runtime dependency is needed.
- Provider clients own vendor-specific request shapes and normalization. Tools should remain thin and model-facing.
- Provider failures become redacted `ToolResult.error` values. API keys, authorization headers, cookies, session connect URLs, and raw response bodies do not enter model-visible output or traces.
- `SearchHit`, `FetchedPage`, `SearchPayload`, and `FetchPayload` preserve a normalized shape while retaining bounded raw vendor mappings for application code.
- The built-in price table has explicit zero-cost entries for free operations. An operation that has no trustworthy pricebook entry is recorded with `cost_usd=None`, making `cost_complete=False` instead of silently reporting zero.
- Existing retry attempts are considered usage metadata. The new clients will preserve that behavior and will also expose request IDs for reconciliation.

### Observed Constraints

- Vendor pricing is plan-dependent, credit-based, dynamic, or composed of several meters. A single `fixed + per_unit` number is not enough for every endpoint.
- Some APIs are synchronous (`search`, `fetch`, `extract`); others are asynchronous (`research`, Exa agents/websets, Parallel Task/FindAll/Monitor workflows). Polling is not the same billable event as creating or executing the underlying job.
- Browserbase sessions expose capabilities beyond search/fetch and may produce browser-hour, proxy, identity, or agent charges that cannot be known at session creation time.
- The provider APIs evolve quickly. The SDK must expose supported API parameters without making vendor JSON the long-term SDK contract.
- This task uses the no-tests design workflow. No new test files are planned; implementation verification will use the repositoryâ€™s canonical CI stages, static checks, import/smoke checks, and the required second-pass review.

## Scope

### In Scope

- Add executing Browserbase, Exa, Tavily, and Parallel clients using the existing injected-client architecture.
- Add first-class search/fetch tools and provider-specific tools for the documented public API surfaces listed below.
- Make provider tools extensible by using typed endpoint adapters over a shared request/response/usage contract. Adding a new provider endpoint should not require changing runtime billing logic.
- Expand the pricebook to model composed charges, provider meters, plan/mode variants, dynamic credit units, fractional quantities such as browser hours, and explicit unknown pricing.
- Integrate all charge components into `UsageTracker`, `UsageRollup`, agent metadata, and existing cost-completeness behavior.
- Preserve provider request IDs, usage counters, task IDs, and bounded raw payloads for debugging/reconciliation without exposing secrets.
- Document construction, endpoint coverage, pricing assumptions, account-plan overrides, and safe usage controls.
- Re-run the original-intent checklist after implementation and cross-reference the resulting code against this document and the original request.

### Out of Scope

- Building a browser automation engine inside the SDK. Browserbase session tools may create, inspect, and stop sessions, but interactive Playwright/Puppeteer/Selenium/Stagehand control remains in the application that owns the session.
- Implementing provider web dashboards, billing-plan discovery, automatic plan selection, or automatic account-credit reconciliation.
- Silently falling back from one provider to another. Fallback policy belongs to the application/runtime orchestration layer and must create separate usage records for each provider actually called.
- Adding provider SDK dependencies. HTTP clients remain SDK-owned and injectable.
- Creating a new test suite under this no-tests workflow.

## Detailed Design

### Architecture

Use four layers:

```text
model tool call
      |
      v
provider endpoint tool  --->  provider client  --->  HttpTransport  ---> vendor API
      |                              |
      +--> normalized payload        +--> request id / usage / raw payload
      |
      v
pricebook charge components ---> UsageTracker ---> UsageRollup
```

`PricedOperationTool` will remain the compatibility base for the existing search/fetch classes. Add a small `ProviderApiTool` specialization for endpoints that are not naturally a search or fetch. Each endpoint class declares:

- a stable tool name and `ToolSpec`;
- `operation` and `provider` pricebook keys;
- the provider client method it calls;
- a provider mode and charge component mapping;
- whether the call is billable, asynchronous, or lifecycle-only;
- a bounded model-facing renderer and an application-facing typed/raw payload.

Avoid one catch-all tool such as `parallel_api(action, payload)`. It would make the tool schema unhelpful to models, make permissions too coarse, and allow unsupported endpoints to drift into the public contract. The extensibility point is a typed endpoint adapter, not an untyped escape hatch.

Provider API coverage:

| Provider | Search/fetch tools | Additional API tools covered by the adapter layer |
| --- | --- | --- |
| Browserbase | Search, Fetch | Browser session create/get/stop, context create/list/delete, and session metadata/recording/observability operations exposed by the REST API. A session tool returns a redacted session identifier and connection metadata only to the application payload, not the model. |
| Exa | Search, Contents | Answer, deep/deep-reasoning search modes, page summaries/highlights/images, Websets create/get/update/delete, Webset searches/items/enrichments, imports, monitors, and async status/webhook-friendly lifecycle operations. |
| Tavily | Search, Extract | Map, Crawl, Research create/status/stream, project header support, raw content/images/favicon controls, domain/path filters, output schema, and usage fields. |
| Parallel | Search, Extract | Chat, Responses, Task create/get/cancel/result, FindAll create/get/cancel/result, Monitor create/list/get/update/delete/run, enrichments, webhooks, and processor/mode selection. |

The endpoint list is generated from the official API references audited for this design. Unsupported or newly introduced vendor endpoints remain available through a custom application client until a typed adapter and pricebook entry are added.

### Data Flow

1. The application constructs a provider client with an API key, base URL override if needed, retry policy, timeout, response ceiling, and optional project/account metadata.
2. The application injects that client into one or more endpoint tools and registers the tools in `Tools`.
3. The model receives explicit parameters such as `query`, `num_results`, `search_depth`, `urls`, `processor`, `max_depth`, or `output_schema`.
4. The tool validates bounds before any network request. The client builds the vendor request, adds auth/project headers, and sends it through the shared bounded transport.
5. The client normalizes the provider response, preserving a bounded `raw` mapping, request/task IDs, provider usage counters, and a list of SDK pricebook charge dimensions.
6. The tool renders a compact result for the model and stores the typed payload plus usage metadata on the `ToolResult`.
7. `AgentRuntime` records one usage event per declared charge component and provider attempt. A non-billable poll or management operation is retained in tool metadata/tracing but does not create a paid operation record.
8. `UsageTracker` resolves each charge against the configured `OperationPricingRegistry`. The registryâ€™s pricebook math determines `cost_usd`; vendor-reported dollars are stored separately for reconciliation only.
9. The final `UsageRollup` combines model and operation costs. Any unknown tariff keeps `cost_complete=False` and is visible in the operation record rather than being coerced to zero.

Composed pricing is represented as multiple pricebook components. For example, an Exa search with 13 results and summaries can emit:

```python
charges = (
    Charge(operation="search", provider="exa", mode="search", meter="request", units=1),
    Charge(operation="search_extra_result", provider="exa", mode="search", meter="result", units=3),
    Charge(operation="content_summary", provider="exa", mode="summary", meter="page", units=13),
)
```

This keeps the pricebook authoritative without embedding vendor prices in tool code.

### Interfaces and Contracts

The shared provider client contract will support both simple and advanced endpoints:

```python
class WebOperationClient:
    async def request_json(...) -> tuple[Mapping[str, Any], int]: ...
    @property
    def provider(self) -> str: ...

class ProviderApiTool(PricedOperationTool):
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

Normalized payloads will gain optional fields rather than forcing every provider into one response shape:

```python
@dataclass(frozen=True, slots=True)
class ProviderOperationPayload:
    provider: str
    operation: str
    data: Mapping[str, Any]
    request_id: str | None = None
    async_id: str | None = None
    provider_usage: Mapping[str, Any] = field(default_factory=dict)
    provider_reported_cost_usd: float | None = None  # audit only
    charges: tuple[OperationCharge, ...] = ()
```

`OperationCharge` contains `operation`, `provider`, `mode`, `meter`, `units`, and `billable`. `units` becomes a finite non-negative number so browser hours, credit counts, page counts, result counts, and URL counts can be represented. Existing integer calls remain valid.

The tracker contract changes in one important way: `reported_cost_usd` can no longer override pricebook cost. It is renamed or preserved as an audit field such as `provider_reported_cost_usd`; `cost_usd` always comes from `OperationPricingRegistry.resolve(...).cost_usd(...)`. A custom registry supplied by the application is still authoritative for that run and is the supported mechanism for account-plan-specific rates.

Example provider request shapes captured by the clients:

```python
# Browserbase Search
await client.search(query="latest Python release", num_results=10)

# Exa Search with contents and structured output
await client.search(
    query="Python release notes",
    num_results=10,
    type="auto",
    contents={"text": {"verbosity": "compact"}, "highlights": {"maxCharacters": 1200}},
)

# Tavily Crawl: always pass a hard page limit
await client.crawl(url="https://docs.example.com", max_depth=2, limit=50, extract_depth="basic")

# Parallel Extract: up to 20 known URLs
await client.extract(urls=["https://example.com/a"], objective="return the pricing table")
```

Provider-specific parameter policy:

- Preserve vendor parameter names in the public SDK tool schema when they carry meaningful provider semantics (`search_depth`, `extract_depth`, `processor`, `max_age_hours`).
- Validate numeric limits locally and clamp only where the vendor documents a hard maximum. Invalid caller input should fail before a paid request.
- Use `Mapping[str, Any]` for genuinely extensible vendor fields such as Exa `output_schema` or Parallel `output_schema`, but validate that it is JSON-serializable and bounded.
- Keep endpoint-specific methods typed. A new API field is added to one provider client/tool, not to normalized cross-provider records unless it is genuinely common.

### State and Lifecycle

Synchronous calls complete in one tool invocation. Async APIs use explicit lifecycle tools or client methods:

```text
create/start -> return async_id -> get/status/result -> optional cancel
```

Creation/execution records the providerâ€™s billable operation. Status polling, webhook acknowledgment, and cancellation are non-billable unless the providerâ€™s official pricing says otherwise; those calls still expose request IDs and status metadata. A client will never busy-poll internally without a caller-configured timeout, interval, and maximum poll count.

Browserbase session IDs, context IDs, and connect URLs are stateful capabilities. The SDK will not persist them globally. The application passes them explicitly, and lifecycle tools will redact connect URLs from model output unless the tool is explicitly configured for application-only use.

### Error Handling

- Transport retries apply only to documented transient statuses and configured retry budgets. The result records attempts so the usage ledger cannot hide provider work.
- HTTP failures become provider-specific `ProviderRequestError`/`ProviderResponseError` values with a short redacted excerpt. Never include response bodies, auth headers, cookies, or connection URLs in model-facing errors.
- Partial batch results are represented explicitly: successful URLs/results remain available, failed items carry bounded per-item errors, and charge units follow the providerâ€™s documented successful-item billing rule.
- JSON shape changes fail closed with a normalized response error rather than returning misleading empty results.
- Async timeout returns the async ID and a resumable status, not a fabricated completed result.
- Unknown provider mode or endpoint pricing does not block the provider call; it records an unpriced operation and marks the run cost incomplete. This is safer than guessing or silently using another modeâ€™s tariff.

### Security and Privacy

- API keys are constructor-only secrets and must not be present in `ToolResult.output`, payload renderers, trace attributes, exception strings, or raw metadata exposed to models.
- Redaction covers `Authorization`, `X-API-Key`, Browserbase connect URLs, cookies, session tokens, signed URLs, proxy credentials, webhook secrets, and arbitrary fields whose names contain key/token/secret/password/auth/credential.
- URL inputs are user-controlled. The client layer must not add server-side fetches beyond the selected vendor endpoint, and error excerpts must not reflect sensitive query strings.
- Browserbase contexts may contain authenticated state; context/session tools require explicit permission and should return opaque IDs only.
- Raw vendor data is bounded by the existing response ceiling and should be application-visible only. Model renderers return selected title/URL/snippet/content fields with provider-configured character limits.
- Provider-specific project/account identifiers are non-secret but should be treated as trace metadata and scrubbed if they encode tenant information.

### Observability and Operations

Every provider operation should expose safe, structured metadata:

- provider, operation, mode, endpoint/tool name;
- request ID, async/task ID, HTTP status, attempts, latency, result/page counts;
- pricebook key, meter, units, pricebook version/as-of date, and computed cost;
- provider-reported credits/dollars as reconciliation metadata, never as SDK billing authority;
- redacted error category and retry outcome.

Add a pricebook refresh note to the implementation documentation. Provider prices will be updated by changing `OPERATION_PRICING`, its as-of date, and source links in one reviewed change. Plan-specific rates should be supplied through an `OperationPricingRegistry` override at application construction, not patched into individual tools.

### Compatibility and Migration

- Brave and Firecrawl tool names, constructors, normalized payload fields, and successful model-facing output remain compatible.
- Existing `PricedOperationTool(client=None)` contract stubs continue to work for applications that use the tools only for schema/catalog purposes.
- Existing `UsageTracker.record_operation(..., reported_cost_usd=...)` remains source-compatible during migration, but the argument is recorded as provider-reported audit data and cannot override the pricebook cost.
- Existing integer `units` remain valid; fractional units are added for meters such as browser hours.
- Existing operation records remain readable. New fields use defaults, and old single-charge metadata is normalized into a one-element charge list.
- No automatic provider fallback or credential discovery is introduced.

### Performance and Scaling

- Reuse one injected `HttpTransport`/client policy per provider rather than constructing a new transport per tool call where the caller needs connection pooling.
- Keep result counts, content lengths, crawl limits, and async polling bounds explicit in tool schemas. Defaults must be conservative enough for agent loops.
- Do not return full raw pages by default. Exa/Tavily/Parallel content tools expose targeted excerpts or bounded markdown, with an application payload for full bounded data.
- Batch APIs should use one provider request when the provider bills per batch, but the charge meter must follow the providerâ€™s successful-item rule.
- Browserbase session creation should not be used as a hidden implementation detail of search/fetch; separate session-hour usage would otherwise be impossible to attribute.
- Async result retrieval must be resumable by ID, so long-running research does not tie up an agent loop or leak repeated polling costs.

### Testing Strategy

No new tests will be created under this workflow. Verification will consist of:

- the repositoryâ€™s canonical source and package CI stages from a clean implementation worktree;
- import/export smoke checks for all new clients and tools;
- injected-transport request-shape checks run through existing CI mechanisms where available;
- manual contract checks for success, partial batch failure, transient retry, redacted errors, async lifecycle, unknown pricing, and pricebook-only cost calculation;
- a final self-critique that maps every original user intent to an implementation artifact and records any remaining limitation.

### Code Quality and Repository Hygiene

Implementation will follow existing Context Protocol headers, type annotations, frozen dataclasses, bounded output conventions, and package exports. Before implementation, create the isolated worktree from `main` and commit this design document first. Do not overwrite the unrelated dirty-worktree design documents already present in the current checkout.

## File Manifest

### Create

1. `vidbyte/tools/builtins/operations/clients/browserbase.py` â€” Browserbase Search, Fetch, and session/context/lifecycle client methods.
2. `vidbyte/tools/builtins/operations/clients/exa.py` â€” Exa Search, Contents, Answer, Websets, monitors, and async client methods.
3. `vidbyte/tools/builtins/operations/clients/tavily.py` â€” Tavily Search, Extract, Map, Crawl, Research, and status/stream methods.
4. `vidbyte/tools/builtins/operations/clients/parallel.py` â€” Parallel Search, Extract, Chat, Responses, Task, FindAll, Monitor, and lifecycle methods.
5. `vidbyte/tools/builtins/operations/api.py` â€” Shared endpoint-tool adapter for non-search/fetch operations, charge metadata, async lifecycle rendering, and bounded output.
6. `vidbyte/tools/builtins/operations/providers/__init__.py` â€” Provider-specific endpoint-tool exports.
7. `vidbyte/tools/builtins/operations/providers/browserbase.py` â€” Browserbase endpoint tools beyond the common Search/Fetch classes.
8. `vidbyte/tools/builtins/operations/providers/exa.py` â€” Exa Contents, Answer, Websets, monitor, and async tools.
9. `vidbyte/tools/builtins/operations/providers/tavily.py` â€” Tavily Map, Crawl, Research, and lifecycle tools.
10. `vidbyte/tools/builtins/operations/providers/parallel.py` â€” Parallel Chat, Responses, Task, FindAll, Monitor, and lifecycle tools.
11. `docs/usage/priced-web-provider-tools.md` â€” Construction examples, endpoint matrix, pricing assumptions, safety limits, and pricebook override guidance.

### Modify

1. `vidbyte/lib/registries/operation_pricing.py` â€” Add the four providers, all supported billable meters/modes, fractional/composed tariff support, source/as-of metadata, and explicit unknown-price behavior.
2. `vidbyte/lib/dataclasses/operations.py` â€” Add charge components and provider-operation payload fields while preserving Search/Fetch compatibility.
3. `vidbyte/agents/pricing/records.py` â€” Add meter, charge identity, provider-reported audit cost, and numeric units with backwards-compatible defaults.
4. `vidbyte/agents/pricing/tracker.py` â€” Price every charge strictly through the pricebook; record provider-reported values separately; support non-billable lifecycle metadata and composed charges.
5. `vidbyte/agents/runtime.py` â€” Consume charge lists, multiply pricebook charges by declared provider attempts, and skip non-billable lifecycle/polling events.
6. `vidbyte/tools/builtins/operations/base.py` â€” Support charge-list usage metadata, fractional units, provider-reported audit fields, and compatibility with existing single-charge results.
7. `vidbyte/tools/builtins/operations/search.py` â€” Implement Browserbase, Exa, Tavily, and Parallel calls and expose current provider parameters/modes.
8. `vidbyte/tools/builtins/operations/fetch.py` â€” Implement Browserbase, Exa Contents, Tavily Extract, and Parallel Extract calls with per-item billing dimensions.
9. `vidbyte/tools/builtins/operations/clients/_base.py` â€” Generalize the common client contract for provider-specific endpoints, request IDs, project headers, async responses, and safe payload bounds.
10. `vidbyte/tools/builtins/operations/clients/brave.py` and `firecrawl.py` â€” Adapt existing clients to the expanded common payload/charge contract without changing their public behavior.
11. `vidbyte/lib/dataclasses/__init__.py` and `vidbyte/lib/registries/__init__.py` â€” Export new payload/pricebook contracts.
12. `vidbyte/tools/builtins/operations/__init__.py`, `vidbyte/tools/builtins/__init__.py`, and `vidbyte/tools/builtins/operations/clients/__init__.py` â€” Export clients and endpoint tools.

### Delete

None planned. Existing Brave/Firecrawl files and the current pricebook registry will be extended in place.

## Risk Assessment

### Technical Risks

- Provider schemas and pricing can change independently, especially Exa agent/websets, Tavily Research, Browserbase plans, and Parallel processors.
- Composed and fractional pricing can produce incorrect totals if a tool emits the wrong meter or if retries are double-counted.
- A broad endpoint surface can create a large, repetitive adapter layer.
- Async APIs can outlive a process and require durable application state that the SDK does not own.

### Operational Risks

- Agent-generated crawl limits, result counts, browser sessions, or research processors can cause unexpectedly high provider spend.
- Provider rate limits and concurrency quotas differ materially: Browserbase Search/Fetch, Parallel Search, Tavily credits, and async processor limits all need explicit caller controls.
- A free-tier or included allowance cannot be inferred from a provider API response consistently, so SDK totals are estimates of the configured marginal tariff.

### Security Risks

- Browser sessions and contexts can grant access to authenticated websites.
- Raw content, signed links, proxy credentials, and provider task results may contain sensitive user or third-party data.
- Error/trace metadata can accidentally expose credentials or session connection URLs.

### Mitigations

- Make the pricebook the sole SDK billing authority and version it with dated official source links.
- Use charge components and meters instead of hidden vendor arithmetic in tool code.
- Require explicit limits and validate them before network calls; never auto-start a browser session for a search/fetch tool.
- Keep async lifecycle calls resumable and non-billable unless the pricebook explicitly says otherwise.
- Bound response bodies and model output; redact secrets and session capabilities at transport, error, result, and tracing boundaries.
- Use injected custom registries for plan-specific rates and mark missing rates as incomplete rather than guessing.
- Reconcile the implementation twice: once against this design during coding and again against the original user request after CI.

## Open Questions

These are implementation choices to resolve while coding, not approval blockers:

1. Whether to name the new generic base `ProviderApiTool` or `ApiOperationTool`, based on the existing tool naming conventions.
2. Whether Browserbase context/session management should be exported by default or marked application-only in the tool catalog because of its authenticated-state risk.
3. Whether the pricebook should represent fractional quantities directly or use a canonical integer meter such as milliseconds for browser hours. The implementation should choose the representation that preserves exact, readable rollups and backwards compatibility.
4. Which provider endpoints currently expose enough official pricing to receive a concrete tariff on day one. Unsupported/dynamic endpoints must still be callable but remain visibly unpriced until the pricebook has a reviewed entry.
5. Whether streaming methods should be surfaced as one final tool result or as an application callback/iterator. The first implementation should preserve final result semantics and keep streaming as an optional client method where it does not complicate runtime accounting.

## Approval

This design is ready for implementation approval. After explicit approval, implementation will begin in a fresh worktree based on `main`, with this document committed first. The implementation will then run canonical CI, perform the required second-pass cross-reference against the original request and this design, resolve critical/notable issues, and report the exact verification evidence.




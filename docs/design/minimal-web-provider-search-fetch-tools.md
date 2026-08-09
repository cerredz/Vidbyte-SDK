# Design Doc: Minimal Web-Provider Search/Fetch Tools

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-03
**Last Updated:** 2026-08-03

---

> **⚠️ EVERY PARALLEL RATE IN THIS DOCUMENT IS WRONG BY 1000× AND WAS REVERTED (2026-08-08).**
> Wherever this doc shows `0.000001` or `0.000005` for a Parallel search/extract rate —
> §"Verified pricing corrections", the numbered requirement about `("fetch", "parallel",
> "default")`, and the `OPERATION_PRICING` code blocks — the value is wrong. Parallel's
> pricing table column is headed **`Cost ($/1000)`**, so a value of `1` is $1 per 1,000
> units = **$0.001 per unit**, not "$0.001 per 1,000". This doc read the column value as
> dollars-per-unit and divided by 1,000 a second time, which also caused it to revert
> PR #325's correct values. Live rates: turbo `0.001`, pro/base/advanced `0.005`,
> additional results `0.001`, Extract `0.001`/URL. See
> `docs/design/operation-pricing-payg-corrections.md`. Everything in this doc that is not
> a Parallel rate — including the Tavily depth analysis — remains correct. Original text
> preserved below for history.

---

## 1. Overview

Four providers — Browserbase, Exa, Tavily, and Parallel — currently exist in the SDK only as priced *contract stubs*: their tool classes return `_contract_result(...)` and never call the vendor API. This change gives each of them a real executing client and a working search and/or fetch tool, built exactly like the existing `BraveClient` / `FirecrawlClient` pair, and expands `OPERATION_PRICING` with the researched rates for those providers' documented API surfaces. The usage-tracking contract — `OperationUsageRecord`, `UsageTracker.record_operation`, `AgentRuntime._record_operation_usage`, `PricedOperationTool`, and the `SearchPayload` / `FetchPayload` dataclasses — is not modified. Every new operation produces exactly one usage record per provider attempt, priced solely by the existing four-field `OperationPricing` tariff.

---

## 2. Goals & Non-Goals

### Goals

- Add executing `BrowserbaseClient`, `ExaClient`, `TavilyClient`, and `ParallelClient` following the `brave.py` / `firecrawl.py` shape.
- Replace the stub bodies of `ExaSearchTool`, `TavilySearchTool`, `ParallelSearchTool`, `TavilyExtractTool`, and `ParallelExtractTool` with real provider calls.
- Add `BrowserbaseSearchTool` and `BrowserbaseFetchTool`.
- Expand `OPERATION_PRICING` with researched, source-linked rates covering each provider's documented single-meter API products, and refresh `OPERATION_PRICING_AS_OF`.
- Fix the verified 1000× error in `("fetch", "parallel", "default")`.
- Keep the usage-tracking shape byte-for-byte unchanged.

### Non-Goals

- **Any product whose price requires two meters on one call.** Excluded: Tavily Crawl (map credits + extract credits), Parallel FindAll (fixed generator cost + per-match cost), and Exa Contents billed per content type. This is the explicit alteration requested for this PR.
- **Any product whose price is a dynamic range, not a tariff.** Excluded: Tavily Research (4–110 / 15–250 credits) and Exa Agent `auto` metered mode.
- **Any product whose meter is fractional.** Excluded: Browserbase browser-hours and proxy-GB, because `OperationPricing.cost_usd` rounds up to whole batches and would over-bill a partial unit.
- No changes to `records.py`, `tracker.py`, `runtime.py`, `operations/base.py`, `lib/dataclasses/operations.py`, `lib/http/transport.py`, or `clients/_base.py`.
- No `OperationCharge`, no charge lists, no `meter` field, no fractional `units`, no provider-reported-cost field.
- No new endpoint-adapter layer (`ProviderApiTool`), no `providers/` package, no SSE streaming, no async job lifecycle tools, no browser session/context management.
- No new test files (per the no-tests workflow). Existing CI gates are not waived.
- No new runtime dependencies.

---

## 3. Background & Context

### Why now

PR #325 attempted this feature and grew to +1968/−91 across 30 files. It reached for the full documented API surface of all four providers — Websets, Research, FindAll, Monitors, browser sessions — and those endpoints genuinely do bill on multiple meters per call. To carry that, it introduced an `OperationCharge` dataclass and threaded a charge *list* through `PricedOperationTool`, `AgentRuntime`, `UsageTracker`, and `OperationUsageRecord`, and demoted vendor-reported cost to an audit field. The requested scope was narrower: add search/fetch providers the way Brave and Firecrawl were added, and bolt them onto the pricing that already exists.

### Current state

`main` already contains the correct seam:

- `PricedOperationTool` (`operations/base.py`) carries `operation` / `provider` ClassVars and derives `mode` / `units` / `attempts` from `ToolResult.metadata["operation_usage"]`. Tools are stateless; the runtime prices from the result alone.
- `WebOperationClient` (`clients/_base.py`) owns bounded JSON transport, retry budget, attempt counting, and error normalization via `request_json(...) -> (payload, attempts)`.
- `BraveClient` and `FirecrawlClient` are the two reference implementations; both normalize vendor JSON into `SearchPayload` / `FetchPayload` and set `billable_units`.
- `OperationPricing(usd_fixed, usd_per_unit, included_units, unit_batch)` already models fixed-plus-per-unit tariffs with an allowance and batch rounding.

The stub tools (`ExaSearchTool`, `TavilySearchTool`, `ParallelSearchTool`, `TavilyExtractTool`, `ParallelExtractTool`) declare correct identities and specs but return `_contract_result(...)` without a network call. Browserbase has no presence at all.

### Verified pricing corrections

> **⚠️ CORRECTION (2026-08-08): claims 1 and 2 below are wrong and were reverted.**
> Parallel's pricing table column is headed **`Cost ($/1000)`**, so a value of `1` means
> $1 per 1,000 units = **$0.001 per unit** — not "$0.001 per 1,000". Both claims read the
> column value as dollars-per-unit and then divided by 1,000 a second time, which put all
> six Parallel search/extract entries 1000× *under* the published rate and incorrectly
> reverted PR #325's correct values. The rates were restored in
> `docs/design/operation-pricing-payg-corrections.md`: turbo `0.001`, pro/base/advanced
> `0.005`, additional results `0.001`, Extract `0.001` per URL. The paragraph on Tavily
> below is unaffected and remains correct. Original text preserved for history.

Provider pricing was re-researched against official sources on 2026-08-03. Two defects were confirmed:

1. **`("fetch", "parallel", "default")` is 1000× too high on `main`.** It reads `usd_per_unit=0.001`; Parallel publishes Extract at **$0.001 per 1,000 URLs**, so the per-URL rate is `0.000001`. This PR fixes it.
2. **PR #325's Parallel *search* rows are 1000× too high.** It changed them to `usd_fixed=0.005`; the published rate is $0.005 per 1,000 requests → `0.000005`. `main`'s existing `0.000001` (turbo) and `0.000005` (pro) rows are **correct** and are kept. This PR does not adopt #325's values.

PR #325 additionally flattened all Tavily search depths to one rate, losing advanced's documented 2-credit cost. `main`'s `basic=0.008` / `advanced=0.016` rows are correct and are kept.

### Constraints from the field guide

- *Priced Operation Execution* — every prebuilt search/fetch tool must keep supporting the injected-client seam: constructor stays `__init__(self, *, client=None)`, the SDK tool's spec / identity / normalization / usage metadata stay authoritative, and provider exceptions are redacted. No new required constructor parameters.
- *Local CI Verification* — run the source stage with `PYTHONPATH=$(pwd)` from the worktree, the package stage **without** it, and `git add -A` before semgrep so new files are actually scanned.
- *Declarative Config Resolution* — registries live in `vidbyte/lib/registries/`; `operation_pricing.py` already is one and is extended in place.
- Semgrep rule `no-untyped-mapping-fallback` forbids `def f(..., value: object|Any, ...)` followed by `if not isinstance(value, Mapping): return ...`. All normalizer parameters must be annotated `Mapping[str, Any]` explicitly, as `firecrawl.py` already does.

---

## 4. Requirements

### Functional Requirements

1. `BrowserbaseClient.search(query, *, num_results)` returns a `SearchPayload` with `billable_units=1`.
2. `BrowserbaseClient.fetch(url, *, proxies)` returns a `FetchPayload` with `billable_units=1`.
3. `ExaClient.search(query, *, num_results, search_type)` returns a `SearchPayload` whose `billable_units` is the returned hit count, floored at 1.
4. `TavilyClient.search(query, *, max_results, search_depth)` returns a `SearchPayload` with `billable_units=1`.
5. `TavilyClient.extract(urls, *, extract_depth)` returns a `FetchPayload` whose `billable_units` counts only successfully extracted pages.
6. `ParallelClient.search(objective, *, max_results, processor)` returns a `SearchPayload` whose `billable_units` is the returned result count, floored at 1.
7. `ParallelClient.extract(urls)` returns a `FetchPayload` whose `billable_units` is the returned page count.
8. Every new tool returns a priced `_contract_result(...)` unchanged when `self._client is None`.
9. Every new tool converts `ProviderRequestError` / `ProviderResponseError` into `_failed_result(...)` declaring `attempts=self._client.max_attempts`, with no vendor body, URL query string, or credential in the message.
10. Every new tool emits exactly one `operation_usage` annotation per call, in the existing `{operation, provider, mode, units, attempts}` shape.
11. `OPERATION_PRICING` gains rows for every in-scope single-meter product of the four providers; `("fetch", "parallel", "default")` is corrected to `0.000001`.
12. `OPERATION_PRICING_AS_OF` becomes `2026-08-03` and the source-link block names one official URL per provider.
13. No pricebook row is added for an excluded product (Section 2 Non-Goals); those resolve to `None` and keep `cost_complete=False` rather than being guessed.
14. All new clients and tools are exported through `clients/__init__.py`, `operations/__init__.py`, and `tools/builtins/__init__.py`.

### Non-Functional Requirements

- **Performance:** one HTTP request per tool call for every provider except Parallel Extract, which follows Firecrawl's per-URL loop only if the vendor requires it. Result counts are clamped to each vendor's documented maximum before the request.
- **Scalability:** transports are injectable so callers can share a pooled `HttpTransport`; no client constructs global state.
- **Security:** API keys are constructor-only and appear solely inside `_headers()`. No credential, `Authorization` value, or raw response body reaches `ToolResult.output`, `ToolResult.metadata["error"]`, or an exception message. Model-facing renders are bounded (titles, URLs, snippet ≤300 chars, page sizes).
- **Observability:** attempt counts flow from `HttpResponse.attempts` into `payload.attempts` into the usage record, so retried provider work stays visible and billable.
- **Reliability:** vendor JSON-shape violations raise `ProviderResponseError` rather than returning misleading empty results; a result entry without a usable URL is dropped, not fabricated.
- **Type safety:** every normalizer takes `Mapping[str, Any]`; no `object` / `Any` parameter is silently coerced (semgrep gate).

---

## 5. High-Level Design

The change is three horizontal slices with no vertical coupling between them.

**Slice 1 — clients.** Four new modules under `operations/clients/`, each a `WebOperationClient` subclass with exactly two public coroutines (one for Browserbase/Exa where only one operation is in scope). Each owns its vendor endpoint, its auth header, its request body construction with documented limit clamping, and its private normalizers that turn vendor JSON into `SearchHit` / `FetchedPage`. Each calls the inherited `request_json`, which already returns `(payload, attempts)`. No client gains a generic `api()` passthrough, a streaming method, or an async-job method.

**Slice 2 — tools.** `search.py` gains `BrowserbaseSearchTool` and has three stub bodies replaced; `fetch.py` gains `BrowserbaseFetchTool` and has two stub bodies replaced. Each replacement follows the `BraveSearchTool.execute` template exactly: read arguments, branch to `_contract_result` when no client, `await` the client inside `try`, map provider errors to `_failed_result`, and return `_executed_result(render, payload, units=payload.billable_units, mode=..., attempts=payload.attempts)`.

**Slice 3 — pricebook.** `OPERATION_PRICING` gains rows; the header comment gains the researched conversion basis and per-provider source links. `OperationPricing` itself, its field types, and `cost_usd`'s signature are untouched — every in-scope meter is an integer count (requests, results, pages, URLs), which the existing `int` contract already handles.

Data flow is identical to Brave's today:

```
model tool call
      |
      v
  <Provider>SearchTool.execute
      |
      +-- self._client is None? --> _contract_result (priced stub, no network)
      |
      v
  <Provider>Client.search  -->  WebOperationClient.request_json  -->  HttpTransport --> vendor API
      |                                                                    |
      |                                                              (attempts)
      v
  SearchPayload(hits, attempts, billable_units)
      |
      v
  _executed_result -> ToolResult.metadata["operation_usage"] = {operation, provider, mode, units, attempts}
      |
      v
  AgentRuntime._record_operation_usage  (UNCHANGED)
      |
      v
  UsageTracker.record_operation  (UNCHANGED)  -->  OperationPricingRegistry.resolve(op, provider, mode).cost_usd(units)
      |
      v
  UsageRollup
```

### Key design decisions

**D1 — The usage-tracking files are a hard zero-diff boundary.** Verified after implementation by `git diff --stat main..HEAD -- vidbyte/agents/ vidbyte/lib/dataclasses/ vidbyte/lib/http/ vidbyte/tools/builtins/operations/base.py vidbyte/tools/builtins/operations/clients/_base.py` returning empty. This is the acceptance criterion for the whole PR, not a nice-to-have.

**D2 — Scope is bounded by "one call, one meter."** A provider product enters this PR only if its published price is expressible as one `OperationPricing` tariff applied to one integer unit count. Everything else is deferred with an explicit reason. This is what keeps D1 achievable.

**D3 — Browserbase Fetch does not expose an `extract` switch.** Browserbase bills Fetch and Extract as distinct products at distinct rates. `PricedOperationTool.operation` is a ClassVar, so a tool that switched between them per call would need a per-call operation override in `base.py` — a D1 violation. Browserbase Extract is therefore deferred; its pricebook rows are added as reference data with no emitter.

**D4 — Exa gets search only; no contents/fetch tool.** Exa bills contents at $1 per 1,000 pages **per content type**, so a single call requesting text plus summaries owes two content-type charges. That is the "different usage tracking" case the user asked to defer. `ExaClient` therefore exposes `search` only, `ExaSearchTool` does not send a `contents` block, and no `ExaContentsTool` is created. The `("fetch", "exa", "default")` row is added as reference data with a comment stating it is valid for a single content type only and has no emitter.

**D5 — `units` for per-result providers comes from the returned hit count, floored at 1.** Exa and Parallel bill a fixed request price plus a per-result rate above a 10-result allowance, which `usd_fixed + usd_per_unit + included_units=10` expresses exactly. Using the *returned* count rather than the *requested* count bills what the vendor actually served. The floor of 1 exists because `AgentRuntime._billable_attempts` returns 0 when `units_used(...) < 1`, which would silently drop the request charge for a zero-result search.

---

## 6. Detailed Design

### 6.1 BrowserbaseClient

**File:** `vidbyte/tools/builtins/operations/clients/browserbase.py`
**Type:** New file

#### What it does

Issues Browserbase Search and Fetch requests and normalizes them into `SearchPayload` / `FetchPayload`.

#### Interface / API

```python
class BrowserbaseClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.browserbase.com/v1", timeout_seconds: float = 30.0, retry: RetryPolicy | None = None, max_response_bytes: int = 4_000_000, transport: HttpTransport | None = None) -> None: ...
    async def search(self, query: str, *, num_results: int = 10) -> SearchPayload: ...
    async def fetch(self, url: str, *, proxies: bool = False) -> FetchPayload: ...
    def _headers(self) -> dict[str, str]: ...
    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]: ...
    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None: ...
    def _page_from_payload(self, url: str, payload: Mapping[str, Any]) -> FetchedPage: ...
```

#### Logic / Algorithm

1. `search` clamps `num_results` to 1–25, POSTs `{"query", "numResults"}` to `search`, and normalizes results.
2. `fetch` POSTs `{"url", "proxies"}` to `fetch` and normalizes one page.
3. `_headers` returns `{"X-BB-API-Key": self._api_key, "Content-Type": "application/json"}`.
4. Both set `billable_units=1`; Browserbase bills per call, not per result.

#### Edge Cases & Error Handling

- Non-2xx and non-JSON responses already raise `ProviderRequestError` / `ProviderResponseError` from `_require_ok` / `_decode_object`.
- A missing `results` key returns `()`; a `results` value that is present but not a list raises `ProviderResponseError`, per the Section 4 reliability requirement that a shape violation fails closed rather than returning a misleading empty result set.
- A result item without a non-blank `url` is dropped.
- Empty fetch content raises `ProviderResponseError`, matching `firecrawl.py`'s empty-markdown rule.

---

### 6.2 ExaClient

**File:** `vidbyte/tools/builtins/operations/clients/exa.py`
**Type:** New file

#### What it does

Issues Exa Search requests and normalizes them into `SearchPayload`.

#### Interface / API

```python
class ExaClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.exa.ai", timeout_seconds: float = 30.0, retry: RetryPolicy | None = None, max_response_bytes: int = 4_000_000, transport: HttpTransport | None = None) -> None: ...
    async def search(self, query: str, *, num_results: int = 10, search_type: str = "auto") -> SearchPayload: ...
    def _headers(self) -> dict[str, str]: ...
    def _search_body(self, query: str, num_results: int, search_type: str) -> dict[str, object]: ...
    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]: ...
    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None: ...
```

#### Logic / Algorithm

1. `_search_body` clamps `num_results` to 1–100 and emits `{"query", "numResults", "type"}`. **It never emits a `contents` block** (D4).
2. POSTs to `search`, reads the `results` array.
3. `billable_units = max(1, len(hits))`.
4. `_hit_from_result` maps `title` / `url` / `text`-or-`snippet` / `publishedDate` and keeps the vendor record in `raw`.

#### Edge Cases & Error Handling

- `search_type` outside the documented set is clamped by the *tool*, not the client; the client forwards what it is given.
- Zero results still bill the fixed request price via the floor of 1 (D5).
- A missing or non-list `results` key returns `()`.

---

### 6.3 TavilyClient

**File:** `vidbyte/tools/builtins/operations/clients/tavily.py`
**Type:** New file

#### Interface / API

```python
class TavilyClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.tavily.com", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: HttpTransport | None = None) -> None: ...
    async def search(self, query: str, *, max_results: int = 5, search_depth: str = "basic") -> SearchPayload: ...
    async def extract(self, urls: Sequence[str], *, extract_depth: str = "basic") -> FetchPayload: ...
    def _headers(self) -> dict[str, str]: ...
    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]: ...
    def _pages_from_payload(self, payload: Mapping[str, Any]) -> tuple[FetchedPage, ...]: ...
```

#### Logic / Algorithm

1. `search` clamps `max_results` to 1–20, POSTs `{"query", "search_depth", "max_results"}` to `search`, sets `billable_units=1`.
2. `extract` POSTs `{"urls", "extract_depth"}` to `extract`, reads the `results` array, and builds one `FetchedPage` per entry that carries non-blank content.
3. `billable_units = len(pages)` — entries appearing in `failed_results`, or carrying an `error`, never become pages and therefore never bill. This satisfies Tavily's documented "per 5 *successful* URL extractions" rule together with the `unit_batch=5` tariff.

#### Edge Cases & Error Handling

- An extract call where every URL fails yields zero pages and `billable_units=0`; `_billable_attempts` then returns 0 and no charge is recorded, which is correct for Tavily.
- Snippets are truncated to 300 characters in the tool render, not in the payload.

---

### 6.4 ParallelClient

**File:** `vidbyte/tools/builtins/operations/clients/parallel.py`
**Type:** New file

#### Interface / API

```python
class ParallelClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.parallel.ai/v1beta", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: HttpTransport | None = None) -> None: ...
    async def search(self, objective: str, *, max_results: int = 10, processor: str = "turbo") -> SearchPayload: ...
    async def extract(self, urls: Sequence[str]) -> FetchPayload: ...
    def _headers(self) -> dict[str, str]: ...
    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]: ...
    def _pages_from_payload(self, payload: Mapping[str, Any]) -> tuple[FetchedPage, ...]: ...
```

#### Logic / Algorithm

1. `search` clamps `max_results` to 1–40, POSTs `{"objective", "processor", "max_results"}` to `search`, sets `billable_units = max(1, len(hits))`.
2. `extract` clamps the URL list to 20 entries (Parallel's documented batch maximum), POSTs `{"urls"}` to `extract`, sets `billable_units = len(pages)`.
3. `_headers` returns `{"x-api-key": self._api_key, "Content-Type": "application/json"}`.

#### Edge Cases & Error Handling

- A URL list longer than 20 is truncated before the request rather than sent and rejected; the tool render reports the page count actually returned.
- An empty URL list is rejected by the tool before the client is called.

---

### 6.5 Search tools

**File:** `vidbyte/tools/builtins/operations/search.py`
**Type:** Modified

#### What it does

Adds `BrowserbaseSearchTool`; replaces the stub `execute` bodies of `ExaSearchTool`, `TavilySearchTool`, and `ParallelSearchTool`.

#### Interface / API

```python
class BrowserbaseSearchTool(PricedOperationTool):
    operation = "search"
    provider = "browserbase"
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _render(self, payload: SearchPayload) -> str: ...
```

`ExaSearchTool.spec` changes its `type` parameter description and default, from `'standard' | 'agentic'` (default `standard`) to the documented `auto | fast | deep-lite | deep | deep-reasoning` (default `auto`), and drops "with contents" from the tool description because the client no longer requests a contents block (D4). Its tool name, other parameters, `operation`, and `provider` are unchanged. `TavilySearchTool.spec` and `ParallelSearchTool.spec` are unchanged.

A module-level `_render_search_results(label, payload)` helper carries the render shared by all five search tools. `BraveSearchTool._render` delegates to it, producing byte-identical output to its current inline implementation.

#### Logic / Algorithm

Every `execute` follows one template:

1. Read and coerce arguments through the existing `_int_arg` / `_mode_arg` helpers.
2. `if self._client is None: return self._contract_result(summary, units=..., mode=...)`.
3. `try: payload = await self._client.<method>(...)`.
4. `except (ProviderRequestError, ProviderResponseError): return self._failed_result(msg, units=..., mode=..., attempts=self._client.max_attempts, error="search_failed")`.
5. `return self._executed_result(self._render(payload), payload, units=payload.billable_units, mode=mode, attempts=payload.attempts)`.

Modes per tool: Browserbase `"default"`; Exa one of `auto | fast | deep-lite | deep | deep-reasoning`; Tavily `basic | advanced`; Parallel `turbo | pro`.

#### Edge Cases & Error Handling

- An out-of-range or wrong-typed `type` / `search_depth` / `processor` clamps to the tool's default via `_mode_arg`, so an invalid mode can never resolve to a missing tariff.
- A blank query is forwarded; the provider's own validation error surfaces as a redacted `_failed_result`.
- Renders reuse the existing Brave format: a numbered `title — url` list with an indented snippet capped at 300 characters, and a `no results` line when `hits` is empty.

---

### 6.6 Fetch tools

**File:** `vidbyte/tools/builtins/operations/fetch.py`
**Type:** Modified

#### What it does

Adds `BrowserbaseFetchTool`; replaces the stub `execute` bodies of `TavilyExtractTool` and `ParallelExtractTool`.

#### Interface / API

```python
class BrowserbaseFetchTool(PricedOperationTool):
    operation = "fetch"
    provider = "browserbase"
    def spec(self) -> ToolSpec: ...   # url: string (required), proxies: bool (optional, default False)
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _render(self, payload: FetchPayload) -> str: ...
```

`TavilyExtractTool.spec` and `ParallelExtractTool.spec` are unchanged apart from noting Parallel's 20-URL batch maximum in the `urls` description.

A module-level `_render_fetched_pages(label, payload)` helper carries the render shared by all four page-fetch tools. `FirecrawlFetchTool._render` delegates to it, producing byte-identical output. The `_urls_count` helper is removed: both of its callers now resolve concrete URLs through `_url_list`, leaving it dead.

#### Logic / Algorithm

1. `BrowserbaseFetchTool` reads `url`, sets `mode = "proxy" if call.arguments.get("proxies") is True else "default"`, and follows the standard template with `units=1`.
2. `TavilyExtractTool` and `ParallelExtractTool` resolve URLs through the existing `_url_list(call)` helper, return `_failed_result(..., units=0, attempts=0, error="missing_url")` when it is empty, then follow the standard template with `units=payload.billable_units`.
3. Renders reuse Firecrawl's format: one `index. final_url (N chars)` line per page.

#### Edge Cases & Error Handling

- Empty or non-list `urls` is caught before any network call, mirroring `FirecrawlFetchTool`.
- A partial batch is not an error: successful pages bill, failed URLs do not appear and do not bill.
- `units=0` on a total failure means `_billable_attempts` returns 0, so nothing is recorded. This is existing runtime behavior and is intentional.

---

### 6.7 Operation pricebook

**File:** `vidbyte/lib/registries/operation_pricing.py`
**Type:** Modified

#### What it does

Adds rows for the four providers' in-scope single-meter products, corrects one verified rate error, and refreshes the as-of date and source links. `OperationPricing`, `cost_usd`, and `OperationPricingRegistry` are **not** modified.

#### Interface / API

```python
OPERATION_PRICING_AS_OF: str = "2026-08-03"

# ── added: browserbase ──
("search",  "browserbase", "default"): OperationPricing(usd_fixed=0.007),
("fetch",   "browserbase", "default"): OperationPricing(usd_per_unit=0.001),
("fetch",   "browserbase", "proxy"):   OperationPricing(usd_per_unit=0.004),
("extract", "browserbase", "default"): OperationPricing(usd_per_unit=0.004),   # reference; no emitter (D3)
("extract", "browserbase", "proxy"):   OperationPricing(usd_per_unit=0.007),   # reference; no emitter (D3)

# ── added: exa ──
("search", "exa", "auto"):            OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
("search", "exa", "fast"):            OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
("search", "exa", "deep-lite"):       OperationPricing(usd_fixed=0.012, usd_per_unit=0.001, included_units=10),
("search", "exa", "deep"):            OperationPricing(usd_fixed=0.012, usd_per_unit=0.001, included_units=10),
("search", "exa", "deep-reasoning"):  OperationPricing(usd_fixed=0.015, usd_per_unit=0.001, included_units=10),
("fetch",  "exa", "default"):         OperationPricing(usd_per_unit=0.001),   # reference; single content type only, no emitter (D4)
("answer", "exa", "default"):         OperationPricing(usd_fixed=0.005),
("monitor","exa", "default"):         OperationPricing(usd_fixed=0.015),
("agent",  "exa", "minimal"):         OperationPricing(usd_fixed=0.012),
("agent",  "exa", "low"):             OperationPricing(usd_fixed=0.025),
("agent",  "exa", "medium"):          OperationPricing(usd_fixed=0.10),
("agent",  "exa", "high"):            OperationPricing(usd_fixed=0.50),
("agent",  "exa", "xhigh"):           OperationPricing(usd_fixed=1.00),

# ── added: tavily ──
("map", "tavily", "default"):      OperationPricing(usd_per_unit=0.008, unit_batch=10),
("map", "tavily", "instructions"): OperationPricing(usd_per_unit=0.016, unit_batch=10),

# ── added: parallel ──
("search",  "parallel", "base"):     OperationPricing(usd_fixed=0.000005, usd_per_unit=0.000001, included_units=10),
("search",  "parallel", "advanced"): OperationPricing(usd_fixed=0.000005, usd_per_unit=0.000001, included_units=10),
("chat",    "parallel", "speed"):    OperationPricing(usd_fixed=0.005),
("chat",    "parallel", "lite"):     OperationPricing(usd_fixed=0.005),
("chat",    "parallel", "base"):     OperationPricing(usd_fixed=0.010),
("chat",    "parallel", "core"):     OperationPricing(usd_fixed=0.025),
("response","parallel", "low"):      OperationPricing(usd_fixed=0.010),
("response","parallel", "medium"):   OperationPricing(usd_fixed=0.050),
("response","parallel", "high"):     OperationPricing(usd_fixed=0.250),
("task",    "parallel", "lite"):     OperationPricing(usd_fixed=0.005),
("task",    "parallel", "base"):     OperationPricing(usd_fixed=0.010),
("task",    "parallel", "core"):     OperationPricing(usd_fixed=0.025),
("task",    "parallel", "core2x"):   OperationPricing(usd_fixed=0.050),
("task",    "parallel", "pro"):      OperationPricing(usd_fixed=0.100),
("task",    "parallel", "ultra"):    OperationPricing(usd_fixed=0.300),
("task",    "parallel", "ultra2x"):  OperationPricing(usd_fixed=0.600),
("task",    "parallel", "ultra4x"):  OperationPricing(usd_fixed=1.200),
("task",    "parallel", "ultra8x"):  OperationPricing(usd_fixed=2.400),
("monitor", "parallel", "lite"):     OperationPricing(usd_per_unit=0.003),
("monitor", "parallel", "base"):     OperationPricing(usd_per_unit=0.010),

# ── corrected ──
("fetch", "parallel", "default"): OperationPricing(usd_per_unit=0.000001),   # was 0.001 — $0.001 per 1,000 URLs
```

#### Logic / Algorithm

1. Rows are appended into the existing `search` / `fetch` comment sections, with new `# ── other provider APIs ──` grouping for `answer` / `agent` / `chat` / `response` / `task` / `monitor` / `map`.
2. The header comment records the conversion basis: published pay-as-you-go / on-demand overage rates, Tavily at PAYG $0.008/credit, Browserbase at Developer-plan overage, with plan-specific rates left to an `OperationPricingRegistry` override.
3. The header comment gains an explicit exclusions block naming Tavily Crawl, Tavily Research, Parallel FindAll, Exa Agent `auto`, Browserbase browser-hours, and Browserbase proxy-GB, each with its reason.
4. Source links are updated to the URLs verified on 2026-08-03.

#### Edge Cases & Error Handling

- Rows marked *reference; no emitter* are inert until a future tool records against them; they neither change existing behavior nor are reachable from this PR's code.
- Excluded products resolve to `None` through `OperationPricingRegistry.resolve`, which `UsageTracker` already records as `cost_usd=None`, keeping `cost_complete=False`.
- Existing `exa` `standard` / `agentic` and `parallel` `turbo` / `pro` rows are retained unchanged so any caller pinned to those modes keeps resolving.

---

### 6.8 Package exports

**Files:** `vidbyte/tools/builtins/operations/clients/__init__.py`, `vidbyte/tools/builtins/operations/__init__.py`, `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

#### What it does

Re-exports the four clients and the two new tool classes, keeping each `__all__` alphabetically sorted as the files already are.

#### Logic / Algorithm

1. `clients/__init__.py` adds `BrowserbaseClient`, `ExaClient`, `ParallelClient`, `TavilyClient`.
2. `operations/__init__.py` adds those four clients plus `BrowserbaseFetchTool` and `BrowserbaseSearchTool`.
3. `tools/builtins/__init__.py` adds `BrowserbaseFetchTool` and `BrowserbaseSearchTool` to its existing operations import block and `__all__`.
4. Each file's Context Protocol header Architecture/Description lines are updated to name the new providers.

#### Edge Cases & Error Handling

- No module instantiates a client at import time, so a missing API key can never break `import vidbyte`.
- `vidbyte/lib/registries/__init__.py` is deliberately **not** touched: it does not export the operation-pricing symbols today, and leaving it alone avoids the export-list conflict that PR #325 hit.

---

## 7. Data Model Changes

N/A — no schema, dataclass, or persisted-record change. `SearchPayload`, `FetchPayload`, `SearchHit`, `FetchedPage`, and `OperationUsageRecord` are used exactly as they exist on `main`. This is the D1 invariant.

---

## 8. API Changes

No HTTP API is exposed by this SDK. The model-facing tool schemas change as follows.

### 8.1 `browserbase_search`

**Change type:** New

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | The search query. |
| `num_results` | int | no | 10 | Results to return (max 25). |

### 8.2 `browserbase_fetch`

**Change type:** New

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | yes | — | The page URL to fetch. |
| `proxies` | bool | no | false | Route through Browserbase proxies; selects the higher-priced mode. |

### 8.3 `exa_search`

**Change type:** Modified

The `type` parameter's allowed values change from `standard | agentic` to `auto | fast | deep-lite | deep | deep-reasoning`, and its default from `standard` to `auto`. `query` and `num_results` are unchanged. The pricebook retains `standard` and `agentic` rows, so a caller passing the old values still resolves to a tariff even though `_mode_arg` now clamps them to `auto`.

### 8.4 `tavily_search`, `tavily_extract`, `parallel_search`, `parallel_extract`

**Change type:** Modified behavior, unchanged schema

Parameters are identical. The tools now perform a real provider request when a client is injected, instead of always returning a contract stub.

**Error cases (all tools):**

| Condition | Result |
|---|---|
| No client injected | `ToolResult.success` contract stub, priced, no network call |
| Missing/empty `urls` | `ToolResult.error`, `units=0`, `attempts=0`, `error="missing_url"` |
| Provider non-2xx or transport failure | `ToolResult.error`, `attempts=client.max_attempts`, `error="search_failed"` / `"fetch_failed"` |
| Provider non-JSON or wrong-shape body | Same as above; no vendor body in the message |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/minimal-web-provider-search-fetch-tools.md` | This design doc; first commit on the branch |
| CREATE | `vidbyte/tools/builtins/operations/clients/browserbase.py` | Browserbase Search + Fetch client |
| CREATE | `vidbyte/tools/builtins/operations/clients/exa.py` | Exa Search client |
| CREATE | `vidbyte/tools/builtins/operations/clients/tavily.py` | Tavily Search + Extract client |
| CREATE | `vidbyte/tools/builtins/operations/clients/parallel.py` | Parallel Search + Extract client |
| MODIFY | `vidbyte/tools/builtins/operations/search.py` | Add `BrowserbaseSearchTool`; execute Exa/Tavily/Parallel |
| MODIFY | `vidbyte/tools/builtins/operations/fetch.py` | Add `BrowserbaseFetchTool`; execute Tavily/Parallel |
| MODIFY | `vidbyte/lib/registries/operation_pricing.py` | New rows, corrected Parallel fetch rate, refreshed as-of + sources |
| MODIFY | `vidbyte/tools/builtins/operations/clients/__init__.py` | Export four clients |
| MODIFY | `vidbyte/tools/builtins/operations/__init__.py` | Export four clients and two new tools |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export two new tools |

**Totals:** 5 created (1 doc, 4 code), 6 modified, 0 deleted.

**Explicitly NOT modified** (the D1 invariant): `vidbyte/agents/pricing/records.py`, `vidbyte/agents/pricing/tracker.py`, `vidbyte/agents/runtime.py`, `vidbyte/tools/builtins/operations/base.py`, `vidbyte/tools/builtins/operations/clients/_base.py`, `vidbyte/lib/dataclasses/operations.py`, `vidbyte/lib/http/transport.py`, `vidbyte/lib/registries/__init__.py`.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `httpx` | `>=0.27` (already a project dependency) | HTTP transport via existing `HttpTransport` | None; no version change |
| Browserbase API | `https://api.browserbase.com/v1` | Search, Fetch | Response shape unverified against a live key; normalizers fail closed |
| Exa API | `https://api.exa.ai` | Search | Same |
| Tavily API | `https://api.tavily.com` | Search, Extract | Same |
| Parallel API | `https://api.parallel.ai/v1beta` | Search, Extract | Beta path may move; `base_url` is constructor-overridable |

No new package is added to `pyproject.toml`.

Pricing sources verified 2026-08-03:
- Browserbase — https://www.browserbase.com/pricing, https://www.browserbase.com/blog/fetch-api
- Exa — https://exa.ai/pricing
- Tavily — https://docs.tavily.com/documentation/api-credits
- Parallel — https://docs.parallel.ai/getting-started/pricing

---

## 11. Rollout & Deployment

- **Feature flags:** none. New tools are opt-in by construction — nothing registers them automatically, and each is inert without an injected client.
- **Breaking changes:** none to the usage-tracking contract. Two behavioral changes worth calling out in the PR body:
  1. `exa_search`, `tavily_search`, `parallel_search`, `tavily_extract`, and `parallel_extract` previously *never* made a network call. Any caller that injected no client sees identical behavior; a caller that injects one now incurs real provider cost.
  2. `exa_search`'s `type` parameter no longer accepts `standard` / `agentic` as distinct modes; both clamp to `auto`. The pricebook rows are retained so historical records still resolve.
- **Deployment order:** single package; no coordination required.
- **Rollback:** revert the PR. No migration, no persisted state, no config change.

---

## 12. Open Questions

- [ ] Should `("fetch", "exa", "default")` and the two `("extract", "browserbase", …)` rows ship at all, given no tool emits them in this PR? They are inert reference data and make the follow-up PR tools-only, but an unemitted row cannot be verified by exercising it. Default: ship them with an explicit `# reference; no emitter` comment.
- [ ] Tavily documents `fast` and `ultra-fast` as `search_depth` values but does not publish their credit cost. Default: omit the rows and leave those depths out of `_mode_arg`'s allowed set, so they clamp to `basic` rather than resolving to a guessed tariff.
- [ ] Parallel's search processor names in the tool schema are `turbo` / `pro` (from `main`), while the pricing page names Turbo and Basic/Advanced. Default: keep `turbo` / `pro` in the schema for compatibility, add `base` / `advanced` pricebook rows at the same verified rate, and document the mapping in the header comment.
- [ ] Provider response field names are taken from published API references, not from live calls against a funded key. If a normalizer proves wrong in production it fails closed (`ProviderResponseError`, or zero hits) rather than mis-billing. Confirm this is acceptable for a first cut.

---

## 13. Alternatives Considered

### Alternative 1: Adopt PR #325 as-is

- **What:** Merge the existing branch with `OperationCharge`, the `ProviderApiTool` adapter layer, the `providers/` package, and full endpoint coverage.
- **Why rejected:** It changes the usage-tracking shape in five files to support endpoints outside the request, carries two verified 1000× pricing errors in the Parallel search rows, loses Tavily's advanced-depth 2× rate, multiplies response-derived charge units by retry attempts, and conflicts with `main`. The user explicitly scoped this PR to search/fetch on the existing tracking.

### Alternative 2: Keep #325's charge list but ship only search/fetch tools

- **What:** Land `OperationCharge` and the tracker/runtime changes now, use them for a small tool set, and add endpoints later.
- **Why rejected:** It pays the full shape-change cost with none of the benefit — every in-scope search/fetch tariff is expressible in the existing four-field `OperationPricing`, as six of the eight required rows on `main` already demonstrate. Migrating the record shape should be driven by a product that needs it.

### Alternative 3: Ship `ExaContentsTool` with `units = pages × content_types`

- **What:** Add an Exa fetch tool that multiplies the page count by the number of requested content types into a single record.
- **Why rejected:** Arithmetically correct while every content type shares the $1/1k rate, but it hides a per-meter calculation inside a client and breaks the moment Exa prices summaries differently from text. The user asked to defer exactly this case. Deferred to a follow-up that can decide the representation deliberately.

### Alternative 4: One `browserbase_fetch` tool with an `extract` switch

- **What:** A single tool that selects Browserbase Fetch or Extract per call.
- **Why rejected:** `PricedOperationTool.operation` is a ClassVar, so per-call operation selection requires a per-call override in `base.py` — a D1 violation. Two separate tools would be the correct shape; Extract is deferred to keep this PR minimal.

### Alternative 5: Expose an `options: object` passthrough on every tool

- **What:** Let callers forward arbitrary documented vendor fields, as PR #325 does.
- **Why rejected:** An untyped bag makes the tool schema unhelpful to a model, lets unsupported and differently-priced vendor features reach a priced call path without a tariff, and is the same escape hatch #325's own design doc rejected at the endpoint level. Typed parameters can be added one line at a time; a passthrough cannot be withdrawn once models depend on it.

---

## 14. Verification Plan

The repository's canonical CI command, recorded per the workflow:

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

From the implementation worktree, per the field guide's *Local CI Verification*:

```bash
PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source   # diagnostic
python scripts/run_ci.py --stage package                    # diagnostic, no PYTHONPATH
git add -A && semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte
python scripts/run_ci.py                                    # full gate before push
```

Feature-specific checks beyond CI:

1. **D1 invariant:** `git diff --stat main..HEAD -- vidbyte/agents/ vidbyte/lib/dataclasses/ vidbyte/lib/http/ vidbyte/tools/builtins/operations/base.py vidbyte/tools/builtins/operations/clients/_base.py` must print nothing.
2. **Import smoke:** `python -c "from vidbyte.tools.builtins import BrowserbaseSearchTool, BrowserbaseFetchTool"` and the same for all four clients from `vidbyte.tools.builtins.operations`.
3. **Contract-stub parity:** every new and modified tool constructed with `client=None` returns a `success` result carrying an `operation_usage` annotation.
4. **Pricebook resolution:** every `(operation, provider, mode)` triple a tool can emit resolves to a non-`None` tariff; every excluded product resolves to `None`.
5. **Redaction:** no new module's `_failed_result` message or `ToolResult` metadata contains an API key, `Authorization` header, URL query string, or vendor response body.

No new test files are created under this workflow.

---

END OF DESIGN DOC

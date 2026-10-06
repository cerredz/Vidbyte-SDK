# Design Doc: Agent Operation Pricing — Search & Fetch Usage Tracking

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-24
**Last Updated:** 2026-07-24

---

## 1. Overview

Adds a second, per-*operation* pricing axis (web **search** and **fetch**) to the agent's existing usage tracking. Where PR #304 priced model **token** usage `(provider, model) → per-million rates`, this feature prices tool **operations** `(operation, provider, mode) → per-unit rates`, so an agent that calls a Brave search or a Firecrawl scrape accrues a USD cost the same way a model call does. Both axes live in the one `UsageTracker` the agent already owns, so `agent.get_cost_usd()`, `usage_rollup`, `on_usage`, and `ctx.model_usage` transparently include tool spend. A small library of first-class **priced-contract tools** in `vidbyte/tools/builtins/operations/` carries the `(operation, provider, mode, units)` signal; the runtime detects them by type and records each call.

---

## 2. Goals & Non-Goals

### Goals
- Add an `OperationPricing` rate record and an `OperationPricingRegistry` mirroring the shape and conventions of `ModelPricing` / `ModelPricingRegistry`.
- Populate a verified `OPERATION_PRICING` table for all 12 `(operation, provider)` pairs, keyed by `(operation, provider, mode)`, capturing units, depth/mode tiers, two-part tariffs, and per-batch billing.
- Extend `UsageTracker` with `record_operation(...)`, an internal operations ledger, and a combined `UsageRollup` that spans tokens + operations without breaking token totals.
- Prefer provider-reported cost when a provider returns one (Exa `costDollars`, Tavily/Parallel `usage`), exactly as the token side prefers OpenRouter's `usage.cost`.
- Ship pre-built priced-contract tools (7 search + 5 fetch) in the tooling layer, each declaring its `(operation, provider)` and deriving `mode`/`units`/`reported_cost` purely from its call and result.
- Wire the runtime to record an operation for any `PricedOperationTool` after a successful execution, with no change to the agent public API.

### Non-Goals
- **No live provider API clients.** The pre-built tools ship as priced-contract tools: correct spec/params and a deterministic result whose metadata carries the billing signal. Authenticated HTTP clients are a follow-up PR.
- No new test files (per the no-tests workflow); existing CI must stay green.
- No pricing for out-of-scope sub-features (Firecrawl JSON/stealth multipliers beyond a `mode`, Exa multi-content-type billing, Parallel Task API deep-research processors).
- No changes to the token pricing axis (`ModelPricing`, `PROVIDER_PRICING`, provider usage classes).
- No new middleware, budget surface, or persistence.

---

## 3. Background & Context

PR #304 (`feat/agent-usage-pricing`, merged to `main` as `661a944`) delivered per-provider token usage classes, a `ModelPricingRegistry`, a `UsageTracker` fed once per model call in the runtime loop (`runtime.py:383`), and an immutable `UsageRollup` surfaced on `AgentMessage.metadata["usage_rollup"]` and `BaseAgent.get_usage()` / `get_cost_usd()`.

Agents increasingly perform **web search and fetch** through providers (Brave, Exa, Tavily, Linkup, Parallel, OpenAlex, Semantic Scholar for search; Firecrawl, Parallel, Tavily, Linkup, direct HTTP for fetch). These are billed per operation, not per token, and their real pricing is multi-dimensional — verified against each provider's docs on 2026-07-24:

| Op | Provider | Real pricing shape |
|---|---|---|
| search | brave | $0.005/req flat (Search endpoint) |
| search | exa | $0.007 base for first 10 results + $0.001/result beyond 10; agentic $0.012; returns `costDollars.total` |
| search | tavily | credits: basic 1cr, advanced 2cr @ $0.008/cr PAYG; returns `usage` |
| search | linkup | standard $0.005 vs deep $0.05 |
| search | parallel | turbo $0.001/1k req + $0.001/1k results; basic/pro $0.005/1k; returns `usage[]` |
| search | openalex | $0.001/search call ($1/day free allowance) |
| search | semantic_scholar | free |
| fetch | firecrawl | 1 credit/page @ $0.00083/cr (Standard); features multiply |
| fetch | parallel | $0.001/URL (Extract API); returns `usage[]` |
| fetch | tavily | basic 1cr / 5 URLs, advanced 2cr / 5 URLs; returns `usage` |
| fetch | linkup | no-JS $0.001/page vs JS $0.005/page |
| fetch | direct_http | free (our `sources/fetches/http.py`) |

Three billing dimensions the token model does not have: (1) **units** (10 pages ≠ 1 page), (2) **mode/depth tiers** (often order-of-magnitude), (3) **two-part tariffs** (fixed + per-unit). Credit-based providers (Tavily, Firecrawl) fold a plan-dependent credit→USD rate that the SDK cannot know at call time, so their cost is an estimate at a documented reference plan — the same modeling decision #304 made for MiniMax's baked-in promo rate.

Constraint: `ModelProvider` is the enum of LLM providers; search/fetch providers are **not** LLM providers and must not be jammed into it. The operation axis uses its own string key space.

---

## 4. Requirements

### Functional Requirements
1. `OperationPricingRegistry.default().resolve("search", "brave")` returns non-None pricing; `resolve` accepts an optional `mode` (default `"default"`) and returns exact or `(operation, provider, "default")` fallback, else `None`.
2. `OperationPricing.cost_usd(units)` computes `usd_fixed + usd_per_unit * ceil(max(0, units - included_units) / unit_batch)`; free providers resolve to `0.0` (never `None`); unknown `(operation, provider, mode)` resolves to `None`.
3. All 12 `(operation, provider)` pairs are present with verified USD rates and an `OPERATION_PRICING_AS_OF` stamp; mode variants exist for exa (standard/agentic), tavily (basic/advanced), linkup search (standard/deep) and fetch (nojs/js), parallel search (turbo/pro), firecrawl (scrape).
4. `UsageTracker.record_operation(operation, provider, *, mode="default", units=1, reported_cost_usd=None)` resolves pricing, computes cost (preferring `reported_cost_usd` when provided), appends an `OperationUsageRecord`, and returns it; returns `None` when the operation/provider is unusable.
5. `UsageTracker.rollup()` folds operation records into `UsageRollup.operations` and `operation_count`, and the rollup's `cost_usd` is the None-aware sum of token cost + operation cost; `cost_complete` is `False` when any token **or** operation cost is `None`.
6. `UsageTracker.reset()` clears both the token ledger and the operation ledger.
7. Token-only fields (`input_tokens`, `output_tokens`, `total_tokens`, `model_call_count`) remain token-only and unchanged.
8. A `PricedOperationTool` subclass declares `operation` and `provider` class attributes and exposes `mode_used(call, result)`, `units_used(call, result)`, and `reported_cost_usd(call, result)`, all pure functions of the call/result (no mutable per-call state).
9. After a successful tool execution, the runtime records exactly one operation for any tool that is a `PricedOperationTool`; non-priced tools and failed/denied executions record nothing.
10. Pre-built tools exist for all 12 pairs; `DirectHttpFetchTool` wraps the existing `HttpFetcher` and prices to `$0.0`; each search tool derives `units` from the requested/returned result count and each fetch tool from the page/URL count.
11. No existing public signature changes; `agent.get_usage().cost_usd` reflects both axes with zero caller changes.

### Non-Functional Requirements
- **Accuracy:** every rate traceable to an official page dated `OPERATION_PRICING_AS_OF`; unverifiable specifics omitted (resolve to `None`) rather than guessed; reference-plan assumptions recorded in comments.
- **No network at import:** rates are static literals; the priced-contract tools perform no live network calls in this PR.
- **Concurrency-safe:** priced tools hold no mutable per-call state; all billing values derive from the call and result passed in.
- **Back-compat:** additive only — new module, new record type, new tracker method, new tools; existing token behavior byte-identical.
- **Observability:** operation cost flows through the existing `usage_rollup` / `on_usage` / `ctx.model_usage` surfaces; no new logging.
- **CI:** `python -m pip install -e ".[dev]" && python scripts/run_ci.py` (source = pytest, package = build/clean-install) passes unchanged.

---

## 5. High-Level Design

Two tracks land in one PR.

**Track A — Operation price book + tracker integration.** A new `vidbyte/lib/registries/operation_pricing.py` mirrors `registries/pricing.py`: an immutable `OperationPricing` dataclass with the four-field tariff (`usd_fixed`, `usd_per_unit`, `included_units`, `unit_batch`) and a `cost_usd(units)` method; a static `OPERATION_PRICING` table keyed `(operation, provider, mode)`; and an `OperationPricingRegistry` with `default() / resolve() / register()`. `records.py` gains `OperationUsageRecord` and `UsageRollup` gains `operations` + `operation_count` with a combined `cost_usd` / `cost_complete`. `tracker.py` gains an `_operations` ledger, a `record_operation(...)` method, and folds both ledgers in `rollup()` / `reset()`.

**Track B — Priced-contract tools + runtime linkage.** A new `vidbyte/tools/builtins/operations/` package defines `PricedOperationTool(BaseTool)` (the "specific type" the runtime checks) plus 7 search and 5 fetch concrete tools. The runtime resolves the tool instance inside `execute_tool_call` already; a new `_record_operation_usage(tool, call, result)` step runs after a successful execution, checks `isinstance(tool, PricedOperationTool)`, and calls `self.usage_tracker.record_operation(...)`.

```
Agent(tools=[BraveSearchTool(), FirecrawlFetchTool(), ...])
      │  model loop                              tool loop
      ▼                                          ▼
AgentRuntime._invoke_with_middleware        AgentRuntime._process_tool_call
  usage_tracker.record_call(response)  ──►    execute_tool_call(call)
      │  (token axis, unchanged)                 tool = _get_tool(call)
      │                                          result = _execute_tool(tool, call)
      │                                          _record_operation_usage(tool, call, result)
      │                                            └─ isinstance(tool, PricedOperationTool)?
      │                                               usage_tracker.record_operation(
      │                                                 tool.operation, tool.provider,
      │                                                 mode=tool.mode_used(call, result),
      │                                                 units=tool.units_used(call, result),
      │                                                 reported_cost_usd=tool.reported_cost_usd(call, result))
      ▼
UsageTracker.rollup() ──► UsageRollup(calls=…, operations=…, cost_usd=Σtokens+Σops)
      └─► agent.get_usage() / get_cost_usd() / usage_rollup / on_usage / ctx.model_usage
```

Key decisions: (1) **one tracker, two ledgers** — operations are stored in their own `_operations` list, not jammed into the token `calls` list, so no `Union` pollutes `UsageRecord`; the rollup carries both. (2) **USD cost unit** — operation rates are USD floats folding straight into `cost_usd` (sub-cent precision is free), matching the token tracker's unit exactly. (3) **`(operation, provider, mode)` key with a four-field tariff** — the minimum shape that prices every provider correctly, deliberately the same fixed + per-unit + tier skeleton the token side uses. (4) **prefer provider-reported cost** — `reported_cost_usd` short-circuits table math when present, mirroring OpenRouter handling. (5) **billing derived from call+result, not mutable tool state** — safe under concurrent tool execution.

---

## 6. Detailed Design

### 6.1 `OperationPricing` + `OperationPricingRegistry`
**File(s):** `vidbyte/lib/registries/operation_pricing.py` — **New**

#### What it does
Source-of-truth per-operation USD rate table and lookup registry for search/fetch providers, parallel to `ModelPricingRegistry`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class OperationPricing:
    usd_fixed: float = 0.0        # per-call base component (parallel fixed, exa first-10 bundle)
    usd_per_unit: float = 0.0     # per result / page / URL beyond included_units
    included_units: int = 0       # units already covered by usd_fixed
    unit_batch: int = 1           # bill per batch of N units (tavily extract: 5 URLs / credit)

    def cost_usd(self, units: int) -> float: ...   # usd_fixed + usd_per_unit * ceil(max(0, units-included)/batch)

OPERATION_PRICING_AS_OF: str = "2026-07-24"
OPERATION_PRICING: dict[tuple[str, str, str], OperationPricing] = { ... }

class OperationPricingRegistry:
    @classmethod
    def default(cls) -> "OperationPricingRegistry": ...
    def resolve(self, operation: str, provider: str, mode: str = "default") -> OperationPricing | None: ...
    def register(self, operation: str, provider: str, mode: str, pricing: OperationPricing) -> None: ...
```

#### Logic / Algorithm
1. `cost_usd(units)`: clamp `billable = max(0, units - included_units)`; `batches = ceil(billable / unit_batch)`; return `usd_fixed + usd_per_unit * batches`.
2. `resolve`: copy-on-init table like `ModelPricingRegistry`; look up exact `(operation, provider, mode)`; if absent and `mode != "default"`, fall back to `(operation, provider, "default")`; else `None`.
3. `register`: validate non-empty strings and `OperationPricing` type, raising `ConfigurationError` (reusing `vidbyte.lib.errors`).

#### The `OPERATION_PRICING` table (USD, `AS_OF=2026-07-24`)
```
("search","brave","default"):            usd_fixed=0.005
("search","exa","default"|"standard"):   usd_fixed=0.007, usd_per_unit=0.001, included_units=10
("search","exa","agentic"):              usd_fixed=0.012, usd_per_unit=0.001, included_units=10
("search","tavily","default"|"basic"):   usd_fixed=0.008
("search","tavily","advanced"):          usd_fixed=0.016
("search","linkup","default"|"standard"):usd_fixed=0.005
("search","linkup","deep"):              usd_fixed=0.05
("search","parallel","default"|"turbo"): usd_fixed=0.000001, usd_per_unit=0.000001, included_units=10
("search","parallel","pro"):             usd_fixed=0.000005, usd_per_unit=0.000001, included_units=10
("search","openalex","default"):         usd_fixed=0.001
("search","semantic_scholar","default"): (free) all-zero
("fetch","firecrawl","default"|"scrape"):usd_per_unit=0.00083
("fetch","parallel","default"):          usd_per_unit=0.001
("fetch","tavily","default"|"basic"):    usd_per_unit=0.008, unit_batch=5
("fetch","tavily","advanced"):           usd_per_unit=0.016, unit_batch=5
("fetch","linkup","default"|"nojs"):     usd_per_unit=0.001
("fetch","linkup","js"):                 usd_per_unit=0.005
("fetch","direct_http","default"):       (free) all-zero
```

> **⚠️ CORRECTION (2026-08-08):** the two `("search","parallel",…)` lines above are wrong by
> 1000×. Parallel's pricing column is headed `Cost ($/1000)`, so its value of `1` is $1 per
> 1,000 requests = **$0.001 per request**. Live rates are turbo `usd_fixed=0.001,
> usd_per_unit=0.001` and pro `usd_fixed=0.005, usd_per_unit=0.001`. Note that this doc's
> own §5 provider table and the `("fetch","parallel","default"): usd_per_unit=0.001` line
> above state the rates **correctly** — only this sketch is wrong, and that internal
> inconsistency is what later PRs propagated. See
> `docs/design/operation-pricing-payg-corrections.md`.

A module comment records the reference-plan assumptions (Tavily/Firecrawl credit→USD at PAYG/Standard; Exa one content type; Parallel ~10 included results; OpenAlex prices the marginal call, ignoring the $1/day credit) and the per-provider source URLs.

#### Edge Cases & Error Handling
- `units <= included_units` → `usd_fixed` only.
- Free entries → `cost_usd` returns `0.0` for any `units`.
- `resolve` mode fallback keeps flat providers callable without a mode; unknown pairs → `None` (caller treats as unpriced).
- `register` rejects malformed input with `ConfigurationError` (no silent no-op).

### 6.2 `OperationUsageRecord` and `UsageRollup` extension
**File(s):** `vidbyte/agents/pricing/records.py` — **Modified**

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class OperationUsageRecord:
    call_index: int
    operation: str
    provider: str
    mode: str = "default"
    units: int = 1
    cost_usd: float | None = None

@dataclass(frozen=True, slots=True)
class UsageRollup:
    calls: tuple[UsageRecord, ...] = ()
    model_call_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    cost_complete: bool = False
    operations: tuple[OperationUsageRecord, ...] = ()   # NEW
    operation_count: int = 0                            # NEW
```

#### Logic / Algorithm
- New fields are defaulted and appended, preserving positional/keyword construction of existing callers.
- `cost_usd` semantics widen from "sum of call costs" to "sum of call + operation costs" (computed in the tracker; the dataclass stays a dumb container).

#### Edge Cases & Error Handling
- A run with only operations (no model calls) yields `model_call_count=0`, `input_tokens=None`, `operation_count>0`, and a numeric `cost_usd` — valid and expected.

### 6.3 `UsageTracker.record_operation` + combined rollup
**File(s):** `vidbyte/agents/pricing/tracker.py` — **Modified**

#### Interface / API
```python
def __init__(self, *, pricing: ModelPricingRegistry | None = None, operation_pricing: OperationPricingRegistry | None = None) -> None: ...
def record_operation(self, operation: str, provider: str, *, mode: str = "default", units: int = 1, reported_cost_usd: float | None = None) -> OperationUsageRecord | None: ...
```

#### Logic / Algorithm
1. `__init__`: bind `self._operation_pricing = operation_pricing or OperationPricingRegistry.default()`; add `self._operations: list[OperationUsageRecord] = []`.
2. `record_operation`: normalize `operation`/`provider` to non-empty strings (else return `None`); resolve pricing via the registry; compute `cost = reported_cost_usd if reported_cost_usd is not None else (pricing.cost_usd(units) if pricing is not None else None)`; append `OperationUsageRecord(call_index=len(self._operations)+1, operation, provider, mode, units, cost_usd=cost)`; return it.
3. `rollup()`: build the existing token totals, then set `operations=tuple(self._operations)`, `operation_count=len(self._operations)`; `cost_usd = _sum_or_none(all token costs + all operation costs)`; `cost_complete = bool(records or operations) and all token costs not None and all operation costs not None`.
4. `reset()`: clear `self._records` **and** `self._operations`.
5. Add `@property operations` returning the immutable operation ledger (parallel to `records`).

#### Edge Cases & Error Handling
- `units < 1` is coerced to `0`-floored by `cost_usd`'s `max(0, …)`; a non-int `units` is rejected (return `None`) to keep the ledger clean.
- Unknown provider/mode → `cost_usd=None` on the record and `cost_complete=False` on the rollup (does not raise).
- `reported_cost_usd` present but negative/non-numeric → ignored (falls back to table math) to avoid poisoning totals.

### 6.4 `PricedOperationTool` base
**File(s):** `vidbyte/tools/builtins/operations/base.py` — **New**

#### What it does
Abstract base for tools whose execution incurs a priced search/fetch operation. Carries the stable `(operation, provider)` identity and three pure derivations the runtime reads.

#### Interface / API
```python
class PricedOperationTool(BaseTool):
    operation: ClassVar[str]                # "search" | "fetch"
    provider: ClassVar[str]                 # "brave", "firecrawl", ...

    def mode_used(self, call: ToolCall, result: ToolResult) -> str: ...          # default "default"
    def units_used(self, call: ToolCall, result: ToolResult) -> int: ...         # default 1
    def reported_cost_usd(self, call: ToolCall, result: ToolResult) -> float | None: ...  # default None
```

#### Logic / Algorithm
- Subclasses set `operation`/`provider` class attrs and override the three hooks as needed.
- A protected helper `_operation_metadata(units, mode)` returns a `dict` the subclass merges into `ToolResult.metadata["operation_usage"]` during `execute`, so the billing signal is inspectable and the default hooks can read it back — keeping the tool stateless.

#### Edge Cases & Error Handling
- If a subclass forgets to override and the result carries no metadata, defaults (`mode="default"`, `units=1`, `reported_cost=None`) apply — the call is still priced at the flat/default rate.

### 6.5 Search tools
**File(s):** `vidbyte/tools/builtins/operations/search.py` — **New**

#### What it does
Seven priced-contract search tools: `BraveSearchTool`, `ExaSearchTool`, `TavilySearchTool`, `LinkupSearchTool`, `ParallelSearchTool`, `OpenAlexSearchTool`, `SemanticScholarSearchTool`.

#### Interface / API (representative)
```python
class BraveSearchTool(PricedOperationTool):
    operation = "search"
    provider = "brave"
    def spec(self) -> ToolSpec: ...                          # params: query (req), count (opt)
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def units_used(self, call, result) -> int: return 1      # per-request billing
```
Per-provider specifics:
- **ExaSearchTool** — params `query`, `num_results`, `type`(mode); `units_used` = returned result count; `reported_cost_usd` reads `costDollars.total` when present.
- **TavilySearchTool** — params `query`, `search_depth`(→ mode basic/advanced), `max_results`; `units_used`=1; `reported_cost_usd` reads `usage`.
- **LinkupSearchTool** — params `query`, `depth`(→ mode standard/deep); `units_used`=1.
- **ParallelSearchTool** — params `objective`, `processor`(→ mode turbo/pro), `max_results`; `units_used`=result count; `reported_cost_usd` reads `usage[]`.
- **OpenAlexSearchTool** — params `query`, `per_page`; `units_used`=1.
- **SemanticScholarSearchTool** — params `query`, `limit`; `units_used`=1 (free).

#### Logic / Algorithm
Each `execute` validates args, produces a deterministic priced-contract `ToolResult` whose `metadata["operation_usage"]` encodes the resolved `mode` and `units` derived from the request (e.g. `num_results`), plus any echoed `reported_cost`. Real API calls are deferred; the result body is a structured placeholder describing the intended request.

#### Edge Cases & Error Handling
- Missing required `query` → `ToolResult.error` (via `validate_call`), which the runtime treats as a failure and does **not** record as a priced operation.
- Mode arg outside the known set → clamp to the provider's `"default"` mode.

### 6.6 Fetch tools
**File(s):** `vidbyte/tools/builtins/operations/fetch.py` — **New**

#### What it does
Five priced-contract fetch tools: `FirecrawlFetchTool`, `ParallelExtractTool`, `TavilyExtractTool`, `LinkupFetchTool`, `DirectHttpFetchTool`.

#### Interface / API (representative)
```python
class FirecrawlFetchTool(PricedOperationTool):
    operation = "fetch"
    provider = "firecrawl"
    def spec(self) -> ToolSpec: ...                          # params: url (req) | urls (opt)
    def units_used(self, call, result) -> int: ...           # #pages fetched (default 1)

class DirectHttpFetchTool(PricedOperationTool):
    operation = "fetch"
    provider = "direct_http"
    def units_used(self, call, result) -> int: return 1      # free
```
Per-provider specifics:
- **ParallelExtractTool** — params `urls`; `units_used`=len(urls); `reported_cost_usd` reads `usage[]`.
- **TavilyExtractTool** — params `urls`, `extract_depth`(→ mode); `units_used`=count of successful URLs; `reported_cost_usd` reads `usage`.
- **LinkupFetchTool** — params `url`, `render_js`(→ mode nojs/js); `units_used`=1.
- **DirectHttpFetchTool** — wraps `vidbyte.sources.fetches.http.HttpFetcher`; single page; `$0.0`.

#### Logic / Algorithm
Batch fetch tools derive `units` from the `urls` argument length (or successful count encoded in the result metadata for Tavily). `DirectHttpFetchTool.execute` may actually invoke `HttpFetcher.fetch` (it is the SDK's own zero-cost fetcher and already exists), returning body + status; all others are priced-contract placeholders pending real clients.

#### Edge Cases & Error Handling
- Empty `urls` list → `units=0` → `cost_usd` `usd_fixed` only (0 for these) — no crash.
- `HttpFetcher` raising `SourceFetchError` → `ToolResult.error`, not recorded as a priced operation.

### 6.7 Runtime linkage
**File(s):** `vidbyte/agents/runtime.py` — **Modified**

#### What it does
Records one operation for any successfully executed `PricedOperationTool`.

#### Interface / API
```python
def _record_operation_usage(self, tool: object, call: ToolCall, result: ToolResult) -> None: ...
```

#### Logic / Algorithm
1. In `execute_tool_call`, immediately after the successful-execution block (post output-schema validation, before `end_span`), call `self._record_operation_usage(tool, call, result)`.
2. `_record_operation_usage`: return early unless `isinstance(tool, PricedOperationTool)` and `result.status is ToolStatus.SUCCESS`; then call `self.usage_tracker.record_operation(tool.operation, tool.provider, mode=tool.mode_used(call, result), units=tool.units_used(call, result), reported_cost_usd=tool.reported_cost_usd(call, result))`.
3. Wrap the derivations in a defensive `try/except` that swallows and skips on any tool bug, so a mis-implemented pricing hook can never break tool execution (consistent with the tracker's defensive `record_call`).

#### Edge Cases & Error Handling
- Failed/denied/errored tool results → not recorded (guarded by `ToolStatus.SUCCESS`).
- A `PricedOperationTool` whose provider is absent from the table → `record_operation` returns a record with `cost_usd=None`, flipping `cost_complete` to `False` (surfaced, not hidden).
- Import placement: `PricedOperationTool` imported at module top of `runtime.py`; no cycle (tools layer does not import the runtime).

### 6.8 Package exports
**File(s):** `vidbyte/agents/pricing/__init__.py`, `vidbyte/tools/builtins/operations/__init__.py`, `vidbyte/tools/builtins/__init__.py` — **Modified/New**

- `agents/pricing/__init__.py`: export `OperationUsageRecord` alongside `UsageRecord`/`UsageRollup`.
- `tools/builtins/operations/__init__.py` (new): export `PricedOperationTool` and all 12 concrete tools.
- `tools/builtins/__init__.py`: re-export the operations package tools, following the existing import/`__all__` pattern.

---

## 7. Data Model Changes

### 7.1 `OperationPricing`
**Change type:** New — immutable dataclass (`usd_fixed`, `usd_per_unit`, `included_units`, `unit_batch`) with `cost_usd(units)`. No persistence. N/A — the SDK has no database.

### 7.2 `OperationUsageRecord`
**Change type:** New — immutable per-operation record. In-memory only.

### 7.3 `UsageRollup`
**Change type:** Modified — two additive defaulted fields (`operations`, `operation_count`); `cost_usd`/`cost_complete` widen to span both axes. Frozen dataclass; defaults preserve existing construction.

No DB/schema migration. N/A — the SDK has no database.

---

## 8. API Changes

N/A — No HTTP endpoints. Public Python surface changes are additive only: new `OperationPricing` / `OperationPricingRegistry` / `OPERATION_PRICING`, new `OperationUsageRecord`, new `UsageTracker.record_operation(...)` and constructor kwarg, new `PricedOperationTool` + 12 concrete tools. No existing signature changes; `get_usage()` / `get_cost_usd()` return values now include operation cost without a shape change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-operation-pricing.md` | This design doc (first commit). |
| CREATE | `vidbyte/lib/registries/operation_pricing.py` | `OperationPricing`, `OPERATION_PRICING` table, `OperationPricingRegistry`, `OPERATION_PRICING_AS_OF`. |
| MODIFY | `vidbyte/agents/pricing/records.py` | Add `OperationUsageRecord`; extend `UsageRollup` with `operations` + `operation_count`. |
| MODIFY | `vidbyte/agents/pricing/tracker.py` | `operation_pricing` kwarg, `_operations` ledger, `record_operation(...)`, combined `rollup()`/`reset()`, `operations` property. |
| MODIFY | `vidbyte/agents/pricing/__init__.py` | Export `OperationUsageRecord`. |
| CREATE | `vidbyte/tools/builtins/operations/__init__.py` | Export `PricedOperationTool` + concrete tools. |
| CREATE | `vidbyte/tools/builtins/operations/base.py` | `PricedOperationTool` base with `(operation, provider)` + `mode_used`/`units_used`/`reported_cost_usd`. |
| CREATE | `vidbyte/tools/builtins/operations/search.py` | 7 priced-contract search tools. |
| CREATE | `vidbyte/tools/builtins/operations/fetch.py` | 5 priced-contract fetch tools. |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Re-export the operations tools. |
| MODIFY | `vidbyte/agents/runtime.py` | `_record_operation_usage`; call it after successful execution in `execute_tool_call`. |

**Totals: 6 created, 5 modified, 0 deleted.**

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Provider pricing pages | Brave / Exa / Tavily / Linkup / Parallel / OpenAlex / Semantic Scholar / Firecrawl docs | Source of static per-operation rates | Rates drift; mitigated by `OPERATION_PRICING_AS_OF` + omit-if-unverifiable + reference-plan comments. |
| `vidbyte.sources.fetches.http.HttpFetcher` | in-repo | Backing for `DirectHttpFetchTool` | None — existing internal component. |

No new Python package dependencies. No live third-party calls in this PR (real API clients deferred).

---

## 11. Rollout & Deployment

- **Feature flags:** none. Rates are static; priced-contract tools are inert unless a developer adds one to an agent's toolset.
- **Breaking change:** no. Additive module + additive record type + additive tracker method + additive tools + two defaulted rollup fields. Existing token pricing and `get_usage()` shape are unchanged; totals now include operation cost only when a priced tool actually runs.
- **Deployment order:** single PR into `main`; no service coordination.
- **Rollback:** revert the PR; no state or migration to undo.
- **CI gate:** `python -m pip install -e ".[dev]" && python scripts/run_ci.py` (source = pytest, package = build + clean-install smoke).

---

## 12. Open Questions

- [ ] **Reference-plan rates for credit-based providers.** Tavily/Firecrawl USD rates bake in PAYG/Standard-plan credit prices; a customer on another plan bills differently. Encode the reference-plan effective rate (recommended, stamped `AS_OF`) — accepted per the talk phase.
- [ ] **Parallel Search included-result count.** The docs price "$X/1k requests + $Y/1k additional results" without stating the included baseline; assumed `included_units=10`. Confirm or pin when the docs specify.
- [ ] **OpenAlex daily free credit.** Priced at the marginal `$0.001/search`, ignoring the account-level `$1/day` allowance the SDK cannot track per-call. Accept (recommended).
- [ ] **DirectHttpFetchTool live fetch.** It wraps the existing zero-cost `HttpFetcher`; should this one tool actually perform the fetch in this PR (it is free and in-repo) while the other 11 stay priced-contract? Assumed **yes**.

---

## 13. Alternatives Considered

### Alternative 1: Reuse `ModelPricing` / `ModelPricingRegistry` for operations
- What: Add search/fetch rows to the token table keyed by provider/model.
- Why rejected: The token registry keys on `ModelProvider` (an LLM-provider enum) and prices per-million tokens; operations are non-LLM providers priced per unit with mode tiers and two-part tariffs. Overloading it would corrupt the enum's meaning and the per-million semantics. A parallel registry keeps each axis honest.

### Alternative 2: A separate `OperationUsageTracker` object
- What: Track operation cost in its own tracker; caller sums token + operation cost.
- Why rejected: The user requires one agent-level cost number; a separate tracker means `agent.get_cost_usd()` silently omits tool spend. Storing operations in a second ledger *inside* the existing tracker gives one rollup with clean types.

### Alternative 3: Flat per-call price (the original `_OPERATION_MILLICENTS` shape)
- What: One USD number per `(operation, provider)`, 1 op per call.
- Why rejected: Verified pricing is multi-dimensional — firecrawl is per-page, exa is base+overage, tavily/linkup have order-of-magnitude depth tiers, tavily-extract bills per 5-URL batch. A flat number under-/over-charges most providers, violating the accuracy requirement ("10 webpages cost more").

### Alternative 4: Record operations via `ToolResult.metadata` read in the model loop
- What: Have every tool stuff usage into metadata and scan it generically.
- Why rejected: The runtime already resolves the concrete tool instance in `execute_tool_call`; an `isinstance(PricedOperationTool)` check there is more explicit and type-safe than string-scanning arbitrary tool metadata, and it cleanly excludes non-priced tools. Metadata is still used as the stateless carrier *within* a priced tool, but the recording decision is type-driven.

### Alternative 5: Mutable `self.mode` set during `execute`
- What: Store per-call mode/units on the tool instance.
- Why rejected: Tools are singletons in the catalog and may execute concurrently; mutable per-call state races. Deriving mode/units purely from the `(call, result)` pair passed to the hooks is concurrency-safe.

---

## Phase 2 Report

- **Manifest:** 6 created, 5 modified, 0 deleted.
- **Key risks:** (1) reference-plan rates for credit-based providers are effective-price estimates (documented, stamped); (2) two rate specifics assumed pending doc confirmation (Parallel included results, OpenAlex free credit); (3) priced-contract tools do not make live calls yet — pricing is exercised via deterministic result metadata, real clients follow.
- **Accuracy:** all 12 pairs verified against official docs on 2026-07-24 with per-provider source URLs recorded in-module; unverifiable specifics omitted rather than guessed.
- **Open questions:** 4 (see §12), all with a recommended default; none blocking.

**Requesting approval to proceed to Phase 3 (worktree off `main`) and Phase 4 (implementation).**

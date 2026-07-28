# Design Doc: Executing Priced Web Operation Tools (Brave + Firecrawl)

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-27
**Last Updated:** 2026-07-27

---

## 1. Overview

Today the SDK's prebuilt search and fetch tools cannot perform provider I/O. `BraveSearchTool` and `FirecrawlFetchTool` contain no HTTP code and no credentials: they declare a model-facing schema, a `(operation, provider)` billing identity, and a unit rule, then return a deterministic placeholder string. Every application that wants working search must write its own Brave client, HTTP transport, and response normalizer — which is exactly what `backend/provider/web/` is in the Vidbyte repo, 287 lines against the SDK's ~20.

This change moves execution into the SDK. Two new clients, `BraveClient` and `FirecrawlClient`, own vendor transport with industry-standard retry, timeout, and response-size policy; they accept an API key rather than discovering one. The tools execute through them and return two channels on one `ToolResult`: a compact model-facing `output`, and a typed payload in `metadata` that the application consumes and maps to its own domain. Metering becomes attempt-accurate: every provider attempt a retry policy makes, including the attempts of a call that ultimately fails, is priced as its own operation record against the SDK pricebook and reaches the user's wallet. The Vidbyte repo deletes its Brave and Firecrawl adapters and its bounded JSON client, keeps its research policy and URL-safety guard, and reads usage from one meter instead of two.

---

## 2. Goals & Non-Goals

### Goals

- Add `BraveClient` and `FirecrawlClient` to the SDK under `vidbyte/tools/`, owning vendor transport: API key auth, timeouts, exponential-backoff retry, bounded response bodies, redacted failures.
- Make `BraveSearchTool` and `FirecrawlFetchTool` execute through those clients when one is supplied, while preserving today's contract-stub behavior when no client is supplied.
- Return a typed, provider-neutral payload to the application alongside the model-facing output, so the application can apply its own policy to real results.
- Meter usage attempt-accurately: `N` provider attempts produce `N` priced operation records, and attempts of a failed call are still billed.
- Extend pre-call wallet authorization to cover the maximum attempts a retry policy may make, so a retried call cannot overdraw a reservation.
- Update Vidbyte PR #284 to consume the new SDK surface: delete the duplicated vendor adapters, refactor the search executor into a payload consumer, route deterministic fetch through `FirecrawlClient`, and collapse the two competing usage meters into one.
- Keep both repositories' existing CI gates green with no new test files.

### Non-Goals

- Porting the other five search providers (Exa, Tavily, Linkup, Parallel, OpenAlex, Semantic Scholar) and three fetch providers (Parallel, Tavily, Linkup) to real execution. They keep the contract-stub path. This change is the wedge that proves the shape on two providers; the rest port mechanically afterward.
- Changing any rate in `OPERATION_PRICING` or `PROVIDER_PRICING`, or changing `pricebook_version` semantics.
- Adding credential discovery, rotation, or environment scanning to the SDK. Clients accept a key; Vidbyte keeps `credentials_loader.py`.
- Registering `firecrawl_fetch` as a model-callable tool in the research harness. Research retrieval stays deterministic; the harness uses `FirecrawlClient` directly.
- Mid-call wallet enforcement. Wallet checks continue to land at model-call and operation boundaries.
- New test files. Existing suites are updated where their subject is deleted.

---

## 3. Background & Context

### Why now

Vidbyte PR #284 (`ai/resolve-pr-281-review-comments`, 201 files) pins the SDK to `6998a92`. That commit exists only on the unmerged SDK branch `feat/pr-284-operation-executor`, has no open PR, and is not an ancestor of `origin/main`. It added an `executor=` callable seam to `PricedOperationTool` so the application could inject provider I/O. `origin/main`'s `PricedOperationTool` has no `__init__` and zero occurrences of "executor", so the moment the pin moves toward main, `BraveSearchTool(executor=executor)` in `backend/services/harnesses/research/harness.py:153` raises `TypeError: BaseTool() takes no arguments` and the research harness's search path stops working.

An SDK PR has to be opened either way. Opening it for the executor seam would merge a contract we already know we want to replace, then pay the migration a second time. This design lands the intended shape directly.

### The problem being solved

The SDK publishes a dated, source-of-truth rate table for 7 search and 5 fetch providers but cannot call any of them. That forces every consumer to build twelve clients, and it splits vendor knowledge across two repositories: the SDK knows what Firecrawl costs per page, while the Vidbyte repo knows how to ask Firecrawl for a page. Vendor unit rules — Tavily extract bills per 5-URL batch, Exa bills per result over a 10-result bundle, Firecrawl bills per page — are precisely the facts that are cheap to centralize and expensive to get wrong once per consumer.

### Current state

**SDK (`origin/main`, `982ae5d`):**

- `vidbyte/tools/builtins/operations/base.py` — `PricedOperationTool`: `operation`/`provider` ClassVars, `mode_used`/`units_used`/`reported_cost_usd` hooks reading a `metadata["operation_usage"]` annotation, and `_contract_result()` which builds a placeholder success result carrying that annotation. No `__init__`.
- `operations/search.py`, `operations/fetch.py` — 12 tools. All return `_contract_result(...)` except `DirectHttpFetchTool`, which already performs a live GET through the SDK's own `HttpFetcher` and prices at zero. **The SDK already has one executing priced tool**; Brave and Firecrawl differ only in needing credentials.
- `vidbyte/lib/http/transport.py` — `HttpTransport.request()` already implements async exponential-backoff retry (`retry_count`, `backoff_seconds`, `backoff_multiplier`, `retry_status_codes=(408, 409, 425, 429, 500, 502, 503, 504)`) and normalizes failures to `ProviderRequestError`. It does not report how many attempts it made, and it has no response-size ceiling.
- `vidbyte/agents/runtime.py:1165` — `_record_operation_usage` records **one** operation per tool call, and returns early unless `result.status.value == "success"`.
- `vidbyte/lib/registries/operation_pricing.py` — `("search", "brave", "default"): OperationPricing(usd_fixed=0.005)` and `("fetch", "firecrawl", "scrape"): OperationPricing(usd_per_unit=0.00083)`.

**Vidbyte (`worktree-pr-281-resolve`, HEAD `cfd17710`):**

- `backend/provider/web/` — `base.py` (43 lines, `SearchProvider`/`ContentProvider` protocols), `brave.py` (118), `client.py` (67, `BoundedJsonHttpClient`), `firecrawl.py` (76), `url_safety.py` (59, `validate_public_url`).
- `services/harnesses/research/operations.py` — `ResearchSearchExecutor`, injected as the SDK tool's executor. Calls the provider, then applies research policy: dedup against `visited_hashes`, cap at `max_candidates`, map to `ResearchSource`, offer to `ResearchDiscoveryLedger`, and stash candidates for `selected_sources(urls)`.
- `services/usage/session.py:43` — `UsageSession` owns its **own** `UsageTracker`, a second meter parallel to the agent's.
- `services/usage/operation_scope.py` — `BillableOperationScope`: `__aenter__` authorizes, `record_attempt()` meters, `__aexit__` reconciles. Its header already states the intended invariant: *"Failed and fallback provider attempts remain individually billable."*
- `services/usage/adapters/sdk_middleware.py` — `WalletModelUsageMiddleware`: `before_model_call` authorizes; `after_model_response` re-parses a response the SDK runtime already priced.
- `lib/usage/ledger.py` — `UsageLedger`, correctly scoped: USD float → integer millicents with `ROUND_CEILING`, `UsageSnapshot` durable across Inngest steps, pricebook-vintage guard on resume.

### Three findings that shape the design

**Finding 1 — `units` does not scale cost for flat-rate providers.** Brave's tariff is `usd_fixed=0.005, usd_per_unit=0.0`, and `OperationPricing.cost_usd(units)` returns `usd_fixed + usd_per_unit * batches`. Recording one operation with `units=3` for three attempts therefore bills **$0.005, not $0.015** — it silently under-bills while making the snapshot's `search_calls` counter look right. Attempt-accurate billing requires **one priced record per attempt**, not one record with summed units.

**Finding 2 — failed tool calls are not metered at all.** `_record_operation_usage` returns early when the result status is not success. If every retry fails, the tool returns an error result and **zero** units are recorded, even though the provider was contacted `N` times. Satisfying "retry policies count towards usage" requires metering to key off declared billable attempts rather than success.

**Finding 3 — the executor cannot report units, by design.** At the pinned commit, `_priced_result` does `metadata.update(self._usage_metadata(...))`, overwriting anything an executor placed under `operation_usage`, and the file header says *"Do not trust executor-supplied operation_usage metadata."* That distrust is correct for an application-supplied callable. Once the client is SDK-owned and SDK-constructed, the units it reports are trustworthy, which is what makes attempt-accurate billing expressible at all.

### Field guide constraints consulted

- `field-guide/vidbyte-sdk/priced-operation-execution.md` — the current principle prescribes the executor seam. **This design supersedes it**; the entry needs rewriting (Section 12).
- `field-guide/vidbyte-sdk/local-ci-verification.md` — run the source stage with `PYTHONPATH=$(pwd)` from a worktree; run the package stage without it; `git add -A` before trusting a semgrep scan.
- `field-guide/vidbyte/research-harness-boundaries.md` — "Translate provider payloads at reusable capability boundaries… harness code contains no vendor JSON parsing." Preserved and strengthened: vendor JSON parsing leaves the Vidbyte repo entirely.
- `field-guide/vidbyte/research-usage-tracking.md` — `UsageLedger` accepts only SDK-priced records and never reprices; `HarnessRun.usage` stays a bounded aggregate; only the active pricebook vintage may resume a run. All preserved.

### Constraints

- SDK dependencies are `pydantic>=2,<3` and `httpx>=0.27`. No new dependency needed.
- Semgrep rule `no-untyped-mapping-fallback` scans `/vidbyte/**/*.py`, excluding `lib/http/**`, `providers/**`, `mcp_server/**`, `tools/mcp/**`. New client code under `tools/builtins/operations/` **is scanned**, so vendor JSON must be validated at a boundary that raises, not coerced through `isinstance(x, Mapping)` fallbacks.
- SDK CI: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` (stages `source`, `package`).
- SDK file headers on `origin/main` use the `"""Context Protocol Header` form with Description / Purpose / Architecture / Relations / Similar Files. Vidbyte backend headers use the `FILE: / PURPOSE: / ROLE IN CODEBASE:` form. Each repo keeps its own.

---

## 4. Requirements

### Functional Requirements

1. `BraveClient` accepts an API key and returns a typed search payload for one query; it never reads an environment variable or a file.
2. `FirecrawlClient` accepts an API key and returns typed page payloads for one or more URLs; it never reads an environment variable or a file.
3. Both clients apply a configurable retry policy — attempt count, initial backoff, multiplier, retryable status codes — defaulting to the SDK transport's existing industry-standard values.
4. Both clients enforce a configurable response-body byte ceiling and raise rather than parse a payload that exceeds it.
5. Both clients report the number of provider attempts made, including the attempt that succeeded.
6. Both clients raise `ProviderRequestError` for transport and non-2xx failures and `ProviderResponseError` for a 2xx body that cannot be normalized; neither error message, nor any log line, may contain the API key, request headers, or the raw response body beyond the 500-character excerpt the SDK error types already truncate to.
7. `BraveSearchTool` executes through an injected `BraveClient` when one is present and returns the existing contract-stub result when none is present.
8. `FirecrawlFetchTool` executes through an injected `FirecrawlClient` when one is present and returns the existing contract-stub result when none is present.
9. On success, both tools return a `ToolResult` whose `output` is a compact model-facing summary and whose `metadata["operation_payload"]` carries the typed provider-neutral payload.
10. On provider failure after exhausting retries, both tools return an error `ToolResult` that still declares the billable attempts made.
11. Each tool declares, in `metadata["operation_usage"]`, the billing `mode`, the `units` for a single attempt, and the `attempts` count.
12. `AgentRuntime` records one priced operation per declared attempt, so `N` attempts produce `N` `OperationUsageRecord` values against the pricebook.
13. `AgentRuntime` meters a failed priced-operation result when it declares `attempts >= 1` and `units >= 1`, and meters nothing when a call never reached the provider.
14. The Vidbyte research harness obtains search results from the SDK payload and applies its own dedup, candidate cap, `ResearchSource` mapping, and discovery-ledger offer to that payload.
15. The Vidbyte research harness fetches source content through `FirecrawlClient` and records the resulting fetch operation with the real page count and attempt count.
16. Vidbyte pre-call operation authorization reserves for the maximum attempts the configured retry policy permits.
17. Exactly one `UsageTracker` meters a run: the agent's. `UsageSession` constructs none.
18. `UsageSession` applies an SDK `UsageRollup` after each agent call and fails closed when `cost_complete` is false.
19. `backend/provider/web/brave.py`, `firecrawl.py`, `client.py`, and `base.py` are deleted; `url_safety.py` is retained.
20. Deterministic research fetch remains outside the model's tool surface: `firecrawl_fetch` is not registered on any research agent.

### Non-Functional Requirements

- **Performance.** No added round trips. Retry backoff is non-blocking (`asyncio.sleep`), matching the existing transport. Firecrawl batch scrape issues one request for `N` URLs where the vendor supports it.
- **Concurrency.** Clients hold no per-request mutable state and are safe to share across concurrent tool calls. Tools remain stateless per call, as `PricedOperationTool` requires.
- **Security.** API keys are held as strings inside the client and written only into an `Authorization`/`X-Subscription-Token` request header. No header, body, or credential is logged. Response excerpts in errors stay within the SDK error types' existing 500-character truncation. Vidbyte keeps `validate_public_url` in front of every URL handed to a fetch provider.
- **Observability.** Provider failures surface as typed SDK errors with provider, status code, and truncated excerpt. Attempt counts are visible in `metadata["operation_usage"]["attempts"]` and therefore in the usage rollup.
- **Reliability.** A provider outage degrades to a redacted error `ToolResult` the agent can react to, never an unhandled exception escaping the runtime. Billing remains correct across a partially failed retry sequence.
- **Billing correctness.** Money crosses into Vidbyte as an SDK-priced record only. `UsageLedger` continues to be the sole USD→millicents converter, ceiling-rounded.
- **Backward compatibility.** Constructing any priced operation tool with no arguments keeps working and keeps returning a contract stub.

---

## 5. High-Level Design

The change has three layers, and the boundary between them is the same one the SDK already draws for `ProviderOperationTool` (`vidbyte/tools/builtins/providers/_base.py`), whose docstring reads *"It does not create a new MongoDB connection"* — the SDK executes, the application supplies the connected client.

**Layer 1 — SDK clients.** Two new classes under `vidbyte/tools/builtins/operations/clients/` own everything vendor-specific: endpoint, auth header, request body, retry policy, response ceiling, and JSON→typed-payload normalization. They build on `HttpTransport.request()`, which already implements the retry loop; the transport gains an `attempts` field on its response and an optional byte ceiling so the clients can report attempts and bound bodies without reimplementing HTTP.

**Layer 2 — SDK tools.** `PricedOperationTool` gains an optional client and an `attempts_used()` hook along`mode_used()`/`units_used()`. `BraveSearchTool` and `FirecrawlFetchTool` call their client, annotate the result with `{mode, units, attempts}` plus the typed payload, and fall back to the existing contract stub when no client was injected. `AgentRuntime._record_operation_usage` changes from "one record per successful call" to "one record per declared attempt, success or failure" — which is what makes retries billable and, per Finding 1, what makes flat-rate providers bill correctly at all.

**Layer 3 — Vidbyte.** The four vendor files in `backend/provider/web/` are deleted. `ResearchSearchExecutor` stops being an injected executor and becomes `ResearchSearchCandidates`, a payload consumer: the tool executes, and Vidbyte reads `metadata["operation_payload"]` to apply dedup, caps, `ResearchSource` mapping, and the discovery-ledger offer. Because the SDK now meters every search through the agent's tracker, `UsageSession` drops its own tracker and instead applies the agent's `UsageRollup` after each call; `BillableOperationScope` keeps its `__aenter__` authorization (widened to cover max attempts) and loses `record_attempt`. Deterministic extraction calls `FirecrawlClient` directly and records one operation per attempt through the one remaining manual meter.

```
                        ┌── SDK ───────────────────────────────────────────────┐
                        │  OPERATION_PRICING (rates, dated)                    │
                        │            ▲                                         │
 model decides ─────────┼─► BraveSearchTool ──► BraveClient ──► HttpTransport ─┼──► api.search.brave.com
                        │        │  ▲                │  (retry, ceiling)       │
                        │        │  └─ attempts ─────┘                         │
                        │        ▼                                             │
                        │  ToolResult                                          │
                        │    output   = "3 results: …"        → context window │
                        │    metadata["operation_payload"]    → application    │
                        │    metadata["operation_usage"]      → runtime        │
                        │        │                                             │
                        │        ▼  AgentRuntime._record_operation_usage        │
                        │     N attempts → N OperationUsageRecord              │
                        │        └──────► agent UsageTracker (the ONE meter)    │
                        └────────────────────┬─────────────────────────────────┘
                                             │ agent.get_usage() → UsageRollup
 ┌── Vidbyte ────────────────────────────────▼─────────────────────────────────┐
 │  ResearchSearchCandidates.consume(payload)   dedup, caps, ResearchSource     │
 │  UsageSession.apply_agent_usage(rollup)  →  UsageLedger  →  UsageSnapshot    │
 │  BillableOperationScope.__aenter__       →  authorize(units × max_attempts)  │
 │  extraction.py → FirecrawlClient + one explicit record_operation per attempt │
 │  url_safety.validate_public_url          (retained: egress policy is ours)   │
 └──────────────────────────────────────────────────────────────────────────────┘
```

**Key decisions**

1. *One priced record per attempt, not summed units.* Forced by Finding 1: Brave's `usd_per_unit` is zero, so summing units into one record under-bills every retry. Per-attempt records price correctly for both flat-fixed and per-unit tariffs and keep `search_calls`/`fetch_calls` meaningful.
2. *Meter declared attempts on failure, not all failures.* Gating on a declared `operation_usage` annotation means a call that never reached the provider (bad arguments, unknown tool, zero URLs) declares nothing and bills nothing, while contract-stub tools are unaffected because they never fail.
3. *Payload in `metadata`, summary in `output`.* A tool result serves the model and the application at once. Splitting the channels is what makes "we take the payload and do whatever we want with it" true; a single rendered string would destroy the structure the harness needs for dedup and persistence.
4. *Keep the contract-stub fallback.* `client=None` preserving today's behavior makes this additive for the ten providers not being ported and for any existing consumer.
5. *Retire the `executor=` seam rather than merge it.* The seam exists only on an unmerged branch; a client-based tool with a typed payload covers the same need without asking the application to satisfy a `ToolResult` contract.
6. *Extend the shared transport rather than write a second HTTP layer.* `HttpTransport.request()` already has the retry loop. Two additive, defaulted parameters are a smaller change than a parallel bounded client, and every future SDK client benefits.

---

## 6. Detailed Design

### 6.1 SDK HTTP transport — attempt reporting and response ceiling

**File(s):** `vidbyte/lib/http/transport.py`
**Type:** Modified

#### What it does

Reports how many attempts a retrying request consumed, and optionally refuses a response body above a byte ceiling. Both are additive and defaulted, so every existing caller is unchanged.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str
    headers: Mapping[str, str]
    raw_bytes: bytes | None = None
    attempts: int = 1

class HttpTransport:
    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504), max_response_bytes: int | None = None) -> HttpResponse: ...
```

#### Logic / Algorithm

1. Keep the existing attempt loop unchanged.
2. Track the 1-based attempt index; when returning a response, return `replace(response, attempts=attempt + 1)`.
3. When `max_response_bytes` is set, `_send_once` streams the response and accumulates bytes, raising `ProviderRequestError` as soon as the accumulated length would exceed the ceiling; when it is `None`, `_send_once` behaves exactly as today.
4. On a declared `content-length` above the ceiling, fail before reading the body.

#### Edge Cases & Error Handling

- Ceiling exceeded → `ProviderRequestError(provider="http", status_code=<status>)`, no body excerpt, so an oversized page can neither be parsed nor logged.
- `retry_count=0` → one attempt, `attempts == 1`, identical to current behavior.
- Every retry returning a retryable status → the last response is returned with `attempts == retry_count + 1`; the client decides whether that status is an error.
- A transport-level `httpx.RequestError` still raises `ProviderRequestError` before any response exists, so no attempt count is reported and nothing is billed.

---

### 6.2 SDK operation payload dataclasses

**File(s):** `vidbyte/lib/dataclasses/operations.py`
**Type:** New file

#### What it does

Defines the provider-neutral payloads the clients return and the tools attach to results — the application-facing half of the two-channel contract.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str | None = None
    published_at: str | None = None
    language: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class SearchPayload:
    provider: str
    query: str
    hits: tuple[SearchHit, ...] = ()
    attempts: int = 1
    billable_units: int = 1

@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    final_url: str
    content: str
    content_type: str
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class FetchPayload:
    provider: str
    pages: tuple[FetchedPage, ...] = ()
    attempts: int = 1
    billable_units: int = 1
```

#### Logic / Algorithm

1. `raw` preserves the undecoded vendor record for each hit and page. This is the escape hatch that stops SDK release cadence from blocking an application that needs a field the SDK has not normalized yet.
2. `billable_units` is the unit count for **one** attempt — pages for Firecrawl, `1` for Brave. `attempts` multiplies it at metering time; the payload never pre-multiplies.
3. `published_at` is an ISO date string, not a `date`, so the payload stays trivially serializable into tool metadata.

#### Edge Cases & Error Handling

- Frozen dataclasses: an application cannot mutate a payload and confuse a later reader.
- A vendor result missing a URL is dropped by the client before it becomes a `SearchHit`; the SDK does not synthesize identifiers.

---

### 6.3 SDK web client base

**File(s):** `vidbyte/tools/builtins/operations/clients/_base.py`
**Type:** New file

#### What it does

Holds the retry/timeout/ceiling configuration and the one JSON request helper both clients share, so neither client reimplements transport policy.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)

class WebOperationClient:
    def __init__(self, api_key: str, *, provider: str, base_url: str, timeout_seconds: float = 15.0, retry: RetryPolicy | None = None, max_response_bytes: int = 2_000_000, transport: HttpTransport | None = None) -> None: ...
    @property
    def max_attempts(self) -> int: ...
    async def request_json(self, operation: str, method: str, *, path: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, query: Mapping[str, str] | None = None) -> tuple[Mapping[str, Any], int]: ...
    def _require_ok(self, operation: str, response: HttpResponse) -> None: ...
    def _decode_object(self, operation: str, response: HttpResponse) -> Mapping[str, Any]: ...
```

#### Logic / Algorithm

`request_json` composes three named steps and returns the decoded object with the attempt count:

1. Build the absolute URL from `base_url` plus `path`, appending a URL-encoded query string when `query` is given (Brave search is a GET; the transport takes no `params`).
2. Delegate to `HttpTransport.request(...)`, passing `retry_count=max_attempts - 1`, the backoff settings, the retryable status set, the timeout, and `max_response_bytes`.
3. `_require_ok` raises `ProviderRequestError` for any non-2xx status, carrying provider, status code, and no body.
4. `_decode_object` parses the body as JSON and raises `ProviderResponseError` unless the result is a JSON object.
5. Return `(payload, response.attempts)`.

#### Edge Cases & Error Handling

- Non-2xx after all retries → `ProviderRequestError` with `status_code`; the caller still knows `attempts` because the tool asks the client for `max_attempts` when no response was produced (Section 6.7 step 5).
- Non-object JSON, or invalid JSON → `ProviderResponseError`, never a silent `{}`. This is what keeps the semgrep `no-untyped-mapping-fallback` rule satisfied: the boundary raises instead of coercing.
- `api_key` is stored on the instance and interpolated only into the header a subclass builds. It never appears in an error, a URL, or a payload.

---

### 6.4 BraveClient

**File(s):** `vidbyte/tools/builtins/operations/clients/brave.py`
**Type:** New file

#### What it does

Calls Brave Search and normalizes ranked web results into a `SearchPayload`.

#### Interface / API

```python
class BraveClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.search.brave.com/res/v1", timeout_seconds: float = 15.0, retry: RetryPolicy | None = None, max_response_bytes: int = 2_000_000, transport: HttpTransport | None = None) -> None: ...
    async def search(self, query: str, *, count: int = 10, language: str = "en") -> SearchPayload: ...
    def _query_params(self, query: str, count: int, language: str) -> dict[str, str]: ...
    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]: ...
    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None: ...
```

#### Logic / Algorithm

1. `search` builds params, issues `GET /web/search`, converts the payload to hits, and returns `SearchPayload(provider="brave", query=..., hits=..., attempts=..., billable_units=1)`.
2. `_query_params` normalizes vendor constraints: collapse whitespace, cap the query at 50 words and 400 characters, clamp `count` to Brave's documented maximum of 20, take the primary language subtag, and set `safesearch=moderate`.
3. `_hits_from_payload` reads `payload["web"]["results"]`, raising `ProviderResponseError` when `web` is present but not an object, and returning an empty tuple when Brave legitimately reports no web block for a query.
4. `_hit_from_result` requires a string `url`, falls back to the URL when `title` is absent, keeps `description` as the snippet, normalizes `page_age`/`age` to a 10-character ISO date when parseable, and stores the whole vendor item in `raw`.
5. `billable_units=1` because Brave's tariff is flat per request.

#### Edge Cases & Error Handling

- A result without a usable URL is skipped, not synthesized.
- An unparseable date becomes `None` rather than raising; a missing date is not a provider failure.
- `count` above 20 or below 1 is clamped, never rejected — the model supplying an out-of-range count must not fail the run.
- **Domain and recency filtering are deliberately absent.** Brave exposes no server-side domain parameter, and which domains a caller wants is application policy. Vidbyte applies both to the payload (Section 6.13).

---

### 6.5 FirecrawlClient

**File(s):** `vidbyte/tools/builtins/operations/clients/firecrawl.py`
**Type:** New file

#### What it does

Calls Firecrawl v2 `/scrape` and normalizes markdown page content into a `FetchPayload`.

#### Interface / API

```python
class FirecrawlClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.firecrawl.dev/v2", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, cache_ms: int = 172_800_000, only_main_content: bool = True, transport: HttpTransport | None = None) -> None: ...
    async def scrape(self, urls: Sequence[str]) -> FetchPayload: ...
    def _scrape_body(self, url: str) -> dict[str, object]: ...
    async def _scrape_one(self, url: str) -> tuple[FetchedPage, int]: ...
    def _page_from_payload(self, url: str, payload: Mapping[str, Any]) -> FetchedPage: ...
```

#### Logic / Algorithm

1. `scrape` iterates the URLs, awaits `_scrape_one` for each, and returns `FetchPayload(provider="firecrawl", pages=..., attempts=<max attempts observed>, billable_units=<len(pages)>)`.
2. `_scrape_body` builds the deterministic request body: `formats=["markdown"]`, `onlyMainContent`, `maxAge=cache_ms`, `blockAds=True` — the same options the deleted Vidbyte adapter used, so cache and content behavior do not regress.
3. `_scrape_one` issues `POST /scrape`, returning the normalized page and that request's attempt count.
4. `_page_from_payload` requires `payload["data"]` to be an object and `data["markdown"]` to be a non-blank string, raising `ProviderResponseError` otherwise; it prefers `metadata.sourceURL` then `metadata.url` for `final_url`, falling back to the requested URL, sets `content_type="text/markdown"`, and stores `data` in `raw`.
5. A longer default timeout (60s) and a larger ceiling (8 MB) than Brave, because a scrape returns page content rather than a result list.

#### Edge Cases & Error Handling

- Empty or whitespace-only markdown is a `ProviderResponseError`, matching the deleted adapter's rule that an empty scrape is a provider failure rather than an empty document.
- An empty `urls` sequence returns a payload with no pages and `billable_units=0`, so nothing is billed for a call that contacted no provider.
- A partial batch failure raises on the first failing URL. **Consequence:** pages already scraped in that call are not billed, because the tool's error path reports `billable_units` for the whole call and the raise loses per-URL progress. This under-bills a partial failure rather than over-billing it, which is the safer direction; Section 12 records it.
- Firecrawl's own retry of a `maxAge`-cached hit costs nothing at the vendor but is indistinguishable from a fresh scrape in the response, so cached pages are still billed. This matches the deleted adapter's behavior.

---

### 6.6 PricedOperationTool — client injection and attempt reporting

**File(s):** `vidbyte/tools/builtins/operations/base.py`
**Type:** Modified

#### What it does

Adds an optional client, an `attempts_used()` hook the runtime reads, and one shared path for turning a client call into a priced result — success or failure.

#### Interface / API

```python
class PricedOperationTool(BaseTool):
    operation: ClassVar[str] = ""
    provider: ClassVar[str] = ""
    _USAGE_KEY: ClassVar[str] = "operation_usage"
    _PAYLOAD_KEY: ClassVar[str] = "operation_payload"

    def __init__(self, *, client: WebOperationClient | None = None) -> None: ...
    def mode_used(self, call: object, result: ToolResult) -> str: ...
    def units_used(self, call: object, result: ToolResult) -> int: ...
    def attempts_used(self, call: object, result: ToolResult) -> int: ...
    def reported_cost_usd(self, call: object, result: ToolResult) -> float | None: ...
    def _contract_result(self, summary: str, *, units: int = 1, mode: str = "default", reported_cost_usd: float | None = None) -> ToolResult: ...
    def _executed_result(self, summary: str, payload: object, *, units: int, mode: str, attempts: int) -> ToolResult: ...
    def _failed_result(self, message: str, *, units: int, mode: str, attempts: int, error: str) -> ToolResult: ...
    def _usage_metadata(self, *, units: int, mode: str, attempts: int, reported_cost_usd: float | None = None) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. `__init__` stores the client; `client=None` keeps every existing zero-argument construction working.
2. `attempts_used` reads `operation_usage["attempts"]`, returning `1` for any missing, non-integer, boolean, or non-positive value.
3. `units_used` and `mode_used` keep their current reading behavior; `_usage_metadata` gains the `attempts` key.
4. `_executed_result` builds a success result with the model-facing summary in `output`, the typed payload under `_PAYLOAD_KEY`, and the usage annotation under `_USAGE_KEY`.
5. `_failed_result` builds an error result that **still carries the usage annotation**, so exhausted retries remain billable, plus an `error` code for the agent.
6. `_contract_result` is unchanged in behavior and now records `attempts=1`.

#### Edge Cases & Error Handling

- A subclass that forgets `attempts` bills one attempt — the current behavior, so the change cannot silently over-bill.
- `attempts=0` or a negative value normalizes to `1` on the success path; the "bill nothing" case is expressed with `units=0`, not `attempts=0`, and is checked by the runtime (Section 6.9).
- The payload is stored as a dataclass instance, not JSON. Nothing in the runtime serializes tool metadata, and the Vidbyte consumer wants the typed object.

---

### 6.7 BraveSearchTool executes

**File(s):** `vidbyte/tools/builtins/operations/search.py`
**Type:** Modified

#### What it does

Runs a real Brave search when a client is injected, and renders a compact summary for the model while handing the structured payload to the application.

#### Interface / API

```python
class BraveSearchTool(PricedOperationTool):
    operation = "search"
    provider = "brave"
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _render(self, payload: SearchPayload) -> str: ...
```

#### Logic / Algorithm

1. `spec()` is unchanged — `query` required, `count` optional with default 10 — so no agent YAML or prompt changes.
2. When `self._client is None`, return `_contract_result(f"brave search: {query}", units=1)`; behavior identical to today.
3. Read `query` and `count` from the call, clamping a non-integer or out-of-range `count` to the spec default.
4. `await self._client.search(query, count=count)`.
5. On `ProviderRequestError` or `ProviderResponseError`, return `_failed_result("brave search failed.", units=1, mode="default", attempts=self._client.max_attempts, error="search_failed")` — the client raised without reporting attempts, so the tool bills the full configured attempt budget, which is what the retry policy actually spent.
6. On success, `_executed_result(self._render(payload), payload, units=payload.billable_units, mode="default", attempts=payload.attempts)`.
7. `_render` produces a compact numbered list of title, URL, and truncated snippet — token-bounded prose, not JSON, because the model reads `output`.

#### Edge Cases & Error Handling

- Zero hits is a success with an empty list and one billable attempt: Brave charges for the request regardless.
- An empty query string fails `validate_call` through the existing required-parameter check before `execute` runs, so nothing is billed.
- The other six search tools in this file are untouched and keep returning contract stubs.

---

### 6.8 FirecrawlFetchTool executes

**File(s):** `vidbyte/tools/builtins/operations/fetch.py`
**Type:** Modified

#### What it does

Scrapes real pages when a client is injected, billing per page and per attempt.

#### Interface / API

```python
class FirecrawlFetchTool(PricedOperationTool):
    operation = "fetch"
    provider = "firecrawl"
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _render(self, payload: FetchPayload) -> str: ...
```

#### Logic / Algorithm

1. `spec()` is unchanged — optional `url`, optional `urls`.
2. Resolve the target URL list from `urls` when it is a list or tuple, else from a single `url`, else an empty list.
3. When the list is empty, return `_failed_result("firecrawl fetch requires a url.", units=0, mode="scrape", attempts=0, error="missing_url")` — `units=0` is the explicit "bill nothing" signal.
4. When `self._client is None`, return `_contract_result("firecrawl scrape", units=len(urls), mode="scrape")`.
5. `await self._client.scrape(urls)`, then `_executed_result(self._render(payload), payload, units=payload.billable_units, mode="scrape", attempts=payload.attempts)`.
6. On provider error, `_failed_result(..., units=len(urls), mode="scrape", attempts=self._client.max_attempts, error="fetch_failed")`.
7. `_render` lists each page's final URL with its character count; page content itself goes to the application through the payload, not into the model's context by default.

#### Edge Cases & Error Handling

- `mode="scrape"` matches the `("fetch", "firecrawl", "scrape")` pricebook key; `"default"` carries the identical rate, so a mode typo cannot change the price.
- `DirectHttpFetchTool` and the three other fetch tools are untouched.

---

### 6.9 AgentRuntime — per-attempt metering

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Records one priced operation per declared provider attempt, and meters a failed priced call that actually reached the provider.

#### Interface / API

```python
def _record_operation_usage(self, tool: object, call: ToolCall, result: ToolResult) -> None: ...
def _billable_attempts(self, tool: PricedOperationTool, call: ToolCall, result: ToolResult) -> int: ...
```

#### Logic / Algorithm

1. Return immediately when the tool is not a `PricedOperationTool`.
2. `_billable_attempts` reads `units_used` and `attempts_used`; it returns `0` when either is below 1, and when the result is a failure that carries no `operation_usage` annotation.
3. Return when `_billable_attempts` is `0` — this is the "never reached the provider" case and the unchanged behavior for stub tools that error.
4. Otherwise loop `attempts` times, calling `usage_tracker.record_operation(tool.operation, tool.provider, mode=..., units=..., reported_cost_usd=...)` once per iteration.
5. Keep the existing `try/except` that swallows hook errors, so a pricing bug can still never break tool execution.

#### Edge Cases & Error Handling

- Successful contract-stub tools: `attempts=1`, `units>=1` → one record, byte-identical to today's behavior.
- Failed stub tools (`DirectHttpFetchTool` on a dead URL): no `operation_usage` annotation on the error result → nothing recorded, unchanged. `direct_http` is a zero-cost tariff regardless.
- `units=0` on an error result → nothing recorded, which is how "missing url" bills nothing.
- The loop bounds itself on `attempts`, which `attempts_used` already normalizes to a positive integer, so a malformed annotation cannot produce an unbounded loop.

---

### 6.10 SDK exports

**File(s):** `vidbyte/tools/builtins/operations/clients/__init__.py` (new), `vidbyte/tools/builtins/operations/__init__.py` (modified), `vidbyte/lib/dataclasses/__init__.py` (modified)
**Type:** New + Modified

#### What it does

Makes the clients, the retry policy, and the payload types importable from stable paths.

#### Interface / API

```python
from vidbyte.tools.builtins.operations import BraveClient, FirecrawlClient, RetryPolicy, WebOperationClient
from vidbyte.lib.dataclasses import FetchPayload, FetchedPage, SearchHit, SearchPayload
```

#### Logic / Algorithm

1. `clients/__init__.py` re-exports `WebOperationClient`, `RetryPolicy`, `BraveClient`, `FirecrawlClient`.
2. `operations/__init__.py` adds those four names to its imports and `__all__`, keeping the existing twelve tool exports and their ordering.
3. `lib/dataclasses/__init__.py` adds the four payload types.

#### Edge Cases & Error Handling

- Purely additive; no existing import path changes. The package CI stage imports the installed wheel and will catch a missing re-export.

---

### 6.11 Vidbyte — delete the duplicated vendor adapters

**File(s):** `backend/provider/web/brave.py`, `firecrawl.py`, `client.py`, `base.py`, `__init__.py`, `README.md`
**Type:** Deleted (4 files) + Modified (2 files)

#### What it does

Removes the vendor code the SDK now owns, and keeps the egress guard the SDK deliberately does not own.

#### Logic / Algorithm

1. Delete `brave.py` (118 lines), `firecrawl.py` (76), `client.py` (67), and `base.py` (43). The `SearchProvider`/`ContentProvider` protocols go with `base.py`: their only implementations are being deleted, and their consumers now depend on concrete SDK clients.
2. Keep `url_safety.py` unchanged — DNS-resolving SSRF defense is a property of the deployment's network position, not of any vendor.
3. Rewrite `__init__.py` to export only `validate_public_url`.
4. Update `README.md`: the folder's remaining responsibility is egress safety, and its non-goals gain "do not add vendor HTTP clients; the SDK owns provider transport and normalization."

#### Edge Cases & Error Handling

- `lib/dtos/providers.py` keeps `SearchRequestDto`, `SearchHitDto`, `SearchResponseDto`, `FetchRequestDto`, `FetchedDocumentDto`. They stay as the *application's* capability contract — `SearchRequestDto`'s domain normalization and disjointness validator are research policy — but they are now populated from SDK payloads rather than from vendor JSON. Their header's `RELATED DOCS`/`TESTS` lines are updated.

---

### 6.12 Vidbyte — construct SDK clients in the worker composition root

**File(s):** `backend/services/harnesses/research/deps.py`
**Type:** Modified

#### What it does

Builds `BraveClient` and `FirecrawlClient` from Vidbyte-loaded credentials instead of assembling vendor adapters over a bounded HTTP client.

#### Interface / API

```python
class ResearchDependencies:
    search_client: BraveClient | None
    content_client: FirecrawlClient | None
```

#### Logic / Algorithm

1. Replace the `provider.web` imports with `from vidbyte.tools.builtins.operations import BraveClient, FirecrawlClient, RetryPolicy`.
2. In `build()`, construct `BraveClient(require_brave_api_key(), retry=RetryPolicy(max_attempts=self.config.search.max_attempts))` and `FirecrawlClient(require_firecrawl_api_key(), retry=RetryPolicy(max_attempts=self.config.limits.fetch_max_attempts))`, reading attempt budgets from the already-validated research policy rather than hardcoding them.
3. Delete the two `BoundedJsonHttpClient` constructions. The shared `httpx.AsyncClient` remains only if another dependency still needs it; if not, it is removed with its lifecycle hooks.
4. Rename the attributes from `search_provider`/`content_provider` to `search_client`/`content_client` so no reader mistakes them for the deleted protocols.

#### Edge Cases & Error Handling

- Both `require_*_api_key()` calls keep raising when the harness is enabled without credentials — fail-closed at the worker boundary is unchanged.
- If `config.search.max_attempts` / `config.limits.fetch_max_attempts` do not exist on `ResearchHarnessConfigDto`, they are added to the DTO and to `services/harnesses/research/config.yaml`. Adding a required key changes `spec_id`, which is acceptable inside PR #284 because that PR already reshaped the config; it must not be done as a standalone change to a released config.

---

### 6.13 Vidbyte — search payload consumer

**File(s):** `backend/services/harnesses/research/operations.py`
**Type:** Modified

#### What it does

Replaces `ResearchSearchExecutor` (an SDK executor callable) with `ResearchSearchCandidates` (a consumer of the SDK's search payload). All the research policy that made the old class valuable is retained; only the vendor call and the billing side effect leave.

#### Interface / API

```python
class ResearchSearchCandidates:
    def __init__(self, *, ledger: ResearchDiscoveryLedger, request: ResearchRequest, visited_hashes: set[str], max_candidates: int) -> None: ...
    def consume(self, payload: SearchPayload) -> tuple[ResearchSource, ...]: ...
    def selected_sources(self, urls: list[str]) -> list[ResearchSource]: ...
    def _sources_from_payload(self, payload: SearchPayload) -> Iterator[ResearchSource]: ...
    def _is_admissible(self, source: ResearchSource, published_at: date | None) -> bool: ...
```

#### Logic / Algorithm

1. `consume` maps payload hits to `ResearchSource` values, filters them, records the survivors as candidates, offers their URLs to the discovery ledger, and returns them.
2. `_sources_from_payload` builds each `ResearchSource` with `provider=payload.provider`, `kind=ResearchSourceKind.WEB`, and metadata carrying the hit language — the same mapping as today.
3. `_is_admissible` applies the four policy rules that used to live in `brave.py` and the old executor together: the host must satisfy `include_domains`/`exclude_domains`, `published_at` must not precede `request.published_after`, the canonical URL hash must be neither visited nor already a candidate, and the candidate count must be below `max_candidates`.
4. `selected_sources` is unchanged.
5. The class no longer touches `UsageSession` or `BillableOperationScope`, and no longer builds a `ToolResult`.

#### Edge Cases & Error Handling

- Domain filtering moves here from the deleted `brave.py:_domain_allowed` with identical semantics: exact host match or dot-suffix match, include-then-exclude.
- Recency filtering moves here from `brave.py:_normalize_hit`: a hit with no parseable date is excluded when `published_after` is set, matching today.
- The class has no `fatal_error` field. Wallet errors no longer originate inside a tool call, so the harness observes them directly at its own `reconcile()` call instead of recovering them from an executor.

---

### 6.14 Vidbyte — harness wiring

**File(s):** `backend/services/harnesses/research/harness.py`
**Type:** Modified

#### What it does

Injects the SDK client into the tool, consumes the payload after each search, and keeps the model's view of results identical to today.

#### Logic / Algorithm

1. Replace `from provider.web import ContentProvider, SearchProvider` with the SDK client imports; change the constructor parameters to `search_client: BraveClient` and `content_client: FirecrawlClient`.
2. Construct `candidates = ResearchSearchCandidates(...)` and `search_tool = BraveSearchTool(client=self._search_client)`.
3. Wrap the tool so each successful call feeds the payload through `candidates.consume(...)` and rewrites the model-facing `output` to the admitted candidates only — preserving today's invariant that the model never sees a duplicate, an over-cap, or a policy-excluded source. The wrapper is the harness's own thin `BaseTool` subclass delegating to the SDK tool, so the SDK tool's `spec()`, `operation`, `provider`, and usage annotation stay authoritative and the runtime still meters it.
4. `persist_selected` continues to call `candidates.selected_sources(urls)`.
5. Authorize before the discovery agent runs with `units × max_attempts` so a retried search cannot overdraw the reservation.

#### Edge Cases & Error Handling

- The wrapper must preserve `metadata` so the runtime's `_record_operation_usage` still reads `operation_usage`. It rewrites `output` only.
- Because the wrapper subclasses the SDK tool rather than reimplementing it, `isinstance(tool, PricedOperationTool)` remains true and metering is unaffected.
- A failed search returns the SDK's error result to the model; the harness does not translate it into a run failure, matching today's behavior for a provider hiccup.

---

### 6.15 Vidbyte — deterministic extraction through FirecrawlClient

**File(s):** `backend/services/harnesses/research/extraction.py`
**Type:** Modified

#### What it does

Fetches one source's content through the SDK client and records the fetch operation with real page and attempt counts — the one legitimate manual meter.

#### Logic / Algorithm

1. Replace `ContentProvider` with `FirecrawlClient`; keep `validate_public_url(source.url)` immediately before the call.
2. Keep `BillableOperationScope` for pre-call authorization, passing `authorization_multiplier=self._content_client.max_attempts` so the reservation covers every attempt the retry policy may make.
3. `payload = await self._content_client.scrape([source.url])`, then record usage once per attempt through `UsageSession.record_operation_attempt("fetch", "firecrawl", mode="scrape", units=payload.billable_units, attempts=payload.attempts)`.
4. Read `payload.pages[0]` for `content`, `content_type`, and `final_url`; keep the existing `extraction_max_chars` rejection and the `fetched_at` status field, generating the timestamp locally now that the payload carries no clock.
5. Keep every status transition, artifact upsert, and publication rule unchanged.

#### Edge Cases & Error Handling

- A `ProviderRequestError` or `ProviderResponseError` from the client is caught where the old `ContentProvider` failure was caught, so the source is marked failed exactly as today.
- Attempts are still billed when the fetch ultimately fails, because `record_operation_attempt` is called from the error path with `attempts=self._content_client.max_attempts`.
- `validate_public_url` stays even though Firecrawl performs the egress: it prevents Vidbyte from paying a vendor to fetch a private address on a caller's behalf.

---

### 6.16 Vidbyte — one meter

**File(s):** `backend/services/usage/session.py`, `backend/lib/usage/ledger.py`, `backend/services/usage/adapters/sdk_middleware.py`, `backend/services/usage/operation_scope.py`
**Type:** Modified

#### What it does

Collapses the two competing meters into the agent's single `UsageTracker`, read as a rollup.

#### Interface / API

```python
class UsageSession:
    def apply_agent_usage(self, rollup: UsageRollup) -> None: ...
    def record_operation_attempt(self, operation: str, provider: str, *, mode: str = "default", units: int = 1, attempts: int = 1) -> None: ...

class UsageLedger:
    def apply_rollup(self, rollup: UsageRollup) -> None: ...
```

#### Logic / Algorithm

1. `UsageSession.__init__` drops the `tracker` parameter and `self._tracker`; `record_model_response` is deleted.
2. `apply_agent_usage` raises `UsageModelPricingError` when `rollup.cost_complete` is false, then delegates to `UsageLedger.apply_rollup` — one fail-closed check spanning both the token and operation axes, replacing the per-record `cost_usd is None` checks.
3. `UsageLedger.apply_rollup` iterates `rollup.calls` through `_apply_model` and `rollup.operations` through `_apply_operation`. `apply` is retained for the manual fetch path.
4. `record_operation_attempt` gains `attempts` and constructs one record per attempt against a tracker it creates for that purpose only — the deterministic fetch path has no agent and therefore no agent tracker. This is the single documented manual meter.
5. `WalletModelUsageMiddleware.after_model_response` is deleted; `before_model_call` is unchanged.
6. `BillableOperationScope.record_attempt` is deleted. `__aenter__` keeps authorizing and now multiplies by the attempt budget. `__aexit__` reconciles when the scope was entered rather than when an attempt was recorded.

#### Edge Cases & Error Handling

- The harness calls `apply_agent_usage(agent.get_usage())` after every `generate_reply`. This is safe precisely because `BaseAgent._usage_tracker.reset()` fires at the top of every reply (`vidbyte/agents/base.py:578`), so each read is exactly that call's usage — no watermark, no double count.
- `UsageSnapshot`'s shape, field names, and `pricebook_version` are unchanged, so in-flight runs resume without migration. `search_calls` and `fetch_calls` now count provider attempts rather than logical calls; both are monotonic counters with no validation coupling, so a run that began before the change resumes correctly.
- `record_operation_attempt` keeps raising `UsageOperationPricingError` when the SDK cannot price the operation.

---

### 6.17 Vidbyte — existing tests whose subject is deleted

**File(s):** `backend/tests/features/research_harness_platform/test_provider_contracts.py`, `test_usage_domain.py`, `test_extraction_contract.py`, `test_architecture_contracts.py`
**Type:** Modified (3) + Deleted (1)

#### What it does

Keeps the existing suite passing without adding new test files.

#### Logic / Algorithm

1. Delete `test_provider_contracts.py`. Its entire subject — `BraveSearchProvider`, `FirecrawlContentProvider`, `BoundedJsonHttpClient` — is deleted. It is replaced by nothing in this PR; SDK-side coverage of the clients is a follow-up per the no-tests scope.
2. `test_usage_domain.py`: update the cases that drive `UsageSession.record_model_response` and `BillableOperationScope.record_attempt` to drive `apply_agent_usage` and the new `record_operation_attempt` signature.
3. `test_extraction_contract.py`: keep both `validate_public_url` patches; replace the `ContentProvider` double with a `FirecrawlClient` double returning a `FetchPayload`.
4. `test_architecture_contracts.py`: update any import-boundary assertion naming `provider.web` members that no longer exist.

#### Edge Cases & Error Handling

- If any assertion encodes "one search call bills one unit", it becomes "one search call with one attempt bills one unit" — the attempt dimension must be explicit or the test will pass for the wrong reason.

---

### 6.18 Vidbyte — SDK pin

**File(s):** `backend/requirements.txt`
**Type:** Modified

#### What it does

Moves the pin off the unmerged `feat/pr-284-operation-executor` branch onto the merge commit of this design's SDK PR.

#### Logic / Algorithm

1. Replace `vidbyte-sdk @ git+https://github.com/cerredz/Vidbyte-SDK.git@6998a92` with the same URL at the new merge commit on `main`.
2. `lib/enums/research.py:ResearchPricebookVersion.V1` derives from `PRICING_AS_OF` and `OPERATION_PRICING_AS_OF`, neither of which this change touches, so `pricebook_version` is stable and in-flight runs are not invalidated.

#### Edge Cases & Error Handling

- The Vidbyte half cannot merge before the SDK half. Section 11 records the ordering.

---

## 7. Data Model Changes

### 7.1 `UsageSnapshot` (Vidbyte, `backend/lib/usage/ledger.py`)

**Change type:** Modified semantics, unmodified schema

```python
class UsageSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    search_calls: int = Field(default=0, ge=0)   # now counts provider ATTEMPTS
    fetch_calls: int = Field(default=0, ge=0)    # now counts pages × attempts
    accrued_millicents: int = Field(default=0, ge=0)
    billed_cents: int = Field(default=0, ge=0)
    pricebook_version: str = USAGE_PRICING_VERSION
```

**Migration strategy:**

- Forward: none. No field is added, removed, or retyped, and `pricebook_version` is unchanged, so the resume guard in `_validated` continues to accept existing snapshots.
- Rollback: none required. A snapshot written after this change remains readable by the previous code; the counters would simply have been incremented on a different definition. Both are monotonic and neither is used as a divisor or a limit.

### 7.2 `HarnessRun.usage` (MongoDB)

**Change type:** Unchanged

`HarnessRun.usage` remains the same bounded aggregate document. Per the field guide, no SDK per-call record is persisted and no new collection is introduced.

### 7.3 SDK payload dataclasses

**Change type:** New, in-memory only

`SearchPayload`, `SearchHit`, `FetchPayload`, `FetchedPage` are frozen dataclasses passed through tool metadata. Nothing persists them.

### 7.4 `ResearchHarnessConfigDto` (Vidbyte)

**Change type:** Modified

Adds `search.max_attempts: int` and `limits.fetch_max_attempts: int`, with matching keys in `backend/services/harnesses/research/config.yaml`.

**Migration strategy:**

- Forward: both keys are added to the reviewed `config.yaml` in the same commit, so `extra="forbid"` validation and `spec_id` derivation stay consistent within PR #284.
- Rollback: reverting the DTO and the YAML together restores the previous `spec_id`.

---

## 8. API Changes

N/A — no HTTP endpoint, request shape, response shape, or status code changes. `POST /research/run` and every public API surface keep their contracts. The changes are confined to the SDK's Python surface, the research worker's internals, and the usage domain.

---

## 9. File Change Manifest

### vidbyte-sdk (branch `feat/executing-priced-web-operation-tools`, base `main`)

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/executing-priced-web-operation-tools.md` | This design doc; first commit on the branch |
| CREATE | `vidbyte/lib/dataclasses/operations.py` | `SearchHit`, `SearchPayload`, `FetchedPage`, `FetchPayload` |
| CREATE | `vidbyte/tools/builtins/operations/clients/__init__.py` | Client package exports |
| CREATE | `vidbyte/tools/builtins/operations/clients/_base.py` | `WebOperationClient`, `RetryPolicy` |
| CREATE | `vidbyte/tools/builtins/operations/clients/brave.py` | `BraveClient` |
| CREATE | `vidbyte/tools/builtins/operations/clients/firecrawl.py` | `FirecrawlClient` |
| CREATE | `vidbyte/tools/builtins/operations/clients/README.md` | Folder intent and non-goals, matching repo convention |
| MODIFY | `vidbyte/lib/http/transport.py` | `HttpResponse.attempts`; optional `max_response_bytes` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export the four payload types |
| MODIFY | `vidbyte/tools/builtins/operations/base.py` | Client injection, `attempts_used`, `_executed_result`, `_failed_result` |
| MODIFY | `vidbyte/tools/builtins/operations/search.py` | `BraveSearchTool` executes through `BraveClient` |
| MODIFY | `vidbyte/tools/builtins/operations/fetch.py` | `FirecrawlFetchTool` executes through `FirecrawlClient` |
| MODIFY | `vidbyte/tools/builtins/operations/__init__.py` | Export clients and `RetryPolicy` |
| MODIFY | `vidbyte/agents/runtime.py` | Per-attempt metering; meter declared failures |

### vidbyte (existing branch `ai/resolve-pr-281-review-comments`, PR #284)

| Action | File Path | Reason |
|--------|-----------|--------|
| DELETE | `backend/provider/web/brave.py` | SDK `BraveClient` owns Brave transport and normalization |
| DELETE | `backend/provider/web/firecrawl.py` | SDK `FirecrawlClient` owns Firecrawl transport and normalization |
| DELETE | `backend/provider/web/client.py` | SDK transport owns bounded JSON I/O |
| DELETE | `backend/provider/web/base.py` | Capability protocols have no remaining implementations |
| DELETE | `backend/tests/features/research_harness_platform/test_provider_contracts.py` | Subject deleted |
| MODIFY | `backend/provider/web/__init__.py` | Export only `validate_public_url` |
| MODIFY | `backend/provider/web/README.md` | Folder narrows to egress safety; new non-goal |
| MODIFY | `backend/lib/dtos/providers.py` | Header doc/test references; DTOs now fed from SDK payloads |
| MODIFY | `backend/services/harnesses/research/deps.py` | Construct `BraveClient`/`FirecrawlClient`; drop bounded HTTP clients |
| MODIFY | `backend/services/harnesses/research/operations.py` | `ResearchSearchExecutor` → `ResearchSearchCandidates` |
| MODIFY | `backend/services/harnesses/research/harness.py` | Inject client, consume payload, authorize for max attempts |
| MODIFY | `backend/services/harnesses/research/extraction.py` | Fetch through `FirecrawlClient`; attempt-accurate fetch metering |
| MODIFY | `backend/services/harnesses/research/config.yaml` | `search.max_attempts`, `limits.fetch_max_attempts` |
| MODIFY | `backend/lib/dtos/research.py` | Same two config keys on the DTO |
| MODIFY | `backend/services/usage/session.py` | Drop the second tracker; add `apply_agent_usage` |
| MODIFY | `backend/lib/usage/ledger.py` | `apply_rollup` |
| MODIFY | `backend/services/usage/adapters/sdk_middleware.py` | Delete `after_model_response` |
| MODIFY | `backend/services/usage/operation_scope.py` | Delete `record_attempt`; authorize for max attempts |
| MODIFY | `backend/requirements.txt` | Re-pin the SDK off the unmerged branch |
| MODIFY | `backend/tests/.../test_usage_domain.py` | New session/scope signatures |
| MODIFY | `backend/tests/.../test_extraction_contract.py` | `FirecrawlClient` double returning `FetchPayload` |
| MODIFY | `backend/tests/.../test_architecture_contracts.py` | Import-boundary assertions for deleted members |

**Totals:** 7 created, 14 modified in the SDK. 5 deleted, 18 modified in Vidbyte. **7 created, 32 modified, 5 deleted.**

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `httpx` | `>=0.27`, already a SDK dependency | Async transport under `HttpTransport` | None new |
| `pydantic` | `>=2,<3`, already a SDK dependency | Not required by the new clients (frozen dataclasses + explicit raises) | None |
| Brave Search API | `https://api.search.brave.com/res/v1/web/search` | Web search | Field renames break `_hit_from_result`; `raw` preserves the vendor record so an application can recover without an SDK release |
| Firecrawl v2 | `https://api.firecrawl.dev/v2/scrape` | Page → markdown | Same; plus a `maxAge` cache hit is billed as a scrape |
| SDK pricebook | `OPERATION_PRICING`, `2026-07-24` | Rates for both operations | Unchanged by this design |

---

## 11. Rollout & Deployment

**Feature flags.** No new flag. `CREDENTIALS.research_harness_enabled` continues to gate the whole harness at both the API and worker boundaries.

**Breaking changes.** None for SDK consumers: every priced tool still constructs with no arguments and still returns a contract stub without a client. Inside Vidbyte, `provider.web`'s vendor exports are removed, and the four modules that imported them are updated in the same commit.

**Deployment order.**

1. Merge the SDK PR into `Vidbyte-SDK` `main`. Nothing consumes the new surface yet, so this is independently safe.
2. Re-pin `backend/requirements.txt` to that merge commit on the PR #284 branch.
3. Land the Vidbyte changes on `ai/resolve-pr-281-review-comments` (PR #284). API and worker deploy together; the API path does not touch provider clients, so there is no cross-service version window.

**Rollback.** Revert the Vidbyte commits and restore the previous pin. The SDK change is additive and can stay merged. `UsageSnapshot` is schema-compatible in both directions, so an in-flight run is not stranded by a rollback.

**Verification before the PR.** From the SDK worktree, per the field guide: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH`, then the full `python scripts/run_ci.py`. `git add -A` before the semgrep static-policy scan, since it only reads git-tracked files. On the Vidbyte side, the repository's `ruff` and `pytest` gates plus the PR checks on #284.

---

## 12. Open Questions

- [ ] **Retryable statuses may not be vendor-charged.** The requirement is explicit that retries count toward usage, and this design bills every attempt that produced an HTTP response. But a `429` means the vendor rejected the request, and a `503` usually is not billed either, so attempt-accurate billing can over-bill relative to the vendor's own invoice. Recommendation: ship as specified, then reconcile against a real Brave/Firecrawl invoice and, if they diverge, narrow the billable set to statuses the vendor actually charges for — a one-line change in `_billable_attempts` because the policy has exactly one home.
- [ ] **A partial Firecrawl batch failure under-bills.** `_scrape_one` raises on the first failing URL, so pages already scraped in that call are not billed (Section 6.5). Accepted for now because it errs toward the customer. Fixing it means returning partial payloads instead of raising, which changes the client's error contract.
- [ ] **`RetryPolicy.max_attempts` default of 3.** Chosen to match common practice and the transport's existing retryable-status set. Worth confirming against Brave's and Firecrawl's rate limits before merge, since a wallet reservation now scales with it.
- [ ] **Which `max_attempts` the research config should declare.** Section 6.12 reads it from `ResearchHarnessConfigDto`; the actual reviewed values in `config.yaml` need a decision.
- [ ] **`field-guide/vidbyte-sdk/priced-operation-execution.md` is superseded.** It prescribes the executor seam this design retires. It should be rewritten to the new principle — "the SDK owns provider transport and normalization; applications inject credentials and consume typed payloads" — with this PR as evidence. Not part of the code change.
- [ ] **SDK-side coverage for the two clients.** Out of scope under "no tests." The natural follow-up is recorded-fixture tests so CI never needs live keys.

---

## 13. Alternatives Considered

### Alternative 1: Merge the `executor=` seam as-is

- **What:** Open the SDK PR for `feat/pr-284-operation-executor` unchanged, keeping the application-supplied executor callable and leaving all provider code in Vidbyte.
- **Why rejected:** It leaves the SDK at roughly 7% of the search path (about 20 lines against 287) and keeps a rate table for twelve providers the SDK cannot call. It also forces the application to satisfy a `ToolResult` contract just to make an HTTP request, and — per Finding 3 — the seam explicitly cannot report units, so attempt-accurate billing is not expressible through it. Merging it would mean paying the migration twice.

### Alternative 2: Sum retry units into one operation record

- **What:** Keep one `record_operation` per tool call and pass `units = units_per_attempt × attempts`.
- **Why rejected:** Finding 1. Brave's tariff is `usd_fixed=0.005, usd_per_unit=0.0`, so `cost_usd(3)` equals `cost_usd(1)`. This silently under-bills every retried search while making the `search_calls` counter look correct — the worst possible failure shape for a billing change.

### Alternative 3: Meter every failed priced tool call

- **What:** Delete the `result.status.value != "success"` guard in `_record_operation_usage` outright.
- **Why rejected:** Too broad. It would bill calls that never reached a provider — unknown tool, permission denied, missing arguments — and would change billing for the ten providers still returning contract stubs. Gating on a declared `operation_usage` annotation with positive units bills exactly the attempts that happened.

### Alternative 4: Intercept the payload with `after_tool_call` middleware

- **What:** Let the SDK tool return the raw payload to the model, and have Vidbyte apply dedup, caps, and ledger offers in an `AgentMiddleware.after_tool_call` hook.
- **Why rejected:** The hook exists (`vidbyte/middleware/base.py:62`) and would work, but it puts research policy in a component ordered against every other middleware, and it must mutate a result the model has conceptually already received. A thin harness-owned subclass of the SDK tool keeps the ordering obvious, keeps `isinstance(tool, PricedOperationTool)` true so metering is untouched, and is fewer moving parts.

### Alternative 5: A new bounded HTTP client in the SDK instead of extending `HttpTransport`

- **What:** Port Vidbyte's `BoundedJsonHttpClient` into the SDK as a separate layer, leaving `HttpTransport` untouched.
- **Why rejected:** It duplicates the retry loop that `HttpTransport.request` already implements, and leaves the SDK with two HTTP policies. Two additive, defaulted parameters on the existing transport is the smaller change and benefits every future SDK client. The risk — touching a shared primitive — is contained because both parameters default to today's exact behavior.

### Alternative 6: Port all twelve providers in this change

- **What:** Give every search and fetch tool a real client at once.
- **Why rejected:** The user asked for minimal changes, and the two-channel result contract plus the retry/billing policy are unproven. Brave (flat-fixed) and Firecrawl (per-unit) between them exercise both tariff shapes, which is the smallest set that validates the design. The remaining ten port mechanically once the shape is settled.

---

END OF DESIGN DOC

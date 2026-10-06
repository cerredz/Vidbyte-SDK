# Design Doc: Exa Search Date Normalization and Optional Highlights

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-07
**Last Updated:** 2026-08-07

---

## 1. Overview

`SearchHit.published_at` has no documented format, and the executing search clients
disagree about what they put there: `BraveClient` normalizes to a bare ISO date
(`YYYY-MM-DD`), while `ExaClient` and `TavilyClient` pass the vendor timestamp
through untouched. Any consumer that calls `date.fromisoformat` on the field works
against Brave and silently fails against Exa. This change makes the contract explicit,
moves normalization onto `WebOperationClient` so all three clients share one
implementation, and adds an opt-in `include_highlights` mode to `ExaClient` so a caller
that needs snippet text can request Exa's `contents.highlights` block — with matching
pricebook entries so the extra content charge is metered rather than silently absorbed
by the existing search rate.

---

## 2. Goals & Non-Goals

### Goals

- Give `SearchHit.published_at` one documented format (`YYYY-MM-DD`) that every
  executing client honors.
- Move the date-normalization helper onto `WebOperationClient` and use it from
  `BraveClient`, `ExaClient`, and `TavilyClient`.
- Add an opt-in `include_highlights` flag to `ExaClient` that requests Exa's
  `contents.highlights` block and surfaces it as `SearchHit.snippet`.
- Add an opt-in `max_results` transport ceiling to `ExaClient`, symmetric with the
  existing `max_response_bytes`, so an embedding application can bound per-result
  billing exposure.
- Register `("search", "exa", "<type>+highlights")` pricebook entries so the content
  charge is priced rather than resolved away by the registry's `default` fallback.

### Non-Goals

- No change to default behavior for any existing SDK consumer. `include_highlights`
  defaults to `False` and `max_results` defaults to today's `_MAX_RESULTS = 100`.
- No change to `ExaSearchTool.spec()`. The tool's model-facing schema stays
  SDK-authoritative per the `priced-operation-execution` field-guide entry.
- No new Exa capability (`/answer`, `/contents`, `/findsimilar`). Only `/search`.
- No repricing of any existing `(operation, provider, mode)` triple.
- No change to `ParallelClient` or `BrowserbaseClient`, which never populate
  `published_at`.

---

## 3. Background & Context

The Vidbyte research harness is switching its discovery provider from Brave to Exa.
That migration surfaced two defects in the SDK that are invisible while Brave is the
only search provider in production use.

**Current state — dates.** `BraveClient._published_date` slices the vendor value to ten
characters and round-trips it through `date.fromisoformat` before storing it. `ExaClient`
stores Exa's `publishedDate` verbatim, which is a full ISO timestamp
(`2023-05-01T00:00:00.000Z`). On Python 3.11 — the SDK's floor — `date.fromisoformat`
rejects that string:

```
'2023-05-01'                 -> 2023-05-01
'2023-05-01T00:00:00.000Z'   -> ValueError: Invalid isoformat string
```

`TavilyClient` has the same untreated passthrough on `published_date`.

**Current state — snippets.** `ExaClient._search_body` requests results only, with the
comment *"a contents block would add per-content-type charges."* That is a correct
default, but it means `SearchHit.snippet` is always `None` for Exa, because Exa's
`/search` returns no text without an explicit `contents` block. A consumer that
selects results on snippet quality gets nothing to select on.

**Constraint — the registry does not fail closed.** `OperationPricingRegistry.resolve`
falls back to the provider's `"default"` mode when an exact triple is missing:

```python
exact = self._table.get((operation, provider, mode))
if exact is not None:
    return exact
return self._table.get((operation, provider, "default"))
```

So introducing a `"+highlights"` mode string without a matching table entry would not
raise — it would silently price highlighted searches at the non-highlighted rate. The
pricebook entries are therefore a correctness requirement of the highlights flag, not
a follow-up.

---

## 4. Requirements

### Functional Requirements

1. `SearchHit.published_at` is documented as a bare ISO-8601 date, `YYYY-MM-DD`, or `None`.
2. `WebOperationClient` exposes a shared static helper that converts an arbitrary vendor
   date-ish string to that format, returning `None` for anything unparseable.
3. `BraveClient._hit_from_result` produces identical output to today via the shared helper.
4. `ExaClient._hit_from_result` normalizes `publishedDate` through the shared helper.
5. `TavilyClient._hit_from_result` normalizes `published_date` through the shared helper.
6. `ExaClient.__init__` accepts `include_highlights: bool = False`. When `False`, the
   request body is byte-identical to today's.
7. When `include_highlights=True`, `_search_body` adds a `contents.highlights` block, and
   `_hit_from_result` prefers the joined `highlights` array over `text`/`snippet`.
8. `ExaClient` exposes an `includes_highlights` read-only property.
9. `ExaClient.__init__` accepts `max_results: int = 100`, clamping `numResults` to
   `min(max(1, num_results), max_results)`.
10. `ExaSearchTool.execute` appends `+highlights` to the billing mode when the bound
    client reports `includes_highlights`, for both the success and failure result paths.
11. `OPERATION_PRICING` gains one `+highlights` entry per existing Exa search mode
    (`default`, `standard`, `auto`, `fast`, `agentic`, `deep-lite`, `deep`,
    `deep-reasoning`), preserving each mode's `usd_fixed` and raising `usd_per_unit`
    from `0.001` to `0.002`.

### Non-Functional Requirements

- **Backward compatibility:** every new constructor parameter is keyword-only with a
  default preserving current behavior. No existing call site changes.
- **Security:** no credential or vendor payload enters a log or an exception message.
  The existing `_require_ok` redaction behavior is untouched.
- **Observability:** none added. Billing observability comes from the pricebook entries.
- **Performance:** the shared date helper is a `staticmethod` doing one slice and one
  `date.fromisoformat`; it runs at most once per hit.
- **Reliability:** an unparseable or absent date yields `None`, never an exception.
  Highlights parsing tolerates a missing, non-list, or non-string-element array.

---

## 5. High-Level Design

Three files carry behavior changes and two carry documentation or table changes.

`clients/_base.py` gains one `@staticmethod` on `WebOperationClient`, `iso_date`, lifted
verbatim from `BraveClient._published_date`. This follows the `class-bound-helpers`
field-guide entry: the helper joins the class that already owns shared transport policy
rather than becoming a module-level free function. The three clients that populate
`published_at` then call `self.iso_date(...)`, and `BraveClient`'s private copy is deleted.

`clients/exa.py` gains two keyword-only constructor parameters. `max_results` replaces the
module constant `_MAX_RESULTS` as the clamp source, defaulting to the same `100`, matching
how `max_response_bytes` already works on the base class — a transport bound the composition
root reviews and supplies. `include_highlights` gates a `contents` block in `_search_body`
and a highlights branch in `_hit_from_result`. Because `_hit_from_result` must now read
instance state, it stops being a `@staticmethod` and becomes a regular method.

`operations/search.py` changes only `ExaSearchTool.execute`, deriving the billing mode
suffix from the bound client. The client is the only object that knows whether the request
asked for contents, so it is the only correct source for the mode that prices it. The tool's
`spec()` is untouched, keeping the model-facing schema SDK-authoritative.

```
ExaSearchTool.execute
   |
   |-- mode = _mode_arg(call, "type", ...)              # model-chosen search type
   |-- if client.includes_highlights: mode += "+highlights"
   |
   v
ExaClient.search(query, num_results, search_type)
   |
   |-- _search_body: numResults clamped to self._max_results
   |                 contents.highlights added when self._include_highlights
   |-- _hit_from_result: highlights -> text -> snippet
   |                     publishedDate -> WebOperationClient.iso_date
   v
SearchPayload(billable_units=len(hits))
   |
   v
UsageTracker.record_operation("search", "exa", mode, units) -> OPERATION_PRICING
```

The key decision is that highlights is a **client** flag rather than a tool argument.
Making it a tool argument would let the model turn on a billable content charge, and would
require changing `spec()`. Making it a client flag puts the decision in the composition root
that already reviews transport policy, and leaves the model unable to spend on it.

---

## 6. Detailed Design

### 6.1 SearchHit contract

**File:** `vidbyte/lib/dataclasses/operations.py`
**Type:** Modified

#### What it does

Documents the `published_at` format so future clients cannot re-introduce the divergence.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SearchHit:
    """One normalized web-search result with its undecoded vendor record."""

    title: str
    url: str
    snippet: str | None = None
    # Bare ISO-8601 calendar date (YYYY-MM-DD) or None. Clients must normalize
    # vendor timestamps through WebOperationClient.iso_date; consumers parse this
    # with date.fromisoformat, which rejects a full timestamp on Python 3.11.
    published_at: str | None = None
    language: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
```

#### Edge Cases & Error Handling

N/A — comment only, no runtime behavior.

---

### 6.2 Shared date normalization

**File:** `vidbyte/tools/builtins/operations/clients/_base.py`
**Type:** Modified

#### What it does

Provides the one conversion from a vendor date-ish string to the documented
`SearchHit.published_at` format, on the class that already owns shared client policy.

#### Interface / API

```python
class WebOperationClient:
    @staticmethod
    def iso_date(value: object) -> str | None: ...
```

#### Logic / Algorithm

1. Return `None` when the value is not a `str` or is shorter than ten characters.
2. Slice the leading ten characters, which is the `YYYY-MM-DD` prefix of every ISO-8601
   timestamp form the supported vendors emit.
3. Round-trip through `date.fromisoformat(...).isoformat()` so a syntactically
   date-shaped but calendar-invalid value (`2023-02-30`) is rejected rather than stored.
4. Return `None` on `ValueError`.

This is `BraveClient._published_date` verbatim; the method is public rather than
underscore-prefixed because three subclasses in two modules call it.

#### Edge Cases & Error Handling

- Non-string input (`None`, `int`, `dict`) → `None`.
- Shorter than ten characters (`"2023"`, `"1 day ago"`) → `None`.
- Calendar-invalid (`"2023-02-30T00:00:00Z"`) → `None`.
- Timestamp with any suffix (`Z`, `+00:00`, `.000Z`) → the date part.
- Never raises.

---

### 6.3 BraveClient

**File:** `vidbyte/tools/builtins/operations/clients/brave.py`
**Type:** Modified

#### What it does

Unchanged behavior; drops its private duplicate of the date helper.

#### Logic / Algorithm

1. Delete the `_published_date` staticmethod.
2. In `_hit_from_result`, call `self.iso_date(item.get("page_age") or item.get("age"))`.
3. Remove the now-unused `from datetime import date` import.

#### Edge Cases & Error Handling

Identical to today by construction — the helper body is unchanged, only relocated.

---

### 6.4 ExaClient

**File:** `vidbyte/tools/builtins/operations/clients/exa.py`
**Type:** Modified

#### What it does

Normalizes `publishedDate`, adds an opt-in highlights request, and accepts a
caller-supplied per-request result ceiling.

#### Interface / API

```python
class ExaClient(WebOperationClient):
    def __init__(self, api_key: str, *, base_url: str = "https://api.exa.ai", timeout_seconds: float = 30.0, retry: RetryPolicy | None = None, max_response_bytes: int = 4_000_000, max_results: int = _MAX_RESULTS, include_highlights: bool = False, transport: HttpTransport | None = None) -> None: ...

    @property
    def includes_highlights(self) -> bool: ...

    async def search(self, query: str, *, num_results: int = 10, search_type: str = "auto") -> SearchPayload: ...

    def _search_body(self, query: str, num_results: int, search_type: str) -> dict[str, object]: ...
    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None: ...
    def _snippet_from_result(self, item: Mapping[str, Any]) -> str | None: ...
```

#### Logic / Algorithm

`__init__`:
1. Store `self._max_results = min(max(1, int(max_results)), _MAX_RESULTS)` so a caller
   cannot raise the ceiling above Exa's documented maximum, only lower it.
2. Store `self._include_highlights = bool(include_highlights)`.

`_search_body` (now an instance method, since it reads both new fields):
1. Build the existing `{"query", "numResults", "type"}` body, clamping `numResults` to
   `min(max(1, num_results), self._max_results)`.
2. When `self._include_highlights`, add
   `"contents": {"highlights": {"numSentences": _HIGHLIGHT_SENTENCES, "highlightsPerUrl": _HIGHLIGHTS_PER_URL}}`.

`_snippet_from_result` (new private method):
1. Read `item.get("highlights")`. When it is a list or tuple, join its non-empty string
   elements with `" … "`, truncate to `_MAX_SNIPPET_CHARS`, and return it if non-empty.
2. Fall back to the existing `item.get("text") or item.get("snippet")` behavior,
   truncated to `_MAX_SNIPPET_CHARS`.
3. Return `None` when nothing usable is present.

`_hit_from_result`:
1. Unchanged URL guard and title fallback.
2. `snippet=self._snippet_from_result(item)`.
3. `published_at=self.iso_date(item.get("publishedDate"))`.

New module constants: `_HIGHLIGHT_SENTENCES = 3`, `_HIGHLIGHTS_PER_URL = 2`,
`_HIGHLIGHT_JOINER = " … "`.

#### Edge Cases & Error Handling

- `highlights` absent, `None`, a bare string, or a list of non-strings → falls through to
  the `text`/`snippet` path rather than raising.
- `highlights` present but all elements empty → falls through.
- Joined highlights longer than `_MAX_SNIPPET_CHARS` → truncated, consistent with the
  existing `text` handling.
- `max_results` passed as `0`, negative, or above 100 → clamped into `[1, 100]` at
  construction, so `_search_body` can never emit an out-of-range `numResults`.
- `include_highlights=False` (default) → request body and parsing are byte-identical to
  today, which is what preserves every existing consumer.

---

### 6.5 TavilyClient

**File:** `vidbyte/tools/builtins/operations/clients/tavily.py`
**Type:** Modified

#### What it does

Closes the same date-normalization gap as Exa.

#### Logic / Algorithm

1. Change `_hit_from_result` from a `@staticmethod` to an instance method.
2. Replace the raw passthrough with `published_at=self.iso_date(item.get("published_date"))`.

#### Edge Cases & Error Handling

Tavily emits both `"2023-05-01"` and full timestamps depending on the source. Both now
normalize; anything else yields `None` instead of an unparseable string.

---

### 6.6 ExaSearchTool billing mode

**File:** `vidbyte/tools/builtins/operations/search.py`
**Type:** Modified

#### What it does

Reports the mode that actually describes what was billed, so the pricebook lookup matches
the request that was sent.

#### Interface / API

```python
class ExaSearchTool(PricedOperationTool):
    def _billing_mode(self, call: ToolCall) -> str: ...
```

#### Logic / Algorithm

1. `_billing_mode` reads the model's `type` argument through the existing `_mode_arg`
   guard, then appends `_HIGHLIGHTS_MODE_SUFFIX` when the bound client is present and
   reports `includes_highlights`.
2. `execute` calls `_billing_mode(call)` once and uses the result for the contract-stub,
   failure, and success paths alike, replacing the current local `mode` variable.

New module constant: `_HIGHLIGHTS_MODE_SUFFIX = "+highlights"`.

`spec()` is deliberately unchanged.

#### Edge Cases & Error Handling

- No bound client (contract-stub path) → no suffix, because no request is made and no
  content charge is incurred.
- Client bound with `include_highlights=False` → no suffix, so existing consumers keep
  resolving today's rates exactly.
- Failure path → the suffix is still applied, because a failed attempt against a
  highlights-enabled endpoint still consumed the attempt the retry policy reports.

---

### 6.7 Operation pricing table

**File:** `vidbyte/lib/registries/operation_pricing.py`
**Type:** Modified

#### What it does

Prices the content charge that `include_highlights` incurs.

#### Interface / API

```python
("search", "exa", "auto+highlights"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.002, included_units=10),
```

one per existing Exa search mode, preserving that mode's `usd_fixed`:

| Mode | usd_fixed | usd_per_unit | included_units |
|---|---|---|---|
| `default+highlights` | 0.007 | 0.002 | 10 |
| `standard+highlights` | 0.007 | 0.002 | 10 |
| `auto+highlights` | 0.007 | 0.002 | 10 |
| `fast+highlights` | 0.007 | 0.002 | 10 |
| `agentic+highlights` | 0.012 | 0.002 | 10 |
| `deep-lite+highlights` | 0.012 | 0.002 | 10 |
| `deep+highlights` | 0.012 | 0.002 | 10 |
| `deep-reasoning+highlights` | 0.015 | 0.002 | 10 |

#### Logic / Algorithm

1. Add the eight entries immediately after the existing Exa search block.
2. Extend the file's header comment block with an explicit note that the folded rate is an
   approximation: Exa bills highlights from the first result while search bills above the
   ten-result allowance, so the entry slightly under-prices calls at or below ten results
   and slightly over-prices very large ones. It is accurate near twenty results, which is
   the intended operating point.
3. Remove "Exa Contents billed per content type" from the "deliberately absent" list, or
   narrow it to the content types still unpriced (`text`, `summary`), since `highlights`
   is now represented.

#### Edge Cases & Error Handling

Without these entries, `resolve` falls back to `("search", "exa", "default")` and silently
under-bills every highlighted search. That fallback is why the table change ships in the
same commit as the client flag, not after it.

---

## 7. Data Model Changes

N/A — the SDK holds no persistent schema. `SearchHit` is an in-memory frozen dataclass;
its `published_at` field type is unchanged (`str | None`) and only its documented format
is being pinned down.

---

## 8. API Changes

N/A — no HTTP endpoints. The public Python surface changes are additive and
backward-compatible, and are covered in Section 6:

- `WebOperationClient.iso_date` (new public staticmethod)
- `ExaClient(..., max_results=..., include_highlights=...)` (new keyword-only params)
- `ExaClient.includes_highlights` (new property)

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/dataclasses/operations.py` | Document the `SearchHit.published_at` format contract |
| MODIFY | `vidbyte/tools/builtins/operations/clients/_base.py` | Add the shared `WebOperationClient.iso_date` helper |
| MODIFY | `vidbyte/tools/builtins/operations/clients/brave.py` | Use the shared helper; delete the private duplicate |
| MODIFY | `vidbyte/tools/builtins/operations/clients/exa.py` | Normalize dates; add `max_results` and `include_highlights` |
| MODIFY | `vidbyte/tools/builtins/operations/clients/tavily.py` | Normalize `published_date` through the shared helper |
| MODIFY | `vidbyte/tools/builtins/operations/search.py` | Derive the Exa billing mode suffix from the bound client |
| MODIFY | `vidbyte/lib/registries/operation_pricing.py` | Add eight `+highlights` Exa search entries and the rate caveat |
| MODIFY | `docs/design/exa-search-normalization-and-highlights.md` | This document |

**Totals:** 0 created, 8 modified, 0 deleted.

No new tests. The repository's existing suite under `tests/` plus
`python scripts/run_ci.py` is the gate.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Exa Search API | `POST https://api.exa.ai/search` | Neural web search | Adding `contents.highlights` bills a second meter. Rate assumed at $0.001/result from exa.ai/pricing; must be confirmed against a live invoice. |
| Tavily Search API | `POST /search` | Existing search client | None — the change only reformats a field already returned. |
| Brave Search API | `GET /res/v1/web/search` | Existing search client | None — behavior-preserving refactor. |
| Python stdlib `datetime.date` | 3.11+ | ISO date parsing | `date.fromisoformat` accepts full ISO-8601 from 3.11 only for dates, not timestamps. The slice-then-parse approach is version-independent. |

No new third-party packages.

---

## 11. Rollout & Deployment

- **Feature flags:** none. `include_highlights` and `max_results` default to
  behavior-preserving values, so merging changes nothing for any existing consumer until a
  caller opts in.
- **Breaking change:** no. All new parameters are keyword-only with defaults. The one
  behavioral change to an existing path is `TavilyClient.published_at`, which moves from an
  unparseable string to a parseable date or `None` — strictly an improvement for any
  consumer, and `None` was already a possible value.
- **Deployment order:** this PR merges and is released before the dependent Vidbyte
  research-harness PR, which pins the resulting commit.
- **Rollback:** revert the single PR. No persisted state, no migration, no flag to unwind.

---

## 12. Open Questions

- [ ] Exa's `/search` returning no snippet text without a `contents` block is inferred from
      the current client's own comment and from `SearchHit.snippet` being unconditionally
      `None` for Exa. Confirm with one live call before relying on the highlights path.
- [ ] Confirm Exa bills `highlights` at the same ~$0.001/result as `text`. If it differs,
      only the `usd_per_unit` constant in the eight new entries changes.
- [ ] `_HIGHLIGHT_SENTENCES = 3` / `_HIGHLIGHTS_PER_URL = 2` are chosen to land near Brave's
      `description` length (~200 chars). Worth revisiting once real discovery output exists.
- [ ] Should `WebOperationClient.iso_date` be public or `_iso_date`? Public is proposed
      because it crosses module boundaries to three subclasses; flag if the repo prefers
      underscore-private with cross-module use.

---

## 13. Alternatives Considered

### Alternative 1: Normalize the date in the consuming application

- **What:** Leave the SDK alone and make Vidbyte's `ResearchSearchCandidates._published_date`
  tolerate full timestamps.
- **Why rejected:** It fixes one consumer and leaves the SDK contract ambiguous, so the next
  application to read `published_at` hits the same defect. The divergence is between two
  clients of one dataclass; it belongs where the dataclass lives.

### Alternative 2: Make `include_highlights` a tool argument on `ExaSearchTool.spec()`

- **What:** Expose `include_highlights` to the model like `num_results` and `type`.
- **Why rejected:** It hands the model a switch that turns on a billable content charge, and
  it changes the SDK tool's model-facing schema — which the `priced-operation-execution`
  field-guide entry says must stay authoritative. A client flag set by the composition root
  gets the capability without the exposure.

### Alternative 3: Turn highlights on unconditionally in `ExaClient`

- **What:** Always request `contents.highlights`; no flag.
- **Why rejected:** It silently starts billing a second meter for every existing SDK consumer
  of `ExaSearchTool`, none of whom asked for it. The existing `_search_body` comment shows
  the results-only default was a deliberate cost decision, and this change should extend it
  rather than reverse it.

### Alternative 4: Request `contents.text` instead of `highlights`

- **What:** `contents: {text: {maxCharacters: 500}}`, matching what `_hit_from_result`
  already reads.
- **Why rejected:** Marginally simpler, but leading page text is a weaker relevance signal
  than query-relevant highlights for the selection decision this exists to support. Same
  content charge either way, so the weaker signal buys nothing.

### Alternative 5: A separate `content_charge` field on `OperationPricing`

- **What:** Model the second meter as a first-class field rather than folding it into
  `usd_per_unit` under a suffixed mode.
- **Why rejected:** It changes a frozen dataclass every pricing entry depends on, to express
  one provider's billing shape. Mode strings already carry billing variants throughout this
  table (`tavily` basic/advanced, `linkup` standard/deep), so the suffix follows the grain.
  Revisit if a second provider needs the same treatment.

# Design Doc: Operation Pricebook PAYG/API Rate Corrections

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-08
**Last Updated:** 2026-08-08

---

## 1. Overview

`OPERATION_PRICING` in `vidbyte/lib/registries/operation_pricing.py` prices every search/fetch operation the SDK bills. An audit of all 60 entries against each vendor's live pricing page found nine of ten providers exact, and **all six Parallel search/extract entries wrong by a factor of 1,000** — a unit-conversion slip that reads Parallel's `Cost ($/1000)` column as dollars-per-unit and divides by 1,000,000 instead of 1,000. Because the lookup still *succeeds*, `UsageRollup.cost_complete` stays `true` and the runtime reports a confidently precise cost that is three orders of magnitude too low, defeating the registry's own design (unknowable rates resolve to `None` so incompleteness is visible). This change corrects those six rates, adds a magnitude guard to the existing pricing test so the slip cannot recur, and repairs the derivation notes and downstream docs that caused this exact value to be reverted once already.

---

## 2. Goals & Non-Goals

### Goals

- Correct all six `("search"|"fetch", "parallel", …)` entries to the published per-unit USD rate.
- Re-verify and record every other entry in the table against its vendor pricing page as of 2026-08-08, bumping `OPERATION_PRICING_AS_OF`.
- Make the plan-vs-PAYG basis of each non-PAYG rate explicit in the comment block, so the "API rate, not subscription rate" rule is auditable rather than implicit.
- Add a magnitude-floor assertion to the existing `tests/test_agent_pricing.py` that fails on any implausibly small rate, catching this class of error mechanically.
- Repair the downstream artifacts that restate Parallel rates (`skills/usage/available_tools.md`) and the historical design doc that asserts the wrong derivation as fact, so the next reader does not re-revert.

### Non-Goals

- **Changing any rate that verified correct.** Brave, Exa, Tavily, Linkup, OpenAlex, Semantic Scholar, Browserbase, and Firecrawl values are unchanged.
- **Changing the `OperationPricing` dataclass, `OperationPricingRegistry`, `UsageTracker.record_operation`, or the rollup.** The pricing *model* is correct; only six numbers are wrong.
- **Fixing `ParallelClient`'s endpoint or processor enum.** `ParallelClient` posts to `https://api.parallel.ai/v1beta` + `search`, which Parallel's API reference now labels the *legacy* path (current is `/v1/search`), and `ParallelSearchTool` exposes `("turbo", "pro")` while the v1 endpoint documents `turbo/basic/advanced` and the beta endpoint documents `base/pro`. That is a request-behavior defect needing its own verification against a live key — see §12 and §14. It is deliberately out of scope so this rate correction stays reviewable in isolation.
- **Adding new test files.** The guard goes into the existing `tests/test_agent_pricing.py`.
- **Adding pricebook entries for products currently absent by design** (Tavily Crawl/Research, Parallel FindAll, Exa metered `auto`, Browserbase browser-hours/proxy-GB). Their `None` resolution is intentional and correct.

---

## 3. Background & Context

### Why now

The user asked for a verification pass over the search/fetch pricebook against **platform API pricing, not subscription-plan pricing**. That audit surfaced one hard defect and two documentation problems.

### Current state

`OPERATION_PRICING_AS_OF` reads `"2026-08-03"` — five days old — so this is not a staleness problem. Every rate except Parallel's was correct on the day it was written and is still correct today. The Parallel rows were wrong from the moment they were written.

### The bug has already flip-flopped twice, which is why this doc exists

`git log origin/main -- vidbyte/lib/registries/operation_pricing.py` shows three commits, and the design docs record an argument:

- `docs/design/agent-operation-pricing.md` (PR #311) stated the rates correctly in prose at line 51 — `fetch | parallel | $0.001/URL (Extract API)` — and encoded `("fetch","parallel","default"): usd_per_unit=0.001`, **correct**. Its own table sketch at lines 162–163 nonetheless showed `0.000001`/`0.000005` for search, so the doc was internally inconsistent from day one.
- PR #325 changed the Parallel *search* rows to `usd_fixed=0.005` — **correct**.
- `docs/design/minimal-web-provider-search-fetch-tools.md` then reverted both. Its line 61 asserts *"`("fetch","parallel","default")` is 1000× too high on main. It reads `usd_per_unit=0.001`; Parallel publishes Extract at $0.001 per 1,000 URLs, so the per-URL rate is `0.000001`."* Line 62 asserts *"PR #325's Parallel search rows are 1000× too high … `main`'s existing `0.000001` (turbo) and `0.000005` (pro) rows are correct."*

Both assertions are wrong, and they are wrong in a specific, reproducible way: they read Parallel's price column value `1` as *"$0.001"* and then divided by 1,000 again.

### The settled ground truth

Parallel's pricing table column header is verbatim **`Cost ($/1000)`**. The rows are:

| Component | Cost ($/1000) | Per-unit USD |
|---|---|---|
| Per 1,000 `turbo` requests (default 10 results) | 1 | **0.001** |
| Per 1,000 `basic` or `advanced` requests (default 10 results) | 5 | **0.005** |
| Per 1,000 additional page results & excerpts | 1 | **0.001** |
| Per 1,000 URLs (Extract) | 1 | **0.001** |

Three independent cross-checks confirm the divisor is 1,000:

1. **Internal.** The same dict already converts the same column correctly elsewhere. Parallel Task Lite is `$5 per 1,000 runs` → `("task","parallel","lite"): usd_fixed=0.005`. Chat `speed` is `5` → `0.005`. Monitor `base` is `10` → `0.010`. Only the search/extract rows use a different divisor. One page, one column, two conversions — that is a slip, not a modeling decision.
2. **Cross-provider.** Every other provider in the table uses the identical per-1,000 convention and the identical divisor: Exa `$7/1k` → `0.007`, Brave `$5/1k` → `0.005`, Tavily PAYG `$8/1k` → `0.008`. Parallel is the sole outlier.
3. **External.** Third-party API pricing comparisons place Parallel Search at roughly **$4–$9 per 1,000 requests**, consistent with `0.005`/request and irreconcilable with `0.000005`/request.

### Why this defect is worse than a missing price

The comment block states the registry's safety contract explicitly: products whose cost is unknowable are *deliberately absent* so they "resolve to None so cost_complete stays visibly false instead of being guessed." A 1,000× error bypasses that guard entirely. `UsageTracker.rollup()` computes:

```python
cost_complete=bool(records or operations) and all(cost is not None for cost in token_costs + operation_costs),
```

A wrong-but-present cost is not `None`, so `cost_complete` remains `true`. A missing price makes noise; this one is silent. Any `cost_budget` middleware layered on `get_cost_usd()` is checking a budget against a rounding error and will never fire.

### Blast radius today

This is the live default path, not a reference-only row. `ParallelClient.search` defaults to `processor="turbo"`, and `ParallelSearchTool.execute` clamps to `("turbo","pro")` defaulting to `"turbo"` — so the most common call resolves to the worst-scaled entry.

---

## 4. Requirements

### Functional Requirements

1. `("search","parallel","default")` and `("search","parallel","turbo")` MUST price at `usd_fixed=0.001, usd_per_unit=0.001, included_units=10`.
2. `("search","parallel","pro")`, `("search","parallel","base")`, and `("search","parallel","advanced")` MUST price at `usd_fixed=0.005, usd_per_unit=0.001, included_units=10`.
3. `("fetch","parallel","default")` MUST price at `usd_per_unit=0.001`.
4. No other `OPERATION_PRICING` entry's numeric values may change.
5. `OPERATION_PRICING_AS_OF` MUST read `"2026-08-08"`.
6. The comment block MUST state, for each rate not derived from a published pay-as-you-go API rate, which plan it assumes and what the spread across plans is.
7. The comment block MUST state Parallel's conversion rule explicitly (`Cost ($/1000)` ÷ 1,000) so the divisor is not re-derived by inference.
8. Every source URL in the comment block MUST point at the vendor's own pricing page, not a third-party or marketing page.
9. `tests/test_agent_pricing.py` MUST fail if any `OPERATION_PRICING` entry has a non-zero `usd_fixed` or `usd_per_unit` below `1e-5`.
10. `tests/test_agent_pricing.py` MUST assert the corrected Parallel turbo and pro rates directly, pinning the divisor.
11. `skills/usage/available_tools.md` MUST state Parallel search billing as per-request USD, and MUST list the `type` values `ExaSearchTool` actually accepts.
12. `docs/design/minimal-web-provider-search-fetch-tools.md` MUST carry a correction notice at its incorrect assertions, pointing to this doc.
13. No new test file is created.

### Non-Functional Requirements

- **Performance:** N/A — module-level dict literal, no runtime cost change. `OperationPricingRegistry.__init__` copies the dict; entry count is unchanged.
- **Scalability:** N/A — no data store, no query, no per-request allocation change.
- **Security:** N/A — no credential, network, or input-handling surface is touched.
- **Observability:** The corrected values flow into `OperationUsageRecord.cost_usd` and `UsageRollup.operation_cost_usd`. No new logging.
- **Reliability:** Behavior is unchanged for every non-Parallel provider. `cost_complete` semantics are untouched — the same keys resolve, only their values change.
- **Correctness guard:** The magnitude floor must have real headroom against every legitimate entry. Post-fix, the smallest legitimate non-zero rate in the table is Firecrawl's `0.00083`; a `1e-5` floor clears it by 83×, and all six defective values (`1e-6`, `5e-6`) fail it.

---

## 5. High-Level Design

This is a data correction to one module-level dict plus three documentation repairs. No control flow, type, or interface changes.

**Components modified:**

- `vidbyte/lib/registries/operation_pricing.py` — six dict values ×1,000; comment block restructured so each rate's basis (PAYG / plan-derived / free) is explicit; two source URLs corrected; `OPERATION_PRICING_AS_OF` bumped.
- `tests/test_agent_pricing.py` — one new `unittest.TestCase` class with two methods, added to the existing file.
- `skills/usage/available_tools.md` — two table cells corrected.
- `docs/design/minimal-web-provider-search-fetch-tools.md` — correction notice appended at the two wrong assertions.

**Data flow, unchanged end to end:**

```
ParallelSearchTool.execute(call)
  -> _mode_arg(call, "processor", ("turbo","pro"), "turbo")     # mode
  -> ParallelClient.search(...) -> SearchPayload(billable_units=len(hits))
  -> PricedOperationTool._executed_result(units=..., mode=...)
  -> UsageTracker.record_operation(operation, provider, mode=, units=)
       -> OperationPricingRegistry.resolve(op, provider, mode)   # <-- table read
       -> OperationPricing.cost_usd(units)                       # fixed + per_unit*ceil(billable/batch)
  -> OperationUsageRecord.cost_usd -> UsageRollup.operation_cost_usd
```

Only the value returned by `resolve` changes.

**Key design decisions:**

*Correct the values in place rather than restructure.* The `OperationPricing` shape (`usd_fixed` + `usd_per_unit` over `included_units`, batched by `unit_batch`) models Parallel's "base request + additional results above 10" exactly, and `included_units=10` is already right. The minimal complete change is six numbers.

*Encode the divisor as a comment, and the magnitude as a test.* A comment alone already failed — the existing bullet *"Parallel publishes per-1,000 rates; entries below are the per-call quotient"* is correct prose sitting directly above wrong numbers, and nobody caught it in two review cycles. The floor assertion is what makes the fix durable, because it tests the *property* that was violated (implausible magnitude) rather than restating each rate, which would just duplicate the mistake in a second place.

*Repair the historical doc rather than rewrite it.* `minimal-web-provider-search-fetch-tools.md` is a record of a shipped PR. Rewriting it erases why the value was reverted; leaving it untouched invites a third revert. A dated correction notice preserves the history and blocks the loop.

---

## 6. Detailed Design

### 6.1 Operation pricing registry

**File:** `vidbyte/lib/registries/operation_pricing.py`
**Type:** Modified

#### What it does

Holds the source-of-truth per-operation USD tariff table and the registry that resolves `(operation, provider, mode)` triples against it with a `"default"`-mode fallback and caller overrides.

#### Interface / API

Unchanged. `OperationPricing`, `OperationPricingRegistry`, `OPERATION_PRICING`, and `OPERATION_PRICING_AS_OF` keep their current signatures and exports. Only dict values, comments, and the as-of date change.

```python
OPERATION_PRICING_AS_OF: str = "2026-08-08"   # was "2026-08-03"

# ── search ──
("search", "parallel", "default"):  OperationPricing(usd_fixed=0.001, usd_per_unit=0.001, included_units=10),
("search", "parallel", "turbo"):    OperationPricing(usd_fixed=0.001, usd_per_unit=0.001, included_units=10),
("search", "parallel", "pro"):      OperationPricing(usd_fixed=0.005, usd_per_unit=0.001, included_units=10),
("search", "parallel", "base"):     OperationPricing(usd_fixed=0.005, usd_per_unit=0.001, included_units=10),
("search", "parallel", "advanced"): OperationPricing(usd_fixed=0.005, usd_per_unit=0.001, included_units=10),

# ── fetch ──
("fetch",  "parallel", "default"):  OperationPricing(usd_per_unit=0.001),
```

#### Logic / Algorithm

1. Multiply the five `("search","parallel",*)` `usd_fixed` values by 1,000 (`0.000001 → 0.001` for `default`/`turbo`; `0.000005 → 0.005` for `pro`/`base`/`advanced`).
2. Multiply the same five entries' `usd_per_unit` by 1,000 (`0.000001 → 0.001`). Leave `included_units=10` untouched.
3. Multiply `("fetch","parallel","default")`'s `usd_per_unit` by 1,000 (`0.000001 → 0.001`).
4. Replace the Tavily/Firecrawl combined bullet with two bullets that separate the compliant PAYG case from the plan-derived one:
   - Tavily bills in credits at a published pay-as-you-go rate of `$0.008/credit` with no monthly commitment; monthly plans are cheaper (`$0.005–$0.0075`), so the table's figure is the plan-free API rate and over-prices a subscribed account.
   - Firecrawl publishes **no** pay-per-use rate — its FAQ states *"We currently do not offer a pay-per-use plan."* USD uses the Standard plan (`$83 / 100,000 credits = $0.00083/credit`). Plans span 5.3× (`Hobby $0.0032` → `Scale $0.0006`), so accounts off Standard should override this registry via `OperationPricingRegistry.register`.
5. Rewrite the Parallel bullet to name the column and the divisor: rates come from a `Cost ($/1000)` column, so every entry is that value ÷ 1,000; search bills a base request plus `$0.001` per result above the ten included.
6. Repoint two source URLs: `brave` → `https://brave.com/search/api/` (was a marketing comparison post at `brave.com/learn/...`), `firecrawl` → `https://www.firecrawl.dev/pricing` (was the third-party `eesel.ai` blog).
7. Bump `OPERATION_PRICING_AS_OF` to `"2026-08-08"`.

#### Verified-unchanged entries

Re-checked against vendor pages on 2026-08-08; **no edits**:

| Provider | Verified | Basis |
|---|---|---|
| Brave | search `0.005` | `$5/1k` published API rate |
| Exa | search `0.007`; `deep-lite`/`deep` `0.012`; `deep-reasoning` `0.015`; `+0.001`/result over 10; contents `0.001`/page/type; answer `0.005`; monitor `0.015`; agent `0.012/0.025/0.10/0.50/1.00` | published API rates, exact |
| Tavily | search basic `0.008` / advanced `0.016`; extract `0.008`/`0.016` per 5-URL batch; map `0.008`/`0.016` per 10-page batch | PAYG `$0.008/credit` — compliant |
| Linkup | search `0.005`/`0.05`; fetch `0.001`/`0.005` | published API rates, exact |
| OpenAlex | search `0.001` | published per-call rate |
| Semantic Scholar | free → all-zero tariff | free API; zero (not `None`) is correct |
| Browserbase | search `0.007`; fetch `0.001`/proxy `0.004`; extract `0.004`/proxy `0.007` | Developer-plan overage, already documented |
| Firecrawl | fetch `0.00083`/page | Standard plan; no PAYG exists (see §12) |

#### Edge Cases & Error Handling

- **`"default"`-mode fallback:** `resolve` falls back to the provider's `"default"` entry for unknown modes. Parallel's `"default"` maps to turbo's `0.001`, matching `ParallelClient`'s own `processor="turbo"` default. An unknown mode therefore under-reports relative to `pro`; this mirrors Tavily's existing `default → basic` convention and is unchanged behavior.
- **Zero-result search:** `SearchPayload(billable_units=max(1, len(hits)))` floors units at 1, so `cost_usd(1)` returns `usd_fixed` alone — `max(0, 1-10) = 0` billable marginal units. Correct: Parallel bills the request even when it returns nothing.
- **Caller overrides:** `OperationPricingRegistry.__init__` copies the source table, so `register()` never mutates module state. Any caller who worked around the bug by registering a corrected Parallel rate keeps working — their override still wins.
- **No `None` transitions:** every key that resolved before still resolves. `cost_complete` cannot regress from `true` to `false` for any existing call pattern.

---

### 6.2 Pricing table guard

**File:** `tests/test_agent_pricing.py`
**Type:** Modified (existing file — no new test file)

#### What it does

Adds one `unittest.TestCase` asserting the table's rate magnitudes are plausible and pinning Parallel's conversion, alongside the existing `PricingBaseTests`, `CompatibleProviderTests`, `OpenRouterUsageTests`, and `PricingRegistryStrictnessTests`.

#### Interface / API

```python
class OperationPricingTableTests(unittest.TestCase):
    def test_no_rate_is_implausibly_small(self) -> None: ...
    def test_parallel_rates_convert_from_the_per_thousand_column(self) -> None: ...
```

#### Logic / Algorithm

1. `test_no_rate_is_implausibly_small` iterates `OPERATION_PRICING.items()` and, for each entry, asserts that every non-zero value among `usd_fixed` and `usd_per_unit` is `>= _MIN_PLAUSIBLE_RATE_USD` (`1e-5`), reporting the offending key in the failure message. Zero values are skipped — free operations legitimately carry an all-zero tariff.
2. `test_parallel_rates_convert_from_the_per_thousand_column` asserts `resolve("search","parallel","turbo")` is `usd_fixed=0.001, usd_per_unit=0.001`, `resolve("search","parallel","pro")` is `usd_fixed=0.005`, and `resolve("fetch","parallel","default")` is `usd_per_unit=0.001`.
3. The `1e-5` threshold is a module-level named constant, not an inline literal, per house style.

#### Edge Cases & Error Handling

- **Free operations** (`semantic_scholar` search, `direct_http` fetch) have `usd_fixed == 0.0` and `usd_per_unit == 0.0`; the non-zero filter skips them so they do not trip the floor.
- **Future genuinely-sub-`1e-5` rate:** none exists today across ten providers, and the floor sits 83× below the smallest real rate. Should a vendor ever publish one, the test fails loudly and the threshold is revisited deliberately — which is the intended behavior, not a false positive to route around.
- **Float comparison:** rates are exact decimal literals compared with `assertAlmostEqual` in the spot-check to avoid binary-float brittleness.

---

### 6.3 Tool catalog documentation

**File:** `skills/usage/available_tools.md`
**Type:** Modified

#### What it does

Documents each pre-built tool's provider, billing basis, and accepted arguments for skill consumers.

#### Logic / Algorithm

1. `ParallelSearchTool` billing cell reads `Per-result ($0.001/1k req)` — ambiguous, and reconcilable with the defective value. Change to `Per-result (turbo $0.001/req, pro $0.005/req, +$0.001/result beyond 10)`.
2. `ExaSearchTool` description claims `Supports `type` param: `standard`, `agentic``, but `_EXA_SEARCH_TYPES` in `vidbyte/tools/builtins/operations/search.py` is `("auto", "fast", "deep-lite", "deep", "deep-reasoning")` — the doc names two values the tool rejects and omits all five it accepts. Correct the list to the five real values.
3. `ParallelExtractTool`'s cell already reads `Per-URL ($0.001/URL)` — correct, and further corroboration of the intended rate. **No change.**

#### Edge Cases & Error Handling

N/A — Markdown table cells with no execution path.

---

### 6.4 Historical design doc correction notice

**File:** `docs/design/minimal-web-provider-search-fetch-tools.md`
**Type:** Modified

#### What it does

Records the design of the shipped minimal-web-provider PR, including two assertions about Parallel rates that are wrong and that caused a correct value to be reverted.

#### Logic / Algorithm

Insert a short, dated correction notice immediately above the numbered claims at lines 61–62, stating that both assertions were wrong, that Parallel's column header is `Cost ($/1000)` so the divisor is 1,000, and linking to `docs/design/operation-pricing-payg-corrections.md`. The original text is left intact beneath it.

#### Edge Cases & Error Handling

N/A. Deliberately additive — this doc is a historical record and the notice must not erase why the revert happened, only stop it recurring.

---

## 7. Data Model Changes

N/A — no database, collection, schema, or persisted type is touched. `OPERATION_PRICING` is an in-process module-level dict literal with no serialized form, and no field on `OperationPricing`, `OperationUsageRecord`, or `UsageRollup` changes shape.

---

## 8. API Changes

N/A — no HTTP endpoint, route, or request/response contract is touched. The public Python surface (`OperationPricing`, `OperationPricingRegistry`, `OPERATION_PRICING`, `OPERATION_PRICING_AS_OF`, `UsageTracker.record_operation`) keeps identical signatures and exports; only table values change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/operation-pricing-payg-corrections.md` | This design doc |
| MODIFY | `vidbyte/lib/registries/operation_pricing.py` | Six Parallel rates ×1,000; comment block states each rate's PAYG/plan basis and Parallel's ÷1,000 divisor; two vendor source URLs; `OPERATION_PRICING_AS_OF` → `2026-08-08` |
| MODIFY | `tests/test_agent_pricing.py` | Add `OperationPricingTableTests` — magnitude floor + Parallel conversion spot-check |
| MODIFY | `skills/usage/available_tools.md` | Parallel search billing cell; Exa `type` value list |
| MODIFY | `docs/design/minimal-web-provider-search-fetch-tools.md` | Correction notice on the two wrong Parallel assertions |

**Totals:** 1 created, 4 modified, 0 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Parallel pricing page | `docs.parallel.ai/getting-started/pricing` | Source of the six corrected rates; column header `Cost ($/1000)` | Vendor may reprice; mitigated by `OPERATION_PRICING_AS_OF` and the magnitude guard |
| Exa / Tavily / Linkup / Brave / OpenAlex / Browserbase / Firecrawl pricing pages | see comment block | Re-verification sources for unchanged entries | Same |
| `vidbyte.lib.errors.ConfigurationError` | in-repo | Already imported by the module | None |
| Python stdlib `unittest`, `math.ceil` | stdlib | Existing test framework and batch math | None |

No new package dependency is added. No network call is made at runtime — all rates are static literals.

---

## 11. Rollout & Deployment

- **Feature flags:** None. A pricebook correction behind a flag would mean shipping two costing regimes; the current values are simply wrong.
- **Breaking change:** Not to any API signature. It *is* a behavioral change to reported cost: any caller using `ParallelSearchTool` or `ParallelExtractTool` will see `get_cost_usd()` and `metadata["usage_rollup"]` rise by ~1,000× for those operations. That is the correction, not a regression — the previous numbers were fiction. Callers with `cost_budget` middleware tuned against the old figures may now legitimately trip their budget; this must be called out in the PR body.
- **Migration path:** None required. No persisted cost figures exist in the SDK; the rollup is per-session and in-memory. Any downstream system that stored historical Parallel cost figures produced by this SDK has under-reported values, and this doc's §3 table is the multiplier for restating them.
- **Deployment order:** Single repo, single commit series. No cross-service ordering.
- **Rollback:** `git revert` of the implementation commits. The change is six literals plus documentation, with no state to unwind.
- **Verification gate:** `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` from the worktree. Per the field guide's *Local CI Verification*, the source stage runs as `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` from a worktree, and the package stage runs with **no** `PYTHONPATH`; the full `python scripts/run_ci.py` is the authoritative final run.

---

## 12. Open Questions

- [x] **How should Firecrawl resolve, given it publishes no PAYG rate?** — *Settled by the user:* keep `0.00083` (Standard plan) and expand the comment to name the 5.3× plan spread and point at `OperationPricingRegistry.register` as the override. Rejected: switching to Hobby `0.0032` (trades under-reporting for 3.9× over-reporting), and removing the entries (would make `cost_complete` false for every call of a live, shipped tool).
- [ ] **Is `ParallelSearchTool`'s `("turbo","pro")` mode set valid against the endpoint it calls?** Parallel documents `turbo/basic/advanced` for `/v1/search` and `base/pro` for the beta endpoint; `ParallelClient` posts to `/v1beta/search`, which the API reference now labels legacy. One of the two exposed modes is likely rejected at runtime. Needs a live-key check — tracked as a follow-up PR (§2 Non-Goals, §14).
- [ ] **Should `("search","exa","agentic")` stay?** It matches Exa's reported `$12/1k` agentic tier but is unreachable through `ExaSearchTool` (`_EXA_SEARCH_TYPES` excludes it). Harmless as a reference entry reachable via `record_operation`; left in place. Flagging only so a future reader does not delete it as dead.

---

## 13. Alternatives Considered

### Alternative 1: Restate every rate in a test rather than assert a magnitude floor

- **What:** A test enumerating all 60 entries with their expected USD values.
- **Why rejected:** It duplicates the mistake in a second place. Whoever mis-derives a rate writes the same wrong number in the test, and the suite goes green on a wrong value — precisely how this bug survived two reviews. The floor tests the *property* that was actually violated (implausible magnitude) and would have caught all six entries without anyone knowing Parallel's true rate.

### Alternative 2: Model Parallel's rates in native `$/1000` units with a conversion helper

- **What:** Store `usd_per_thousand` on `OperationPricing` and divide at `cost_usd` time.
- **Why rejected:** It changes a frozen dataclass consumed by `UsageTracker` and every priced tool, to fix six numbers. It also solves the wrong problem — nine of ten providers publish per-1,000 rates and were converted correctly, so the conversion is not the hard part; noticing a bad magnitude is. That is what the guard does, for one test instead of a dataclass migration.

### Alternative 3: Remove the Parallel entries so they resolve to `None`

- **What:** Treat the rates as disputed and let `cost_complete` go false.
- **Why rejected:** The rate is not unknowable — it is published, with a verbatim column header, and confirmed by three independent cross-checks. `None` is reserved for genuinely underivable prices (Tavily Crawl's two meters, Parallel FindAll's fixed-plus-per-match). Using it here would discard correct information and silently degrade a live tool.

### Alternative 4: Rewrite the wrong assertions out of `minimal-web-provider-search-fetch-tools.md`

- **What:** Edit lines 61–62 to state the correct derivation.
- **Why rejected:** That doc records a shipped PR's reasoning. Erasing the wrong claim hides that the value was reverted once on a stated rationale, and the next person to audit the table hits the same reasoning and reverts again. An additive, dated correction notice preserves the history and breaks the loop.

### Alternative 5: Fix the Parallel endpoint/processor enum in the same PR

- **What:** Also move `ParallelClient` to `/v1/search` and reconcile the processor names.
- **Why rejected:** It is a request-behavior change requiring live-key verification, with a different failure mode and a different reviewer question. Bundling it would make a six-literal correction unreviewable and delay it behind an integration test. Tracked as a follow-up.

---

## 14. Follow-Ups (not in this PR)

1. **Parallel endpoint and processor enum.** Verify `/v1beta/search` vs `/v1/search` and whether `turbo` and `pro` are both accepted by the endpoint actually called; reconcile `ParallelSearchTool`'s allowed set with the live API.
2. **Periodic re-verification.** `OPERATION_PRICING_AS_OF` is manual. Consider a scheduled check that re-reads the ten vendor pricing pages and diffs against the table.

---

END OF DESIGN DOC

# Design Doc: Cache Hit Tracking For All Providers

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-29
**Last Updated:** 2026-08-29

---

## 1. Overview

`vidbyte/agents/pricing` already parses provider-native cache-token fields for every supported provider (`cached_input_tokens` on OpenAI, Gemini, and the shared `ChatCompletionUsage` class; `cache_creation_input_tokens`/`cache_read_input_tokens` on Anthropic), but two things are missing. First, `AnthropicUsage` never exposes the generic `cached_input_tokens` accessor that every other provider populates, so any caller reading cache data through the uniform `ProviderUsage` surface sees `None` for Anthropic even though Anthropic reports the richest cache data of any provider. Second, nothing rolls per-call cache data up to a run-level "cache hit rate," and nothing in the repository records *where* each provider's cache-pricing rates and mechanics were verified — `PRICING_SOURCE_URL` is a single OpenAI-only URL sitting over a nine-provider table. This change adds a uniform, provider-aware `cache_hit_rate` to `ProviderUsage`, fixes the Anthropic gap, rolls cache totals and rate up to `UsageRollup`, and records the specific first-party documentation page consulted for each provider's cache-pricing mechanics.

---

## 2. Goals & Non-Goals

### Goals
- Make `cached_input_tokens` report correctly for every provider that has an entry in `PROVIDER_PRICING`, including Anthropic.
- Add a `cache_hit_rate` property to `ProviderUsage` that is correct under both provider billing models: cache-as-subset-of-input (OpenAI, Gemini, OpenRouter, and the shared `ChatCompletionUsage` family) and cache-as-additive-bucket (Anthropic).
- Roll cache totals and an aggregate hit rate up to `UsageRollup` so a caller can read run-level cache performance from `BaseAgent.get_usage()` / `AgentMessage.metadata["usage_rollup"]` without inspecting individual `UsageRecord`s.
- For every provider with a priced entry in `PROVIDER_PRICING`, record the specific first-party API documentation page that describes that provider's cache-pricing mechanics, verified today (2026-08-29).
- Where no such first-party page could be found despite a real search, say so explicitly in code and in this document rather than fabricating a URL.

### Non-Goals
- Re-verifying or changing any existing `$`-per-million rate in `PROVIDER_PRICING`. This change touches cache *visibility* and *documentation provenance*, not the rate table itself.
- Adding Mistral pricing. `ModelProvider.MISTRAL` already routes through `ChatCompletionUsage`, but `PROVIDER_PRICING` has zero entries for it today — a pre-existing gap unrelated to caching. Bootstrapping a full rate table for an unpriced provider is out of scope here.
- Modeling Gemini's separate hourly cache-storage fee. `ModelPricing` has no storage-cost dimension today; adding one is a larger schema change than this task's scope.
- Any new test file. Per this workflow's "no tests" variant, correctness is demonstrated by the full existing CI gate (`scripts/run_ci.py`) staying green, not by new test code.

---

## 3. Background & Context

`vidbyte/agents/pricing` gives every provider its own `ProviderUsage` subclass so the SDK can price a model call regardless of vendor (`AGENTS.md` §`vidbyte/agents/pricing/`). Two billing shapes exist side by side:

- **Subset billing** (OpenAI, Gemini, OpenRouter, and xAI/DeepSeek/GLM/MiniMax/Kimi/Meta/Mistral via the shared `ChatCompletionUsage`): the provider's `input_tokens` already includes the cached portion; `cached_input_tokens` names the discounted subset, and `subset_billing_cost()` in `base.py` prices the uncached remainder at the input rate and the cached subset at the cache-read rate.
- **Additive-bucket billing** (Anthropic): `input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens` are three separate, non-overlapping buckets that all bill on top of each other. `AnthropicUsage.cost_usd()` sums all four buckets directly and never calls `subset_billing_cost()`.

`ProviderUsage.cached_input_tokens` is declared once on the base class and defaults to `None`; `OpenAIUsage`, `GeminiUsage`, and `ChatCompletionUsage`/`OpenRouterUsage` each override it with a real dataclass field. `AnthropicUsage` never overrides it — an oversight, not a deliberate design choice: its own cost formula doesn't need `cached_input_tokens`, so the gap was invisible to `test_agent_pricing.py`, but any caller that reads `usage.cached_input_tokens` generically (which this change's new `cache_hit_rate` property does) would silently see "no cache activity" for the provider with the most detailed cache accounting of all.

Separately, `vidbyte/lib/registries/pricing.py` carries exactly one source-of-truth citation — `PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"` — for a table that prices nine providers. The field guide entry `operation-pricebook-rates.md` establishes the house discipline for this kind of table: cite the vendor's own page, never a third-party blog, and omit a rate rather than guess it. `docs/design/openai-gpt-5-6-catalog-pricing.md` §"Add rates... only if verified against the vendor's official pricing page... Omit the model rather than guessing" states the same rule for this exact table. No such per-provider citation exists today for the eight non-OpenAI providers' cache mechanics.

---

## 4. Requirements

### Functional Requirements
1. `ProviderUsage` gains a `total_prompt_tokens` property. It defaults to `self.input_tokens` (correct for every subset-billing provider, where `input_tokens` already spans the cached and uncached portions of the prompt).
2. `AnthropicUsage` overrides `total_prompt_tokens` to return `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` (None-safe, treating unreported buckets as `0` once at least one bucket is present), because Anthropic's `input_tokens` alone excludes both cache buckets.
3. `AnthropicUsage` overrides `cached_input_tokens` to return `self.cache_read_input_tokens`, so the generic accessor reports "tokens served from cache" consistently with every other provider.
4. `ProviderUsage` gains a `cache_hit_rate` property: `None` when `total_prompt_tokens` is `None`/`<= 0` or `cached_input_tokens` is `None`; otherwise `min(cached_input_tokens, total_prompt_tokens) / total_prompt_tokens`, clamped the same way `uncached_input_tokens` already clamps its subtraction.
5. `UsageRollup` gains two new fields: `cached_input_tokens: int | None` (None-aware sum across all calls, matching the existing `input_tokens`/`output_tokens`/`total_tokens` pattern) and `cache_hit_rate: float | None` (aggregate rate across all calls that reported both a prompt size and a cache count; `None` when no call in the run reported cache data).
6. `UsageTracker.rollup()` computes both new fields when building `UsageRollup`, using a new private helper (`_cache_hit_rate`) following the existing `_sum_or_none`-style, None-aware accumulation already used in that module.
7. `vidbyte/lib/registries/pricing.py` gains `CACHE_PRICING_SOURCE_URLS: dict[ModelProvider, str]`, mapping every provider with a `PROVIDER_PRICING` entry to the specific first-party API documentation page that describes its cache-pricing mechanics, and `CACHE_PRICING_SOURCES_AS_OF: str = "2026-08-29"` recording when those pages were checked. Both are re-exported from `vidbyte/lib/registries/__init__.py` alongside the existing `PRICING_SOURCE_URL`/`PRICING_AS_OF`.
8. `ModelProvider.META` is deliberately omitted from `CACHE_PRICING_SOURCE_URLS`, with an inline comment explaining that no first-party Meta Model API documentation page could be located as of 2026-08-29 despite the `$0.15/M` cached-input rate already in the table being corroborated by multiple independent third-party sources.

### Non-Functional Requirements
- No behavior change to any existing `cost_usd()` calculation for any provider — verified by the existing `test_agent_pricing.py` suite passing unmodified.
- No new required dependency, no new registry, no new public tool or API surface beyond the properties/fields listed above.
- Every inserted documentation URL must be the vendor's own first-party domain, not a third-party pricing aggregator or blog, per the field guide's `operation-pricebook-rates.md` discipline (applied here to cache-pricing citations by the same reasoning).

---

## 5. High-Level Design

```
UsageTracker.record_call()
        |
        v
ProviderUsage subclass (unchanged parsing)
        |
        v
NEW: usage.cached_input_tokens   (now correct for Anthropic too)
NEW: usage.total_prompt_tokens   (provider-aware prompt-size denominator)
NEW: usage.cache_hit_rate        (derived from the two above)
        |
        v
UsageTracker.rollup()
        |
        v
NEW: UsageRollup.cached_input_tokens   (summed across the run)
NEW: UsageRollup.cache_hit_rate        (aggregate across the run)
        |
        v
BaseAgent.get_usage() / AgentMessage.metadata["usage_rollup"]   (unchanged call sites, richer data)
```

Separately, `vidbyte/lib/registries/pricing.py` gains a `ModelProvider -> str` documentation-citation map (`CACHE_PRICING_SOURCE_URLS`), structured exactly like the existing `_usage_class_map` and `PROVIDER_PRICING` tables that are already keyed by `ModelProvider`. This is additive metadata; it does not participate in any resolution or pricing call path, so it carries zero runtime risk to `ModelPricingRegistry.resolve()`.

The two halves of this change are independent: the `cache_hit_rate`/`cached_input_tokens` fix is a correctness change to the usage-parsing layer; `CACHE_PRICING_SOURCE_URLS` is documentation-provenance metadata for the rate table. Both were requested together because both close the same gap — "cache hit information... for all of our providers" — from two different angles: what the SDK reports at runtime, and what the SDK can point to as evidence for how each provider's cache pricing actually works.

---

## 6. Detailed Design

### 6.1 `ProviderUsage.total_prompt_tokens` and `ProviderUsage.cache_hit_rate`

**File(s):** `vidbyte/agents/pricing/base.py`
**Type:** Modified

#### What it does
Adds the provider-agnostic denominator and the derived hit-rate property that every subclass inherits for free.

#### Interface / API
```python
@property
def total_prompt_tokens(self) -> int | None:
    # All tokens considered part of this call's prompt, cached or fresh — the
    # denominator for cache_hit_rate. Subset-billing providers already fold the
    # cached subset into input_tokens, so this defaults to input_tokens;
    # additive-bucket providers (Anthropic) override it to include their
    # separate cache-read/cache-write buckets.
    return self.input_tokens

@property
def cache_hit_rate(self) -> float | None:
    # Fraction of this call's prompt tokens served from cache; None when either
    # prompt size or cache data is unreported by the provider.
    total = self.total_prompt_tokens
    if total is None or total <= 0 or self.cached_input_tokens is None:
        return None
    return min(self.cached_input_tokens, total) / total
```

#### Logic / Algorithm
1. `total_prompt_tokens` defaults to `input_tokens`, which is already correct for every subset-billing subclass without any override.
2. `cache_hit_rate` reads `total_prompt_tokens` and `cached_input_tokens` (both already correct per-provider after 6.2) and divides, clamping the numerator the same way `uncached_input_tokens` already clamps its subtraction, so a malformed payload reporting more cached tokens than total tokens can't push the rate above `1.0`.

#### Edge Cases & Error Handling
- `total_prompt_tokens is None` (provider reported nothing) → `cache_hit_rate` is `None`, not `0.0` — "unknown" and "definitely zero" stay distinguishable, matching every other `None`-aware property in this file.
- `total_prompt_tokens == 0` → `None` (avoids a division by zero on a degenerate/empty call).
- `cached_input_tokens` is `None` (provider doesn't report cache data at all, e.g. a provider with no `usage_class()` mapping) → `None`.

---

### 6.2 `AnthropicUsage` cache accessor fix

**File(s):** `vidbyte/agents/pricing/anthropic.py`
**Type:** Modified

#### What it does
Overrides the two generic accessors so Anthropic's already-parsed `cache_creation_input_tokens`/`cache_read_input_tokens` become visible through the shared `ProviderUsage` surface.

#### Interface / API
```python
@property
def cached_input_tokens(self) -> int | None:
    # Maps Anthropic's cache-read bucket onto the shared cached-input accessor.
    return self.cache_read_input_tokens

@property
def total_prompt_tokens(self) -> int | None:
    # Anthropic's input_tokens excludes both cache buckets (additive billing),
    # so the prompt total is all three buckets combined.
    parts = (self.input_tokens, self.cache_creation_input_tokens, self.cache_read_input_tokens)
    if all(part is None for part in parts):
        return None
    return sum(part or 0 for part in parts)
```

#### Logic / Algorithm
1. `cached_input_tokens` is a one-line pass-through to the field Anthropic already parses in `from_usage_payload()`.
2. `total_prompt_tokens` mirrors the exact None-handling idiom `total_tokens` already uses two properties above it in the same file (`all(... is None ...)` guard, then `sum(part or 0 ...)`), so the new property reads as consistent with the rest of the class rather than introducing a new idiom.

#### Edge Cases & Error Handling
- A cache-miss-only call (`cache_creation_input_tokens` and `cache_read_input_tokens` both `0` or `None`, only `input_tokens` populated) → `total_prompt_tokens == input_tokens`, `cache_hit_rate == 0.0` (correctly "no hit," not "unknown," since the buckets were reported as zero/absent rather than the whole payload being unparseable).
- `cost_usd()` is untouched — it already sums all four buckets directly and never reads `cached_input_tokens` or `total_prompt_tokens`, so this change cannot alter any existing cost figure.

---

### 6.3 `UsageRollup` cache fields

**File(s):** `vidbyte/agents/pricing/records.py`
**Type:** Modified

#### What it does
Adds run-level cache visibility next to the existing token/cost totals.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class UsageRollup:
    calls: tuple[UsageRecord, ...] = field(default_factory=tuple)
    model_call_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None      # NEW
    cache_hit_rate: float | None = None         # NEW
    cost_usd: float | None = None
    cost_complete: bool = False
    operations: tuple[OperationUsageRecord, ...] = field(default_factory=tuple)
    operation_count: int = 0
    recording_integrity: UsageRecordingIntegrity = UsageRecordingIntegrity.INTACT
```

#### Logic / Algorithm
Pure data addition; both fields default to `None` so every existing construction of `UsageRollup()` in the test suite and elsewhere keeps working unmodified (dataclass defaults, not positional-order-sensitive since all fields already have defaults).

#### Edge Cases & Error Handling
N/A — this is a typed container with no logic of its own; correctness lives entirely in 6.4.

---

### 6.4 `UsageTracker.rollup()` cache aggregation

**File(s):** `vidbyte/agents/pricing/tracker.py`
**Type:** Modified

#### What it does
Computes the two new `UsageRollup` fields from the run's recorded calls.

#### Interface / API
```python
def rollup(self) -> UsageRollup:
    ...
    return UsageRollup(
        calls=records,
        model_call_count=len(records),
        input_tokens=_sum_or_none(record.usage.input_tokens for record in records),
        output_tokens=_sum_or_none(record.usage.output_tokens for record in records),
        total_tokens=_sum_or_none(record.usage.total_tokens for record in records),
        cached_input_tokens=_sum_or_none(record.usage.cached_input_tokens for record in records),  # NEW
        cache_hit_rate=_cache_hit_rate(records),                                                    # NEW
        cost_usd=_sum_or_none(token_costs + operation_costs),
        cost_complete=bool(records or operations) and all(cost is not None for cost in token_costs + operation_costs),
        operations=operations,
        operation_count=len(operations),
        recording_integrity=(...),
    )


def _cache_hit_rate(records: Iterable[UsageRecord]) -> float | None:
    # Aggregate cache-hit rate across every call that reported both a prompt
    # size and a cached-token count; None when no call in the run reported
    # cache data at all. Weighted by prompt size, not averaged per call, so a
    # handful of huge cached calls aren't diluted by many tiny uncached ones.
    cached_total = 0
    prompt_total = 0
    reported = False
    for record in records:
        usage = record.usage
        total = usage.total_prompt_tokens
        if total is None or usage.cached_input_tokens is None:
            continue
        cached_total += min(usage.cached_input_tokens, total)
        prompt_total += total
        reported = True
    if not reported or prompt_total <= 0:
        return None
    return cached_total / prompt_total
```

#### Logic / Algorithm
1. `cached_input_tokens` reuses the existing `_sum_or_none` helper exactly like the three token totals immediately above it — no new summation idiom.
2. `_cache_hit_rate` is a new private module-level function, placed alongside the existing `_parse_usage`/`_as_provider`/`_is_billable_key`/`_reported_or_table_cost`/`_sum_or_none` free functions this module already uses (this file has no class-bound-helper convention to match — see §13 for why a bound helper class was considered and rejected).
3. It accumulates a weighted rate (`sum(cached) / sum(total)`) rather than averaging each call's individual `cache_hit_rate`, so the run-level number reflects actual token volume rather than treating a 50-token call and a 50,000-token call as equally important.

#### Edge Cases & Error Handling
- A run with zero model calls → both new fields are `None`, matching how `input_tokens` etc. already behave for an empty run.
- A run where every call used a provider with no cache reporting at all (e.g. a provider with no `usage_class()`, or one that never populates `cached_input_tokens`) → `cache_hit_rate` is `None`, not `0.0`, preserving the "unknown vs. definitely zero" distinction from 6.1.
- A run mixing providers, some reporting cache data and some not → only the calls that reported both `total_prompt_tokens` and `cached_input_tokens` contribute to either accumulator; calls without cache data are silently skipped rather than treated as zero-cache, which would understate the true rate.

---

### 6.5 Per-provider cache-pricing documentation citations

**File(s):** `vidbyte/lib/registries/pricing.py`, `vidbyte/lib/registries/__init__.py`
**Type:** Modified

#### What it does
Records the specific first-party API documentation page consulted for each provider's cache-pricing mechanics, replacing the implicit assumption that the single OpenAI-scoped `PRICING_SOURCE_URL` covers the whole table.

#### Interface / API
```python
CACHE_PRICING_SOURCES_AS_OF: str = "2026-08-29"

# First-party documentation for each provider's cache-pricing mechanics, checked
# on CACHE_PRICING_SOURCES_AS_OF. ModelProvider.META is deliberately absent: no
# first-party Meta Model API documentation page could be located for Muse Spark's
# cache pricing despite the $0.15/M cache_read_per_million rate above being
# corroborated by multiple independent third-party sources. Omitted rather than
# guessed, per the same discipline docs/design/openai-gpt-5-6-catalog-pricing.md
# applies to the rate table itself.
CACHE_PRICING_SOURCE_URLS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "https://developers.openai.com/api/docs/guides/prompt-caching",
    ModelProvider.ANTHROPIC: "https://platform.claude.com/docs/en/build-with-claude/prompt-caching",
    ModelProvider.GEMINI: "https://ai.google.dev/gemini-api/docs/caching",
    ModelProvider.XAI: "https://docs.x.ai/developers/advanced-api-usage/prompt-caching",
    ModelProvider.DEEPSEEK: "https://api-docs.deepseek.com/guides/kv_cache/",
    ModelProvider.GLM: "https://docs.z.ai/guides/capabilities/cache",
    ModelProvider.MINIMAX: "https://platform.minimax.io/docs/api-reference/text-prompt-caching",
    ModelProvider.KIMI: "https://platform.moonshot.ai/docs/guide/use-context-caching-feature-of-kimi-api",
    ModelProvider.OPENROUTER: "https://openrouter.ai/docs/guides/best-practices/prompt-caching",
}
```
`__all__` in both `vidbyte/lib/registries/pricing.py` and `vidbyte/lib/registries/__init__.py` gains `"CACHE_PRICING_SOURCE_URLS"` and `"CACHE_PRICING_SOURCES_AS_OF"`, and the latter file's import line adds both names from `vidbyte.lib.registries.pricing`.

#### Logic / Algorithm
A static, provider-keyed dict — no resolution logic, no lookup method beyond ordinary `dict.get(provider)`. Kept at provider granularity (like `_usage_class_map` and the top-level keys of `PROVIDER_PRICING`) rather than duplicated per-model, since the cache-pricing *mechanism* documentation is genuinely shared across every model a given vendor prices — duplicating the same URL across 5-9 `ModelPricing` entries per provider would violate the "value declared exactly once" discipline the rest of `vidbyte/lib/constants` already follows.

#### Verification performed against each cited page (2026-08-29)
Cross-checked the mechanic and, where a concrete figure was independently reported, the number, against the existing `PROVIDER_PRICING` entries:
- **OpenAI** — cached tokens discounted automatically, no code change required; `gpt-5.6-sol` cache_read (`0.5`) is exactly 10% of its input rate (`5.0`), consistent with the documented discount range.
- **Anthropic** — 5-minute cache writes at 1.25x base input price, cache reads at 0.1x; `claude-sonnet-5` (`input=2.0, cache_write=2.5, cache_read=0.2`) and `claude-opus-4-8` (`input=5.0, cache_write=6.25, cache_read=0.5`) both match those multipliers exactly.
- **Gemini** — cached tokens billed at a reduced rate plus a separate storage fee (storage not modeled here, see Non-Goals); `gemini-3.5-flash` cache_read (`0.15`) is exactly 10% of its input rate (`1.5`).
- **xAI** — automatic prompt caching; independently reported figures for `grok-4.5` ($0.30/M cached), `grok-4.3` ($0.20/M cached), and `grok-build-0.1` ($0.20/M cached) match the table's `cache_read_per_million` values exactly for all three models.
- **DeepSeek** — Context Caching on Disk, enabled by default; `deepseek-v4-flash` (`0.0028`) matches the independently reported cache-hit rate exactly.
- **GLM (Z.ai)** — automatic context caching; `glm-5.2` (`0.26` against `1.40` input) matches the independently reported figure exactly.
- **MiniMax** — automatic prefix-based caching; `MiniMax-M3` cache_read (`0.06`) is consistent with the documented list-price cache rate (`0.12`) halved by the same "permanent 50% off" promo the existing code comment already notes for the input/output rates.
- **Kimi (Moonshot)** — automatic context caching, no configuration required; `kimi-k2.7-code` (`0.19`) matches the independently reported cache-hit figure exactly.
- **OpenRouter** — pass-through caching whose rate depends on the routed provider; consistent with the table's existing empty `{}` entry and `OpenRouterUsage` preferring the provider-reported `usage.cost`.

#### Edge Cases & Error Handling
- `CACHE_PRICING_SOURCE_URLS.get(provider)` returning `None` for `ModelProvider.META` (and every provider without a `PROVIDER_PRICING` entry, e.g. `MISTRAL`, `ELEVENLABS`, `PLAYAI`) is the expected, documented behavior — callers must not treat a missing key as a bug.

---

## 7. Data Model Changes

### 7.1 `UsageRollup` (dataclass, `vidbyte/agents/pricing/records.py`)

**Change type:** Modified (additive fields only)

```python
cached_input_tokens: int | None = None
cache_hit_rate: float | None = None
```

**Migration strategy:** N/A — both new fields default to `None`, so every existing call site constructing a `UsageRollup` (in `tracker.py` and in tests) continues to work without modification. This is a purely additive, backward-compatible dataclass change.

---

## 8. API Changes

N/A — no HTTP endpoints. The only public-surface changes are new properties (`ProviderUsage.total_prompt_tokens`, `ProviderUsage.cache_hit_rate`), new dataclass fields (`UsageRollup.cached_input_tokens`, `UsageRollup.cache_hit_rate`), and two new module-level constants (`CACHE_PRICING_SOURCE_URLS`, `CACHE_PRICING_SOURCES_AS_OF`), all additive and all documented in §6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/pricing/base.py` | Add `total_prompt_tokens` and `cache_hit_rate` properties to `ProviderUsage`. |
| MODIFY | `vidbyte/agents/pricing/anthropic.py` | Override `cached_input_tokens` and `total_prompt_tokens` so Anthropic's cache buckets surface through the shared accessor. |
| MODIFY | `vidbyte/agents/pricing/records.py` | Add `cached_input_tokens` and `cache_hit_rate` fields to `UsageRollup`. |
| MODIFY | `vidbyte/agents/pricing/tracker.py` | Populate the two new `UsageRollup` fields in `rollup()`; add `_cache_hit_rate` helper. |
| MODIFY | `vidbyte/lib/registries/pricing.py` | Add `CACHE_PRICING_SOURCE_URLS` and `CACHE_PRICING_SOURCES_AS_OF`; export both from `__all__`. |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Re-export the two new constants alongside the existing `PRICING_SOURCE_URL`/`PRICING_AS_OF`. |
| MODIFY | `docs/design/cache-hit-tracking-all-providers.md` | This design doc, committed first per workflow. |

No files are deleted. No new files are created (the design doc is the only new file, per workflow requirement).

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None (new) | — | This change adds no new runtime dependency, network call, or external service. The inserted URLs are inert string constants, not fetched at runtime. | None |

---

## 11. Rollout & Deployment

- No feature flag — this is additive data (new properties/fields default sensibly) with no behavior change to any existing code path.
- Not a breaking change: every new field has a safe default, and no existing method signature, return type, or cost calculation changes.
- No deployment ordering concerns (single package, no service boundary).
- Rollback: revert the commits; no data migration exists to unwind since nothing is persisted externally.

---

## 12. Open Questions

- [ ] Should `ModelProvider.META`'s cache-pricing citation be revisited once (or if) Meta Model API publishes first-party developer documentation? Tracked here rather than blocking this change — the `$0.15/M` rate already in the table is well-corroborated by independent third-party reporting even without a first-party citation.
- [ ] Should `PRICING_SOURCE_URL` (singular, OpenAI-only) eventually be replaced by a provider-keyed map the same shape as the new `CACHE_PRICING_SOURCE_URLS`, for the base input/output rates too? Left alone here as a pre-existing pattern outside this task's scope.
- [ ] Gemini's per-hour cache-storage fee has no home in `ModelPricing` today. Worth a follow-up design doc if storage-cost accuracy becomes a priority.

---

## 13. Alternatives Considered

### Alternative 1: Per-model cache-pricing URLs on `ModelPricing` itself
- What: Add a `cache_pricing_source_url: str | None` field directly to the `ModelPricing` dataclass, set on every one of the ~30 model entries.
- Why rejected: The cache-pricing *documentation page* is a provider-level fact (one page per vendor covers every model that vendor prices), not a per-model fact. Duplicating the same URL string across 5-9 entries per provider violates the "declare a shared value exactly once" discipline `vidbyte/lib/constants` already follows elsewhere in this codebase, and would require touching every existing `ModelPricing(...)` construction instead of adding one new dict.

### Alternative 2: A bound helper class for the new tracker aggregation function
- What: Wrap `_cache_hit_rate` (and the existing free functions in `tracker.py`) in a static helper class, per the field guide's `class-bound-helpers.md` guidance for "a module of related free functions."
- Why rejected: That guidance targets a *new* module being introduced with several related free functions and no existing convention. `tracker.py` already has five established private free functions (`_parse_usage`, `_as_provider`, `_is_billable_key`, `_reported_or_table_cost`, `_sum_or_none`) with no bound-helper wrapper; introducing one now for a sixth function would create an inconsistent module rather than following its existing, already-settled local convention.

### Alternative 3: Treat a missing `cache_hit_rate` as `0.0` instead of `None`
- What: Default the aggregate and per-call rate to `0.0` when a provider reports no cache data, rather than `None`.
- Why rejected: Every other derived accessor in this file (`uncached_input_tokens`, `total_tokens` on the additive providers) already treats "provider didn't report this" as `None`, distinct from "provider reported zero." Collapsing "unknown" into "definitely zero" would make a provider with no cache support at all look identical to one that supports caching but had a 0% hit rate on a given run — a real and useful distinction for anyone using this as an SLO signal.

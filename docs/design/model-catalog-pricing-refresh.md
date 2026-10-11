# Design Doc: Model Catalog and Pricebook Refresh (October 2026)

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

The SDK's model catalog (`vidbyte/lib/constants/runners.py`) and token pricebook (`vidbyte/lib/registries/pricing.py`) were last refreshed for OpenAI's GPT-5.6 launch, with `PRICING_AS_OF = "2026-07-30"`. Since then every frontier lab has shipped new models: GPT-6 Astra, Sol, Luna and GPT-6.1 Sol; Claude Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5; Gemini 3.8 Flash; Grok 4.7; and others. Several served prices have also changed. This change adds every current text model that a provider we already offer lists on its own API docs. Each one gets the price that provider's own pricing page states, cited in a comment above the row. It also corrects existing rows whose first-party price has changed, and fixes the one formula gap (Claude Haiku 5.5's 100K prompt tier) that would otherwise misprice a newly added model.

---

## 2. Goals & Non-Goals

### Goals
- Add the current text models of each provider in `ModelProvider` (OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM/Z.ai, MiniMax, Kimi/Moonshot, Meta, Mistral) that the catalog lacks, to both runner maps and the modality map.
- Give each added model a `PROVIDER_PRICING` row equal to the rate the provider charges on its own API. The comment above each row cites the provider's documentation URL.
- Price current-lineup models that are already catalogued but have no price row: claude-fable-5, claude-mythos-5, gemini-3.1-flash-lite, kimi-k3, kimi-k2.6, and Mistral's medium/small/large aliases.
- Correct existing rows whose first-party price changed: gpt-5.6-sol, gemini-3.6-flash, gemini-3.5-flash (now routed to 3.6 Flash), deepseek-v4-pro and deepseek-v4-flash.
- Price Claude Haiku 5.5's 100K prompt tier correctly. Anthropic counts cache reads and writes toward that threshold.
- Move `PRICING_AS_OF` to 2026-10-11 and refresh the C010 vintage lock.

### Non-Goals
- Adding new providers, such as Qwen/Alibaba or NVIDIA. Each needs an adapter, endpoint, key and usage parser.
- Changing any provider's default model in `DEFAULT_PROVIDER_MODELS`.
- Pricing legacy catalogued models that have no price today, such as gpt-4o, o3 and gemini-2.5-*.
- Time-of-day (DeepSeek peak/off-peak), batch, flex, fast or data-residency billing in the cost formulas. These stay metadata or comments, as for GPT-5.6 today.
- Separate 1-hour cache-write pricing for Anthropic and Kimi. The single `cache_write_per_million` stays the 5-minute rate, as today.
- Models that are subscription-only, verification-only with no documented API price, or deprecated: MiniMax-M3.1-Flash-Preview (M Plan only), gpt-5.6-cyber and gpt-rosalind-* (trusted access), devstral-2512 (deprecated) and gemini-3.7-flash (deprecated, routed).
- Bumping the backend's SDK pin. That belongs to the backend repo.
- Image, video, audio and embedding models. The SDK prices none of its 47 catalogued non-text models, and `PROVIDER_PRICING` has no per-image or per-second unit. So a new media model could not get the correct price the request asks for until a media pricing path exists.

---

## 3. Background & Context

- **Why now:** The user asked for an up-to-date catalog with first-party-verified prices. The backend's managed generative route (Vidbyte#672) bills callers from this pricebook at cost plus 2%. A missing row means a refused call, and a stale row means a wrong charge.
- **Current state:** The catalog stops at GPT-5.6, Claude Sonnet 5 / Opus 4.8 / Fable 5, Gemini 3.5 Flash, Grok 4.5, GLM 5.2, Kimi K2.7 Code and Muse Spark 1.1. Mistral has no price rows at all, so C009 carries its default as baseline debt.
- **Constraints:**
  - `ModelPricingRegistry.resolve` falls back to the longest key prefix. A new model whose name extends an older key, such as `claude-sonnet-5-5` over `claude-sonnet-5` or `glm-5.3` over `glm-5`, is silently priced at the older model's rate until it gets its own row.
  - C010 requires `PRICING_AS_OF` to move whenever any rate changes. The backend persists that vintage as each resumable run's pricebook identity.
  - S014 requires the qualified and bare runner maps to stay in parity.
  - Memory/feedback: every rate must equal the provider's own API price, with the doc URL in the comment. A promotional served price is priced as served, with the regular rate noted.

### Verified first-party sources (fetched 2026-10-11)

| Provider | Source pages |
|---|---|
| OpenAI | https://developers.openai.com/api/docs/pricing ; https://developers.openai.com/api/docs/models/{gpt-6-astra,gpt-6-sol,gpt-6.1-sol,gpt-6-luna,gpt-5.6-sol} |
| Anthropic | https://platform.claude.com/docs/en/about-claude/pricing ; https://platform.claude.com/docs/en/models/{fable-5-1,opus-5-5,sonnet-5-5,haiku-5-5,mythos-5-1,opus-5,fable-5,mythos-5}/overview |
| Gemini | https://ai.google.dev/gemini-api/docs/pricing ; https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash (deprecation and routing notice) |
| xAI | https://docs.x.ai/developers/models ; https://docs.x.ai/developers/models/{grok-4.7,grok-4.6} |
| DeepSeek | https://api-docs.deepseek.com/quick_start/pricing |
| GLM (Z.ai) | https://docs.z.ai/guides/overview/pricing ; https://docs.z.ai/guides/llm/glm-5.3 ; https://docs.z.ai/guides/vlm/glm-5.3-flash |
| MiniMax | https://platform.minimax.io/docs/guides/pricing-paygo (no change needed) |
| Kimi | https://platform.kimi.ai/docs/pricing/chat |
| Meta | https://dev.meta.ai/docs/pricing-rate-limits ; https://dev.meta.ai/docs/prompt-caching |
| Mistral | https://docs.mistral.ai/models/{mistral-medium-3-5-26-04,mistral-small-4-0-26-03,mistral-large-3-25-12,mistral-large-4-0} |

### Rates (USD per 1M tokens; "long" = over-threshold tier)

| Model | Input | Cached | Cache write | Output | Threshold → long in / out |
|---|---|---|---|---|---|
| gpt-6-astra | 10 | 1.0 | 12.5 | 50 | >272K → 20 / 75 |
| gpt-6-sol | 2 | 0.2 | 2.5 | 10 | >272K → 4 / 15 |
| gpt-6.1-sol | 2 | 0.1 | 2.5 | 10 | >272K → 4 / 15 |
| gpt-6-luna | 0.1 | 0.01 | 0.125 | 0.5 | >272K → 0.2 / 0.75 |
| gpt-5.6-sol (promo, at least through 2026-11-21) | 4 | 0.4 | 5 | 20 | >272K → 8 / 30 |
| claude-fable-5-1, claude-mythos-5-1 | 10 | 0.25 | 12.5 | 50 | none |
| claude-opus-5-5 | 4 | 0.2 | 5 | 20 | none |
| claude-sonnet-5-5 | 2 | 0.1 | 2.5 | 10 | none |
| claude-haiku-5-5 | 0.1 | 0.01 | 0.125 | 0.5 | prompt >100K (all input incl. cache) → 0.5 / 2.5 |
| claude-opus-5 | 5 | 0.5 | 6.25 | 25 | none |
| claude-fable-5, claude-mythos-5 | 10 | 1.0 | 12.5 | 50 | none |
| gemini-3.8-flash, gemini-3.6-flash, gemini-3.5-flash (routed) | 0.75 | 0.075 | - | 3.75 | none; promo through 2026-12-31, then 1.50/0.15/7.50 |
| gemini-3.5-flash-lite | 0.30 | 0.03 | - | 2.50 | none |
| gemini-3.1-flash-lite | 0.25 | 0.025 | - | 1.50 | none (text rate) |
| grok-4.7, grok-4.6 | 2 | 0.5 | - | 6 | ≥200K → 4 / 12 (inclusive) |
| deepseek-flash, deepseek-v4-flash | 0.30 | 0.006 | - | 1.20 | peak rate; off-peak is half |
| deepseek-v4-pro | 1.32 | 0.044 | - | 3.96 | peak rate; off-peak is half |
| glm-5.3 | 1.4 | 0.26 | - | 4.4 | none |
| glm-5.3-flash | 0.15 | 0.03 | - | 0.50 | none |
| glm-5.3-flashx | 0.37 | 0.075 | - | 1.25 | none |
| kimi-k3 | 3.00 | 0.30 | 3.00 (5-min TTL) | 15.00 | none |
| kimi-k2.6 | 0.95 | 0.16 | - | 4.00 | none |
| muse-spark-1.3, muse-spark-1.2 | 1.25 | 0.15 | - | 4.25 | none |
| muse-spark-1.3-contributor, -1.2-contributor | 0.10 | 0.002 | - | 0.20 | none |
| mistral-medium-3-5, mistral-medium-latest | 1.5 | - | - | 7.5 | none |
| mistral-small-2603, mistral-small-latest | 0.15 | - | - | 0.6 | none |
| mistral-large-2512, mistral-large-latest | 0.5 | - | - | 1.5 | none |
| mistral-large-4, mistral-large-4-0 (sale) | 0.68 | 0.07 | - | 2.09 | none; original 1.36/0.14/4.18 |

Rows re-checked and unchanged:
- gpt-5.6-terra/luna, gpt-5.5, gpt-5.4 family;
- Claude Sonnet 4.x, Opus 4.x and Haiku 4.5;
- gemini-3.1-pro-preview;
- grok-4.5, grok-4.3 and grok-build-0.1;
- GLM 5.2/5.1/5/4.7/4.6/4.5;
- MiniMax M3/M2.7, kimi-k2.7-code and muse-spark-1.1.

`glm-5-turbo` is no longer listed on Z.ai's pricing page. Its row is kept as is and a comment says so.

---

## 4. Requirements

### Functional Requirements
1. Each added model resolves through `ProviderModelRegistry.validate_provider_model_pair(provider, model)` under strict validation.
2. Each added model resolves, by exact key, to a `ModelPricing` whose fields equal the table in §3. No added model resolves through a shorter sibling prefix.
3. `ModalityDetector.detect_modality(model)` returns `TEXT` for every added model.
4. `gpt-5.6-sol` resolves to 4 / 20 / 0.4 / 5.0, with a 272K threshold and 8 / 30 over it. Its tier metadata matches the pricing page for the standard, batch, flex and fast tiers.
5. GPT-6 tier metadata (`OPENAI_GPT6_TIER_RATES`) carries the standard, batch, flex and fast rates, plus ultrafast for astra and 6.1-sol, as published.
6. For `claude-haiku-5-5`, `AnthropicUsage.cost_usd` charges the over-threshold rates when input plus cache reads plus cache writes is over 100,000. It charges base rates at exactly 100,000.
7. Anthropic models without a threshold still price exactly as before. The threshold change only affects rows that set `threshold_tokens`.
8. `deepseek-v4-flash` and `deepseek-flash` resolve to the same rates.
9. `gemini-3.5-flash` resolves to the `gemini-3.6-flash` rates.
10. `PRICING_AS_OF == "2026-10-11"`, and C010 passes with a refreshed lock.
11. The Mistral default (`mistral-medium-latest`) resolves to a price, so C009's Mistral finding is gone and its baseline is ratcheted down.

### Non-Functional Requirements
- **Performance:** dictionary additions only. `resolve` stays O(rows per provider).
- **Security:** no keys, no network calls in tests.
- **Observability:** unchanged. Unpriced models still record `cost_usd=None`.
- **Reliability:**
  - Every comment cites a first-party URL.
  - Promotional rates name their end date and regular rate, so the next refresh knows when they lapse (gemini 2026-12-31 → 2027-01-01; gpt-5.6-sol "at least through 2026-11-21").

---

## 5. High-Level Design

This is a data refresh with one formula fix. Four registries change in step:
- the runner catalog (qualified and bare maps);
- the modality map;
- `ProviderModelRegistry.OPENAI_CATALOG`;
- the pricebook.

A new `OPENAI_GPT6_TIER_RATES` constant holds GPT-6 per-tier metadata, beside the existing GPT-5.6 one. Anthropic's usage parser gains an override of the shared threshold check. Anthropic's `input_tokens` excludes both cache buckets, while Anthropic's documented Haiku 5.5 threshold counts all of them.

```
caller model name ──► ProviderModelRegistry.validate_provider_model_pair ──► runners.py catalog (S014 parity)
                 └──► ModalityDetector ──► model_modality.py map / prefixes
response usage ──► UsageTracker ──► ModelPricingRegistry.resolve(provider, model) ──► PROVIDER_PRICING row
                                 └──► ProviderUsage.cost_usd(pricing)
                                          └─ AnthropicUsage._over_threshold → total_prompt_tokens (new)
```

**Key decisions:**
1. **DeepSeek is priced at the peak rate.** The table already carries each provider's undiscounted standard rate and leaves condition-dependent discounts unmodelled (OpenAI batch/flex, Anthropic batch). DeepSeek's off-peak rate is a 50% discount that depends on the UTC hour, so the peak rate is the standard one and never under-bills. Off-peak rates are kept in `tier_rates` metadata and in the comment.
2. **gemini-3.5-flash is priced as gemini-3.6-flash.** Google's model page says every request to it "is automatically routed to gemini-3.6-flash", and the pricing page no longer lists 3.5 Flash. Keeping 1.50/9.00 would overcharge by roughly 2x.
3. **Promotional rates are priced as served,** with the regular rate in the comment (existing rule).
4. **No provider defaults change** (non-goal). A deprecated default (gemini-3.5-flash) still prices correctly through decision 2.

---

## 6. Detailed Design

### 6.1 Pricebook rows

**File(s):** `vidbyte/lib/registries/pricing.py`
**Type:** Modified

#### What it does
Holds every model's per-token USD rates.

#### Interface / API
```python
OPENAI_GPT6_TIER_RATES: dict[str, dict[str, dict[str, float]]]   # new, exported in __all__
DEEPSEEK_TIME_OF_DAY_RATES: dict[str, dict[str, dict[str, float]]]  # new, exported in __all__
PRICING_AS_OF: str = "2026-10-11"
PROVIDER_PRICING[ModelProvider.MISTRAL] = {...}                    # new provider block
```

#### Logic / Algorithm
1. Add `OPENAI_GPT6_TIER_RATES` with the same field names as `OPENAI_GPT56_TIER_RATES`. gpt-6-sol's long-context fields are derived from its model page's stated rule (2x input and cache, 1.5x output), because the "All models" table shows only short-context columns for it.
2. Update `gpt-5.6-sol` in both the tier constant and the row.
3. Add or modify the rows in §3, each provider block headed by a comment citing its first-party URL(s) and noting promotions, peak/off-peak or routing.
4. Add `DEEPSEEK_TIME_OF_DAY_RATES` (peak and off-peak input, cached-input and output rates for `deepseek-flash` and `deepseek-v4-pro`), and attach it as `tier_rates` on the DeepSeek rows. The rows bill the peak rate, because the SDK does not know the request time in DeepSeek's billing timezone.
5. Update the module docstring's Architecture list to name both new constants, and re-export them from `vidbyte/lib/registries/__init__.py` beside `OPENAI_GPT56_TIER_RATES`.
6. Move `PRICING_AS_OF`, then run `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`.

#### Edge Cases & Error Handling
- **Prefix capture:** each new model has an exact key, and tests assert exact-key equality for all of them.
- **No published cache rate (Mistral medium/small/large-3):** `cache_read_per_million=None`, so cached tokens price at the input rate. That overstates cost and never understates it.

### 6.2 Anthropic prompt-length threshold

**File(s):** `vidbyte/agents/pricing/anthropic.py`
**Type:** Modified

#### What it does
Prices Anthropic calls. It gains `_over_threshold`, so the tier decision uses the full prompt.

#### Interface / API
```python
def _over_threshold(self, pricing: ModelPricing) -> bool:
    # Anthropic counts cache reads and writes toward its prompt-length tier, so compare the full prompt.
```

#### Logic / Algorithm
1. If `pricing.threshold_tokens` is None or `total_prompt_tokens` is None, return False.
2. Compare `total_prompt_tokens` with the threshold, honoring `threshold_inclusive`, exactly as the base class does.
3. The base `effective_rates` already scales the cache-read and cache-write rates by the active input ratio. For Haiku 5.5 that gives ×5, which matches Anthropic's published over-threshold cache rates (0.05 and 0.625).

#### Edge Cases & Error Handling
- No usage fields → None → base rates, as before.
- A prompt of exactly 100,000 → base rates, because Anthropic says "over 100,000".
- A small uncached input plus a large cache read over 100K → high tier. This is the case the old code underpriced.

### 6.3 Runner catalog

**File(s):** `vidbyte/lib/constants/runners.py`
**Type:** Modified

Add each new model to `MODEL_PROVIDER_RUNNER_TYPE_MAP` (`<provider>/<model>`, lowercase) and to `MODEL_RUNNER_TYPE_MAP` (bare) as `RUNNER_TYPE_TEXT`.

The new models:
- `gpt-6-astra`, `gpt-6-sol`, `gpt-6.1-sol`, `gpt-6-luna`
- `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-mythos-5-1`, `claude-opus-5`
- `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`
- `grok-4.7`, `grok-4.6`
- `deepseek-flash`
- `glm-5.3`, `glm-5.3-flash`, `glm-5.3-flashx`
- `muse-spark-1.3`, `muse-spark-1.2`, `muse-spark-1.3-contributor`, `muse-spark-1.2-contributor`
- `mistral-medium-3-5`, `mistral-small-2603`, `mistral-large-4`, `mistral-large-4-0`

Update the header's KNOWN EDGE CASES / RELATED DOCS line.

### 6.4 Modality map and OpenAI catalog tuple

**File(s):** `vidbyte/lib/enums/model_modality.py`, `vidbyte/lib/registries/models.py`
**Type:** Modified

- Add `ModelNameModality` members and bare `_MODEL_NAME_MODALITY_MAP` entries for the new models, following PR #301's pattern. Also add the missing entry for the already-catalogued `muse-spark-1.1`. Skip names that already have an entry, such as `mistral-small-2603`.
- Add the GPT-6 models to `ProviderModelRegistry.OPENAI_CATALOG`.

### 6.5 Registries README

**File(s):** `vidbyte/lib/registries/README.md`
**Type:** Modified

Meta now publishes a first-party prompt-caching and pricing page, so:
- replace the "Meta deliberately absent" paragraph;
- add a Meta row and a Mistral row to the cache-source table.

---

## 7. Data Model Changes

N/A. No persisted schema changes. `ModelPricing` gains no fields; only table data changes.

The backend persists `PRICING_AS_OF` as a run's pricebook version. Runs started under `2026-07-30` cannot resume after the backend bumps its SDK pin, which is C010's intended behavior.

---

## 8. API Changes

N/A. No HTTP endpoints. The public Python surface gains two exported constants, `OPENAI_GPT6_TIER_RATES` and `DEEPSEEK_TIME_OF_DAY_RATES`, and the new catalogued model names.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/model-catalog-pricing-refresh.md` | This design doc |
| MODIFY | `vidbyte/lib/registries/pricing.py` | New and corrected rate rows, GPT-6 tier metadata, Mistral block, vintage |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Re-export `OPENAI_GPT6_TIER_RATES` and `DEEPSEEK_TIME_OF_DAY_RATES` |
| MODIFY | `lint/pricebook_vintage_lock.json` | C010 lock refresh for the new vintage |
| MODIFY | `lint/baseline.json` | Ratchet C009 down after Mistral's default becomes priced (only if the rule reports IMPROVED) |
| MODIFY | `vidbyte/agents/pricing/anthropic.py` | Prompt-length threshold counts cache buckets |
| MODIFY | `vidbyte/lib/constants/runners.py` | Catalog the new models (both maps) |
| MODIFY | `vidbyte/lib/enums/model_modality.py` | Modality entries for the new models |
| MODIFY | `vidbyte/lib/registries/models.py` | GPT-6 in `OPENAI_CATALOG` |
| MODIFY | `vidbyte/lib/registries/README.md` | Meta and Mistral first-party cache sources |
| CREATE | `tests/features/sdk_model_catalog/FEATURE.md` | Feature contract for the refreshed catalog |
| CREATE | `tests/features/sdk_model_catalog/README.md` | Pack README (scope, file index, how to run) |
| CREATE | `tests/features/sdk_model_catalog/test_catalog_pricing_contract.py` | Catalog, exact-rate, prefix and threshold tests |
| CREATE | `scripts/test_model_catalog_pricing_refresh.py` | Phase-5 verification script with PASS/FAIL per case |

---

## 10. Testing Plan

### Unit Tests
- `describe('catalog')` → `it('accepts every added model under its own provider with strict validation')` — [Hidden Assumption]
- `describe('catalog')` → `it('rejects an added model declared under the wrong provider, e.g. claude-opus-5-5 under openai')` — [Hidden Assumption]
- `describe('catalog')` → `it('keeps qualified and bare maps in parity for every added model')` — [Hidden Failure]
- `describe('modality')` → `it('detects TEXT for every added model')` — [Edge Case]
- `describe('pricebook')` → `it('prices every added model with exactly the first-party rates from §3')` — [Silent Failure]
- `describe('pricebook')` → `it('resolves each added model by its own exact key, not a shorter sibling prefix (sonnet-5-5 vs sonnet-5, glm-5.3 vs glm-5, mythos-5-1 vs mythos-5)')` — [Silent Failure]
- `describe('pricebook')` → `it('prices a dated/versioned response id such as claude-opus-5-5-20260922 at the opus-5-5 rate')` — [Edge Case]
- `describe('pricebook')` → `it('prices gpt-5.6-sol at the promotional 4/20 rate, and its tier metadata matches')` — [Silent Failure]
- `describe('pricebook')` → `it('prices deepseek-v4-flash identically to deepseek-flash')` — [Hidden Assumption]
- `describe('pricebook')` → `it('prices gemini-3.5-flash identically to gemini-3.6-flash')` — [Hidden Assumption]
- `describe('pricebook')` → `it('applies xAI grok-4.7 high tier at exactly 200,000 input tokens (inclusive)')` — [Edge Case]
- `describe('pricebook')` → `it('applies OpenAI gpt-6-astra long tier only above 272,000, not at it')` — [Edge Case]
- `describe('pricebook')` → `it('GPT-6 tier metadata has standard/batch/flex/fast for all four models and ultrafast for astra and 6.1-sol')` — [Silent Failure]
- `describe('AnthropicUsage')` → `it('charges Haiku 5.5 high tier when a small uncached input plus a large cache read exceeds 100K')` — [Silent Failure]
- `describe('AnthropicUsage')` → `it('charges Haiku 5.5 base tier at exactly 100,000 prompt tokens')` — [Edge Case]
- `describe('AnthropicUsage')` → `it('prices Haiku 5.5 over-threshold cache reads at 0.05 and writes at 0.625')` — [Silent Failure]
- `describe('AnthropicUsage')` → `it('leaves a no-threshold Anthropic model (opus-5-5) priced identically regardless of prompt size')` — [Hidden Failure]
- `describe('AnthropicUsage')` → `it('returns base rates when usage has no token fields at all')` — [Edge Case]
- `describe('pricebook')` → `it('every PROVIDER_PRICING rate is finite and non-negative')` — [Hidden Failure]
- `describe('pricebook')` → `it('the Mistral default model resolves to a price')` — [Hidden Assumption]
- `describe('catalog')` → `it('rejects a bare gpt-6, which OpenAI does not publish')` — [Edge Case]
- `describe('catalog')` → `it('every model this refresh prices, including already-catalogued ones such as kimi-k3, passes strict validation')` — [Hidden Failure]
- `describe('pricebook')` → `it('DeepSeek rows bill the peak rate, and off-peak metadata is exactly half')` — [Hidden Assumption]
- `describe('pricebook')` → `it('versioned grok-4.7 and glm-5.3-flash ids price at their base rows')` — [Edge Case]
- `describe('pricebook')` → `it('PRICING_AS_OF names this refresh')` — [Hidden Failure]

### Integration Tests
- `UsageTracker.record_call` with a fake Anthropic-shaped response on `claude-haiku-5-5` (cache-heavy, over 100K) records the high-tier cost end to end. This catches a parser and registry mismatch that the unit tests cannot.
- `UsageTracker.record_call` with an OpenAI-shaped response on `gpt-6.1-sol` records the 0.1 cached rate, not gpt-6-sol's 0.2. This is the silent failure if the cached field were mis-keyed. The prompt stays below 272K.
- The same call above 272K records a 0.2 cache rate, because the long-context tier doubles it.
- Lint gates: S014 (parity), C009 (defaults priced), C010 (vintage lock).

### Manual / QA Test Cases
1. Given a fresh install, when `ModelPricingRegistry.default().resolve(ModelProvider.ANTHROPIC, "claude-sonnet-5-5")` is called, then cache_read is 0.10, not Sonnet 5's 0.20. — [Silent Failure]
2. Given `STRICT_MODEL_VALIDATION=True`, when a user configures `provider="openai", model="gpt-6"`, then validation rejects it, because OpenAI publishes no bare `gpt-6` alias. — [Edge Case]
3. Given a 150K-token Haiku 5.5 prompt that is 140K cache hits, when cost is computed, then the high tier applies. — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Provider pricing pages | URLs in §3 | Source of truth for rates | Prices change. Promotions lapse 2026-11-21 (gpt-5.6-sol, "at least") and 2026-12-31 (Gemini Flash). |
| C010 vintage lock | `lint/pricebook_vintage_lock.json` | Pins rates to vintage | Must be refreshed in the same change |

---

## 12. Rollout & Deployment

- No feature flag.
- Not a breaking API change.
- Calls that used to resolve to a stale rate now resolve to the corrected one:
  - gpt-5.6-sol, about 20–33% lower;
  - DeepSeek, higher, because it is now priced at peak;
  - gemini-3.5-flash and 3.6-flash, lower.
- Deployment order: merge the SDK first, then bump the backend's SDK pin in its own PR. Runs persisted with the old vintage cannot resume after the backend bump (C010's documented behavior).
- Rollback: revert the commit. The vintage moves back with it, and the lock is in the same commit.

---

## 13. Open Questions

- [ ] DeepSeek peak vs off-peak: this ships the peak rate (decision 1). Should a later PR add time-of-day pricing, or should the table use off-peak?
- [ ] Defaults: should `DEFAULT_PROVIDER_MODELS` move to the newest models? Candidates are gpt-6.1-sol, claude-sonnet-5-5, gemini-3.8-flash and deepseek-flash. gemini-3.5-flash is deprecated.
- [ ] Promotion expiry: Gemini Flash rates double on 2027-01-01, and gpt-5.6-sol's promotion runs "at least through 2026-11-21". The pricebook needs a refresh at those dates.
- [ ] Qwen/Alibaba and other open-weight providers: add as new providers in a separate PR?

---

## 14. Alternatives Considered

### Alternative 1: Add catalog entries without prices for models whose price is unclear
- What: catalog MiniMax-M3.1-Flash-Preview and similar models now, and price them later.
- Why rejected: an unpriced catalogued model records `cost_usd=None` and is refused by the managed gateway. The user asked for each added model to carry a verified price.

### Alternative 2: Model DeepSeek off-peak billing now
- What: add time windows to `ModelPricing` and a timestamp to `cost_usd`.
- Why rejected: it is a cross-layer feature (record shape, tracker, backend billing) beyond a catalog refresh. It is listed as an open question.

### Alternative 3: Remove the gemini-3.5-flash price row
- What: drop the deprecated model's rate.
- Why rejected: it is the Gemini default, so C009 would fail, and runs on it would go unpriced. Pricing it as the routed model is what Google says happens.

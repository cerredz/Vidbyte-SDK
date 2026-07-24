# Design Doc: Agent Usage & Pricing — Provider Expansion & Tier Accuracy

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-22
**Last Updated:** 2026-07-22

---

## 1. Overview

A follow-up to PR #304 (`feat/agent-usage-pricing`) that (a) fills in the missing GLM and MiniMax rate tables, (b) adds a full Meta provider so Meta's Muse Spark 1.1 can be priced and run, (c) corrects two real accuracy defects in the existing table — OpenAI's missing long-context tiers and xAI's inclusive (`≥`) tier boundary — and (d) records a full re-verification of every provider's rates against its official pricing page. The single controlling requirement is that computed usage cost is accurate in **every** scenario, including the above-threshold long-context case.

---

## 2. Goals & Non-Goals

### Goals
- Add first-party GLM (Z.ai) token rates for the models the SDK can call, including the default `glm-5.2`.
- Add first-party MiniMax token rates including the default `MiniMax-M3`, with its real ≤512k / >512k context tier.
- Add a complete, OpenAI-compatible **Meta** provider (`ModelProvider.META`) and price `muse-spark-1.1`.
- Add OpenAI long-context tiers (272k threshold) to the five tiered models — `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5` (default), `gpt-5.4`.
- Fix the tier-boundary semantics so xAI's `≥ 200k` high tier is applied at exactly 200,000 tokens (the #304 known-gap), without breaking Gemini/OpenAI/MiniMax `>` semantics.
- Re-verify all existing rates (OpenAI, Anthropic, Gemini, xAI, DeepSeek, Kimi) against official pages and record the result.

### Non-Goals
- No new usage-tracking mechanics, agent API, or middleware surface — #304 delivered those; this PR only feeds them more/accurate data.
- No pricing for OpenRouter marketplace models (still prefers provider-reported `usage.cost`), GLM/MiniMax audio, or non-text modalities.
- No resolution of the `grok-4` / `openrouter/auto` alias-to-version mapping (still resolves to `cost=None`; see §12) — mapping an alias to a specific priced version would itself be a guess.
- No streaming-usage or platform-credits work.
- No new test files (per workflow); existing CI must stay green.

---

## 3. Background & Context

PR #304 shipped per-provider usage classes, a `ModelPricingRegistry`, and a whole-request context-tier mechanism (`threshold_tokens` / `input_over_threshold_per_million` / `output_over_threshold_per_million` consumed by `effective_rates`). It deliberately left GLM and MiniMax rate tables empty (no verified rates at the time) and shipped a documented known-gap: `effective_rates` compares with a strict `>` , which is correct for Gemini (`>200k`) but one tier low for xAI at exactly `200k` (`≥200k`).

This PR is requested because (1) GLM and MiniMax are popular providers already wired into the SDK but currently return `cost=None`; (2) OpenAI's flagship models are actually long-context tiered and the current table silently under-charges large requests ~2×; (3) Meta launched its first paid API (Muse Spark 1.1, 2026-07-09) which the user wants priced; and (4) the user requires verified accuracy across every scenario.

Because #304 is still an **open, unmerged** PR and the pricing files do not exist on `origin/main`, this change **stacks on `feat/agent-usage-pricing`** (PR base = that branch, not `main`).

### Verification log (all fetched 2026-07-22 from official pages)

| Provider | Source | Result vs current table |
|---|---|---|
| OpenAI | developers.openai.com/api/docs/pricing + models docs | Short-context rates **accurate**; **missing 272k long-context tier** on sol/terra/luna/gpt-5.5/gpt-5.4 (input ×2, output ×1.5, whole request, `>272k`). |
| Anthropic | platform.claude.com/docs/.../pricing | **Accurate** (sonnet-5 $2/$10 intro, opus-4.x $5/$25, haiku-4.5 $1/$5; 5m-write ×1.25, read ×0.1). No context tiers. |
| Gemini | ai.google.dev/gemini-api/docs/pricing | **Accurate** (3.5-flash $1.5/$9 flat, 3.6-flash $1.5/$7.5 flat, 3.1-pro tiered `>200k` $2→4 / $12→18 / cache $0.2→0.4). |
| xAI | docs.x.ai/docs/models | Values **accurate**; boundary is **`≥200k`** (high tier includes exactly 200k) — current strict `>` is one tier low at the boundary. |
| DeepSeek | api-docs.deepseek.com | **Accurate** (v4-pro $0.435/$0.87/$0.003625, v4-flash $0.14/$0.28/$0.0028). No tiers. |
| Kimi | platform.kimi.ai | **Accurate** (k2.7-code $0.95/$4/$0.19, highspeed $1.90/$8/$0.38). No tiers. |
| GLM (Z.ai) | docs.z.ai/guides/overview/pricing | Not in table → **add** (glm-5.2 $1.4/$4.4/$0.26; glm-5 $1/$3.2/$0.2; glm-5-turbo $1.2/$4/$0.24; glm-4.7/4.6/4.5 $0.6/$2.2/$0.11). No tiers. |
| MiniMax | platform.minimax.io/docs/guides/pricing-paygo | Not in table → **add** (M3 $0.30/$1.20/$0.06 ≤512k; $0.60/$2.40/$0.12 >512k; M2.7 $0.30/$1.20). |
| Meta | ai.developer.meta.com (models) + press consensus | New provider → **add** (muse-spark-1.1 $1.25/$4.25/$0.15, flat). See §12 open question on first-party page sourcing. |

---

## 4. Requirements

### Functional Requirements
1. `ModelPricingRegistry.resolve(ModelProvider.GLM, "glm-5.2")` returns non-None rates ($1.4 / $4.4, cache $0.26); likewise for glm-5, glm-5-turbo, glm-4.7, glm-4.6, glm-4.5.
2. `resolve(ModelProvider.MINIMAX, "MiniMax-M3")` returns $0.30/$1.20 with `threshold_tokens=512_000`, `input_over=0.60`, `output_over=2.40`, `cache_read=0.06`; M2.7 and M2.7-highspeed also priced (no tier).
3. `ModelProvider.META` exists; a `BaseAgent(provider="meta", model_name="muse-spark-1.1")` run produces a `TextModelResponse(provider=META, usage=...)`, its usage parses via `ChatCompletionUsage`, and `resolve(META, "muse-spark-1.1")` returns $1.25/$4.25 with cache $0.15.
4. OpenAI models sol/terra/luna/gpt-5.5/gpt-5.4 carry `threshold_tokens=272_000` with `input_over`/`output_over` equal to 2× input / 1.5× output; a call with `input_tokens > 272_000` is priced at the long-context rate for the **entire** request; a call `≤ 272_000` uses the short rate.
5. xAI grok-4.5/grok-4.3/grok-build-0.1 apply their high tier at `input_tokens ≥ 200_000` (inclusive), while Gemini/OpenAI/MiniMax continue to apply theirs at `input_tokens > threshold` (exclusive).
6. Cache-read rates scale with the active input-rate tier automatically (existing `effective_rates` behavior) and must match each provider's published above-threshold cache price (verified: OpenAI $0.5→$1.0, Gemini $0.2→$0.4, xAI $0.3→$0.6, MiniMax $0.06→$0.12).
7. `muse-spark-1.1` is classified TEXT by `ModalityDetector`, so env auto-resolution and text-runner routing treat Meta as a first-class text provider.
8. All previously verified-accurate rates (Anthropic, DeepSeek, Gemini, Kimi, xAI values, OpenAI short-context values) remain unchanged.

### Non-Functional Requirements
- **Accuracy:** every rate traceable to an official page and dated (`PRICING_AS_OF`); anything unverifiable is omitted (resolves to `cost=None`), never guessed.
- **Back-compat:** additive only — no rename or removal of existing `ModelPricing` fields; new field defaults preserve current behavior.
- **No network at import:** rates are static literals; no runtime fetch.
- **CI:** `python scripts/run_ci.py` (pytest 1436→ green + package build) must pass unchanged; no new failures.
- **Observability:** none new; usage flows through #304's `usage_rollup` / `on_usage` / `ctx.model_usage`.

---

## 5. High-Level Design

Two independent tracks land in one PR:

**Track A — Pricing accuracy & expansion (data + one field).** Add one boolean field `threshold_inclusive` to `ModelPricing` (default `False` = strict `>`), and teach `effective_rates` to use `>=` when it is `True`. Then edit the `PROVIDER_PRICING` literal: add OpenAI 272k tiers, set xAI `threshold_inclusive=True`, and populate GLM, MiniMax (with its 512k tier), and Meta. No change to the usage classes or cost formulas — they already route tiered providers through `effective_rates` and non-tiered ones through flat rates.

**Track B — Meta provider (OpenAI-compatible, mirrors Kimi).** Meta's Model API is drop-in OpenAI Chat Completions (`api.meta.ai/v1`, model `muse-spark-1.1`). So the provider is the same trivial shape as `KimiProvider`: an enum member, a registry triple (default model / endpoint / env var), a two-line `MetaProvider(OpenAICompatibleProvider)`, a dispatch entry in `ModelProviders.text`, a `@usage_for(ModelProvider.META)` on the existing `ChatCompletionUsage` (Muse Spark is a reasoning model → `completion_tokens_details.reasoning_tokens` and `prompt_tokens_details.cached_tokens` are already parsed), a modality entry so `muse-spark-*` is TEXT, and the pricing entry from Track A.

```
Agent(provider="meta", model="muse-spark-1.1")
      │
ModelProviders.text ─► MetaProvider(OpenAICompatibleProvider)  ─► api.meta.ai/v1/chat/completions
      │                        └─ TextModelResponse(provider=META, usage={prompt_tokens,...})
UsageTracker.record_call ─► parse_usage(META, usage) ─► ChatCompletionUsage
      │                                                      └─ cost_usd(resolve(META,"muse-spark-1.1"))
      └─► usage_rollup / on_usage / ctx.model_usage   (unchanged from #304)
```

Key decisions: (1) full Meta provider rather than a dangling pricing row, because a priced provider the SDK can't call would never populate usage — inconsistent with "accurate in every scenario"; the OpenAI-compat shape makes this near-free. (2) `threshold_inclusive` bool rather than encoding xAI as `threshold=199_999`, because the latter obscures the real 200k threshold and is a silent trap for the next editor.

---

## 6. Detailed Design

### 6.1 `ModelPricing` gains a boundary-inclusivity flag
**File:** `vidbyte/lib/registries/pricing.py` — **Modified**

#### Interface
```python
@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None = None
    cache_write_per_million: float | None = None
    threshold_tokens: int | None = None
    input_over_threshold_per_million: float | None = None
    output_over_threshold_per_million: float | None = None
    threshold_inclusive: bool = False   # NEW: True → high tier applies at input == threshold (xAI ≥)
```

#### Edge cases
- Default `False` keeps every existing entry (Gemini) behaving identically.
- `threshold_inclusive=True` is only meaningful alongside `threshold_tokens`; harmless otherwise.

### 6.2 `effective_rates` honors the boundary flag
**File:** `vidbyte/agents/pricing/base.py` — **Modified**

#### Logic
The tier predicate changes from `input_tokens > threshold` to: `input_tokens >= threshold` when `pricing.threshold_inclusive` else `input_tokens > threshold`. Everything else (rate swap, cache-read scaling by `input_rate / base_input_rate`) is unchanged.

```python
def _over_threshold(pricing: ModelPricing, input_tokens: int) -> bool:
    # True when the call's input crosses into the over-threshold tier, honoring inclusivity.
    if pricing.threshold_inclusive:
        return input_tokens >= pricing.threshold_tokens
    return input_tokens > pricing.threshold_tokens
```
`effective_rates` calls `_over_threshold` inside its existing guard (which already checks `threshold_tokens is not None`, `input_tokens is not None`, and both over-rates present).

#### Edge cases
- `input_tokens is None`: guard already returns base rates (unchanged).
- Exactly at threshold: Gemini/OpenAI/MiniMax → base tier; xAI → over tier. Verified against each page.

### 6.3 `PROVIDER_PRICING` table edits
**File:** `vidbyte/lib/registries/pricing.py` — **Modified**

- **OpenAI** — add to `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`: `threshold_tokens=272_000` and `input_over`/`output_over`:
  - sol & gpt-5.5: over `10.0 / 45.0` (short `5.0 / 30.0`, cache `0.5`)
  - terra & gpt-5.4: over `5.0 / 22.5` (short `2.5 / 15.0`, cache `0.25`)
  - luna: over `2.0 / 9.0` (short `1.0 / 6.0`, cache `0.1`)
  - `gpt-5.5-pro`, `gpt-5.4-mini/nano/pro` unchanged (flat, verified).
- **xAI** — add `threshold_inclusive=True` to `grok-4.5`, `grok-4.3`, `grok-build-0.1` (values already correct).
- **GLM** — populate: `glm-5.2` `1.4/4.4` cache `0.26`; `glm-5.1` `1.4/4.4/0.26`; `glm-5` `1.0/3.2/0.2`; `glm-5-turbo` `1.2/4.0/0.24`; `glm-4.7` `0.6/2.2/0.11`; `glm-4.6` `0.6/2.2/0.11`; `glm-4.5` `0.6/2.2/0.11`.
- **MiniMax** — populate: `MiniMax-M3` `0.30/1.20` cache `0.06`, `threshold_tokens=512_000`, over `0.60/2.40`; `MiniMax-M2.7` `0.30/1.20` cache_read `0.06` cache_write `0.375`; `MiniMax-M2.7-highspeed` `0.60/2.40/0.06/0.375`. (Comment records the "permanent 50% off" promo baked into M3's effective rate.)
- **Meta** — new `ModelProvider.META` block: `muse-spark-1.1` `1.25/4.25` cache `0.15` (flat).
- Header comment updated: removes GLM/MiniMax from the "omitted" list; keeps `grok-4` / `openrouter/auto` aliases omitted.

### 6.4 `ModelProvider.META` enum member
**File:** `vidbyte/lib/enums/model_provider.py` — **Modified**
Add `META = "meta"` (and to `__all__`-adjacent ordering; enum only).

### 6.5 Meta registry triple
**File:** `vidbyte/lib/registries/models.py` — **Modified**
- `DEFAULT_PROVIDER_MODELS[ModelProvider.META] = "muse-spark-1.1"`
- `API_KEY_ENV_VARS[ModelProvider.META] = "META_API_KEY"`
- `DEFAULT_ENDPOINTS[ModelProvider.META] = "https://api.meta.ai/v1"`

### 6.6 `MetaProvider`
**File:** `vidbyte/providers/compatible.py` — **Modified**
```python
class MetaProvider(OpenAICompatibleProvider):
    provider = ModelProvider.META
```
Add `"MetaProvider"` to `__all__`.

### 6.7 Provider dispatch
**File:** `vidbyte/providers/__init__.py` — **Modified**
Import `MetaProvider`; add `ModelProvider.META: MetaProvider` to the `ModelProviders.text` dispatch dict; extend the return-type union.

### 6.8 `ChatCompletionUsage` binding
**File:** `vidbyte/agents/pricing/compatible.py` — **Modified**
Add `@usage_for(ModelProvider.META)` to the existing decorator stack on `ChatCompletionUsage` (Muse Spark returns OpenAI-shape `usage` with `prompt_tokens`/`completion_tokens`, `prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens`).

### 6.9 Modality classification
**File:** `vidbyte/lib/agents/modality_detector.py` — **Modified**
Add `("muse-spark", ModelModality.TEXT)` to `_PREFIX_MODALITY_MAP` so `muse-spark-1.1` (and future `muse-spark-*`) resolve TEXT for env auto-resolution and runner routing.

---

## 7. Data Model Changes

### 7.1 `ModelPricing`
**Change type:** Modified — one additive field `threshold_inclusive: bool = False`. No migration; frozen dataclass, default preserves behavior.

### 7.2 `ModelProvider`
**Change type:** Modified — new enum member `META = "meta"`. String enum; additive.

No persistent/DB schema. N/A - the SDK has no database.

---

## 8. API Changes

N/A - No HTTP endpoints. Public Python surface changes are additive only: a new `ModelProvider.META`, a new `ModelPricing.threshold_inclusive` field, new `MetaProvider`, and new `PROVIDER_PRICING` entries. No signature of any existing function changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-usage-pricing-expansion.md` | This design doc (first commit). |
| MODIFY | `vidbyte/lib/registries/pricing.py` | `threshold_inclusive` field; OpenAI 272k tiers; xAI inclusive flags; GLM/MiniMax/Meta rate entries; header comment. |
| MODIFY | `vidbyte/agents/pricing/base.py` | `effective_rates` honors `threshold_inclusive` via `_over_threshold`. |
| MODIFY | `vidbyte/lib/enums/model_provider.py` | Add `META = "meta"`. |
| MODIFY | `vidbyte/lib/registries/models.py` | Meta default model, endpoint, API-key env var. |
| MODIFY | `vidbyte/providers/compatible.py` | Add `MetaProvider`; export it. |
| MODIFY | `vidbyte/providers/__init__.py` | Register `MetaProvider` in `ModelProviders.text`. |
| MODIFY | `vidbyte/agents/pricing/compatible.py` | Bind `ChatCompletionUsage` to `ModelProvider.META`. |
| MODIFY | `vidbyte/lib/agents/modality_detector.py` | Classify `muse-spark-*` as TEXT. |

**Totals: 1 created, 8 modified, 0 deleted.**

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Meta Model API | `https://api.meta.ai/v1` (OpenAI-compatible) | Runtime target for Muse Spark | New third-party endpoint; only reached when a user sets `META_API_KEY` and selects the provider. |
| Provider pricing pages | OpenAI/Anthropic/Gemini/xAI/DeepSeek/Kimi/Z.ai/MiniMax/Meta | Source of the static rates | Rates drift; mitigated by `PRICING_AS_OF` stamp and omit-if-unverifiable rule. |

No new Python package dependencies.

---

## 11. Rollout & Deployment

- **Feature flags:** none. Rates are static; Meta is inert unless a user selects it with credentials.
- **Breaking change:** no. Additive field + additive enum member + additive table rows. Existing `resolve()` results for priced models are unchanged except the two accuracy fixes (OpenAI long-context now higher; xAI at exactly 200k now higher) — both are corrections toward the official price.
- **Stacking:** branch `feat/agent-usage-pricing-expansion` off `feat/agent-usage-pricing`; **PR base = `feat/agent-usage-pricing`** (stacked on #304). Merge #304 first, then this.
- **Rollback:** revert the PR; no state or migration to undo.
- **CI gate:** `python -m pip install -e ".[dev]" && python scripts/run_ci.py` (source = pytest, package = build + clean-install smoke).

---

## 12. Open Questions

- [ ] **Meta first-party pricing source.** `muse-spark-1.1 = $1.25/$4.25/$0.15` is consistent across ~10 sources (the-decoder, AI Weekly, DataCamp, TokenCost) and the official docs confirm the model id/base URL, but the official first-party *pricing* page was not directly fetchable (404/empty). Accept the press-consensus number stamped `PRICING_AS_OF=2026-07-22`, to be re-verified when the page is reachable? (Recommended: yes — it is well-corroborated and omission would leave Meta unpriced.)
- [ ] **Alias defaults.** `grok-4` (the xAI default) and `openrouter/auto` still resolve to `cost=None` because they are version aliases, not priced SKUs. Leave as documented gaps (recommended — mapping `grok-4`→`grok-4.5` is a guess), or pin them?
- [ ] **MiniMax promo price.** M3's `0.30/1.20` reflects the "permanent 50% off" promo over the `0.60/2.40` list price. Encode the effective (billed) price (recommended), or the list price?
- [ ] **GLM coverage depth.** Add only 5.x + the three 4.x flagships (recommended), or the full GLM-4.x matrix incl. Air/Flash/X variants?

---

## 13. Alternatives Considered

### Alternative 1: Encode xAI as `threshold_tokens = 199_999` instead of a flag
- What: Keep the strict `>` comparison, shift xAI's threshold down by one.
- Why rejected: Obscures the true 200k threshold, is invisible to a reader auditing the table, and breaks the moment someone "fixes" it back to 200_000. A named `threshold_inclusive` flag states the intent.

### Alternative 2: Pricing-only Meta (enum + rate row, no provider/adapter)
- What: Add `ModelProvider.META` and a `PROVIDER_PRICING` row but no runner/dispatch.
- Why rejected: The SDK could never produce a `provider=META` response, so the row is dead code and Meta usage is never priced in practice — the opposite of "accurate in every scenario." The OpenAI-compat adapter costs ~4 trivial lines.

### Alternative 3: Add MUSE Spark as an OpenRouter model
- What: Route Muse Spark through the existing OpenRouter provider.
- Why rejected: OpenRouter pricing is intentionally table-empty (prefers provider-reported `usage.cost`); Meta's first-party API is the accurate, direct source, and the user asked for it in the pricing table specifically.

### Alternative 4: Per-tier explicit price rows (one `ModelPricing` per tier)
- What: Separate short/long rows keyed by suffix.
- Why rejected: The registry keys on model string, not request size; per-call token count is only known at cost time. The existing `threshold_*` on one row is the right shape and is already wired through `effective_rates`.

---

## Phase 2 Report

- **Manifest:** 1 created, 8 modified, 0 deleted.
- **Key risks:** (1) Meta first-party *pricing* page not directly fetchable — using well-corroborated press/consensus number (see §12); (2) stacked on unmerged #304, so PR base must be `feat/agent-usage-pricing`; (3) two rate corrections (OpenAI long-context, xAI boundary) change computed cost for those scenarios — intended, toward the official price.
- **Accuracy audit result:** Anthropic, DeepSeek, Gemini, Kimi, and OpenAI/xAI short-context values verified **accurate as-is**; only OpenAI long-context tiers and the xAI `≥` boundary needed fixing; GLM/MiniMax/Meta added.
- **Open questions:** 4 (see §12) — all with a recommended default; none blocking.

**Requesting approval to proceed to Phase 3 (stacked worktree) and Phase 4 (implementation).**

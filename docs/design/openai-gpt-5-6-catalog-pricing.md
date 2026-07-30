# Design Doc: OpenAI GPT-5.6 model catalog and pricing

**Status:** Draft  
**Author:** Codex  
**Created:** 2026-07-30  
**Last Updated:** 2026-07-30

---

## 1. Overview

Refresh the SDK's existing OpenAI model catalog and pricing registry for the
`gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna` family, plus the `gpt-5.6`
alias. The live `main` baseline already includes the three canonical models,
`gpt-5.6-sol` as the OpenAI default, and a provider-wide `ModelPricingRegistry`;
this change updates that existing source of truth instead of introducing a
duplicate registry. The Python SDK still has no frontend/VIT button, so the
implementation stops at the model catalog and SDK pricebook boundary.

---

## 2. Goals & Non-Goals

### Goals

- Advertise the OpenAI GPT-5.6 family through the existing runner/model catalog:
  `gpt-5.6`, `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.
- Resolve the `gpt-5.6` alias to the Sol pricing record without rewriting the
  model string sent to OpenAI.
- Update the existing typed `ModelPricingRegistry` under
  `vidbyte.lib.registries`, preserving its usage-tracker integration.
- Record the current official OpenAI GPT-5.6 input, cached-input, cache-write,
  and output rates for Standard, Batch, Flex, and Fast service tiers, including
  short- and long-context rates.
- Preserve the current strict model-validation contract by adding the alias to
  the runner catalog rather than weakening validation.
- Document the new public registry surface and the pricing units clearly.

### Non-Goals

- Changing `ProviderModelRegistry.default_model(ModelProvider.OPENAI)` from
  `gpt-5.5` to a GPT-5.6 model. That is a separate default-model migration with
  cost and behavior implications.
- Automatically changing `TextModelConfig` or `OpenAITextModelRunner` payloads;
  callers who select a GPT-5.6 model already pass it through to `/responses`.
- Feeding the new pricebook automatically into `Session.usage()`. The current
  session API accepts one scalar price for total tokens and does not persist
  input/output/cached/long-context buckets, so automatic pricing would be
  materially inaccurate.
- Adding or modifying a web/mobile frontend, subscription flow, or `VIT` button.
  No such surface exists in `vidbyte-sdk`; that work belongs in the application
  repository after its exact button and billing contract are identified.
- Fetching prices from OpenAI at runtime.
- Adding new feature-test files under the `design-doc-no-tests` workflow.

---

## 3. Background & Context

The current SDK centralizes provider defaults, runner catalogs, and environment
resolution in `vidbyte/lib/registries/models.py` and
`vidbyte/lib/constants/runners.py`. The live baseline already advertises the
three canonical GPT-5.6 IDs and defaults OpenAI to `gpt-5.6-sol`, but it does not
advertise the unqualified `gpt-5.6` alias. Model validation is strict by default,
so the alias must be added to the runner catalog before it can be selected.

The SDK already owns a provider-wide pricebook in
`vidbyte/lib/registries/pricing.py`. Its `ModelPricing` records support standard
input/output rates, cached-input and cache-write rates, and long-context
thresholds; `UsageTracker` consumes these records to calculate model-call cost.
The GPT-5.6 Terra and Luna entries still contain the prior rates and are the
source that must be corrected.

The only existing pricing path is `Session.usage(prices=...)`, which accepts a
caller-supplied `{model_name: scalar_price_per_token}` mapping and multiplies it
by aggregate token usage. It cannot distinguish input from output tokens, cached
input, cache writes, context length, or service tier. The new registry therefore
provides authoritative lookup data without pretending that the current session
rollup can apply it correctly.

The model and price data were checked against OpenAI's current official
[model catalog](https://developers.openai.com/api/docs/models), the
[GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6),
the [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
[GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
and [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
pages, with the live [OpenAI pricing page](https://developers.openai.com/api/docs/pricing)
treated as the pricing source of truth on 2026-07-30.

Relevant repository constraints from the Vidbyte SDK field guide:

- New lookup registries belong under `vidbyte/lib/registries/`; this change does
  not create a registry because the live baseline already has one.
- The existing pricing registry is already the accepted dependency-light source
  of truth for usage pricing; adding a second `lib/configs/model_pricing.py`
  table would duplicate rates and create drift.
- Usage accounting remains agent-owned; this change must not add a second runtime
  usage-capture or pricing path.
- The canonical checkout currently has no `scripts/run_ci.py`; its documented
  verification commands are in `CONTRIBUTING.md`, while the publish workflow
  validates builds and clean-environment imports.

---

## 4. Requirements

### Functional Requirements

1. The OpenAI runner catalog must include the existing `gpt-5.5` entry and all
   four GPT-5.6 names: `gpt-5.6`, `gpt-5.6-sol`, `gpt-5.6-terra`, and
   `gpt-5.6-luna`.
2. `ProviderModelRegistry.get_supported_models("openai")` must return the
   OpenAI catalog without requiring callers to inspect internal maps.
3. `ProviderModelRegistry.normalize_model("openai", "gpt-5.6")` must return
   `gpt-5.6-sol`; canonical model IDs must resolve to themselves.
4. Because strict model validation is enabled in the live baseline, the alias
   must be present in both qualified and bare runner catalogs before validation
   can accept it.
5. `ModelPricingRegistry` must return a typed price record for each canonical
   GPT-5.6 model and for the `gpt-5.6` alias.
6. The price record must expose four rates in USD per one million tokens:
   uncached input, cached input, cache writes, and output.
7. The pricebook must distinguish Standard, Batch, Flex, and Fast service tiers
   and short-context versus long-context pricing.
8. A lookup for an unknown provider, unknown priced model, or unknown service
   tier must raise `ConfigurationError` with the requested value and available
   values in the error message.
9. The price declarations must include the official pricing-page URL and the
   date on which the values were checked, so future updates are reviewable.
10. Public registry exports and nearby SDK documentation must expose how to
    discover models and retrieve prices. Existing exports should be preserved;
    no duplicate registry package should be introduced.

### Non-Functional Requirements

- **Compatibility:** Existing default model selection, strict model validation,
  explicit model forwarding, API-key resolution, and session usage behavior
  remain unchanged except for accepting the new alias.
- **Performance:** Model and price lookups are in-memory O(1) operations and
  perform no network calls.
- **Correctness:** Alias resolution is centralized; callers cannot accidentally
  use a stale scalar session price as if it were a complete OpenAI price record.
- **Reliability:** Pricing declarations are immutable after import and unknown
  lookup dimensions fail deterministically with actionable errors.
- **Security:** No credentials, user content, or outbound requests are added.
- **Observability:** No runtime logging is required for local registry reads;
  pricing source metadata is available on the returned definition for auditing.
- **Verification:** Run the repository's existing compile, unittest, import,
  build, and distribution checks. Do not skip them because this workflow adds no
  new test file.

---

## 5. High-Level Design

Keep model discovery split across the existing runner catalog and
`ProviderModelRegistry`: add the unqualified alias to both bare and qualified
runner maps, then make `get_supported_models()` use that same catalog with an
optional provider selector. Strict validation remains enabled, so catalog and
validation cannot drift.

Extend the existing `ModelPricing` record and `ModelPricingRegistry` in place.
The registry is already consumed by `UsageTracker`; the implementation updates
the OpenAI records for the current Standard/long-context values and stores the
additional Batch, Flex, and Fast rate metadata without adding a second price
table. Alias resolution maps `gpt-5.6` to the Sol record only for pricing lookup;
the OpenAI request adapter keeps the caller's original model string.

The SDK's public surface becomes:

```text
ProviderModelRegistry
  â”œâ”€ discover OpenAI: gpt-5.5, gpt-5.6, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
  â””â”€ normalize gpt-5.6 -> gpt-5.6-sol

ModelPricingRegistry
  â””â”€ resolve provider + model + service tier + context length
       -> immutable ModelPrice {input, cached_input, cache_write, output}

OpenAI Responses provider
  â””â”€ continues forwarding the caller-selected model unchanged
```

No persistent data, database migration, dependency, or frontend route changes
are involved.

---

## 6. Detailed Design

### 6.1 Provider model catalog and alias resolution

**File(s):** `vidbyte/lib/registries/models.py`  
**Type:** Modified

#### What it does

Extends the existing provider registry's discovery helpers over the runner
catalog. It adds a single canonical alias map while preserving the live
`gpt-5.6-sol` OpenAI default and strict model-validation contract.

#### Interface / API

```python
@classmethod
def get_supported_models(cls, provider: ModelProvider | str | None = None) -> list[str]: ...

@classmethod
def normalize_model(cls, provider: ModelProvider | str, model: str) -> str: ...

@classmethod
def is_supported_model(cls, provider: ModelProvider | str, model: str) -> bool: ...
```

#### Logic / Algorithm

1. Add `gpt-5.6` to both `MODEL_PROVIDER_RUNNER_TYPE_MAP` and
   `MODEL_RUNNER_TYPE_MAP` as a text model.
2. Add a provider-scoped alias map with `gpt-5.6` pointing to
   `gpt-5.6-sol` for normalization and pricing lookup.
3. Normalize the provider using the existing `ModelProvider` conversion and
   trim/validate the model string.
4. Return the runner catalog for all providers or the selected provider when a
   provider is supplied.
5. Keep `_resolve_from_environment()` tied to `DEFAULT_PROVIDER_MODELS` so the
   catalog addition does not change environment-driven selection.

#### Edge Cases & Error Handling

- An unknown provider continues to raise `ConfigurationError` through the
  existing provider validation path.
- Empty model names continue to raise the existing `ConfigurationError`.
- Unknown non-empty models remain subject to the existing strict validation
  behavior; callers can opt out only through the existing
  `STRICT_MODEL_VALIDATION` switch.
- Alias normalization does not alter the model stored in `TextModelConfig` or
  sent in an OpenAI request.

### 6.2 Existing OpenAI pricing declarations

**File(s):** `vidbyte/lib/registries/pricing.py`  
**Type:** Modified

#### What it does

Updates the existing dependency-light source of truth for provider model pricing.
The declarations remain in the established registry because `UsageTracker` and
provider-specific usage formulas already consume `ModelPricing` from this file.
No duplicate `lib/configs/model_pricing.py` table will be introduced.

#### Interface / API

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
    threshold_inclusive: bool = False
    tier_rates: Mapping[str, Mapping[str, float]] | None = None
```

#### Logic / Algorithm

1. Preserve the existing flat fields used by `ProviderUsage` for Standard
   pricing and long-context threshold billing.
2. Correct the canonical `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`
   records in `PROVIDER_PRICING`.
3. Add cache-write rates and a structured optional tier-rate map for the four
   billable token categories when the official table publishes them.
4. Store all rates as USD per 1,000,000 tokens and advance `PRICING_AS_OF` to
   `2026-07-30`.
5. Keep the existing public exports so `UsageTracker` and root `vidbyte` imports
   continue to resolve the same symbols.

The checked rates are:

| Model / mode | Input | Cached input | Cache write | Output |
|---|---:|---:|---:|---:|
| `gpt-5.6-sol`, Standard short | $5.00 | $0.50 | $6.25 | $30.00 |
| `gpt-5.6-sol`, Standard long | $10.00 | $1.00 | $12.50 | $45.00 |
| `gpt-5.6-sol`, Batch/Flex short | $2.50 | $0.25 | $3.125 | $15.00 |
| `gpt-5.6-sol`, Batch/Flex long | $5.00 | $0.50 | $6.25 | $22.50 |
| `gpt-5.6-sol`, Fast | $10.00 | $1.00 | $12.50 | $60.00 |
| `gpt-5.6-terra`, Standard short | $2.00 | $0.20 | $2.50 | $12.00 |
| `gpt-5.6-terra`, Standard long | $4.00 | $0.40 | $5.00 | $18.00 |
| `gpt-5.6-terra`, Batch/Flex short | $1.00 | $0.10 | $1.25 | $6.00 |
| `gpt-5.6-terra`, Batch/Flex long | $2.00 | $0.20 | $2.50 | $9.00 |
| `gpt-5.6-terra`, Fast | $4.00 | $0.40 | $5.00 | $24.00 |
| `gpt-5.6-luna`, Standard short | $0.20 | $0.02 | $0.25 | $1.20 |
| `gpt-5.6-luna`, Standard long | $0.40 | $0.04 | $0.50 | $1.80 |
| `gpt-5.6-luna`, Batch/Flex short | $0.10 | $0.01 | $0.125 | $0.60 |
| `gpt-5.6-luna`, Batch/Flex long | $0.20 | $0.02 | $0.25 | $0.90 |
| `gpt-5.6-luna`, Fast | $0.40 | $0.04 | $0.50 | $2.40 |

Batch and Flex share the same rates in the current official table; the
declaration keeps them as separate service-tier fields so a future OpenAI change
does not require an API shape change.

#### Edge Cases & Error Handling

- The declaration module contains no runtime I/O, so an unavailable network does
  not affect imports or lookups.
- Rates are immutable after import; updates require a reviewed source change.
- No alias entry is duplicated in the price map; aliases resolve through the
  provider registry to avoid divergent prices.

### 6.3 Pricing registry

**File(s):** `vidbyte/lib/registries/pricing.py`  
**Type:** Modified

#### What it does

Extends the existing public lookup API with alias-aware GPT-5.6 resolution while
preserving instance-local overrides and longest-prefix matching for other
providers. It remains the only built-in pricebook consumed by model usage
accounting.

#### Interface / API

```python
class ModelPricingRegistry:
    def resolve(self, provider: ModelProvider, model: str) -> ModelPricing | None: ...

    def register(self, provider: ModelProvider, model: str, pricing: ModelPricing) -> None: ...
```

#### Logic / Algorithm

1. Require a `ModelProvider` enum at the registry boundary, matching the existing
   strict API contract.
2. Resolve `gpt-5.6` to `gpt-5.6-sol` before exact/prefix lookup.
3. Return the immutable pricing record for the selected provider/model.
4. Let `UsageTracker` continue applying provider-native usage formulas and the
   long-context threshold fields.
5. Keep caller-registered overrides local to that registry instance.

#### Edge Cases & Error Handling

- An unpriced model returns `None`, preserving the existing usage behavior for
  providers whose exact rates are unavailable.
- A raw provider string returns `None` from `resolve`; `register` rejects it with
  `ConfigurationError`, preserving the existing strictness tests.
- Alias resolution applies only inside the registry and does not mutate request
  configuration.

### 6.4 Public exports and documentation

**File(s):** `vidbyte/lib/constants/runners.py`, `vidbyte/lib/registries/models.py`, `vidbyte/lib/registries/__init__.py`, `vidbyte/lib/README.md`, `README.md`  
**Type:** Modified

#### What it does

Adds the alias to the strict runner catalog and documents the existing model and
price registry APIs alongside the current provider-registry documentation.

#### Interface / API

```python
from vidbyte.lib.registries import ModelPricingRegistry, ProviderModelRegistry

models = ProviderModelRegistry.get_supported_models("openai")
price = ModelPricingRegistry.default().resolve(ModelProvider.OPENAI, "gpt-5.6-luna")
```

#### Logic / Algorithm

1. Add the alias to the qualified and bare runner maps.
2. Add a short example showing model discovery, alias pricing lookup, and the
   USD-per-million-token units.
3. State that the SDK catalog is not the same as a frontend purchase button and
   link the official OpenAI documentation used for the rates.

#### Edge Cases & Error Handling

- Documentation must not imply that `gpt-5.6` becomes the runtime default.
- Documentation must not claim that `Session.usage()` automatically consumes
  the new detailed pricebook.

---

## 7. Data Model Changes

### 7.1 In-memory model pricing declarations

**Change type:** New

```python
ModelPricing(
    input_per_million=0.20,
    output_per_million=1.20,
    cache_read_per_million=0.02,
    cache_write_per_million=0.25,
    threshold_tokens=272_000,
    input_over_threshold_per_million=0.40,
    output_over_threshold_per_million=1.80,
    tier_rates={"batch": {...}, "flex": {...}, "fast": {...}},
)
```

**Migration strategy:** N/A - this is immutable package data, not persisted
state. Forward migration is a normal SDK release. Rollback reverts the catalog
and pricing changes; existing session data and model configurations remain
readable.

---

## 8. API Changes

### 8.1 Package-local model catalog API

**Change type:** Modified

This is not an HTTP endpoint. `ProviderModelRegistry.get_supported_models()` gains
an optional provider selector, and `normalize_model()`/`is_supported_model()` are
new package-local APIs. Existing no-argument callers remain valid.

### 8.2 Package-local pricing API

**Change type:** New

```python
pricing = ModelPricingRegistry.default().resolve(ModelProvider.OPENAI, "gpt-5.6")
# -> ModelPricing for the canonical gpt-5.6-sol record
```

**Error cases:**

| Error | Condition |
|---|---|
| `ConfigurationError` | Provider is not recognized. |
| `None` | Model has no price declaration. |
| `ConfigurationError` | `register()` receives a raw provider, blank model, or wrong pricing type. |

---

## 9. File Change Manifest

Complete list of every file expected for this design and its implementation:

| Action | File Path | Reason |
|---|---|---|
| CREATE | `docs/design/openai-gpt-5-6-catalog-pricing.md` | Approved design artifact and implementation source of truth. |
| MODIFY | `vidbyte/lib/constants/runners.py` | Advertise the `gpt-5.6` alias in strict model validation catalogs. |
| MODIFY | `vidbyte/lib/registries/models.py` | Add provider-scoped catalog discovery and alias normalization. |
| MODIFY | `vidbyte/lib/registries/pricing.py` | Correct GPT-5.6 rates and retain the existing usage-pricebook API. |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Export the GPT-5.6 tier metadata with the existing pricing registry. |
| MODIFY | `vidbyte/lib/README.md` | Document registry and price lookup APIs. |
| MODIFY | `README.md` | Add the new registry to the SDK discovery documentation. |
| DELETE | None | No existing implementation is being removed. |

No test files are planned under this no-tests design workflow. Existing tests and
repository gates remain required verification.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| OpenAI model catalog | `https://developers.openai.com/api/docs/models` | Confirm GPT-5.6 model IDs and availability. | Model names can change; catalog is reviewed source data. |
| OpenAI pricing | `https://developers.openai.com/api/docs/pricing` | Source of truth for rates and service tiers. | Pricing can change; the checked date and source URL make updates auditable. |
| Python standard library | Existing Python `>=3.11` | Enums, frozen dataclasses, and typed mappings. | None beyond the existing runtime support. |
| `pydantic` / `httpx` | Existing project dependencies | Unchanged provider/config infrastructure. | No new dependency or runtime call is introduced. |

---

## 11. Rollout & Deployment

- No feature flag is needed; the new catalog and lookup APIs are additive.
- The existing OpenAI default remains `gpt-5.5`, so deployment does not migrate
  existing callers to a different model or cost profile.
- Release as part of the normal `vidbyte-sdk` package release after the existing
  compile, unittest, import, build, and distribution checks pass.
- Rollback is a package release rollback or a revert of the registry/config/doc
  changes. No database or session-data migration is required.
- A future frontend/VIT-button change must be deployed from the application
  repository with its own billing and entitlement verification.

---

## 12. Open Questions

- [ ] Should the OpenAI default eventually change from `gpt-5.5` to the
  `gpt-5.6` alias? This design recommends a separate, explicitly approved change.
- [ ] Which repository and exact UI contract own the requested `VIT` button?
  `vidbyte-sdk` contains no frontend or `VIT` symbol, so this design deliberately
  does not claim to implement it.
- [ ] Should a later session-usage revision persist separate input, cached-input,
  cache-write, and output token counts so it can apply this detailed pricebook
  automatically? This design leaves the current scalar `prices=` API unchanged.

---

## 13. Alternatives Considered

### Alternative 1: Change only the OpenAI default model

- **What:** Replace `gpt-5.5` in `DEFAULT_PROVIDER_MODELS` with `gpt-5.6`.
- **Why rejected:** It does not expose Sol/Terra/Luna as selectable offerings and
  silently changes the runtime's behavior and cost for environment-driven users.

### Alternative 2: Treat every `gpt-5.6-*` prefix as priced

- **What:** Infer availability and price from the model-name prefix without a
  versioned catalog.
- **Why rejected:** It cannot distinguish official priced models from arbitrary
  compatible-proxy IDs and provides no auditable rates or service-tier data.

### Alternative 3: Put the new prices directly in `SessionUsageBuilder`

- **What:** Make `Session.usage()` automatically look up GPT-5.6 prices.
- **Why rejected:** Session history currently stores only aggregate token counts,
  while OpenAI bills input/output/cache/context/tier categories differently.
  Automatic lookup would produce misleading costs and violate the SDK's agent-owned
  usage-accounting boundary.

### Alternative 4: Fetch OpenAI pricing at runtime

- **What:** Query OpenAI documentation or a remote pricing service for every lookup.
- **Why rejected:** It introduces network latency, availability risk, mutable
  runtime behavior, and a new external trust boundary into a local registry API.

### Alternative 5: Add a VIT button to this repository

- **What:** Create a UI component or purchase action under `vidbyte-sdk`.
- **Why rejected:** The target repository is a Python SDK with no frontend entry
  point, billing route, or existing VIT contract. Fabricating one would be a
  cross-repository scope expansion rather than a safe SDK change.

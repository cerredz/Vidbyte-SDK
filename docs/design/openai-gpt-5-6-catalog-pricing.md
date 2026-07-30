# Design Doc: OpenAI GPT-5.6 model catalog and pricing

**Status:** Draft  
**Author:** Codex  
**Created:** 2026-07-30  
**Last Updated:** 2026-07-30

---

## 1. Overview

Add an explicit OpenAI GPT-5.6 model catalog and an immutable, SDK-owned pricing
registry for `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`, plus the
`gpt-5.6` alias. This makes the family discoverable through the existing model
registry and gives SDK consumers a single lookup surface for the current official
OpenAI rates. The implementation will not silently change the SDK's existing
`gpt-5.5` default, will not reject arbitrary provider-compatible model IDs, and will
not invent a frontend/VIT button in a Python SDK repository that contains no UI.

---

## 2. Goals & Non-Goals

### Goals

- Advertise the OpenAI GPT-5.6 family through `ProviderModelRegistry`:
  `gpt-5.6`, `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.
- Resolve the `gpt-5.6` alias to `gpt-5.6-sol` for catalog and pricing lookups
  without rewriting the model string sent to OpenAI.
- Add a typed `ModelPricingRegistry` under `vidbyte.lib.registries` backed by
  dependency-light declarations under `vidbyte.lib.configs`.
- Record the current official OpenAI GPT-5.6 input, cached-input, cache-write,
  and output rates for Standard, Batch, Flex, and Fast service tiers, including
  short- and long-context rates.
- Preserve existing model configuration behavior: explicit non-empty model IDs
  remain valid even when they are not in the SDK's discovery catalog.
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

The current SDK centralizes provider defaults and environment resolution in
`vidbyte/lib/registries/models.py`, but its OpenAI catalog contains only the
default `gpt-5.5`. Its validation intentionally accepts any non-empty explicit
model name, and the OpenAI Responses adapter forwards that name unchanged. This
means a caller can technically use a GPT-5.6 ID, but the SDK does not currently
advertise the family or provide a first-party pricebook.

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

- New lookup registries belong under `vidbyte/lib/registries/`.
- Fixed declarations should live in a dependency-light `vidbyte/lib/configs/`
  package so registry resolution does not create a config-loader cycle.
- Usage accounting remains agent-owned; this change must not add a second runtime
  usage-capture or pricing path.
- The canonical checkout currently has no `scripts/run_ci.py`; its documented
  verification commands are in `CONTRIBUTING.md`, while the publish workflow
  validates builds and clean-environment imports.

---

## 4. Requirements

### Functional Requirements

1. `ProviderModelRegistry.get_supported_models()` must include the existing
   OpenAI `gpt-5.5` entry and all four GPT-5.6 names: `gpt-5.6`,
   `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.
2. `ProviderModelRegistry.get_supported_models("openai")` must return the same
   OpenAI catalog without requiring callers to inspect internal maps.
3. `ProviderModelRegistry.normalize_model("openai", "gpt-5.6")` must return
   `gpt-5.6-sol`; canonical model IDs must resolve to themselves.
4. Unknown explicit model IDs must remain usable by existing model-config and
   provider paths; catalog membership is discovery metadata, not an allowlist.
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
    discover models and retrieve prices.

### Non-Functional Requirements

- **Compatibility:** Existing default model selection, arbitrary explicit model
  forwarding, API-key resolution, and session usage behavior remain unchanged.
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

Keep provider defaults and model discovery in `ProviderModelRegistry`, extending
it with an explicit provider catalog and alias map. `get_supported_models()` gains
an optional provider argument for targeted discovery while remaining source
compatible for existing no-argument callers. `validate_model()` remains a
non-empty-string check, so the new catalog does not break compatible proxies or
new provider model IDs that have not yet been added to the catalog.

Put the fixed GPT-5.6 pricing declarations in a new dependency-light
`vidbyte.lib.configs` package. A new `ModelPricingRegistry` owns provider/model
normalization, service-tier selection, context-length selection, and clear error
messages. The registry returns immutable typed records and never contacts
OpenAI. The alias is normalized only for lookup; the OpenAI request adapter keeps
the caller's original model string.

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

Extends the existing provider registry with a complete discoverable OpenAI
GPT-5.6 family and a single canonical alias map. It preserves the existing
default map and explicit-model compatibility contract.

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

1. Add an explicit `SUPPORTED_PROVIDER_MODELS` catalog containing the current
   defaults plus the OpenAI GPT-5.6 names.
2. Add a provider-scoped alias map with `gpt-5.6` pointing to
   `gpt-5.6-sol`.
3. Normalize the provider using the existing `ModelProvider` conversion and
   trim/validate the model string.
4. Return all providers' models for the existing no-argument call, or the
   selected provider's sorted models when a provider is supplied.
5. Keep `_resolve_from_environment()` tied to `DEFAULT_PROVIDER_MODELS` so adding
   an advertised model does not silently make a new model the environment-driven
   runtime default.

#### Edge Cases & Error Handling

- An unknown provider continues to raise `ConfigurationError` through the
  existing provider validation path.
- Empty model names continue to raise the existing `ConfigurationError`.
- Unknown non-empty models return `False` from `is_supported_model()` and remain
  valid for explicit provider requests.
- Alias normalization does not alter the model stored in `TextModelConfig` or
  sent in an OpenAI request.

### 6.2 Immutable OpenAI pricing declarations

**File(s):** `vidbyte/lib/configs/__init__.py`, `vidbyte/lib/configs/model_pricing.py`  
**Type:** New files

#### What it does

Creates the dependency-light source of truth for the GPT-5.6 pricebook. The
declarations are data only; they do not import registries, providers, HTTP
clients, session classes, or configuration loaders.

#### Interface / API

```python
class PricingServiceTier(str, Enum): ...

@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_million_tokens: float
    cached_input_per_million_tokens: float
    cache_write_per_million_tokens: float
    output_per_million_tokens: float

@dataclass(frozen=True, slots=True)
class ModelPricingDefinition:
    provider: ModelProvider
    model: str
    description: str
    standard: ModelPrice
    long_context: ModelPrice
    batch: ModelPrice
    flex: ModelPrice
    fast: ModelPrice
    source_url: str
    pricing_checked_on: str
```

#### Logic / Algorithm

1. Define immutable records for the four billable token categories.
2. Define one immutable `ModelPricingDefinition` for each canonical model:
   `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.
3. Store all rates as USD per 1,000,000 tokens, matching the official pricing
   table's units.
4. Store the live pricing URL and `2026-07-30` audit date on every definition.
5. Export the types and the OpenAI pricing map from the package initializer so
   the registry can consume a clear public declaration surface.

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
**Type:** New file

#### What it does

Provides the public lookup API for model pricing and owns provider/model/tier
validation. It follows the SDK registry pattern and consumes the fixed
declarations rather than embedding pricing literals in session or provider code.

#### Interface / API

```python
class ModelPricingRegistry:
    @classmethod
    def definition(cls, provider: ModelProvider | str, model: str) -> ModelPricingDefinition: ...

    @classmethod
    def get(cls, provider: ModelProvider | str, model: str, *, service_tier: PricingServiceTier | str = PricingServiceTier.STANDARD, long_context: bool = False) -> ModelPrice: ...

    @classmethod
    def get_supported_models(cls, provider: ModelProvider | str | None = None) -> list[str]: ...
```

#### Logic / Algorithm

1. Normalize the provider and model through `ProviderModelRegistry`.
2. Resolve aliases before looking up the canonical definition.
3. Select one of the definition's `standard`, `batch`, `flex`, or `fast` records.
4. Select `long_context` when requested; otherwise use the short-context record.
5. Return the frozen record without network access or mutation.

#### Edge Cases & Error Handling

- A model that is valid for explicit OpenAI use but has no price declaration
  raises `ConfigurationError` from the pricebook lookup, including the provider,
  requested model, and priced model list.
- An invalid service tier raises `ConfigurationError` with the valid tier names.
- Non-boolean `long_context` values are rejected rather than silently coerced.
- Pricing lookup does not mutate or canonicalize the caller's request config.

### 6.4 Public exports and documentation

**File(s):** `vidbyte/lib/registries/__init__.py`, `vidbyte/lib/README.md`, `README.md`  
**Type:** Modified

#### What it does

Exports `ModelPricingRegistry` and documents both model discovery and price
lookup alongside the existing provider registry documentation.

#### Interface / API

```python
from vidbyte.lib.registries import ModelPricingRegistry, ProviderModelRegistry

models = ProviderModelRegistry.get_supported_models("openai")
price = ModelPricingRegistry.get("openai", "gpt-5.6-luna")
```

#### Logic / Algorithm

1. Add the pricing registry import and `__all__` entry.
2. Add a short example showing canonical discovery, alias lookup, service tier,
   and the USD-per-million-token units.
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
ModelPricingDefinition(
    provider=ModelProvider.OPENAI,
    model="gpt-5.6-luna",
    standard=ModelPrice(...),
    long_context=ModelPrice(...),
    batch=ModelPrice(...),
    flex=ModelPrice(...),
    fast=ModelPrice(...),
    source_url="https://developers.openai.com/api/docs/pricing",
    pricing_checked_on="2026-07-30",
)
```

**Migration strategy:** N/A - this is immutable package data, not persisted
state. Forward migration is a normal SDK release. Rollback removes the new
registry/config files and the related exports/documentation; existing session
data and model configurations remain readable.

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
ModelPricingRegistry.get(
    "openai",
    "gpt-5.6-terra",
    service_tier="standard",
    long_context=False,
)
# -> ModelPrice with USD-per-million-token fields
```

**Error cases:**

| Error | Condition |
|---|---|
| `ConfigurationError` | Provider is not recognized. |
| `ConfigurationError` | Model has no price declaration. |
| `ConfigurationError` | Service tier is not Standard, Batch, Flex, or Fast. |
| `ConfigurationError` | Model or tier input is malformed. |

---

## 9. File Change Manifest

Complete list of every file expected for this design and its implementation:

| Action | File Path | Reason |
|---|---|---|
| CREATE | `docs/design/openai-gpt-5-6-catalog-pricing.md` | Approved design artifact and implementation source of truth. |
| CREATE | `vidbyte/lib/configs/__init__.py` | Public exports for dependency-light pricing declarations. |
| CREATE | `vidbyte/lib/configs/model_pricing.py` | Immutable official GPT-5.6 pricing data and typed records. |
| CREATE | `vidbyte/lib/registries/pricing.py` | Provider/model/tier pricing lookup registry. |
| MODIFY | `vidbyte/lib/registries/models.py` | Advertise GPT-5.6 models and resolve the alias. |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Export `ModelPricingRegistry`. |
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

# Feature: Current model catalog and first-party pricebook

## High-Level Feature Description

The SDK accepts a model only when it is catalogued under the provider that serves it, and prices each call from a table of first-party rates. The October 2026 refresh adds the current frontier and open-weight models (GPT-6 Astra, Sol, 6.1 Sol and Luna; Claude Fable 5.1, Mythos 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5; Gemini 3.8 and 3.6 Flash; Grok 4.7 and 4.6; DeepSeek Flash; GLM-5.3; Muse Spark 1.3 and 1.2; Mistral Medium 3.5, Small 4 and Large 4) and corrects rates the providers changed.

## Contract

Every added model validates under its own provider, is rejected under another, appears in both runner maps as text, and resolves to its own exact price row at the rate on the provider's page. A new id that extends an older key (claude-sonnet-5-5, glm-5.3) never prices as that older key. A deprecated name that the provider routes elsewhere bills at the serving model's rate.

## Actors / Callers

`ProviderModelRegistry.validate_provider_model_pair`, `ModalityDetector.detect_modality`, `ModelPricingRegistry.resolve`, `ProviderUsage.cost_usd` subclasses and `UsageTracker.record_call`.

## Inputs and Preconditions

Provider and model names, offline provider-shaped usage mappings and the in-process pricebook; no network credentials.

## Observable Outcomes

A call to an added model records a cost equal to its token counts times the published rate. Prompts past a published tier bill at the tier's rate: Grok 4.7 from exactly 200,000 prompt tokens, GPT-6 above 272,000 input tokens, and Claude Haiku 5.5 above 100,000 prompt tokens counting cache reads and writes.

## State Transitions

None; catalog and pricebook are immutable module data, and each priced call appends one usage record.

## Invariants

Every pricebook rate is finite and non-negative; every provider's default text model has a price; changed rates move `PRICING_AS_OF`.

## External Dependencies

Only the local registries; expected rates were copied from the provider pages cited beside each row in `vidbyte/lib/registries/pricing.py`.

## Known Failure Modes

Longest-prefix lookup silently priced a missing claude-sonnet-5-5 as claude-sonnet-5. Anthropic's `input_tokens` excludes cache buckets, so a cache-heavy Haiku 5.5 prompt over 100K billed the cheaper tier.

## Historical Regressions

2026-10-11: the catalog lacked every model released since July 2026, Claude Opus 5, Fable 5 and Mythos 5 had no price, GPT-5.6 Sol and Gemini 3.6 Flash still showed pre-promotion rates, and Mistral's default model resolved to no price.

## Test Suite Map

`test_catalog_pricing_contract.py` covers catalog validation, wrong-provider rejection, runner-map parity, modality, exact rates, exact-key identity, versioned ids, routed names, tier metadata, every tier boundary and two tracker calls. Run `python -m pytest -q tests/features/sdk_model_catalog`.

## Omitted Testing Strategies

Network probes against provider APIs are omitted: tests must stay offline and keyless, and the rates are pinned from first-party pages instead. Concurrency and performance probes do not apply to immutable lookup tables.

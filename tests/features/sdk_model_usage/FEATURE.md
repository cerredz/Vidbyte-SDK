# Feature: Accountable model usage

## High-Level Feature Description

The SDK records per-call model token counts and USD cost so callers can trust run-level usage totals. Provider payloads can be malformed; impossible token counts must fail closed, while invalid marketplace-reported costs may use a registered model rate.

## Contract

A plain top-level agent's `get_usage()` includes every model call its run causes: calls made by sub-agents it uses as tools (`as_tool()`), by its continual-trace agent, and by lib-level decision calls, each counted exactly once, while each nested agent's own `get_usage()` still shows only its own calls. A provider that bills an HTTP 200 whose reply has no usable text still appears on the bill: the text adapter puts the usage on its ProviderResponseError and the agent runtime records it as a failed call before retrying, falling back or raising. Token counts are non-negative integers. A negative count anywhere in a recognized usage payload corrupts metering and leaves no priced model record. OpenRouter's reported USD cost overrides table pricing only if it is finite and non-negative; otherwise use a registered rate, or remain unpriced if no rate exists. A Jev decision is priced by the versioned model that answered it; when the pricebook has no row for that release (TypeSafe moved `jev-latest` from `jev-1.13.0` to `jev-1.14.0` on 2026-10-14), it is priced as the model `DecisionModelRunner` requested, if that model is priced. Only TypeSafe answer IDs of the documented `jev-<major>.<minor>.<patch>` shape fall back, and a request for an unpriced model stays unpriced, so a JevAgent run still fails closed. An Anthropic call is priced at the speed and inference geography its response's `usage` reports, never the request's: `speed` "fast" bills the model's fast tier (Opus 5.5 $8/$40, Opus 5 and Opus 4.8 $10/$50 per MTok, with caching multipliers on top), and `inference_geo` "us" multiplies every bucket by 1.1, stacking with fast mode, caching and the Claude Haiku 5.5 over-100K tier. "global", "not_available", and an absent or null report bill exactly as standard. An unknown speed or geography, or a fast call on a model without a fast tier, leaves the call unpriced rather than billed at standard rates.

## Actors / Callers

`UsageTracker.record_call` (and its `requested_model` keyword, which only `DecisionModelRunner` passes), `ModelPricingRegistry.resolve_answered`, `record_billed_failure`, `ProviderUsage` subclasses (including `AnthropicUsage.cost_usd`), the provider text adapters and agent runtime that feed them, `BaseAgent.generate_reply`'s usage ledger scope, and users reading `UsageRollup`.

## Inputs and Preconditions

Offline provider-shaped response usage mappings and a local model price registry; no network credentials.

## Observable Outcomes

Malformed counts never appear in a priced record; the tracker reports corrupted recording so fail-closed owners stop. Invalid reported costs cannot produce a negative or non-finite complete total. Zero counts and zero reported costs remain valid.

## State Transitions

A valid call appends one record; an invalid count flags the recording as corrupted without appending; an invalid reported cost records a valid-token call as priced by a table or visibly unpriced.

## Invariants

No negative token counts or non-finite costs in a complete rollup.

## External Dependencies

Only the local model pricing registry, no provider calls.

## Known Failure Modes

The common integer parser accepted negative counts; OpenRouter's optional cost parser accepted negative values, NaN and infinity.
A billed 200 with no usable text (an Anthropic refusal with empty content, Gemini spending its budget on thinking) raised without its usage, so the charge was dropped even when a fallback model then answered.
A plain top-level agent opened no usage ledger, so its sub-agent tools and continual-trace agent found none to merge into and their calls were dropped from its bill.
A TypeSafe release the pricebook lacked left every billed Jev decision unpriced, so `JevUsageAccount.settle()` failed every JevAgent run closed after the spend.
`AnthropicUsage.cost_usd` read only the token buckets, so fast-mode and US-only calls were billed at standard rates.

## Historical Regressions

2026-10-07: an offline OpenAI call with -1,000,000 input tokens produced a negative USD total marked complete; OpenRouter's `usage.cost=Infinity` was marked complete without a pricebook entry.

2026-10-12: an Anthropic refusal billed 1,000 input and 3 output tokens, then a Gemini fallback answered; the run reported only the Gemini cost ($0.001545 of $0.003575).

2026-10-12: a top-level agent with a sub-agent tool made 3 wire calls but billed 2; wrapped one level deeper with a continual trace it made 7 wire calls and billed 2.

2026-10-27: real Anthropic calls on claude-opus-5-5 billed $0.000344 in fast mode and $0.0001892 with US-only inference (13 input and 6 output tokens each); the SDK reported $0.000172 for both.

2026-10-25: production answered Jev decision calls with `jev-1.14.0`, which the pricebook (only `jev-1.13`, `jev-latest`, `jev-preview`) could not price, so every JevAgent run that asked Jev raised `UsageAccountingError` (`unpriced_call`, `typesafe:jev-1.14.0`) after Vidbyte had billed the call.

## Test Suite Map

`test_usage_contract.py` covers base token parsing, nested token fields, billed failures, OpenRouter fallback and valid overrides. `test_billed_unusable_replies.py` covers the usage each text adapter keeps on an unusable-reply error and an agent run that bills a refusal and then a fallback answer. `test_nested_usage_bill.py` covers a top-level agent's bill with a sub-agent tool, a continual trace, and two levels of sub-agents. `test_jev_versioned_answer_pricing.py` covers the `jev-1.14` row, a later release priced as the requested `jev-latest` (at the tracker, through `DecisionModelRunner`, and through a JevAgent run), and the fallback's limits: no requested model, an unpriced request, a non-versioned answer ID, and other providers. `test_anthropic_price_modifiers.py` covers the two live payloads, fast mode and US-only stacked with each other, caching and the Haiku 5.5 tier, the 1x reports, unknown and unrated values left unpriced, the Opus fast-tier pins, the tracker, and one agent run through the Anthropic adapter. Run `python -m pytest -q tests/features/sdk_model_usage`.

## Omitted Testing Strategies

Network, browser, concurrency and performance probes are unnecessary for this in-memory parsing boundary. Existing `tests/test_agent_pricing.py` covers provider-specific successful shapes.

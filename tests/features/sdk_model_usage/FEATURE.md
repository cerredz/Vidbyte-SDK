# Feature: Accountable model usage

## High-Level Feature Description

The SDK records per-call model token counts and USD cost so callers can trust run-level usage totals. Provider payloads can be malformed; impossible token counts must fail closed, while invalid marketplace-reported costs may use a registered model rate.

## Contract

Token counts are non-negative integers. A negative count anywhere in a recognized usage payload corrupts metering and leaves no priced model record. OpenRouter's reported USD cost overrides table pricing only if it is finite and non-negative; otherwise use a registered rate, or remain unpriced if no rate exists.

## Actors / Callers

`UsageTracker.record_call`, `record_billed_failure`, `ProviderUsage` subclasses, and users reading `UsageRollup`.

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

## Historical Regressions

2026-10-07: an offline OpenAI call with -1,000,000 input tokens produced a negative USD total marked complete; OpenRouter's `usage.cost=Infinity` was marked complete without a pricebook entry.

## Test Suite Map

`test_usage_contract.py` covers base token parsing, nested token fields, billed failures, OpenRouter fallback and valid overrides. Run `python -m pytest -q tests/features/sdk_model_usage`.

## Omitted Testing Strategies

Network, browser, concurrency and performance probes are unnecessary for this in-memory parsing boundary. Existing `tests/test_agent_pricing.py` covers provider-specific successful shapes.

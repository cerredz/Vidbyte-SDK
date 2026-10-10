# Feature: Valid middleware guardrails

## High-Level Feature Description

The SDK's built-in budget and limit middleware must receive finite positive limits so its guardrails remain enforceable.

## Contract

Count limits accept positive integers, excluding booleans. Durations and costs accept finite positive numbers, excluding booleans. Invalid inputs raise `ValueError` with the field name during construction, matching the existing middleware constructor contract.

## Actors / Callers

SDK users constructing `CostBudgetMiddleware`, `RuntimeLimitMiddleware`, `TokenBudgetMiddleware`, and `TokenRateLimitMiddleware` directly or through configuration.

## Inputs and Preconditions

Numeric limit parameters, without live model calls or credentials.

## Observable Outcomes

Invalid limits are rejected before a run; valid positive finite limits retain their values and existing execution semantics.

## State Transitions

Failed construction leaves no middleware instance; successful construction stores the limits unchanged.

## Invariants

`True` is not a count, `NaN` and infinities are not usable budgets, and numeric strings are not numeric limits.

## External Dependencies

None; probes instantiate middleware offline.

## Known Failure Modes

Python's `bool` inherits `int`, and `NaN <= 0` is false. Unchecked strings may leak a `TypeError` instead of a field-specific error.

## Historical Regressions

2026-10-07: an offline probe accepted `CostBudgetMiddleware(max_spend_usd=NaN)`, `RuntimeLimitMiddleware(max_model_calls=True, max_elapsed_seconds=NaN)` and `TokenRateLimitMiddleware(max_tokens=True, per_seconds=NaN)`.

## Test Suite Map

`test_middleware_limit_contract.py` tests invalid counts and finite numbers across four public middleware constructors; run `python -m pytest -q tests/features/sdk_middleware_limits`.

## Omitted Testing Strategies

Provider, browser, concurrency, and performance tests are unnecessary at the synchronous validation boundary. Existing middleware test modules cover actual run hooks and their decisions.

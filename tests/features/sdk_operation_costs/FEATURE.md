# Feature: Finite operation costs

## High-Level Feature Description

An SDK caller records billable search/fetch operations and reads their USD cost from the agent's usage rollup. Bad count or cost data must not become a seemingly complete but incorrect cost total.

## Contract

Only positive integer unit counts may produce operation records. A finite, non-negative provider-reported cost takes precedence over the table rate; malformed reported costs fall back to the registered table, or remain unpriced when no table entry exists.

## Actors / Callers

`UsageTracker` callers including search/fetch tool execution and agent usage reporting.

## Inputs and Preconditions

An operation/provider name, a positive integer unit count, and optionally a reported USD cost; no network or credentials required.

## Observable Outcomes

`record_operation` returns a record with finite cost or `None` for an invalid count. `rollup()` contains only accepted operations and reports `cost_complete=False` if a valid operation has no usable price.

## State Transitions

An invalid count leaves the ledger unchanged; a valid count appends one priced or visibly unpriced record.

## Invariants

No negative or zero units; no non-finite or negative cost is recorded as complete; a finite provider override wins over the table.

## External Dependencies

The built-in operation pricing registry (local), no live provider calls.

## Known Failure Modes

Python accepts negative integers for the current units type check. Infinity passes a non-negative comparison, becomes `inf` in a complete rollup, and can propagate through budget and reporting calculations.

## Historical Regressions

The 2026-10-07 offline probe reproduced negative units priced at zero and an infinite completed cost.

## Test Suite Map

`test_operation_cost_contract.py` tests invalid counts, fallback rates, reported overrides, unpriced providers, and rollup integrity. Run with `python -m pytest -q tests/features/sdk_operation_costs`.

## Omitted Testing Strategies

Live provider, browser, concurrency and load tests are omitted: this is a synchronous, in-memory accounting boundary. Vendor rate audits are maintained separately with the pricing registry.

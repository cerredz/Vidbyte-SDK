# Feature: Offline SDK consumer programs

## High-Level Feature Description

Developers should be able to assemble SDK components into real agent runs, not just instantiate them independently. These programs probe cross-subsystem behavior with provider-shaped offline replies.

## Contract

Agent tool loops honor per-run budgets, middleware stops additional model calls, repeated runs reset usage and tool policy, structured replies validate, handoffs survive malformed structured replies, and JEV preflight records a combined priced usage ledger.

## Actors / Callers

SDK users writing Python programs with `Agent`, `HandoffAgent`, `JevAgent`, tools, middleware, trace, and settings.

## Inputs and Preconditions

Deterministic scripted model replies; no credentials, live model requests or external services.

## Observable Outcomes

Every runnable program exits successfully after checking its outputs and accounting. A failure identifies a public SDK flow requiring a smaller minimal reproduction before any production change.

## State Transitions

Fresh runs and repeated runs both complete with expected counters; invalid structured output retries then degrades to prose for handoff only.

## Invariants

Read-only tools cannot execute past a budget. Usage is priced and reset between runs. No fake runner bypasses the SDK runtime.

## External Dependencies

None. Network transport is replaced at the boundary only.

## Known Failure Modes

A fake model response without provider usage fails JEV accounting; one malformed handoff reply exhausts a single-response runner before the configured retry policy completes.

## Historical Regressions

2026-10-08: First consumer probes showed the two fixture mistakes above, not SDK product bugs. Both are documented in `scripts/sdk_edge_probes/README.md`.

## Test Suite Map

`test_consumer_programs.py` invokes each program independently; `python -m scripts.sdk_edge_probes.run` runs the entire sequence manually.

## Omitted Testing Strategies

Live credentials, browser UI, performance and concurrency are out of scope for these deterministic offline programs; provider HTTP tests live elsewhere.

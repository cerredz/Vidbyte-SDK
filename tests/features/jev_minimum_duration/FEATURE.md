# Feature: Jev Minimum Run Duration

## High-Level Feature Description

An SDK caller may require a Jev run to remain eligible for completion only after a minimum monotonic elapsed duration. If the model finishes early, the same run continues with a prompt to keep working. This prevents an early completion attempt from ending the run while ensuring time passage alone never claims the task is complete.

## Contract

- Configure via `JevAgentSettings(done_criteria=(JevPreset.MinimumTime(hours=5),))`.
- Every ordinary model-originated completion path is gated: a plain final response and the internal `isDone` tool.
- Early attempts become visible continuation prompts and continue within the same runtime loop.
- `minimum_duration_met` is the exact computed result metadata when configured; no criterion means no such field.
- The check uses monotonic per-run time, all configured criteria must pass, and regular runtime budgets remain authoritative.

## Actors / Callers

Python callers configure `JevAgentSettings`; `JevRuntime` applies the criterion through the shared direct-runtime finish-attempt seam.

## Inputs and Preconditions

The criterion accepts exactly one finite positive numeric duration in seconds, minutes, hours, or days. Boolean values, invalid ranges, multiple units, missing units, and non-criterion settings entries are invalid. The runtime supplies monotonic elapsed seconds from the current attempt.

## Observable Outcomes

An early completion attempt causes another model invocation with the candidate response and continuation feedback in history. A later model-originated completion is accepted only if all criteria pass. Results expose `minimum_duration_met` as a Boolean when the minimum-time criterion is configured.

## State Transitions

`running -> finish attempt -> running` when a criterion is unmet; `running -> result` only when a model attempts completion and all configured criteria pass. Budget or middleware stops remain terminal according to existing runtime policy.

## Invariants

- Monotonic elapsed time is measured per attempt; criteria do not hold shared run state.
- Threshold passage never completes a task without a model finish attempt.
- Both normal completion paths use the same Jev criteria.
- No configured criteria preserves established Jev behavior and metadata.

## External Dependencies

The runtime's injected monotonic middleware clock and scripted model runner used by tests. No new network calls or dependencies are added.

## Known Failure Modes

Unit conversion overflow, Boolean-as-integer input, off-by-one threshold comparison, final-text-only bypass, `isDone`-only bypass, candidate response omitted from resumed history, shared start-time leakage across concurrent runs, accidental task completion on clock threshold alone, and metadata omitted on budget stops.

## Historical Regressions

No historical runtime regression is known; tests encode the discovered two-path finish boundary so later changes cannot gate only one of them.

## Test Suite Map

- `tests/test_jev_done_criteria.py` covers constructor validation, exact duration evaluation, settings snapshotting, both finish paths, result metadata, and default behavior.
- `scripts/test-jev-done-criteria.py` runs the complete focused module and returns a process failure if any case fails.
- `tests/test_jev_agent.py` remains the regression suite for Jev scaffold construction and normal loop behavior.

## Omitted Testing Strategies

No browser, database migration, security-permission, stress, fuzz, or live provider tests are added because the feature is a local runtime decision over validated duration inputs and monotonic clock values; provider calls are not introduced.

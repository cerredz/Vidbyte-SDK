# Feature: Jev output extent continuation gate

## High-Level Feature Description

The opt-in `OUTPUT_EXTENT` continuation gate tracks explicit numeric constraints on the magnitude of text in a requested output. It matters because a plausible final answer can omit a requested length, line, section, or page amount while sounding complete. The gate must preserve the target, unit, and direction of the original bound from before work starts through every finish attempt. Distinct item counts belong to separate output-count gates.

## Contract

When enabled through `JevContinualSettings.checks`, run state records every unambiguous explicit text extent before work starts. The handoff returns one observed-evidence item per obligation. Each obligation contributes one question to the single batched Jev request. Code applies exact numeric comparisons to supported final-answer scopes even when the final answer omits the requested quota; Jev recognizes that evidence is about the correct target. If an extent fails, continuation feedback names the target, bound, observed amount when available, and handoff gap. If evidence or Jev is unavailable, the advisory check fails open, consistent with other Jev done checks.

## Failure Inventory

- Exact is weakened to minimum, or minimum/exact/maximum direction is lost.
- The agent's quota claim substitutes for observed output text.
- A generated handoff verdict overwrites the original request's explicit amount.
- A short final answer passes because it does not mention the quota.
- A measurement includes unrelated answer or artifact text.
- Vague adjectives become invented numeric quotas.
- Distinct examples/files are treated as text extent rather than output count.
- The handoff omits an item or returns evidence under an unknown id.
- An unavailable handoff or Jev request blocks the main answer rather than failing open.

## Test Suite Map

- `tests/test_jev_done.py` checks typed records and schema descriptions, question registration and size, measurement units and bound direction, and an integration case where an under-length answer fails despite omitting the quota.

## Omitted Testing Strategies

- Live-provider integration omitted because deterministic scripted runners protect the feature boundary without credentials or nondeterminism.
- Browser and accessibility tests omitted because this is a Python SDK gate with no user interface.
- Stress, fuzz, and concurrency tests omitted because the new behavior is bounded string counting and immutable per-run record validation; existing loop tests cover bounded continuation behavior.

## Historical Regressions

- None yet.

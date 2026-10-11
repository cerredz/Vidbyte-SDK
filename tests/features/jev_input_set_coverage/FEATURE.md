# Bounded input-set coverage

## Feature contract

When a developer enables `JevDoneCheck.INPUT_SET_COVERAGE`, JevAgent records the explicitly bounded input-engagement obligations from the request before the main loop. At each finish attempt, the handoff must provide one trace-evidence entry with exactly the same target ids. Jev receives one positive yes/no question per target and recognizes only whether the evidence shows the requested action over the user's full scope and at the requested depth. Paths and result listings do not prove content inspection, excerpts do not prove full review, and failed attempts do not prove successful engagement. Deterministic code owns id matching, threshold/veto scoring, incomplete target selection, batching with other enabled checks, and fail-open behavior; only failed target feedback is appended to the same main-agent loop, up to the shared continuation cap.

The feature applies to finite targets bounded by the request. Open-ended, changing, or dynamically paginated collections are outside this contract and need a separate exhaustion check. Run-state generation can omit an obligation; the original request remains present in Jev's shared state, but this feature does not ask Jev to independently enumerate the user's entire request.

## Failure inventory

- The run-state target list is empty when explicit bounded input work exists.
- The run-state invents, merges, duplicates, or weakens target ids, actions, or boundaries.
- The handoff omits, adds, reorders, or renames an expected id.
- Evidence consists only of a path/listing, final-answer claim, failed call, or excerpt too shallow for the requested action.
- Evidence covers only some members of a target the user bounded as all/every/whole.
- Jev returns a low probability, misses an answer, or is unavailable.
- A failed check does not continue the same loop, focuses passing targets, or exceeds the continuation cap.

## Test map

`tests/test_jev_done.py` protects payload descriptions and schemas, immutable id validation, registered question shape and token length, target-level trace recognition, same-request batching, continuation focus/cap, exact handoff-id validation, empty-target behavior, and fail-open availability. `python scripts/test-jev-multipart-done-criteria.py` runs the network-free suite.

## Omitted strategies

Browser, accessibility, and load testing are omitted because the feature has no UI and the largest bounded input list is constrained by the existing Jev request limits. Provider integration tests are omitted because the existing done-check test suite replaces model boundaries with deterministic scripted runners.

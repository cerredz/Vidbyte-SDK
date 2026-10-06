# Jev question batch verification

## Goal

Protect JevAgent's preflight and done-check contracts: each phase sends all applicable questions in one Jev request, rather than making separate calls that still produce a working result.

## Design

Strengthen the existing deterministic runtime tests, which already replace the decision runner with a recorder. Assert the call count at the Jev boundary and compare the exact question names in each recorded request with the expected question set. Include actionable assertion messages that identify the phase, observed calls, and question names. For done checks, make the assertion per finish attempt: a continuation creates a new attempt and therefore a new batch, not a new call per question.

Do not change runtime behavior or add a second done check solely for testing. The current done-check fixture has two deliverables, enough to detect per-question calls; when the SDK supports multiple fixed presets or done checks, expected batch coverage should expand to multiple enabled checks.

## Files

- `tests/test_jev_preflight.py`: assert one recorded batch containing all enabled fixed preflight questions, including the specialist question when configured.
- `tests/test_jev_done.py`: assert all done-check questions are in one request per finish attempt, including attempts that trigger continuation.
- `docs/design/jev-question-batch-verification.md`: record this test-only change.

## Risks and verification

The SDK currently has one fixed-question preflight preset and one done check, so tests cannot prove cross-check batching for multiple enabled checks that do not yet exist. Exact membership and call-count assertions still catch splitting the existing question set into separate requests. Run both focused Jev test modules, then the repository source CI gate.

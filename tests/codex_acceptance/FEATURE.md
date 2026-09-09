# Final Codex acceptance

A native completed turn becomes a successful Vidbyte reply only after configured
status, fresh trace, schema, and application checks pass. Rejection cannot undo
native effects; it prevents publication and preserves prior accepted history.

The pack tests failures as first-class outcomes: interrupted native status, stale
artifacts, valid empty values, missing schema fields, false/missing callback
returns, exception/timeout/cancellation, mutated snapshots, forged metadata, and
fork dependencies. Integration cases use the actual facade and trace bridge with
mocked native model execution. External model selection, browser behavior, and
performance benchmarks are omitted because this boundary is deterministic.

Run `python scripts/test-codex-final-acceptance.py` for every design case.

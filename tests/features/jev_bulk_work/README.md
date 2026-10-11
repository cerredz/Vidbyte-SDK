# Jev bulk-work feature pack

This folder records the Jev bulk-work contract and its executable checks.

## Files

- `FEATURE.md` describes API behavior, invariants, known regressions, and omitted test strategies.
- `test_jev_bulk_work.py` runs deterministic unit and integration tests through production settings, registry, gate, the run_bulk_work tool, and JevRuntime.

## Run

From the repository root, use `python scripts/test-jev-bulk-work.py`. The script reports each test and exits nonzero on failure.

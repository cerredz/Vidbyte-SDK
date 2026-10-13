# Jev read-only intent feature pack

This folder records the Jev read-only intent contract and its executable checks.

## Files

- `FEATURE.md` describes API behavior, invariants, known regressions, and omitted test strategies.
- `test_jev_read_only.py` runs deterministic unit and integration tests through the production PermissionCeiling, PermissionPolicy, ToolExecutor, registry, gate, JevReadOnly, the run_bulk_work tool, specialist delegation, and JevRuntime.

## Run

From the repository root, use `python scripts/test-jev-read-only.py`. The script prints PASS or FAIL for each test, an X/Y summary, and exits nonzero on failure.

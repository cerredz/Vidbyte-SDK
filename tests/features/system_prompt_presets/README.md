# System-prompt presets feature pack

This folder records the system-prompt preset contract (the Working Principles preset) and its executable checks.

## Files

- `FEATURE.md` describes the API, invariants, known limits, and omitted test strategies.
- `fakes.py` holds the pack's own copy of the Working Principles paragraph, the recording model every agent talks to, and the safety net that refuses real network sends.
- `test_system_prompt_presets_units.py` covers the asset, enum, selection record, run scope, and composer.
- `test_system_prompt_presets_propagation.py` covers agents, children, forks, persistence, JevAgent, the opted-out machinery, the fan-out paradigm, and the documented uncovered paths.

## Run

From the repository root, use `python scripts/test-working-principles-preset.py`. The script prints PASS or FAIL per test, then `X/Y tests passed`, and exits nonzero on failure.

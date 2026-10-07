# Middleware limit probes

## Folder Description / Intent

This folder holds offline probes for the built-in middleware configuration boundary. Numeric guardrails must reject invalid values at construction, before any agent or provider call. Implementation belongs in `vidbyte/middleware/builtins/`; this folder only exercises its public constructors.

## File Index

- `README.md` routes test and production changes.
- `FEATURE.md` records the numeric limit contract and known failures.
- `test_middleware_limit_contract.py` checks malformed and valid cost, runtime, token-budget, and rate-limit settings.

## Logs

- 2026-10-07 - `NaN` bypassed positive comparisons and boolean limits passed as integers; add constructor regression cases before changing validation.

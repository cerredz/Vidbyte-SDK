# Model usage-integrity probes

## Folder Description / Intent

This folder probes model-token accounting with offline, provider-shaped responses. A malformed token count or non-finite marketplace price must not enter a complete usage ledger. Parsing and accounting live in `vidbyte/agents/pricing/`, not in these tests.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` defines valid counters, reported-cost fallback, and fail-closed outcomes.
- `test_usage_contract.py` records malformed and valid model calls through the real usage tracker.

## Logs

- 2026-10-07 - Negative OpenAI input tokens produced a negative, complete rollup; infinite OpenRouter reported cost also produced a complete non-finite rollup.

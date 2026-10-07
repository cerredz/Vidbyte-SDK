# SDK operation-cost probes

## Folder Description / Intent

This folder checks how the public usage tracker prices non-model operations. Its purpose is to keep reported USD costs and billable unit counts meaningful even when a provider or an SDK caller sends malformed data. It covers the recording boundary, not the correctness of any vendor's published rate.

Implementations belong in `vidbyte/agents/pricing/tracker.py`; vendor tariffs belong in `vidbyte/lib/registries/operation_pricing.py`. Provider HTTP behavior belongs in `vidbyte/providers/`, not in this offline feature pack.

## Non-Goals

- Do not add tariffs here; `vidbyte/lib/registries/operation_pricing.py` owns rates.
- Do not add token parsing here; `vidbyte/agents/pricing/` owns provider usage parsing.
- Do not make external requests; `vidbyte/providers/` owns API adapters.
- Do not implement budget enforcement; `vidbyte/middleware/builtins/` owns it.
- Do not add tracing exporters; `vidbyte/providers/tracing/` owns them.
- Do not change Jev decisions; `vidbyte/agents/jev/` owns Jev behavior.
- Do not add SDK tool execution logic; `vidbyte/tools/` owns it.

## File Index

- `README.md` explains the pricing probe boundary and routes changes to their owners.
- `FEATURE.md` states the observable operation-cost contract and failure inventory.
- `test_operation_cost_contract.py` exercises malformed counts, provider-reported costs, and valid fallback pricing through `UsageTracker`; start here for operation-accounting regressions.

## Logs

- 2026-10-07 - A negative unit count was recorded at zero cost and an infinite provider cost marked usage complete - guard before storing a priced record.

# SDK loop-settings probes

## Folder Description / Intent

This folder holds offline, caller-facing probes for the agent loop's configuration boundary. It exists to catch invalid budgets before they reach a runtime, where an invalid limit can disable a guardrail or produce an unrelated error. The tests exercise the public settings constructor and its runtime conversion, not private validation helpers.

It is not a home for middleware policy implementations, provider fixtures, or Jev decision questions. Those belong under `vidbyte/middleware/`, `tests/agent_test_support.py`, and `vidbyte/lib/jev/`, respectively.

## Non-Goals

- Do not add production loop logic here; `vidbyte/agents/runtime.py` owns execution.
- Do not add provider HTTP calls; `vidbyte/providers/` owns adapters.
- Do not implement middleware policies; `vidbyte/middleware/` owns them.
- Do not add JEV questions; `vidbyte/lib/jev/` owns their contracts.
- Do not add pricing tables; `vidbyte/lib/registries/pricing.py` owns pricing.
- Do not add trace exporters; `vidbyte/providers/tracing/` owns external tracing.
- Do not add tool permission code; `vidbyte/tools/security/` owns it.

## File Index

- `README.md` describes why offline boundary tests live here and routes future probes to the owning production layers.
- `FEATURE.md` records the contract, known failure mechanisms, and which test strategies are intentionally omitted.
- `test_contract.py` probes accepted and rejected loop limits through the public constructor and the generated runtime config. Open this first when a settings input passes validation but cannot be enforced as intended.

## Logs

- 2026-10-07 - Boolean and fractional loop budgets passed validation, strings escaped as TypeError, and NaN timeouts passed - probe the constructor before testing runtime limits.
- 2026-10-07 - Nested ToolSettings also accepted NaN and infinite per-tool timeouts; test both loop and tool-call limits.
- 2026-10-07 - ToolErrorPolicy accepted boolean and fractional retry counts and infinite backoff parameters; include retry policy when probing settings limits.

# `vidbyte/agents/multi`

## Folder Description / Intent

This folder owns Vidbyte's ledger-driven multi-agent team abstraction. It exists for open-ended work where a manager must preserve an overall goal, delegate one ready task at a time, evaluate progress, and replan after failure. The package optimizes for bounded autonomy and developer control: agent-to-agent requests, reports, validation, worker construction, cleanup, and completion policy are explicit extension seams.

The mutable structural source of truth is the run-local `TaskLedger`; agents and orchestrators receive immutable snapshots rather than writable shared dictionaries. A `MultiAgent` remains compatible with the normal `BaseAgent` execution surface while deliberately rejecting provider, tool, MCP, and session-persistence behavior at the team facade.

This folder is not a general workflow engine, a concurrent fan-out engine, or a durable session store. Deterministic state machines belong in `vidbyte/workflows`, linear composition belongs in `vidbyte/pipelines`, provider/model execution belongs in `vidbyte/agents/base.py`, and session serialization belongs in `vidbyte/sessions`.

## Blast Radius

The public package is exported through `vidbyte.agents`, `vidbyte.AgentClient`, and the root `vidbyte` namespace. It depends on central contracts in `vidbyte/lib/dataclasses/multi_agent.py`, enum/error surfaces in `vidbyte/lib`, prompt assets in `vidbyte/prompts`, and trace component routing in `vidbyte/trace`.

## Non-Goals

- Do not add durable ledger persistence or session restoration here; those concerns belong in `vidbyte/sessions` and are explicitly unsupported for a team facade.
- Do not add generic graph/state-machine execution here; deterministic validated transitions belong in `vidbyte/workflows`.
- Do not add linear stage composition here; ordered pipelines belong in `vidbyte/pipelines`.
- Do not add model-provider adapters or runner implementations here; those belong in `vidbyte/providers` and `vidbyte/lib/runners`.
- Do not attach tools or MCP servers to the team facade; configure them on worker or manager agents in `vidbyte/agents` and `vidbyte/tools`.
- Do not store mutable cross-run state on an orchestrator or worker template; run isolation belongs in the fork/factory seams defined in this package.
- Do not infer verification from fluent worker prose; evidence verification belongs in developer-supplied transfer validators.
- Do not add concurrent task dispatch without a new ledger concurrency design; the current controller intentionally commits one worker report per round.

## File Index

- `__init__.py` - Re-exports the supported multi-agent public surface. Open this when adding a developer-facing controller, ledger, transfer, or contract type; keep the root and agent package exports aligned.
- `agent.py` - Implements the `MultiAgent` `BaseAgent` facade and bounded controller loop. Open this for run lifecycle, finish gates, limits, cleanup, queue behavior, or facade compatibility; do not place graph-validation logic here.
- `ledger.py` - Implements the sole mutable structural authority for goals, tasks, revisions, events, retries, blockers, evidence, and replan carry-over. Open this for state transition invariants; do not invoke model agents from this file.
- `orchestrator.py` - Defines the orchestrator protocol and the Magentic-One-inspired adapter over a manager `BaseAgent`. Open this for manager prompts, structured phase parsing, renderer hooks, and manager lifecycle; do not mutate a ledger here.
- `transfer.py` - Defines agent bindings and developer-controlled request/report/validation/fork/close seams. Open this when changing what crosses the worker boundary or how worker subtypes are preserved; keep arbitrary payloads out of the default JSON renderer.
- `types.py` - Hosts callback protocols and aliases shared by the other modules. Open this when extending a seam that would otherwise create import cycles; keep stateful implementations out of this file.

## Logs

- 2026-07-13 - Chose serial ledger commits with run-local forks - makes retries and evidence attribution deterministic while preserving specialized agent behavior through explicit factories.
- 2026-07-13 - Kept the team facade schema-free and non-persistable - prevents a restored or structured facade from silently changing orchestration semantics.

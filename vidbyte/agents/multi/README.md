# `vidbyte/agents/multi`

## Folder Description / Intent

This folder owns Vidbyte's ledger-driven multi-agent team abstraction. It exists for open-ended work where a manager must preserve an overall goal, delegate one ready task at a time, evaluate progress, and replan after failure. The package optimizes for bounded autonomy and developer control: agent-to-agent requests, reports, validation, worker construction, cleanup, and completion policy are explicit extension seams.

The mutable structural source of truth is the run-local `TaskLedger`; agents and orchestrators receive immutable snapshots rather than writable shared dictionaries. A `MultiAgent` remains compatible with the normal `BaseAgent` execution surface while deliberately rejecting provider, tool, MCP, and session-persistence behavior at the team facade.

This folder is not a general workflow engine, a concurrent fan-out engine, or a durable session store. Deterministic state machines belong in `vidbyte/workflows`, linear composition belongs in `vidbyte/pipelines`, provider/model execution belongs in `vidbyte/agents/base.py`, and session serialization belongs in `vidbyte/sessions`.

## Blast Radius

The public package is exported through `vidbyte.agents`, `vidbyte.AgentClient`, and the root `vidbyte` namespace. It depends on central contracts in `vidbyte/lib/dataclasses/multi_agent.py`, context construction and primitives in `vidbyte/context`, enum/error surfaces in `vidbyte/lib`, prompt assets in `vidbyte/prompts`, and trace component routing in `vidbyte/trace`.

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
- `agent.py` - Implements the small `MultiAgent` `BaseAgent` facade and initializes its class-based collaborators. Open this for public compatibility or dependency wiring; keep controller policy in the focused runtime modules.
- `cleanup.py` - Closes run-local participants and selectively resets workers after replanning. Open this for cancellation-safe cleanup or worker reset isolation.
- `dispatcher.py` - Executes the sequential approve/build/invoke/parse/validate/commit worker boundary. Open this for dispatch containment and worker invocation retry policy.
- `ledger.py` - Implements the sole mutable structural authority for goals, tasks, revisions, events, retries, blockers, evidence, and replan carry-over. Open this for state transition invariants; do not invoke model agents from this file.
- `ledger_controller.py` - Coordinates manager policy, context snapshots, ledger commits, finish gates, replans, and event callbacks. Open this for controller-to-ledger policy.
- `ledger_reports.py` - Reduces accepted terminal reports into immutable task-record replacements. Open this for evidence/blocker merge semantics.
- `ledger_validation.py` - Validates ledger configuration, dispatches, replans, ownership, and dependency DAGs. Open this for structural guards.
- `lifecycle.py` - Owns the single top-level run exception boundary, cleanup, and trace closure. Open this for success/failure/cancellation lifecycle policy.
- `orchestrator.py` - Defines the orchestrator protocol and the Magentic-One-inspired adapter over a manager `BaseAgent`. Open this for manager prompts, structured phase parsing, renderer hooks, and manager lifecycle; do not mutate a ledger here.
- `orchestrator_runtime.py` - Applies timeout and trace policy to each run-local manager phase. Open this for phase invocation behavior.
- `post_run.py` - Produces terminal synthesis, public results, replies, history, and queued-prompt updates. Open this for terminal SDK boundary behavior.
- `pre_run.py` - Creates the isolated manager, fresh ledger, and subtype-preserving worker forks. Open this for setup ordering and ledger factories.
- `runner.py` - Presents the one-level initialize/plan/rounds/finalize controller protocol. Open this for round action ordering and finite stop reasons.
- `tracing.py` - Encapsulates safe control-only span and run summaries. Open this for trace formatting and handle closure.
- `transfer.py` - Defines agent bindings and developer-controlled request/report/validation/fork/close seams. Open this when changing what crosses the worker boundary or how worker subtypes are preserved; keep arbitrary payloads out of the default JSON renderer.
- `validation.py` - Centralizes facade/runtime `validate_*` guards and safe boundary errors. Open this for configuration, fork, input, and run-resource validation.

Shared callback aliases and run-state contracts live in `vidbyte/lib/dataclasses/multi_agent.py`. Multi-agent context construction and prompt primitives live in `vidbyte/context/multi_agent.py` and `vidbyte/context/primitives/multi_agent.py`.

## Logs

- 2026-07-13 - Chose serial ledger commits with run-local forks - makes retries and evidence attribution deterministic while preserving specialized agent behavior through explicit factories.
- 2026-07-13 - Kept the team facade schema-free and non-persistable - prevents a restored or structured facade from silently changing orchestration semantics.
- 2026-07-13 - Decomposed the facade into constructor-owned collaborators and moved prompt context into `vidbyte/context` - keeps each control path shallow, class-owned, and independently testable.

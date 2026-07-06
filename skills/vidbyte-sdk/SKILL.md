# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure. The SDK is a Python-native agent framework built around agents, tools, runtimes, context-window algorithms, middleware, durable sessions, sources, tracing, and namespace clients.

## Current Layout

```text
vidbyte/
|-- __init__.py
|-- client.py
|-- agents/                 agent actors, fork/restore state, runtimes, aggregate agents
|-- context/                context manager, primitives, presets, algorithms, handoffs
|-- evals/                  eval suites, graders, behavior predicates
|-- harnesses/              namespace clients including sdk.harnesses.sessions
|-- middleware/             deterministic runtime policy and compaction middleware
|-- paradigms/              paradigm client/harness facade
|-- pipelines/              sequential, parallel, conditional, map-reduce string wiring
|-- prompts/                repository-backed prompt catalog
|-- providers/              provider clients and adapters
|-- sessions/               checkpoint-DAG persistence, stores, usage, export/import
|-- sources/                artifact-to-context loaders, fetchers, caches, llms.txt support
|-- tools/                  public tool contracts, built-ins, MCP, filesystem tools
|-- trace/                  semantic tracing, profiles, components, continual trace
|-- shared/
`-- lib/                    dataclasses, enums, errors, runners, tools, tracing protocols
```

There is no active `vidbyte/strategies/` package. Execution paradigms live under `vidbyte/agents/runtimes/`; context-window behavior lives under `vidbyte/context/algorithms/` and `vidbyte/agents/algorithms/`.

## Core Rules

- Keep `vidbyte/` as the top-level Python package namespace and keep public dataclasses/enums/errors in `vidbyte/lib/`.
- Keep agent actor abstractions in `vidbyte/agents/`; user-facing examples should prefer `Agent`, `BaseAgent`, `AgentInput`, `ModelModality`, or namespace clients over direct runner construction.
- Keep execution runtimes under `vidbyte/agents/runtimes/` and follow [`skills/agent-runtimes/SKILL.md`](../agent-runtimes/SKILL.md) when adding or changing runtime behavior.
- Keep context-window algorithm public config under `vidbyte/context/algorithms/` and runtime adapters under `vidbyte/agents/algorithms/`; follow [`adding-context-window-algorithms.md`](adding-context-window-algorithms.md).
- Keep pipelines in `vidbyte/pipelines/`. Pipelines move strings between configured agents; they do not manage shared context, sessions, budgets, or artifacts.
- Keep middleware under `vidbyte/middleware/`; built-ins belong in `vidbyte/middleware/builtins/`, compaction behavior under `vidbyte/middleware/compaction/`, and dataclass contracts in `vidbyte/lib/dataclasses/middleware.py`.
- Keep durable sessions self-contained under `vidbyte/sessions/`. Session dataclasses/enums belong in `vidbyte/lib/dataclasses/sessions.py`; namespace-client entry points belong under `sdk.harnesses.sessions`.
- Keep artifact source loaders under `vidbyte/sources/`; source dataclasses belong in `vidbyte/lib/dataclasses/sources.py`, enums in `vidbyte/lib/enums/sources.py`, and constants in `vidbyte/lib/config/sources.py`.
- Keep prompt assets under `vidbyte/prompts/prompts/` and expose them through `vidbyte.prompts.Prompts`, `vidbyte.lib.enums.prompts.Prompt`, and direct string imports.
- Keep semantic tracing schema, profiles, controllers, session wrappers, and components under `vidbyte/trace/`; provider translators translate semantic spans but do not call external provider SDKs.
- Keep generated repository navigation artifacts such as `artifacts/file_index.md` current when package structure changes materially.

## Tools

Built-in tools belong under `vidbyte/tools/builtins/`. Approved categories include `code_search`, `editing`, `context` (legacy `ContextCompactionTool` only), `context_primitives`, `fork`, `handoff`, `memory`, `mcp`, `providers`, `sessions`, `calculator`, `code_execution`, and `document_retrieval`, plus standalone `reflexion` and `trajectory_checkpoint` context-algorithm tools. Filesystem tools live under `vidbyte/tools/filesystem/`.

`ForkConversationTool` is agent-native: it calls `BaseAgent.fork(...)`, runs an isolated child immediately, and returns the child answer as a tool result. It must remain non-escalating: model changes are allowlisted, extra tools come from developer-configured toolsets, permission policy is inherited, and child state is isolated unless returned to the parent.

Session tools live under `vidbyte/tools/builtins/sessions/`: `CheckpointTool`, `ForkTool`, `BatchForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool`, and `SessionTool`. They bind to a `Session` and respect `SessionScope`.

## Durable Sessions

Sessions persist raw agent history as source of truth and re-supply non-serializable parts such as tools, runner, and middleware at resume/fork time. Never persist secrets, and never use a trace artifact as the resume input.

Current session surfaces include:

- `agent.persist(...)`, `agent.session`, and `sdk.harnesses.sessions.attach(...)`.
- `Session.resume`, `Session.continue_`, `Session.fork_from`, `Session.batch_fork`, `rewind`, `edit`, and checkpoint policies.
- Tags/name lookup through `Session.tag`, `SessionStore.resolve`, and filtered `list_sessions`.
- Usage rollups through `Session.usage(prices=...)`.
- Portable bundles through `Session.export()` and `sdk.harnesses.sessions.export/import_`.

`Session.batch_fork(...)` and `BatchForkTool` create durable child records only; running or comparing children remains explicit caller work.

## Middleware

Middleware is deterministic runtime policy code injected with `middleware=[...]` or, for tool-error behavior, `AgentLoopSettings(tool_error_policy=ToolErrorPolicy(...))`. Middleware is not model-visible and must return `MiddlewareDecision` values instead of mutating runtime internals directly.

Built-ins cover security, budgets, retry/backoff/circuit-breaking, tool-error policy, safety/observability, rate limits, audit logging, and compaction. `ToolErrorPolicyMiddleware` retries transient idempotent tool failures, enforces optional total-error caps, and renders terminal tool errors with full detail. Do not document removed `ErrorVerbosity` or render-options APIs.

Follow [`middleware.md`](middleware.md) for the full hook lifecycle and catalog.

## Semantic Trace Components

`vidbyte/trace/components/` holds Vidbyte-owned span-spec factories. Provider-specific translation stays in `vidbyte/trace/providers/`.

- `agents.py`: `agent.run`, `agent.stop`, aggregate agent, proposer, synthesis, and failure spans.
- `runtimes.py`: linear runtime iteration plus actor and search runtime spans.
- `context.py`: context-window build, context primitive render summaries, compaction, and update spans.
- `algorithms.py`: reflexion, grading, trajectory checkpoint, problem-space search, and error-correction spans.
- `middleware.py`: hook/decision spans, including retry, abort, deny-tool, sleep, and fail-open/fail-closed decisions.
- `tools.py`: tool-call, permission, argument, result, and error spans.
- `parsers.py`: tool-call parsing and structured-output validation spans.

When changing an agent runtime, context-window algorithm, middleware, tool surface, parser, or aggregate-agent behavior, check whether semantic trace specs, README examples, and `llms.txt` need updates.

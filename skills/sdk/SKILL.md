# Vidbyte SDK

## Paradigm

The Vidbyte SDK is a **Python-native agent framework**. Every interaction follows the same core loop:

1. **Define an Agent** — name, system prompt, model provider, and optional runtime, context-window algorithm, tools, permissions, or middleware.
2. **Send a Prompt** — a plain string or a typed `AgentInput` with optional modality routing.
3. **Receive a Reply** — an `AgentMessage` with content, sender, recipient, and metadata.

Agents own their execution context: tools, runtime, context-window algorithm, middleware, history, budget, permissions, and modality routing. Pipelines wire agents together without shared state; `MultiAgent` coordinates open-ended teams through a shared, snapshot-based task ledger and developer-defined worker transfers.

## Framework Boundaries

| Layer | Responsibility | Key Types |
|-------|---------------|-----------|
| **Agent** | Single model-backed actor with tools, runtime, middleware, and history | `Agent`, `AgentInput`, `AgentMessage`, `AgentCard` |
| **Tool** | Callable capability exposed to the model during execution | `@tool`, `BaseTool`, `Tools`, `ToolSpec`, `ToolCall` |
| **Runtime** | Execution paradigm the agent loop runs under | `AgentRuntimeType` (linear, mcts_search, actor model) — see [`skills/agent-runtimes/SKILL.md`](../agent-runtimes/SKILL.md) |
| **Context-Window Algorithm** | SDK-selected runtime behavior that transforms what the model sees | `ContextWindow.preset.<name>` (reflexion, trajectory_checkpoints, grader), `ContextWindowAlgorithm` |
| **Pipeline** | String-in/string-out wiring between agents (sequential, parallel, conditional, map-reduce) | `SequentialPipeline`, `ParallelPipeline`, `ConditionalPipeline`, `MapReducePipeline` |
| **Multi-Agent Team** | Manager-owned goals, ledger tasks, evidence, blockers, retries, and replanning across worker agents | `MultiAgent`, `MagenticOneOrchestrator`, `TaskLedger`, `AgentBinding`, `AgentTransfer` |
| **Middleware** | Deterministic runtime policy code injected into the agent loop; not model-visible | `AgentMiddleware`, `MiddlewareDecision`, built-in middleware under `vidbyte/middleware/builtins/` |
| **Prompt** | Repository-backed text assets, enum-keyed, importable as constants | `Prompts`, `Prompt`, direct string imports |
| **Context** | Runtime budget, permissions, history, artifacts per agent execution | `BaseContext`, `ContextBudget`, `ContextPermissions` |
| **Sources** | Deterministic artifact-to-context loaders for public documents such as `llms.txt` | `Source`, `DocumentSource`, `LlmsTxtSource`, `ArtifactRef`, `Selection` |
| **Session** | Durable checkpoint-DAG persistence, resume, fork, rewind, usage, and export/import | `Session`, `SessionStore`, `SessionScope`, `CheckpointPolicy` |
| **Provider** | Model provider adapters (OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM, MiniMax, OpenRouter, ElevenLabs, PlayAI) | `ModelProvider`, provider adapters |

## Core Use Cases

- **Single agent with tools**: Wrap a model with custom Python functions it can call during execution.
- **Swappable runtimes**: Run an agent under a linear loop, an MCTS tree search, or an actor-model swarm via `runtime=...`.
- **Pipelined workflows**: Chain agents sequentially, run them in parallel, route conditionally, or fan-out/fan-in with map-reduce.
- **Ledger-driven teams**: Delegate one ready task at a time, evaluate explicit worker reports, enforce evidence/completion gates, and replan after stalls or failure.
- **Context-window algorithms**: Attach runtime behaviors like reflexion retries or trajectory checkpoints via `algorithm=ContextWindow.preset.<name>`.
- **Durable sessions**: Persist, resume, fork, batch fork, rewind, tag, inspect usage, and export/import agent checkpoint DAGs.
- **Artifact sources**: Turn public, pinned documents such as `llms.txt` into `DocumentContextItem` primitives via `vidbyte.sources`.
- **Handoffs**: Produce structured handoff documents so another agent (or human) can continue work cold.
- **Middleware injection**: Inject deterministic runtime policies (budgets, guardrails, security, tool-error policy, context compaction) via `middleware=[...]` or `agent_loop_settings=...` on agents.
- **Agent-native fork tool**: Let a model run an immediate isolated child conversation with `ForkConversationTool` under non-escalation rules.
- **MCP integration**: Attach external MCP servers as tools to any agent.
- **Modality routing**: Route requests to text, image, or video models automatically or explicitly.
- **Built-in tools**: Code search (glob, grep, semantic), code execution, filesystem operations, document retrieval, context primitives, memory providers, patch editing.
- **Prompt management**: Access 51 prompts across 19 prompt families through enum keys and direct Python imports.

## Middleware

Middleware is **deterministic runtime policy code** injected into the agent loop. It is not exposed to the model, not included in tool specs or agent cards, and must not mutate runtime state directly. Middleware observes, validates, or transforms agent behavior at each lifecycle hook.

### Lifecycle Hooks

`AgentMiddleware` exposes nine hooks. Each is `async def hook(self, ctx: MiddlewareContext) -> MiddlewareDecision`:

| Hook | Called When |
|------|------------|
| `before_run` | Before the runtime starts executing |
| `before_iteration` | Before each iteration of the loop |
| `before_model_call` | Before the model is invoked |
| `after_model_response` | After a successful model response |
| `on_model_error` | When a model call raises |
| `before_tool_call` | Before permission checks and tool execution |
| `after_tool_call` | After a tool executes or is denied |
| `after_iteration` | After each iteration completes |
| `after_run` | Before the final result is returned |

The full hook lifecycle, available `MiddlewareContext` fields, and the built-in catalog with arguments are documented in [`skills/vidbyte-sdk/middleware.md`](../vidbyte-sdk/middleware.md).

### Building Custom Middleware

Subclass `AgentMiddleware` and override the hooks you need:

```python
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision

class ToolRateLimitMiddleware(AgentMiddleware):
    """Deny tool calls past a per-run ceiling."""

    def __init__(self, max_tool_calls: int = 60):
        self._max = max_tool_calls

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if ctx.tool_call_count >= self._max:
            return MiddlewareDecision.deny_tool(reason="tool budget exceeded")
        return MiddlewareDecision.continue_()
```

### Attaching Middleware

Middleware is injected directly on the agent constructor:

```python
agent = Agent(
    name="guarded-agent",
    system_prompt="You are helpful.",
    provider="openai",
    model_name="gpt-4.1",
    middleware=[ToolRateLimitMiddleware(max_tool_calls=30)],
)
```

### MiddlewareDecision Values

A hook returns one of these `MiddlewareDecision` factories:

| Decision | Meaning |
|----------|---------|
| `MiddlewareDecision.continue_()` | Proceed normally |
| `MiddlewareDecision.abort(reason)` | Terminate the run, raising `AgentExecutionError` |
| `MiddlewareDecision.deny_tool(reason)` | Block the active tool (only in `before_tool_call`) |
| `MiddlewareDecision.retry(reason)` | Retry a failed model call (only in `on_model_error`) |
| `MiddlewareDecision.sleep(seconds)` | Throttle before proceeding |

### Built-in Middleware

Built-in middleware lives under `vidbyte/middleware/builtins/` and ships security/defense (canary tripwire, confused-deputy guard, honeypot), budgets (token, cost), reliability (retry, exponential backoff, circuit breaker, tool-error policy), safety/observability (loop detection, runtime limits, tool policy, token rate limit, audit log), and **context compaction** middleware (tool-result, message-history, summary, trace replacement, and trace-summary-tail compaction). Compaction is middleware, not a tool — see the catalog in [`skills/vidbyte-sdk/middleware.md`](../vidbyte-sdk/middleware.md).

## Usage Skill Files

For step-by-step instructions on specific SDK operations, see the usage skill files:

| Skill | File | Description |
|-------|------|-------------|
| Create Agent | [`skills/usage/create_agent.md`](../usage/create_agent.md) | Constructor, run/arun, modality routing, forking |
| Create Tool | [`skills/usage/create_tool.md`](../usage/create_tool.md) | `@tool` decorator, `BaseTool` subclass, `Tools` catalog |
| Create Agent with Tools | [`skills/usage/create_agent_with_tools.md`](../usage/create_agent_with_tools.md) | Attaching tools to agents, permission policy, built-in tools |
| Import Prompt | [`skills/usage/import_prompt.md`](../usage/import_prompt.md) | `Prompts.get()`, direct imports, prompt families, full prompt listing |
| Create Agents | [`skills/usage/create_agents.md`](../usage/create_agents.md) | `AgentRegistry`, multi-agent patterns, capability metadata |
| Create Pipeline | [`skills/usage/create_pipeline.md`](../usage/create_pipeline.md) | Sequential, parallel, conditional, map-reduce pipelines, nesting |
| Multi-Agent Teams | [`skills/vidbyte-sdk/multi-agent.md`](../vidbyte-sdk/multi-agent.md) | Orchestrator/ledger lifecycle, transfers, completion gates, limits, errors |
| Available Tools | [`skills/usage/available_tools.md`](../usage/available_tools.md) | Complete catalog of built-in tools (code search, filesystem, context primitives, memory, MCP) |
| Available Features | [`skills/usage/available_features.md`](../usage/available_features.md) | Runtimes, pipelines, middleware, modalities, budgets, providers, MCP, prompts |
| Agent Behavior | [`skills/usage/agent-behavior.md`](../usage/agent-behavior.md) | Post-run behavior predicates via `agent.behavior`, `PredicateGrader` in eval suites |
| Durable Sessions | [`skills/sessions.md`](../sessions.md) | Session attach/resume, checkpoint policy, tags, usage rollups, export/import, and session tools |
| Forking | [`skills/forking.md`](../forking.md) | Durable checkpoint-DAG forks/resume patterns and agent-native `ForkConversationTool` |
| Artifact Sources | [`skills/sources/SKILL.md`](../sources/SKILL.md) | Source loaders, fetchers, caches, regex helpers, and trust boundaries |

## SDK Developer Reference

| Doc | File | Description |
|-----|------|-------------|
| SDK Structure & Rules | `skills/sdk/SKILL.md` (this file) | Package layout, module rules, development guardrails |
| Updating Skill Files | [`skills/sdk/update-skill-files.md`](update-skill-files.md) | When and how to update skill files after repo changes |
| Agent Runtimes | [`skills/agent-runtimes/SKILL.md`](../agent-runtimes/SKILL.md) | Linear, MCTS search, and actor-model runtimes |
| Middleware (detailed) | [`skills/vidbyte-sdk/middleware.md`](../vidbyte-sdk/middleware.md) | Full middleware reference: hooks, decisions, built-in catalog, compaction |
| Pipelines (detailed) | [`skills/vidbyte-sdk/pipelines.md`](../vidbyte-sdk/pipelines.md) | Full pipeline reference (topologies, composability, error handling) |
| Multi-Agent Teams | [`skills/vidbyte-sdk/multi-agent.md`](../vidbyte-sdk/multi-agent.md) | Ledger-driven orchestration, public contracts, extension seams, and boundaries |
| Handoffs | [`skills/vidbyte-sdk/handoff.md`](../vidbyte-sdk/handoff.md) | Structured handoff documents and the handoff agent |
| Context-Window Algorithms | [`skills/vidbyte-sdk/adding-context-window-algorithms.md`](../vidbyte-sdk/adding-context-window-algorithms.md) | Adding/changing attached context-window algorithms |
| Context Primitives | [`skills/vidbyte-sdk/context-primitives.md`](../vidbyte-sdk/context-primitives.md) | Context primitives package, `ContextManager`, and context tools |
| Memory Tools | [`skills/vidbyte-sdk/memory-tools.md`](../vidbyte-sdk/memory-tools.md) | Cognee, Letta, Mem0, Supermemory, Zep memory tools |
| Evals | [`skills/vidbyte-sdk/evals.md`](../vidbyte-sdk/evals.md) | Eval suites, graders, and runner |
| Agent Behavior | [`skills/vidbyte-sdk/agent-behavior.md`](../vidbyte-sdk/agent-behavior.md) | Post-run behavior predicates (`agent.behavior`), `RunProbe`, `PredicateGrader` |
| Durable Sessions | [`skills/sessions.md`](../sessions.md) | Session package rules and model-callable session tools |
| Forking | [`skills/forking.md`](../forking.md) | Session fork/resume modes plus `ForkConversationTool` boundaries |
| Artifact Sources | [`skills/sources/SKILL.md`](../sources/SKILL.md) | Source package layout, parser/fetch/cache conventions, and verification |
| Adding Prompts | [`skills/vidbyte-sdk/adding-prompts.md`](../vidbyte-sdk/adding-prompts.md) | How to add prompt JSON assets, enums, and imports |
| Full SDK Reference | [`skills/vidbyte-sdk-doc/SKILL.md`](../vidbyte-sdk-doc/SKILL.md) | Exhaustive reference for all subsystems |

---

## Package Structure

Use this reference when modifying the Vidbyte SDK package structure.

### Current Layout

```text
vidbyte/
|-- __init__.py
|-- client.py
|-- agents/
|   |-- base.py
|   |-- handoff.py            HandoffAgent
|   |-- runtime.py
|   |-- context_algorithms.py runtime dispatcher for context-window algorithms
|   |-- algorithms/           runtime adapters (reflexion, ...)
|   `-- runtimes/             linear, search (MCTS), actor model
|-- context/
|   |-- manager.py
|   |-- presets.py            ContextWindow presets
|   |-- window.py
|   |-- runtime.py            inner-loop context-window lifecycle
|   |-- compaction.py
|   |-- primitives/           context item primitives (package)
|   |-- algorithms/           reflexion, trajectory_checkpoints, grader
|   |-- handoff/              Handoff primitive family
|   |-- handoffs.py           compatibility re-export
|   `-- templates/            context-window templates + recorder
|-- evals/                    eval suites, graders, runner, registry
|-- harnesses/
|   `-- client.py
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- trace/
|   |-- base.py
|   |-- debug.py
|   |-- schema.py
|   |-- profiles.py
|   |-- controller.py
|   |-- session.py
|   |-- components/           semantic span specs for agents/runtimes/context/middleware/tools
|   |-- providers/            semantic-to-provider translators
|   `-- continual/
|-- sources/
|   |-- base.py
|   |-- security.py
|   |-- cache/
|   |-- fetches/
|   |-- loaders/
|   |-- llms_txt/
|   `-- regex/
|-- sessions/
|   |-- session.py
|   |-- store.py
|   |-- portable.py
|   |-- usage.py
|   |-- scope.py
|   `-- stores/
|-- pipelines/
|   |-- __init__.py
|   |-- base.py
|   |-- conditional.py
|   |-- map_reduce.py
|   |-- parallel.py
|   |-- sequential.py
|   `-- types.py
|-- middleware/
|   |-- builtins/
|   `-- compaction/           compaction engine + strategies (re-exported via builtins)
|-- tools/
|   |-- builtins/             code_search, editing, context, context_primitives, fork, handoff, memory, mcp, providers, sessions, ...
|   `-- client.py
|-- shared/
`-- lib/
    |-- dataclasses/
    |-- runners/
    |-- templates/            ContextWindowTemplate subclasses
    |-- tools/
    |-- enums/
    `-- errors/
```

> Note: there is no `vidbyte/strategies/` package. The former "strategy" layer was replaced by **agent runtimes** (`vidbyte/agents/runtimes/`) and **context-window algorithms** (`vidbyte/context/algorithms/`). `StrategyResult` survives only as the internal runtime result dataclass in `vidbyte/lib/dataclasses/strategies.py`.

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep agent actor abstractions in `vidbyte/agents/`.
- Keep agent execution runtimes (linear, MCTS search, actor model) in `vidbyte/agents/runtimes/`. Follow `skills/agent-runtimes/SKILL.md` when adding or modifying runtimes.
- Keep context-window algorithm runtime adapters in `vidbyte/agents/algorithms/` and public config under `vidbyte/context/algorithms/`. Follow `skills/vidbyte-sdk/adding-context-window-algorithms.md`.
- Keep the handoff primitive family under `vidbyte/context/handoff/` and `HandoffAgent` in `vidbyte/agents/handoff.py`. Follow `skills/vidbyte-sdk/handoff.md`.
- Keep eval suites, graders, and the runner under `vidbyte/evals/`. Follow `skills/vidbyte-sdk/evals.md`.
- Keep agent behavior predicates under `vidbyte/evals/behavior/` with one category file per
  behavior group (tool, tool_arguments, stop, handoff) and the `Behavior` facade composing them.
  Follow `skills/vidbyte-sdk/agent-behavior.md` when adding or changing behavior predicates.
- Keep agent-to-agent wiring topologies (pipeline compositions) in `vidbyte/pipelines/`. Pipelines move strings between agents; they do not manage context, budget, or artifacts. Follow `skills/vidbyte-sdk/pipelines.md` when adding or modifying pipeline topology types.
- Keep public context objects in `vidbyte/context/`, but define dataclasses centrally under `vidbyte/lib/dataclasses/`.
- Keep prompt templates in `vidbyte/prompts/prompts/` and expose them through `vidbyte.prompts.Prompts` plus `vidbyte.lib.enums.prompts.Prompt`.
- Follow `skills/vidbyte-sdk/adding-prompts.md` whenever adding or changing prompt assets.
- Keep artifact source loaders under `vidbyte/sources/` and follow `skills/sources/SKILL.md`.
- Keep source dataclasses in `vidbyte/lib/dataclasses/sources.py`, source enums in `vidbyte/lib/enums/sources.py`, and source constants in `vidbyte/lib/config/sources.py`.
- Keep source fetchers under `vidbyte/sources/fetches/`, caches under `vidbyte/sources/cache/`, regex helpers under `vidbyte/sources/regex/`, and concrete source-to-context loaders under `vidbyte/sources/loaders/`.
- Keep the public `Trace` tracer client and helper factories in `vidbyte/trace/base.py`.
- Prefer `Trace.langsmith_default(...)` for user-facing single-agent LangSmith examples; keep it as a facade helper over the existing LangSmith provider adapter.
- Keep concrete debug tracing implementation in `vidbyte/trace/debug.py`.
- Keep semantic tracing schema, profiles, controllers, and session wrappers under `vidbyte/trace/`.
- Keep Vidbyte-owned prebuilt component span specs under `vidbyte/trace/components/`.
- Keep provider translation interfaces under `vidbyte/trace/providers/`; they translate semantic spans to provider fields but do not call external provider SDKs.
- Keep continual tracing presets and future continual trace memory work under `vidbyte/trace/continual/`.
- Keep provider-neutral tracer protocols under `vidbyte/lib/tracing/`.
- Keep external tracing provider adapters under `vidbyte/providers/tracing/`.
- Keep provider-neutral trace payload enrichment such as `llm.call` and `tool.call` input fields in `vidbyte/agents/runtime.py`.
- Keep enum presets under `vidbyte/lib/enums/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK dataclass definitions under `vidbyte/lib/dataclasses/`; package-local type modules should re-export those contracts when stable imports are needed.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep provider-neutral tool formatting helpers under `vidbyte/lib/tools/`.
- Keep middleware runtime policy code under `vidbyte/middleware/`; built-in middleware belongs under `vidbyte/middleware/builtins/`.
- Keep middleware dataclass contracts under `vidbyte/lib/dataclasses/middleware.py`; public middleware modules should re-export stable contracts.
- Keep concrete text/image/video model runners under `vidbyte/lib/runners/`; they are internal or advanced implementation details, not the preferred user-facing docs surface.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Advanced tools are approved under `vidbyte/tools/` when they follow the shared `BaseTool`, `ToolSpec`, `Tools`, and agent-local execution contracts. `ToolRegistry` and `ToolExecutor` are compatibility/lower-level infrastructure, not the preferred public workflow.
- Keep built-in tool categories under `vidbyte/tools/builtins/`; current approved categories are `code_search`, `editing`, `context` (legacy `ContextCompactionTool`), `context_primitives`, `fork`, `handoff`, `memory`, `mcp`, `providers`, `sessions`, `calculator`, `code_execution`, and `document_retrieval`, plus the standalone `reflexion` and `trajectory_checkpoint` context-algorithm tools and `filesystem` via `vidbyte/tools/filesystem/`.
- Context compaction is **middleware**, not a tool. Add compaction behavior under `vidbyte/middleware/compaction/` (re-exported through `vidbyte/middleware/builtins/context_compaction.py`). Follow `skills/vidbyte-sdk/middleware.md`.
- Keep MCP bridge code under `vidbyte/tools/mcp/`.
- Keep permission and sandbox abstractions under `vidbyte/tools/security/`.
- Mutating or executable tools must declare `WRITE` or `EXECUTE` permissions and be guarded by the agent or compatibility executor permission policy.
- Agents select their execution paradigm with `runtime=AgentRuntimeType.<name>`; do not reintroduce single-agent or multi-agent flags.
- Agents package modality routing, model runners, model configuration, runtimes, context-window algorithms, middleware, user-defined role/capability metadata, system prompts, and tools. User-facing examples should pass tools directly into `Agent`/`BaseAgent` with `tools=[...]`.
- User-facing examples should prefer `Agent`/`BaseAgent`, `AgentInput`, `ModelModality`, or `VidbyteSDK().agents` instead of direct `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` construction.
- Base contexts should expose `build_context()` and keep file content, tool calls, model responses, memory, permissions, artifacts, budget, and runtime progress metadata distinct.
- Tools are injected into agents; avoid global mutable tool state for orchestration. Prefer `@tool` and `Tools(...)` for new public examples; keep `@vidbyte_tool`, `ToolRegistry`, and `ToolExecutor` references for compatibility notes only.
- Middleware is injected into agents with `middleware=[...]`; it is deterministic runtime policy code and must not be model-visible or included in tool specs/cards.
- Custom middleware should subclass `AgentMiddleware` and override only needed lifecycle hooks. Middleware should return `MiddlewareDecision` values instead of mutating runtime state directly.
- Concrete `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` classes are internal/advanced implementation details in user-facing docs. Prefer `Agent`/`BaseAgent` or harness composition in examples.
- Do not add provider network calls, remote protocol transports, or private Vidbyte service logic without a separate approved design.
- Keep the durable-sessions primitive self-contained under `vidbyte/sessions/`: the `Session` facade, `SessionStore` protocol + `BaseSessionStore`, `SessionScope`, serialization, trace capture, local stores (`vidbyte/sessions/stores/`), session errors (in `vidbyte/sessions/errors.py`), and compatibility exports from `vidbyte/sessions/contracts.py`. Define session dataclasses and enums centrally in `vidbyte/lib/dataclasses/sessions.py` (`RunState`, `Checkpoint`, `SessionMeta`, `CheckpointPolicy`, `SessionStatus`, `TraceCapture`, `SESSION_SCHEMA_VERSION`) so they follow the SDK dataclass placement rule. Expose the namespace via `sdk.harnesses.sessions`.
- Keep database-backed session stores under `vidbyte/lib/providers/`; they must subclass `ProviderSessionStore`, and import their driver lazily and raise `ConfigurationError` when the driver is absent so the SDK core stays import-safe — except `SqliteSessionStore`, which uses the stdlib `sqlite3` module and has no optional driver.
- Ship prebuilt agent-facing session tools under `vidbyte/tools/builtins/sessions/`: `CheckpointTool`, `ForkTool`, `BatchForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool`, and the central `SessionTool`. They reuse `Session` + `SessionStore` + `SessionScope` and bind to a `Session` via `bind_session()`; `Session._bind_session_tools()` wires them up automatically.
- `Session.batch_fork(...)` and `BatchForkTool` create durable child records only; running or comparing those children remains explicit caller work. `BatchForkTool` accepts 1-64 branches and returns compact created/failed results.
- Sessions support tags/name lookup (`Session.tag`, `SessionStore.resolve`, `list_sessions` filters), usage rollups (`Session.usage(prices=...)`), and portable export/import (`Session.export`, `sdk.harnesses.sessions.export/import_`). Preserve checkpoint ids and lineage when importing unless `new_id=` intentionally rewrites only session ids.
- Sessions persist raw agent history as source of truth and re-supply non-serializable parts (tools, runner, middleware) at `resume`/`fork`. Never persist secrets, and never use the trace artifact as a `resume` input.
- `ForkConversationTool` lives under `vidbyte/tools/builtins/fork/` and is agent-native, not a durable-session tool. It calls `BaseAgent.fork(...)`, runs the child immediately, and must preserve non-escalation rules: provider/model changes are allowlisted, extra tools come from developer-configured toolsets, permission policy is inherited, and child state is isolated unless returned to the parent.
- Tool-error retry/abort policy belongs in `AgentLoopSettings(tool_error_policy=ToolErrorPolicy(...))`, which auto-registers `ToolErrorPolicyMiddleware` on compatible linear agents. Terminal tool errors are rendered with full detail; do not document `ErrorVerbosity` or render-options APIs.
- Keep generated repository navigation artifacts such as `artifacts/file_index.md` current when major files move or new subsystems land; mention them in central docs because agents use them as quick source maps.

## Semantic Trace Components

`vidbyte/trace/components/` holds Vidbyte-owned span-spec factories. These files define stable SDK semantic spans and payload contracts; provider-specific translation stays in `vidbyte/trace/providers/`.

- `agents.py`: `agent.run`, `agent.stop`, aggregate agent, proposer, synthesis, and failure span specs.
- `runtimes.py`: linear runtime iteration plus actor and search runtime span specs.
- `context.py`: context-window build, context primitive render summary, compaction, and update span specs.
- `algorithms.py`: context-window algorithm spans such as reflexion, multi-provider grading, trajectory checkpoints, problem-space search, and error correction.
- `middleware.py`: middleware hook and decision spans, including retry, abort, deny-tool, sleep, and fail-open/fail-closed decisions.
- `tools.py`: tool-call, permission, argument, result, and error span specs.
- `parsers.py`: tool-call parsing and structured-output validation span specs.

When adding or changing an agent runtime, context-window algorithm, middleware class, tool surface, parser, or aggregate-agent behavior, check whether `vidbyte/trace/components/` needs a new or updated span spec in the same change. Update README or `llms.txt` examples when public tracing behavior changes.

## Update Skill Files

When you modify the repo, follow `skills/sdk/update-skill-files.md` to know which skill files must be updated and what to include in each update.


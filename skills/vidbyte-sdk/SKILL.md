<!--
Context Protocol Header

Description:
    Master directory rule file and layout reference for the Vidbyte SDK skills.
Purpose:
    Ensures that codebase modifications preserve the package structure,
    design patterns, client interfaces, context manager policies, tool schemas,
    and runtime systems.
Architecture:
    - Lists complete directory structure map.
    - Specifies architectural rules for packages: agents, pipelines, prompts,
      context, tools, and middleware.
    - References sub-skills: pipelines.md, handoff.md, adding-prompts.md,
      adding-context-window-algorithms.md, and middleware.md.
Relations:
    Root of skills/vidbyte-sdk/. Guides all other sdk skill instructions.
-->

# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- agents/
|-- context/
|   |-- manager.py
|   |-- primitives.py
|   |-- presets.py
|   |-- algorithms/
|   `-- window.py
|-- harnesses/
|   `-- client.py
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- sources/
|   |-- base.py
|   |-- cache/
|   |-- fetches/
|   |-- loaders/
|   |-- llms_txt/
|   `-- regex/
|-- trace/
|   |-- base.py
|   |-- debug.py
|   |-- schema.py
|   |-- profiles.py
|   |-- controller.py
|   |-- session.py
|   |-- components/
|   |-- providers/
|   `-- continual/
|-- pipelines/
|   |-- base.py
|   |-- conditional.py
|   |-- parallel.py
|   |-- sequential.py
|   `-- types.py
|-- middleware/
|   `-- builtins/
|-- strategies/
|   `-- multi_agent/
|-- tools/
|   `-- client.py
|-- shared/
| `-- lib/
    |-- dataclasses/
    |-- runners/
    |-- tools/
    |-- enums/
    `-- errors/
```

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep agent actor abstractions in `vidbyte/agents/`.
- Keep the handoff primitive family under `vidbyte/context/handoff/` with one prebuilt class per file, keep `vidbyte/context/handoffs.py` as a compatibility re-export, and keep the `HandoffAgent` in `vidbyte/agents/handoff.py`; do not create a top-level handoff subsystem. Follow `skills/vidbyte-sdk/handoff.md` when adding handoff variants or changing handoff behavior.
- Keep reasoning and orchestration topologies in `vidbyte/strategies/`.
- Keep multi-agent orchestration implementations in `vidbyte/strategies/multi_agent/`.
- Keep agent-to-agent wiring topologies (pipeline compositions) in `vidbyte/pipelines/`. Pipelines move strings between agents; they do not manage context, budget, or artifacts. Follow `skills/vidbyte-sdk/pipelines.md` when adding new pipeline topology types.
- Keep public context objects in `vidbyte/context/`, but define shared infrastructure dataclasses centrally under `vidbyte/lib/dataclasses/`.
- Keep standardized context item primitives under `vidbyte/context/primitives.py` and expose the central `ContextManager` from `vidbyte/context/manager.py`.
- Keep context-window presets in `vidbyte/context/presets.py` and algorithm implementations under `vidbyte/context/algorithms/`.
- Follow `skills/vidbyte-sdk/adding-context-window-algorithms.md` when adding or changing attached context-window algorithms.
- Keep prompt templates in `vidbyte/prompts/prompts/` and expose them through `vidbyte.prompts.Prompts` plus `vidbyte.lib.enums.prompts.Prompt`; follow the JSON-descriptor-plus-Markdown format in `skills/vidbyte-sdk/adding-prompts.md` for new large prompt assets.
- Follow `skills/vidbyte-sdk/adding-prompts.md` whenever adding or changing prompt assets.
- Keep artifact source loaders under `vidbyte/sources/` and follow `skills/sources/SKILL.md`; source dataclasses belong in `vidbyte/lib/dataclasses/sources.py`, enums in `vidbyte/lib/enums/sources.py`, and constants in `vidbyte/lib/config/sources.py`.
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
- Follow `skills/vidbyte-sdk/middleware.md` when configuring, using, or implementing agent runtime middleware.
- Keep the continual trace agent under `vidbyte/trace/continual/` (`agent.py`, `tools.py`, `middleware.py`, `prebuilt.py`) and its config contracts in `vidbyte/lib/dataclasses/trace.py`; the `trace_option=` agent path is separate from the `trace=`/`tracer=` observability tracers. Follow `skills/vidbyte-sdk/continual-tracing.md` when changing continual tracing behavior.
- Keep concrete text/image/video model runners under `vidbyte/lib/runners/`; they are internal or advanced implementation details, not the preferred user-facing docs surface.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Advanced tools are approved under `vidbyte/tools/` when they follow the shared `BaseTool`, `ToolSpec`, `Tools`, and agent-local execution contracts. `ToolRegistry` and `ToolExecutor` are compatibility/lower-level strategy infrastructure, not the preferred public workflow.
- Keep built-in tool categories under `vidbyte/tools/builtins/`; current approved categories are `code_search`, `editing`, and `context`.
- Keep MCP bridge code under `vidbyte/tools/mcp/`.
- Keep permission and sandbox abstractions under `vidbyte/tools/security/`.
- Mutating or executable tools must declare `WRITE` or `EXECUTE` permissions and be guarded by the agent or compatibility executor permission policy.
- Harnesses should compose strategies through `with_strategy()` and `with_strategies()` rather than exposing single-agent or multi-agent flags.
- Agents package modality routing, model runners, model configuration, user-defined role/capability metadata, system prompts, and tools. User-facing examples should pass tools directly into `Agent`/`BaseAgent` with `tools=[...]`.
- User-facing examples should prefer `Agent`/`BaseAgent`, `AgentInput`, `ModelModality`, `VidbyteSDK().agents`, or harness composition instead of direct `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` construction.
- Base contexts should expose `build_context()` and keep file content, context items, tool calls, model responses, memory, permissions, artifacts, budget, and strategy progress metadata distinct.
- Context items store structured meaning; `ContextManager` owns collection and compatibility conversion into existing context dataclasses. Agent-level context-window algorithms are selected with `algorithm=ContextWindow.preset.<name>` and should remain coarse SDK presets, not low-level custom compiler APIs.
- Agents may accept default `context_items` or a `context_manager`; per-call context belongs on `AgentInput`. Call-level context must not mutate agent defaults.
- Tools are injected into agents or strategies; avoid global mutable tool state for orchestration. Prefer `@tool` and `Tools(...)` for new public examples; keep `@vidbyte_tool`, `ToolRegistry`, and `ToolExecutor` references for compatibility notes only.
- Middleware is injected into direct text agents with `middleware=[...]`; it is deterministic runtime policy code and must not be model-visible or included in tool specs/cards.
- Custom middleware should subclass `AgentMiddleware` and override only needed lifecycle hooks. Middleware should return `MiddlewareDecision` values instead of mutating runtime state directly.
- Concrete `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` classes are internal/advanced implementation details in user-facing docs. Prefer `Agent`/`BaseAgent` or harness composition in examples.
- Do not add provider network calls, remote protocol transports, or private Vidbyte service logic without a separate approved design.
- Keep agent behavior predicates under `vidbyte/evals/behavior/` with one category file per
  behavior group and the `Behavior` facade composing them. Follow `skills/vidbyte-sdk/agent-behavior.md`.

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

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
      adding-context-window-algorithms.md, middleware.md, context-primitives.md,
      memory-tools.md, and evals.md.
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
|   |-- base.py
|   |-- handoff.py
|   |-- runtime.py
|   |-- context_algorithms.py
|   |-- algorithms/        runtime adapters for context-window algorithms
|   `-- runtimes/          linear, search (MCTS), actor model
|-- context/
|   |-- manager.py
|   |-- primitives/        context item primitives (package)
|   |-- presets.py
|   |-- runtime.py         inner-loop context-window lifecycle
|   |-- compaction.py
|   |-- algorithms/
|   |-- handoff/           Handoff primitive family
|   |-- handoffs.py        compatibility re-export
|   |-- templates/         context-window templates + recorder
|   `-- window.py
|-- evals/                 eval suites, graders, runner, registry
|-- harnesses/
|   `-- client.py
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- trace/
|   |-- base.py
|   |-- debug.py
|   `-- continual/
|-- pipelines/
|   |-- base.py
|   |-- conditional.py
|   |-- map_reduce.py
|   |-- parallel.py
|   |-- sequential.py
|   `-- types.py
|-- middleware/
|   |-- builtins/
|   `-- compaction/        compaction engine + strategies
|-- tools/
|   `-- client.py
|-- shared/
| `-- lib/
    |-- dataclasses/
    |-- runners/
    |-- templates/
    |-- tools/
    |-- enums/
    `-- errors/
```

> There is no `vidbyte/strategies/` package. Execution paradigms live in `vidbyte/agents/runtimes/` (runtimes) and `vidbyte/context/algorithms/` (context-window algorithms).

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep agent actor abstractions in `vidbyte/agents/`.
- Keep the handoff primitive family under `vidbyte/context/handoff/` with one prebuilt class per file, keep `vidbyte/context/handoffs.py` as a compatibility re-export, and keep the `HandoffAgent` in `vidbyte/agents/handoff.py`; do not create a top-level handoff subsystem. Follow `skills/vidbyte-sdk/handoff.md` when adding handoff variants or changing handoff behavior.
- Keep agent execution runtimes (linear, MCTS search, actor model) under `vidbyte/agents/runtimes/`. Follow `skills/agent-runtimes/SKILL.md`.
- Keep context-window algorithm runtime adapters under `vidbyte/agents/algorithms/` and public config under `vidbyte/context/algorithms/`. Follow `skills/vidbyte-sdk/adding-context-window-algorithms.md`.
- Keep eval suites, graders, and the runner under `vidbyte/evals/`. Follow `skills/vidbyte-sdk/evals.md`.
- Keep agent-to-agent wiring topologies (pipeline compositions) in `vidbyte/pipelines/`. Pipelines move strings between agents; they do not manage context, budget, or artifacts. Follow `skills/vidbyte-sdk/pipelines.md` when adding new pipeline topology types.
- Keep public context objects in `vidbyte/context/`, but define shared infrastructure dataclasses centrally under `vidbyte/lib/dataclasses/`.
- Keep standardized context item primitives under the `vidbyte/context/primitives/` package (one module per primitive group, exported from `vidbyte/context/primitives/__init__.py`) and expose the central `ContextManager` from `vidbyte/context/manager.py`. Follow `skills/vidbyte-sdk/context-primitives.md`.
- Keep context-window presets in `vidbyte/context/presets.py` and algorithm implementations under `vidbyte/context/algorithms/`.
- Follow `skills/vidbyte-sdk/adding-context-window-algorithms.md` when adding or changing attached context-window algorithms.
- Keep prompt templates in `vidbyte/prompts/prompts/` and expose them through `vidbyte.prompts.Prompts` plus `vidbyte.lib.enums.prompts.Prompt`; follow the JSON-descriptor-plus-Markdown format in `skills/vidbyte-sdk/adding-prompts.md` for new large prompt assets.
- Follow `skills/vidbyte-sdk/adding-prompts.md` whenever adding or changing prompt assets.
- Keep the public `Trace` tracer client and helper factories in `vidbyte/trace/base.py`.
- Keep concrete debug tracing implementation in `vidbyte/trace/debug.py`.
- Keep continual tracing presets and future continual trace memory work under `vidbyte/trace/continual/`.
- Keep provider-neutral tracer protocols under `vidbyte/lib/tracing/`.
- Keep external tracing provider adapters under `vidbyte/providers/tracing/`.
- Keep enum presets under `vidbyte/lib/enums/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK dataclass definitions under `vidbyte/lib/dataclasses/`; package-local type modules should re-export those contracts when stable imports are needed.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep provider-neutral tool formatting helpers under `vidbyte/lib/tools/`.
- Keep middleware runtime policy code under `vidbyte/middleware/`; built-in middleware belongs under `vidbyte/middleware/builtins/`.
- Keep middleware dataclass contracts under `vidbyte/lib/dataclasses/middleware.py`; public middleware modules should re-export stable contracts.
- Follow `skills/vidbyte-sdk/middleware.md` when configuring, using, or implementing agent runtime middleware.
- Keep concrete text/image/video model runners under `vidbyte/lib/runners/`; they are internal or advanced implementation details, not the preferred user-facing docs surface.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Advanced tools are approved under `vidbyte/tools/` when they follow the shared `BaseTool`, `ToolSpec`, `Tools`, and agent-local execution contracts. `ToolRegistry` and `ToolExecutor` are compatibility/lower-level infrastructure, not the preferred public workflow.
- Keep built-in tool categories under `vidbyte/tools/builtins/`; current approved categories are `code_search`, `editing`, `context` (legacy `ContextCompactionTool`), `context_primitives`, `memory`, `mcp`, `calculator`, `code_execution`, and `document_retrieval`, plus the standalone `reflexion` and `trajectory_checkpoint` tools. Context compaction is middleware (`vidbyte/middleware/compaction/`), not a tool.
- Keep MCP bridge code under `vidbyte/tools/mcp/`.
- Keep permission and sandbox abstractions under `vidbyte/tools/security/`.
- Mutating or executable tools must declare `WRITE` or `EXECUTE` permissions and be guarded by the agent or compatibility executor permission policy.
- Agents select their execution paradigm with `runtime=AgentRuntimeType.<name>`; do not reintroduce single-agent or multi-agent flags.
- Agents package modality routing, model runners, model configuration, user-defined role/capability metadata, system prompts, and tools. User-facing examples should pass tools directly into `Agent`/`BaseAgent` with `tools=[...]`.
- User-facing examples should prefer `Agent`/`BaseAgent`, `AgentInput`, `ModelModality`, `VidbyteSDK().agents`, or harness composition instead of direct `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` construction.
- Base contexts should expose `build_context()` and keep file content, context items, tool calls, model responses, memory, permissions, artifacts, budget, and runtime progress metadata distinct.
- Context items store structured meaning; `ContextManager` owns collection and compatibility conversion into existing context dataclasses. Agent-level context-window algorithms are selected with `algorithm=ContextWindow.preset.<name>` and should remain coarse SDK presets, not low-level custom compiler APIs.
- Agents may accept default `context_items` or a `context_manager`; per-call context belongs on `AgentInput`. Call-level context must not mutate agent defaults.
- Tools are injected into agents; avoid global mutable tool state for orchestration. Prefer `@tool` and `Tools(...)` for new public examples; keep `@vidbyte_tool`, `ToolRegistry`, and `ToolExecutor` references for compatibility notes only.
- Middleware is injected into direct text agents with `middleware=[...]`; it is deterministic runtime policy code and must not be model-visible or included in tool specs/cards.
- Custom middleware should subclass `AgentMiddleware` and override only needed lifecycle hooks. Middleware should return `MiddlewareDecision` values instead of mutating runtime state directly.
- Concrete `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` classes are internal/advanced implementation details in user-facing docs. Prefer `Agent`/`BaseAgent` or harness composition in examples.
- Do not add provider network calls, remote protocol transports, or private Vidbyte service logic without a separate approved design.

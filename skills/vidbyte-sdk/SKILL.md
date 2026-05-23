# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- agents/
|-- context/
|-- harnesses/
|   `-- client.py
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- strategies/
|   `-- multi_agent/
|-- tools/
|   `-- client.py
|-- shared/
`-- lib/
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
- Keep reasoning and orchestration topologies in `vidbyte/strategies/`.
- Keep multi-agent orchestration implementations in `vidbyte/strategies/multi_agent/`.
- Keep public context objects in `vidbyte/context/`, but define dataclasses centrally under `vidbyte/lib/dataclasses/`.
- Keep prompt templates in `vidbyte/prompts/prompts/` and register reusable prompts in the prompt registry.
- Keep enum presets under `vidbyte/lib/enums/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK dataclass definitions under `vidbyte/lib/dataclasses/`; package-local type modules should re-export those contracts when stable imports are needed.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep provider-neutral tool formatting helpers under `vidbyte/lib/tools/`.
- Keep concrete text/image/video model runners under `vidbyte/lib/runners/`; they are internal or advanced implementation details, not the preferred user-facing docs surface.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Advanced tools are approved under `vidbyte/tools/` when they follow the shared `BaseTool`, `ToolSpec`, `ToolRegistry`, and `ToolExecutor` contracts.
- Keep built-in tool categories under `vidbyte/tools/builtins/`; current approved categories are `code_search`, `editing`, and `context`.
- Keep MCP bridge code under `vidbyte/tools/mcp/`.
- Keep permission and sandbox abstractions under `vidbyte/tools/security/`.
- Mutating or executable tools must declare `WRITE` or `EXECUTE` permissions and be guarded by the executor permission policy.
- Harnesses should compose strategies through `with_strategy()` and `with_strategies()` rather than exposing single-agent or multi-agent flags.
- Agents package modality routing, model configuration, strategies, user-defined role/capability metadata, system prompts, and tools.
- User-facing examples should prefer `BaseAgent`, `AgentInput`, `ModelModality`, `VidbyteSDK().agents`, or harness composition instead of direct `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` construction.
- Base contexts should expose `build_context()` and keep file content, tool calls, model responses, memory, permissions, artifacts, budget, and strategy progress metadata distinct.
- Tools are injected into agents or strategies; avoid global mutable tool state for orchestration.
- Do not add provider network calls, remote protocol transports, or private Vidbyte service logic without a separate approved design.

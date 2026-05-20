# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- agents/
|-- harnesses/
|   `-- client.py
|-- providers/
|   `-- client.py
|-- strategies/
|   `-- multi_agent/
|-- tools/
|   `-- client.py
|-- shared/
`-- lib/
    `-- errors/
```

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep agent actor abstractions in `vidbyte/agents/`.
- Keep reasoning and orchestration topologies in `vidbyte/strategies/`.
- Keep multi-agent orchestration implementations in `vidbyte/strategies/multi_agent/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Harnesses should compose strategies through `with_strategy()` and `with_strategies()` rather than exposing single-agent or multi-agent flags.
- Agents package model runners, strategies, role/capability metadata, and tools.
- Tools are injected into agents or strategies; avoid global mutable tool state for orchestration.
- Do not add provider network calls, remote protocol transports, or private Vidbyte service logic without a separate approved design.

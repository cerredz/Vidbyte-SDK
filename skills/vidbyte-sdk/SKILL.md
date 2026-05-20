# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- harnesses/
|   `-- client.py
|-- providers/
|   `-- client.py
|-- tools/
|   `-- client.py
|-- shared/
`-- lib/
    `-- errors/
```

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Custom function tools are approved under `vidbyte/tools/`:
  - Use `vidbyte.tools.decorators.vidbyte_tool` for the public decorator.
  - Use `vidbyte.tools.function_tool.FunctionTool` to adapt Python callables to `BaseTool`.
  - Use `ToolRegistry` and `ToolMixin.with_tools()` as the attachment boundary for clients, harnesses, and strategies.
- Keep provider-specific tool schema translation behind provider modules; local execution stays in `ToolExecutor`.

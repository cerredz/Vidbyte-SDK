# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- harnesses/
|   |-- client.py
|   `-- time/
|-- providers/
|   `-- client.py
|-- tools/
|   |-- builtins/
|   `-- client.py
|-- shared/
`-- lib/
    `-- errors/
```

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Time-based harnesses are approved under `vidbyte/harnesses/time/`.
- The minimum-time harness requires date and compaction tool contracts under `vidbyte/tools/builtins/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Do not add additional concrete harness, tool, provider, or error implementations until their structure is approved.

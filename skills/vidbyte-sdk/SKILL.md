# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- harnesses/
|   |-- client.py
|   |-- context_remover/
|   `-- red_team/
|-- prompts/
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
- Concrete harness implementations are approved under `vidbyte/harnesses/red_team/` and `vidbyte/harnesses/context_remover/`.
- Shared ledger, context view, artifact, and model-call contracts for harnesses belong in `vidbyte/shared/`.
- Harness-specific errors belong in `vidbyte/lib/errors/` and should be safe to print by default.
- Prompt templates for harnesses may live under `vidbyte/prompts/translations/harnesses/`.
- Do not add additional concrete harness, tool, provider, or error implementations until their structure is approved.

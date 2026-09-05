---
name: runtime-primitives
description: Guides development of Vidbyte runtime primitives and native Codex or Claude harness agents, including provider control boundaries, translation choices, and safe local composition. Use when creating, extending, or reviewing a HarnessAgent adapter or a runtime primitive that executes through an installed coding-agent SDK.
---

# Runtime Primitives

Use native harness agents when Vidbyte needs to compose an orchestration algorithm around an existing coding-agent loop. Do not model Codex or Claude as a single model call: each provider owns a full loop with tools, context management, permissions, sessions, and provider-specific events.

A **runtime primitive** is a reusable Vidbyte algorithm for arranging work, not a model or a provider. Examples include “send one task to three independent coding agents and select the best result,” “have a reviewer challenge an implementation,” and “fork a proven session before trying two fixes.” The primitive owns the graph—roles, inputs, branches, acceptance rules, aggregation, and normalized output. A harness agent owns the translation into one installed provider SDK and lets that native harness keep control of its internal model/tool loop.

Developers receive primitives as typed SDK objects with declared capability requirements. An application chooses a primitive, supplies one or more configured harness agents, and runs the primitive through Vidbyte. Before launch, the primitive asks each harness agent whether it can provide the required controls. Exact native controls are passed through; policy mappings are named and documented; boundary emulations are visible; unsupported requirements fail before the provider process starts.

```text
application configuration
  -> Vidbyte runtime primitive (topology and acceptance contract)
  -> HarnessAgent capability check and typed request
  -> provider translator (Vidbyte concepts -> provider settings/input)
  -> native Codex or Claude SDK loop
  -> typed provider result -> normalized Vidbyte result
```

Build primitives in three layers: a provider-neutral contract, an orchestration implementation that depends only on that contract, and provider adapters that publish capabilities. Offer them first as Python SDK objects, then as registered/YAML-addressable primitives once their configuration is stable. Never hide a fallback: if Codex cannot enforce a turn bound that Claude can, the primitive must reject Codex or select an explicitly documented alternative policy.

## Required reading

1. Read [references/runtime-primitives.md](references/runtime-primitives.md) for ownership and intended use.
2. Read the provider reference being implemented:
   - [references/codex-sdk.md](references/codex-sdk.md)
   - [references/claude-agent-sdk.md](references/claude-agent-sdk.md)
3. Read [references/control-matrix.md](references/control-matrix.md) before claiming parity or selecting a fallback.

## Implementation rules

- Keep the main agent a small facade; isolate configuration, input/context translation, transport, events/results, and provider errors.
- Classify every Vidbyte abstraction as exact, policy-based, emulated, or unsupported before writing code.
- Prefer the provider's native lifecycle operation for sessions, forks, subagents, tools, and interruption.
- Reject unsupported public options. Silent omission creates a false contract.
- Normalize only observable output and metadata. Never expose hidden reasoning, credentials, or raw environment values.
- Preserve cancellation and close provider clients/processes deterministically.
- Pin pre-1.0 SDK integrations to a reviewed compatibility range and recheck official documentation on upgrade.

## Stop conditions

Stop and revise the design when a requested feature would require nesting the provider loop inside Vidbyte's model loop, weakening provider permissions, manufacturing session lineage locally, or claiming control over behavior the provider SDK does not expose.

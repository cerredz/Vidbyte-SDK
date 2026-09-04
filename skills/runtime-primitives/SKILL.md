---
name: runtime-primitives
description: Guides development of Vidbyte runtime primitives and native Codex or Claude harness agents, including provider control boundaries, translation choices, and safe local composition. Use when creating, extending, or reviewing a HarnessAgent adapter or a runtime primitive that executes through an installed coding-agent SDK.
---

# Runtime Primitives

Use native harness agents when Vidbyte needs to compose an orchestration algorithm around an existing coding-agent loop. Do not model Codex or Claude as a single model call: each provider owns a full loop with tools, context management, permissions, sessions, and provider-specific events.

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

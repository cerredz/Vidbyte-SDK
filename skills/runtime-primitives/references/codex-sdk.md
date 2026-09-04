# Codex SDK Control Inventory

## Surface

The stable Python `openai-codex` package controls the local Codex app-server. Treat the Python API as the adapter boundary and the app-server protocol as the deeper capability reference. `CodexHarnessAgent` currently maps system prompt, additional context, structured output, provider-native forks, and Codex-owned subagents.

## Controls available to the adapter

- Client/process: app-server configuration, working directory, lifecycle, cancellation, and connection errors.
- Thread lifecycle: start, resume, fork, archive/read operations exposed by the installed SDK version, and ephemeral persistence policy.
- Turn lifecycle: prompt input, full-turn execution, output JSON Schema, cancellation/interruption where exposed, and returned item stream/result.
- Model behavior: model, reasoning effort, reasoning summary, personality, service tier, and provider configuration supported by the SDK.
- Instructions/context: developer instructions on thread operations; additional Vidbyte context can be rendered into bounded turn input when no dedicated stable field exists.
- Security: approval mode, sandbox mode, working directory, and configuration-layer overrides. The app-server still enforces policy.
- Multi-agent: enablement, maximum concurrent session threads, default subagent model/effort, interruption messages, project/user custom-agent definitions, and observable collaboration items.
- Extensions: configured MCP servers, skills, hooks, rules, AGENTS.md hierarchy, and other Codex config keys when intentionally admitted by the adapter.
- Observability: thread/turn identifiers, statuses, item events, token usage, duration, diffs/tool activity exposed in typed events, and safe error categories.

## Controls not owned by Vidbyte

- The exact number and ordering of internal model/tool iterations unless Codex exposes a supported limit.
- Hidden reasoning text or undocumented internal state.
- Built-in tool implementation details, compaction heuristics, model routing, availability, or provider-side safety enforcement.
- Whether the model chooses to delegate, which subagent it selects, or the subagent's internal strategy.
- Account entitlement, authentication policy, server-side rate limits, or subscription usage.
- Exact equivalence between Codex hooks/config and Vidbyte middleware. These require per-hook policy mappings.

## Translation guidance

Use native thread fork for lineage, never a new unrelated thread with copied text. Pass JSON Schema through the turn and validate locally after return. Represent Codex subagents as provider activity unless a future SDK exposes stable child handles sufficient for full Vidbyte agents. Put provider-only knobs in `CodexAgentSettings`; do not leak them into the shared abstraction unless another provider can state meaningful semantics.

Official starting points: [Codex SDK](https://developers.openai.com/codex/sdk), [App Server](https://developers.openai.com/codex/app-server), [configuration reference](https://developers.openai.com/codex/config-reference), and [subagents](https://developers.openai.com/codex/subagents).

# Runtime Primitives and Harness Agents

## Product model

A runtime primitive is a Vidbyte-owned orchestration algorithm—adversarial review, debate, fan-out/fan-in, search, or another repeatable coordination pattern—executed by one or more native coding-agent harnesses. A harness agent is the provider adapter that lets the primitive address Codex or Claude through Vidbyte-shaped inputs and results.

```text
Vidbyte runtime primitive
  -> provider-neutral task, topology, budget, and result contract
  -> CodexHarnessAgent / future ClaudeHarnessAgent
  -> native SDK session and provider-owned agent loop
  -> local tools, repository instructions, permissions, and subscription
```

Vidbyte owns composition: roles, task graph, fan-out/fan-in, cross-agent messages, aggregate acceptance criteria, admission, and normalized results. The provider owns its internal reasoning/tool loop, context compaction, built-in tool implementations, model availability, and enforcement of sandbox and permission policy.

## Why use this architecture

- The user's installed agent already understands the repository, tools, MCP servers, skills, and authentication.
- Vidbyte can reuse native session and subagent behavior instead of recreating a coding environment.
- Provider-specific strengths remain available; the adapter does not force every host into a lowest-common-denominator loop.
- The control boundary is honest: Vidbyte configures exposed knobs and observes exposed events, but does not pretend to own hidden provider behavior.

## Translation levels

- **Exact:** one Vidbyte concept maps directly to a documented provider field or lifecycle operation.
- **Policy-based:** the provider supports the outcome through a different set of knobs; the adapter needs a documented rule.
- **Emulated:** Vidbyte must add behavior around the provider boundary. Mark this clearly because semantics may differ.
- **Unsupported:** no reliable public surface exists. Reject the option or require a different provider.

## Adapter decomposition

- Main facade: public state, run/fork entry points, and collaborator composition.
- Configuration translator: validates public settings and emits provider types.
- Context translator: renders shared context without mutating source objects.
- Transport: owns lazy SDK import, connection/process lifecycle, session/thread operations, and cancellation.
- Event/result translator: converts provider events into bounded Vidbyte messages, usage, lineage, and structured data.
- Capability declaration: publishes exact and unavailable features so primitives can check requirements before launch.

## Safety boundary

Runtime primitives execute locally in the chosen host. Do not upload repository contents, process environments, host credentials, or private transcripts for admission. Pass only the task and safe execution metadata required by the primitive. Let the host enforce its own sandbox and approval rules; a Vidbyte policy may narrow those rules but must never silently widen them.

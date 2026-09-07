---
name: claude-agent-sdk-translation
description: Plan, audit, or implement Vidbyte support for the open-source Claude Agent SDK, including capability mapping, provider-owned loop boundaries, sessions, tools, hooks, permissions, subagents, streaming, and observability.
metadata:
  short-description: Translate Claude Agent SDK capabilities into Vidbyte
---

# Claude Agent SDK Translation Skill

Use this skill when planning, reviewing, or implementing Claude Agent SDK support in
`vidbyte-sdk`. The deliverable is a Vidbyte-shaped facade over Anthropic's
provider-owned agent loop. It is not a second Claude Code product, a replacement for
`BaseAgent`, or permission to implement a runtime when the request only asks for a
design or inventory.

## Scope and naming

- Target the open-source Python Claude Agent SDK first. Keep TypeScript parity in
  the capability model, but do not invent Python APIs that are only present in the
  TypeScript SDK.
- Use **Claude Agent SDK**, **Claude Agent**, or **Claude** in product-facing names.
  Do not call the integration "Claude Code" or "Claude Code Agent"; Anthropic's
  branding guidance explicitly disallows those names.
- Treat the SDK as a provider integration governed by Anthropic's commercial terms.
  Use API-key authentication unless Anthropic has explicitly approved another
  authentication arrangement. Never expose or persist credentials in Vidbyte
  configuration, sessions, traces, or skill files.
- Keep the provider adapter separate from the outer `vidbyte.harnesses.Harness`
  execution envelope. A Claude-backed agent can be captured by a Harness, but the
  Harness must not absorb Claude's loop or pretend to own Claude's session state.

## How to use this skill

1. Read the authoritative Claude documentation and the pinned SDK source before
   coding. The public API changes independently of Vidbyte's release cadence.
2. Read the current Vidbyte anchors listed below and the detailed matrix in
   [references/feature-matrix.md](references/feature-matrix.md).
3. Classify every requested behavior as `native`, `translated`, `supervised`,
   `observe_only`, `emulated`, or `unsupported` before choosing an API shape.
4. Write or update a design document and capability contract before adding runtime
   code. If the user asks for an inventory or skill only, stop after the documents.
5. During implementation, translate Vidbyte's semantic contracts first and serialize
   them into Claude SDK arguments second. Do not flatten Vidbyte settings directly
   into an untyped provider dictionary.

## Capability dispositions

- **native** - Claude exposes the behavior directly and the adapter can preserve its
  semantics (for example `max_turns`, `max_budget_usd`, `output_format`, or MCP).
- **translated** - Vidbyte offers a provider-neutral contract and Claude provides a
  close provider-specific equivalent; document any loss of precision (for example
  `max_iterations` to `max_turns`).
- **supervised** - Claude owns the behavior internally; Vidbyte can set a bound,
  receive events, or stop the run but cannot interpose its own algorithm at every
  internal step.
- **observe_only** - expose telemetry or metadata without claiming that Vidbyte can
  alter the provider behavior (for example token-level subagent streaming).
- **emulated** - compose public Claude operations outside the provider loop to offer
  a Vidbyte feature; label it as a composition, not native Claude semantics.
- **unsupported** - reject explicitly or omit through capability negotiation. Never
  silently accept a setting whose guarantee cannot be made.

## Vidbyte architecture anchors

Read these current contracts before making a translation decision:

- `vidbyte/agents/base.py` - public agent facade, runner selection, history,
  fallback, output schema, context, tracing, and queueing.
- `vidbyte/agents/settings/loop.py` and `vidbyte/agents/settings/tool.py` - loop,
  tool, retry, parallelism, compaction, and output-contract policy.
- `vidbyte/middleware/base.py` - deterministic Vidbyte lifecycle hooks; these are
  not equivalent to Claude hooks and must not be represented as if they were.
- `vidbyte/context/manager.py` and `vidbyte/context/` - structured context and
  Vidbyte-owned compaction algorithms.
- `vidbyte/sessions/session.py` and `vidbyte/sessions/stores/` - checkpoint-DAG
  sessions, resume, fork, rewind, tags, export/import, and usage rollups.
- `vidbyte/harnesses/execution.py` - outer run identity, capture, redaction,
  consent, and trajectory export.
- `vidbyte/tools/`, `vidbyte/tools/mcp/`, and `vidbyte/tools/security/` - tool
  contracts, MCP bridges, and permission policy.
- `vidbyte/trace/`, `vidbyte/agents/pricing/`, and `vidbyte/agents/speed/` - typed
  tracing, usage/cost, and latency surfaces.
- `skills/sdk/SKILL.md`, `skills/harnesses/SKILL.md`, and the Vidbyte field guide -
  repository placement and translation rules.

When a future implementation adds a translator, keep shared abstraction
translation, provider serialization, lifecycle collaborators, and request/result
dataclasses separate. Prefer class-bound helpers and centralized frozen dataclass
validation; do not build a free-function conversion wall or hide provider wire
strings in translators.

## Required translation boundary

The Claude Agent SDK runs the Claude Code agent loop in the caller's process and
bundles the provider's built-in tools, context handling, permissions, and session
protocol. Vidbyte should therefore provide:

```text
Vidbyte BaseAgent / ClaudeAgent facade
        |  semantic settings, context, tools, hooks, tracing
        v
Vidbyte -> Claude capability translator
        |  validated ClaudeAgentOptions / ClaudeSDKClient operations
        v
Claude Agent SDK / bundled Claude runtime
        |  provider-owned planning, tool loop, compaction, and subagent execution
        v
typed Vidbyte messages, session records, usage, trace, and capability report
```

The adapter must not claim that Vidbyte's own MCTS, actor-model, middleware,
compaction, or exact model-call interception runs inside Claude's internal loop.
Those are either outer compositions or unsupported controls.

## Candidate future module decomposition

This is a planning seam, not an implementation manifest. A future design may place
the provider-owned integration under `vidbyte/agents/claude/` (or justify another
placement) with responsibilities separated roughly as follows:

- `config.py` / `capabilities.py` - strict Claude-only options and negotiated
  capability report;
- `compiler.py` - Vidbyte semantic settings to validated Claude SDK options;
- `client.py` - one-shot `query()` and persistent `ClaudeSDKClient` lifecycle;
- `messages.py` / `events.py` - typed normalization of content, stream, task,
  rate-limit, and terminal result messages;
- `tools.py` / `permissions.py` / `hooks.py` - tool/MCP bridges and fail-closed
  policy decisions;
- `sessions.py` / `checkpointing.py` - provider transcript/session operations and
  file rewind, kept distinct from Vidbyte checkpoint-DAG state;
- `subagents.py` - `AgentDefinition` translation and parent-child attribution;
- `usage.py` / `tracing.py` / `errors.py` - provider usage, semantic trace events,
  and typed error mapping.

Use `vidbyte/lib/dataclasses/` for stable request/result contracts and keep any
provider wire serialization behind class-bound helpers. Do not create these files
until an implementation request and a new design document authorize them.

## Implementation order for a future request

Implement in this order only after the user explicitly requests implementation:

1. Pin and record the Claude Agent SDK version and bundled runtime version; add an
   optional dependency rather than making the base Vidbyte install depend on it.
2. Add typed capability and error contracts, then validate provider configuration,
   API-key handling, working directory, and unsupported settings at construction.
3. Build the one-shot `query()` path and the persistent `ClaudeSDKClient` path as
   two explicit modes. Normalize both into Vidbyte message/result records.
4. Translate prompts, models, budgets, thinking/effort, tools, permissions, MCP,
   structured output, and environment settings.
5. Add streaming input/output, interrupts, queued prompts, and cancellation with
   correct backpressure and terminal-result handling.
6. Add session resume/fork/external storage and file checkpoint rewind without
   conflating Claude transcript state with Vidbyte checkpoint-DAG state.
7. Add subagents, hooks, skills, plugins, tool search, and MCP lifecycle controls.
8. Add usage/cost, rate-limit, task/todo, speed, and OpenTelemetry translation.
9. Add capability reports, redaction, deployment hardening, and documentation.

The complete feature-by-feature inventory, target seam, and expected disposition is
in [references/feature-matrix.md](references/feature-matrix.md). Treat that matrix
as the checklist for design reviews and future implementation plans.

## Non-negotiable rules

- Do not reimplement Claude's provider loop merely to make it look like Vidbyte's
  linear loop. Use the SDK's public operations and describe provider-owned behavior.
- Do not silently ignore `temperature`, `top_p`, stop sequences, custom compaction,
  exact before-model middleware, MCTS/actor semantics, or other controls Claude does
  not expose. Reject them, translate with an explicit loss, or mark them unsupported.
- Do not mix `query()`'s one-shot semantics with `ClaudeSDKClient`'s persistent
  conversation semantics. Expose the distinction to callers.
- Do not treat a hook that can approve a tool as permission to execute the tool in
  Vidbyte's own tool executor. Claude remains the authority for tools in its loop.
- Do not use provider message dictionaries as Vidbyte's durable public contract.
  Normalize content blocks, results, failures, usage, and session IDs into typed
  Vidbyte records.
- Do not put secrets, full prompts, tool inputs, or file contents into logs/traces by
  default. Reuse Vidbyte redaction and consent boundaries.
- Do not add files under `vidbyte/skills/` for this contributor guidance. That path
  is importable runtime skill machinery; this skill belongs under repository-level
  `skills/`.

## Verification expectations for implementation work

When implementation is eventually requested, verify at least:

- capability negotiation rejects unsupported controls before starting a provider
  process;
- one-shot and persistent modes have distinct session, interrupt, and queue tests;
- all terminal result subtypes and typed SDK errors map to Vidbyte failures;
- tool permissions, hook decisions, MCP reconnect/toggle/status, and cancellation
  preserve fail-closed behavior;
- structured output is validated and invalid-output retry/failure is observable;
- resume, fork, checkpoint rewind, external session storage, and redaction preserve
  identity and lineage;
- usage, cost, rate-limit, speed, trace, and subagent attribution do not leak
  credentials or claim unavailable precision;
- the SDK's pinned version is exercised with a provider-free fake/transport where
  possible, plus a documented opt-in integration smoke test;
- run the repository's canonical `python scripts/run_ci.py` gate. "No new tests"
  does not waive existing lint, packaging, type, or CI checks.

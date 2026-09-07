# Claude Agent SDK Control Inventory

## Surface

The Claude Agent SDK exposes the Claude Code agent loop as Python and TypeScript libraries. One-shot `query()` manages a session per query by default; `ClaudeSDKClient` supports continuous exchanges, streaming input, interrupts, and explicit connection control. This is distinct from the direct Anthropic Client SDK and hosted Managed Agents.

## Implementation status

`vidbyte/agents/claude/` now implements the declarative half of this surface as
`ClaudeHarnessAgent`, pinned to `claude-agent-sdk` 0.2.152 behind the optional
`vidbyte-sdk[claude]` extra and authorized by `docs/design/claude-harness-agent.md`.
It covers one-shot `query()` per turn, session resume, lazy `fork_session`
branching, context rendering, structured output, and typed results with
`total_cost_usd`.

The callback surfaces (`hooks`, `can_use_tool`), the persistent `ClaudeSDKClient`,
streaming, in-process MCP tools, file checkpointing, and session stores are not
built. They are tracked as stable task IDs in `skills/claude-harness-roadmap/`.
Read that checklist before proposing Claude adapter work, and do not build a
second adapter.

## Controls available to an adapter

- Invocation: prompt or streaming input, one-shot query versus connected client, custom transport, environment and executable options documented by the SDK.
- Instructions/config: system prompt or Claude Code preset, append-system-prompt behavior, setting sources, project/user/local configuration loading, working directory, and additional directories.
- Models/reasoning: model, fallback model, effort, thinking configuration, betas, and output style where supported.
- Loop bounds: maximum turns, maximum budget in USD, task budgets, timeout handling, and interruption through the connected client.
- Sessions: continue, resume by session id, fork session, session persistence controls, listing and reading stored session information.
- Output: streamed typed messages, partial assistant events, result message, structured output JSON Schema, usage, duration, cost, errors, and rate-limit events.
- Tools: built-in allow/deny lists, custom in-process SDK MCP tools, external stdio/SSE/HTTP MCP servers, strict tool configuration, and tool search.
- Permissions: permission modes, `can_use_tool` callback, permission updates, and interactive approval/user-input handling.
- Hooks: pre/post tool use, prompt submission, stop, subagent start/stop, compaction, notification, and permission-request callbacks exposed by the SDK.
- Subagents: programmatic agent definitions, model/prompt/tools/skills/MCP configuration per role, and task progress/activity messages.
- Host features: skills, plugins, slash commands, CLAUDE.md memory, checkpointing/file rewind, todos, and OpenTelemetry through documented setting sources.

## Controls not owned by Vidbyte

- Hidden chain-of-thought, built-in compaction implementation, tool implementation internals, and model-side delegation decisions.
- Account authentication, entitlement, provider rate limits, model availability, and server-side safety enforcement.
- Exact placement of every repository instruction when Claude Code configuration loading is enabled.
- Guaranteed parity between a Claude hook and Vidbyte middleware; callbacks differ in event timing, allowed outputs, and failure policy.
- Cross-provider session identity. A Claude session id cannot be treated as a Codex thread id beyond a shared opaque-state field.

## Translation guidance

The shipped adapter uses `query()` per turn with an explicit `resume`, which keeps the provider lifetime bounded per turn at the cost of one subprocess spawn each time; `ClaudeSDKClient` is the pending alternative for a genuinely stateful primitive and is the only route to `interrupt()`. Declare setting sources rather than assuming filesystem configuration is loaded. Use native resume/fork fields for lineage. Treat permission callbacks as a provider boundary that may enforce a stricter Vidbyte policy, never a way to bypass user restrictions.

Official starting points: [Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview), [Python reference](https://platform.claude.com/docs/en/agent-sdk/python), [sessions](https://platform.claude.com/docs/en/agent-sdk/sessions), and [permissions](https://platform.claude.com/docs/en/agent-sdk/permissions).

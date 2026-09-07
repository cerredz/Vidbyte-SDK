# Claude Agent SDK source index

Stable anchors cited by [the future-work checklist](checklist.md). Fetch the linked
page before making an availability claim; the provider ships independently of
Vidbyte's release cadence, and this index records where to look, not what is true
today. Version-specific statements were checked against documentation for
`claude-agent-sdk` 0.2.152 on 2026-09-07.

Inspect the installed package's own types before promising a callable method or a
field name. The public reference and the guides disagreed with each other about
`ResultMessage` fields during the baseline review, which is why task
[C06](checklist.md#c) exists.

<a id="s01"></a>
## S01 — Agent SDK overview

<https://code.claude.com/docs/en/agent-sdk/overview>

Product boundary between the Agent SDK, the Claude Code CLI, the Client SDK, and
Managed Agents. Carries the capability table, the branding restrictions that forbid
naming a third-party product "Claude Code", the note that claude.ai login requires
Anthropic approval, and the commercial-terms reference. Cited by C, A, and V.

<a id="s02"></a>
## S02 — Python SDK reference

<https://code.claude.com/docs/en/agent-sdk/python>

The authoritative Python surface: `query()`, `ClaudeSDKClient`, `tool()`,
`create_sdk_mcp_server()`, the session functions, every `ClaudeAgentOptions` field,
the message and content-block types, `AgentDefinition`, `ThinkingConfig`,
`EffortLevel`, `SettingSource`, `PermissionMode`, the permission result types, the
`Transport` base class, and the SDK error classes. Cited by C, L, R, X, G, and B.

<a id="s03"></a>
## S03 — Streaming input versus single mode

<https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode>

When a prompt must be an async iterable rather than a string, and what changes about
ordering, images, interrupts, and cancellation. Cited by L and T.

<a id="s04"></a>
## S04 — Streaming output

<https://code.claude.com/docs/en/agent-sdk/streaming-output>

Partial-message events under `include_partial_messages`, the raw API event shapes
they wrap, and subagent text forwarding. Cited by T and R.

<a id="s05"></a>
## S05 — Work with sessions

<https://code.claude.com/docs/en/agent-sdk/sessions>

Continue, resume, and fork semantics; how a session id is captured from the result
message even on an error result; the raise-after-error-result behavior of a
single-shot `query()`; transcript locations under `~/.claude/projects/`; and the
same-machine limit on resume. The source for the adapter's two hardest invariants.
Cited by S, F, and D.

<a id="s06"></a>
## S06 — Session storage

<https://code.claude.com/docs/en/agent-sdk/session-storage>

The `SessionStore` adapter contract for mirroring transcripts to caller-owned
storage, and the working-directory-derived lookup key. Cited by S.

<a id="s07"></a>
## S07 — File checkpointing

<https://code.claude.com/docs/en/agent-sdk/file-checkpointing>

Snapshotting and reverting file changes, and why that is a different axis from
branching conversation history. Cited by F.

<a id="s08"></a>
## S08 — Agent loop

<https://code.claude.com/docs/en/agent-sdk/agent-loop>

How turns accumulate, how context is managed and compacted inside the provider's
loop, and how to handle each terminal result. Cited by X and B.

<a id="s09"></a>
## S09 — MCP and custom tools

<https://code.claude.com/docs/en/agent-sdk/mcp> and
<https://code.claude.com/docs/en/agent-sdk/custom-tools>

External stdio, SSE, and HTTP servers; in-process SDK servers via the `tool()`
decorator and `create_sdk_mcp_server()`; tool annotations; and the MCP lifecycle
methods on the persistent client. Cited by U and M.

<a id="s10"></a>
## S10 — Structured outputs

<https://code.claude.com/docs/en/agent-sdk/structured-outputs>

The `output_format` envelope, the draft-07 requirement that a Pydantic schema
violates by default, `ResultMessage.structured_output`, provider-side retries, the
`error_max_structured_output_retries` subtype, and the documented case where a
`success` subtype carries no structured output. Cited by U.

<a id="s11"></a>
## S11 — Permissions

<https://code.claude.com/docs/en/agent-sdk/permissions>

Permission modes, the `can_use_tool` callback, allow and deny results with updated
input, permission-rule updates and their destinations, and sandbox settings with
their platform caveats. Cited by P.

<a id="s12"></a>
## S12 — Hooks

<https://code.claude.com/docs/en/agent-sdk/hooks>

The full event list, `HookMatcher` registration with matcher patterns and timeouts,
the `hookSpecificOutput` shape including `permissionDecision` and `updatedInput`,
parallel hook execution with most-restrictive-wins, async mode, and deferral.
Cited by H, X, and N.

<a id="s13"></a>
## S13 — Skills and configuration loading

<https://code.claude.com/docs/en/agent-sdk/skills> and
<https://code.claude.com/docs/en/agent-sdk/claude-code-features>

How skills, slash commands, and CLAUDE.md memory load from `.claude/` and the home
directory, and how `setting_sources` gates that loading. Cited by K and X.

<a id="s14"></a>
## S14 — Plugins

<https://code.claude.com/docs/en/agent-sdk/plugins>

Packaging skills, agents, hooks, and MCP servers, and loading them by local path.
Cited by K.

<a id="s15"></a>
## S15 — Hosting and environment variables

<https://code.claude.com/docs/en/agent-sdk/hosting> and
<https://code.claude.com/docs/en/env-vars>

Deployment shapes, credential handling, alternate provider routing, and the
environment variables that change transcript and configuration behavior. Cited by
A and S.

<a id="s16"></a>
## S16 — Subagents

<https://code.claude.com/docs/en/agent-sdk/subagents>

Programmatic `AgentDefinition` registration, the complete field list, background
execution, and parent-child attribution. Cited by N.

<a id="s17"></a>
## S17 — Observability

<https://code.claude.com/docs/en/agent-sdk/observability>

OpenTelemetry emission through documented setting sources, and the usage and cost
fields available for accounting. Cited by O.

<a id="s18"></a>
## S18 — Troubleshooting

<https://code.claude.com/docs/en/agent-sdk/troubleshooting>

Documented failure modes and their causes, including the entry on a `success`
result whose `structured_output` is `None`. Cited by B.

<a id="s19"></a>
## S19 — Changelog and examples

<https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md> and
<https://github.com/anthropics/claude-agent-sdk-demos>

Version history for the Python package and reference demo applications. Read the
changelog before widening the version pin in `pyproject.toml`. Cited by C and V.

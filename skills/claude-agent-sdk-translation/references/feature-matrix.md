# Claude Agent SDK Feature Translation Matrix

This is the implementation inventory for the `claude-agent-sdk-translation` skill.
It reflects the public Python Agent SDK reference and its typed source as of
2026-09-05. Re-check the pinned SDK and official documentation before coding; the
provider can add fields without changing Vidbyte's provider-neutral contracts.

Authoritative references:

- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Python SDK reference](https://code.claude.com/docs/en/agent-sdk/python)
- [Hooks](https://code.claude.com/docs/en/agent-sdk/hooks)
- [Sessions](https://code.claude.com/docs/en/agent-sdk/sessions)
- [Structured output](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
- [Subagents](https://code.claude.com/docs/en/agent-sdk/subagents)
- [Streaming input](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
- [Streaming output](https://code.claude.com/docs/en/agent-sdk/streaming-output)
- [Custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)
- [MCP](https://code.claude.com/docs/en/agent-sdk/mcp)
- [Tool search](https://code.claude.com/docs/en/agent-sdk/tool-search)
- [Skills](https://code.claude.com/docs/en/agent-sdk/skills)
- [Plugins](https://code.claude.com/docs/en/agent-sdk/plugins)
- [Permissions](https://code.claude.com/docs/en/agent-sdk/permissions)
- [File checkpointing](https://code.claude.com/docs/en/agent-sdk/file-checkpointing)
- [OpenTelemetry](https://code.claude.com/docs/en/agent-sdk/observability)
- [Hosting](https://code.claude.com/docs/en/agent-sdk/hosting)

## Disposition legend

| Disposition | Meaning in this matrix |
|---|---|
| `native` | Direct Claude option or operation with the same useful guarantee. |
| `translated` | Mapped from a Vidbyte contract with a documented precision difference. |
| `supervised` | Claude owns the internal behavior; Vidbyte bounds, observes, or stops it. |
| `observe_only` | Exposed as telemetry/metadata, not as a control surface. |
| `emulated` | Composed outside Claude's loop from public operations. |
| `unsupported` | Must be rejected or surfaced as unavailable; never silently ignored. |

## 1. Provider boundary and lifecycle

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| `query(prompt, options)` async iterator | `native` | One-shot Claude agent execution on `BaseAgent.arun()` | New session by default; normalize every message and terminal result. |
| `ClaudeSDKClient` context manager | `native` | Persistent provider session collaborator | Owns connect/query/receive/disconnect; do not make it look like a normal stateless runner. |
| Streaming input async iterable | `translated` | `AgentInput`/queued prompt adapter | Preserve ordering, cancellation, images, and generator failure semantics. |
| `session_id` / `continue_conversation` | `translated` | Provider-session identity binding | Require an explicit resume/continuation policy; do not infer identity from prompt text. |
| `interrupt()` | `native` | Agent cancellation/stop operation | Only persistent client mode supports direct interrupts. |
| `stop_task()` | `native` | Explicit task stop control | Map terminal reason and partial result to Vidbyte failure vocabulary. |
| `reconnect_mcp_server()` | `native` | MCP lifecycle method | Never silently reconnect a server after a policy denial. |
| `toggle_mcp_server()` / `get_mcp_status()` | `native` | MCP state/status capability | Include server-level state in diagnostics, not in the model prompt by default. |
| `set_permission_mode()` / `set_model()` | `native` | Persistent-session mutators | Record changes as session events; validate against Vidbyte policy first. |
| `get_context_usage()` / `get_server_info()` | `observe_only` | Context and runtime diagnostics | Expose provider-reported values without pretending they are Vidbyte token counts. |
| bundled Claude runtime process | `supervised` | Provider adapter dependency | Pin package/runtime versions and report them in capability metadata. |

## 2. Prompt, model, budget, and environment settings

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| String system prompt | `native` | `BaseAgent.system_prompt` | Preserve user prompt and system prompt as separate semantic fields. |
| System prompt preset/file | `translated` | Prompt asset/reference resolver | Resolve files under explicit trust rules; never read arbitrary paths from untrusted YAML. |
| `model` | `native` | `runner_config.model_name` | Preserve provider model identity in usage and trace records. |
| `fallback_model` | `translated` | `AgentFallbackSettings` | Claude fallback is provider-owned; distinguish it from Vidbyte retry/fallback orchestration. |
| `max_turns` | `translated` | `AgentLoopSettings.max_iterations` | Turns are not guaranteed to equal Vidbyte iterations/tool rounds; report the mapping. |
| `max_budget_usd` | `translated` | Cost budget policy | Let Claude enforce its bound and reconcile actual provider usage into Vidbyte pricing. |
| `max_tokens` | `unsupported`/`observe_only` | Capability report | Claude Agent SDK does not expose a general Vidbyte-equivalent output-token ceiling for the entire loop. |
| `temperature`, `top_p`, stop sequences | `unsupported` | Construction-time rejection | Do not silently drop provider-runner fields. |
| `thinking` / `effort` / deprecated `max_thinking_tokens` | `translated` | Reasoning/effort capability | Keep provider-specific values typed; mark deprecated fields and model support. |
| `betas` | `native` | Provider extension settings | Keep behind an explicit Claude-only escape hatch; never add to shared settings without semantics. |
| `task_budget` | `translated` | Subagent/task budget contract | Distinguish task budget from top-level dollar budget and turn ceiling. |
| `cwd`, `add_dirs` | `translated` | Working-root and allowed-path policy | Validate roots and include them in run identity where they affect behavior. |
| `env`, `extra_args`, `settings`, `setting_sources` | `translated` | Provider configuration | Redact secrets, make precedence visible, and avoid arbitrary settings injection. |
| `include_hook_events` | `observe_only` | Hook event stream option | Expose raw hook events only through an opt-in diagnostic channel with redaction. |
| `cli_path`, `max_buffer_size`, `stderr`, `load_timeout` | `translated` | Process/runtime configuration | Treat process failures as typed provider errors; cap buffers to avoid memory exhaustion. |
| `user` | `translated` | User/tenant metadata | Keep identity separate from prompt content and credentials. |
| `plugins` | `translated` | Plugin path/config capability | Load only explicitly allowed local plugins; record versions and permissions. |
| `skills` / commands / memory from `.claude` and home settings | `translated`/`supervised` | Skill/resource policy | Resolve allowed setting sources; do not imply that Vidbyte's own skill registry is automatically loaded. |

## 3. Tools, MCP, and permissions

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| Built-in Read/Write/Edit/Bash/Glob/Grep/Web tools | `translated` | Vidbyte tool catalog and security policy | Decide whether Claude-native tools remain provider-owned or are wrapped as observable tool events. |
| `allowed_tools` / `disallowed_tools` | `translated` | `AgentLoopSettings.allowed_tools` + `ToolSettings.denied_tools` | Define precedence and fail closed on conflicting allow/deny rules. |
| SDK `tool()` custom MCP tool | `translated` | Vidbyte `ToolSpec`/tool bridge | Preserve schema, annotations, result limits, pricing identity, and async errors. |
| Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) | `translated` | Vidbyte tool metadata/security hints | Hints inform policy; they are not authorization. |
| MCP stdio, SSE, HTTP, in-process SDK servers | `native` | `vidbyte.tools.mcp` attachment | Keep transport lifecycle, server identity, reconnect, toggle, and status typed. |
| `strict_mcp_config` | `translated` | Strict MCP configuration mode | Reject unknown/invalid server config at construction, before provider start. |
| Tool search/deferred MCP loading | `translated`/`supervised` | Lazy tool catalog capability | Report that Claude selects/searches deferred tools; Vidbyte cannot guarantee its own per-call ordering. |
| `can_use_tool` callback | `translated` | Permission policy adapter | Convert to typed allow/deny/ask/defer results and preserve updated input. |
| `permission_mode` | `translated` | Vidbyte permission preset | Map `default`, `acceptEdits`, `plan`, `bypassPermissions`, and related modes only where safe. |
| Permission prompt tool | `translated` | Host approval callback | Never auto-approve because a caller omitted a callback. |
| Permission hook decisions and rule updates | `translated` | Hook/permission event records | Preserve the most restrictive outcome and audit policy updates. |
| Sandbox settings and network restrictions | `translated`/`supervised` | Vidbyte sandbox/security boundary | Claude sandbox support is OS/runtime-specific; do not claim Windows parity without evidence. |
| Tool result truncation / `maxResultSizeChars` | `translated` | `ToolSettings.result_max_chars` | Keep provider truncation distinguishable from Vidbyte compaction/truncation. |

## 4. Hooks and lifecycle interception

| Claude hook | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| `PreToolUse` | `translated` | Tool permission/validation hook | Can block or update tool input; it is not Vidbyte `before_model_call`. |
| `PostToolUse` | `translated` | Tool result observer | Can add context or update output; preserve provider event ordering. |
| `PostToolUseFailure` | `translated` | Tool failure policy/audit event | Do not double-retry if Claude already owns the attempt. |
| `UserPromptSubmit` | `translated` | Input audit/normalization hook | Distinguish host prompt mutation from Vidbyte context mutation. |
| `Stop` / `SubagentStop` | `translated` | Terminal decision observer | A stop hook can influence provider termination; map final reason. |
| `PreCompact` | `supervised` | Compaction telemetry/guard | Claude owns compaction; Vidbyte cannot substitute its custom context algorithm inside it. |
| `Notification` | `observe_only` | Progress/notification event | Preserve notification type and parent session. |
| `SubagentStart` | `translated` | Child-agent lifecycle event | Include parent tool-use/session IDs. |
| `PermissionRequest` | `translated` | Approval decision path | Keep fail-closed behavior and audit every decision. |
| TypeScript-only `SessionStart`/`SessionEnd` callbacks | `unsupported` for Python | Capability report | Python can approximate with first/last stream messages or settings-file hooks; label as an approximation. |
| Hook matchers and parallel execution | `translated` | Typed hook registration | Claude runs matching hooks in parallel and applies the most restrictive result; do not promise sequential middleware semantics. |

## 5. Messages, streaming, output, and errors

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| User/assistant/system/result message union | `translated` | `AgentInput`/`AgentMessage`/typed result records | Preserve IDs, parent tool-use IDs, session ID, and provider subtype. |
| Text/thinking/tool-use/tool-result content blocks | `translated` | Vidbyte content primitives | Thinking visibility must be explicit and redacted according to policy. |
| `include_partial_messages` / stream events | `translated` | Agent stream API and speed tracker | Raw API events are provider payloads; normalize deltas while retaining opt-in raw details. |
| Incremental tool-input JSON events | `observe_only` | Tool-call stream telemetry | Do not execute a tool before a complete, validated call is received. |
| `forward_subagent_text` | `translated`/`observe_only` | Subagent output forwarding | Token-level partial events are main-session only; complete messages carry attribution. |
| Structured output JSON schema | `native` | `output_schema` / output contract | Read `ResultMessage.structured_output`; validate and expose provider retry/failure. |
| Structured-output invalid retry | `supervised` | Output-contract event | Claude controls retry count; do not count it as Vidbyte middleware retry unless explicitly reported. |
| `ResultMessage` subtype/status | `translated` | `AgentResult` and failure vocabulary | Include duration, turns, cost, usage, model usage, denials, errors, terminal reason. |
| SDK error classes (`CLINotFoundError`, connection/process/result/JSON errors) | `translated` | Typed provider/agent errors | Preserve cause and retryability; never collapse all failures into a string. |
| Rate-limit events/info | `observe_only`/`translated` | Usage/rate-limit tracker | Expose reset windows and scope where available; do not fabricate provider limits. |

## 6. Sessions, persistence, and file state

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| `continue_conversation` | `translated` | `Session.append_context`-like operation | Provider transcript continuation is not identical to appending Vidbyte checkpoints. |
| `resume` by session ID | `native` | Session resume adapter | Validate identity, working directory, model/provider, and policy before resuming. |
| `fork_session` | `native`/`translated` | Session fork façade | Preserve provider branch ID and Vidbyte lineage separately. |
| `resume_session_at` / `resume_drops_turn` | `translated` | Message-level branch selection | Map only if the provider can prove the requested boundary; otherwise reject. |
| `SessionStore` / external session storage | `translated` | `vidbyte.sessions.stores` adapter | Define serialization, locking, ownership, encryption, and cross-host behavior. |
| `session_store_flush` | `translated` | Persistence flush policy | Make durability and flush failures visible; never report a checkpoint before persistence succeeds. |
| `list_sessions`, `get_session_messages/info`, rename, tag, delete | `native` | Session management façade | Keep provider sessions discoverable without making them Vidbyte checkpoint records. |
| Local transcript files | `supervised` | Provider persistence policy | Do not assume local files are portable, private, or suitable as the operational source of truth. |
| `enable_file_checkpointing` | `native` | File checkpoint capability | Track checkpoint IDs and filesystem scope; require explicit opt-in for mutation rollback. |
| `rewind_files(checkpoint_id)` | `native` | File rewind operation | This rewinds file changes, not conversation history; state the distinction in the API. |
| Vidbyte checkpoint/fork/edit/export/import | `emulated` | Outer Session/Harness composition | Never claim Claude can restore arbitrary Vidbyte runtime state. |

## 7. Subagents and orchestration

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| `AgentDefinition` registry | `translated` | Provider child-agent definitions | Preserve prompt, tools, model, skills, memory, MCP, max turns, background, effort, and permission mode. |
| Task/subagent invocation | `supervised` | Child lifecycle and parent-child IDs | Claude owns scheduling, context, and internal tool loop. |
| Background subagents | `supervised` | Task handle/status façade | Do not map directly to Vidbyte actor-model concurrency. |
| Subagent memory/skills | `translated` | Explicit child resource policy | Avoid inheriting secrets or parent context by accident. |
| `TaskCreate/Update/Get/List/Output/Stop` | `translated` | Task/event records | Keep provider task state separate from Vidbyte ledger tasks. |
| `MultiAgent` ledger/team orchestration | `emulated`/`unsupported` inside Claude | Outer Vidbyte coordinator | Use `MultiAgent` outside the provider loop; Claude subagents are not a drop-in ledger worker. |
| Vidbyte MCTS/actor runtime | `unsupported` inside Claude | Outer runtime only | A Claude agent can be a worker, but its internal loop is not an MCTS/actor runtime. |

## 8. Context, compaction, usage, and observability

| Claude feature | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| Provider context management/compaction | `supervised` | Context usage and boundary events | Observe compact boundaries; do not inject Vidbyte compaction algorithms as if provider-native. |
| `get_context_usage()` | `observe_only` | Context diagnostic record | Keep provider token estimates distinct from Vidbyte budget accounting. |
| Token usage/model usage | `translated` | `UsageTracker` / session usage | Normalize input/output/cache/thinking fields when present; preserve raw provider usage for audits. |
| Cost and `max_budget_usd` | `translated` | `UsageRollup` and cost middleware | Provider price tables can differ from Vidbyte's; record source and model. |
| Speed/latency and TTFT | `observe_only` | `AgentSpeedTracker` | Measure stream chunks where available; do not infer token counts from text. |
| OpenTelemetry | `translated` | Vidbyte trace providers/components | Translate semantic spans into typed provider attributes; redact secrets and avoid raw wire strings in translators. |
| Todo lists and progress notifications | `translated`/`observe_only` | Trace/task events | Do not make provider todos the source of truth for Vidbyte workflows. |
| Permission denials and errors | `translated` | Audit trace and failure records | Preserve denial reason without logging sensitive tool input. |

## 9. Security and deployment

| Claude feature/constraint | Disposition | Vidbyte translation target | Required notes |
|---|---|---|---|
| API-key authentication | `native`/`translated` | Provider credential injection | Accept environment/application injection; reject secrets in YAML and durable metadata. |
| Claude.ai login/rate-limit reuse | `unsupported` by default | Capability/error message | Third-party products require Anthropic approval; do not offer it as a Vidbyte default. |
| Anthropic Commercial Terms | `translated` | Dependency/license documentation | Surface commercial terms in install and integration docs. |
| SDK/runtime subprocess isolation | `supervised` | Harness/process lifecycle | Bound startup, output buffers, timeouts, and cleanup. |
| Working-directory and filesystem access | `translated` | `ContextPermissions`/sandbox policy | Resolve paths before process start; prevent traversal and unintended host writes. |
| Network sandbox controls | `translated`/`unsupported` by platform | Security capability report | Report OS-specific gaps instead of claiming uniform sandboxing. |
| Plugin/skill/settings loading | `translated` | Explicit trust and allowlist policy | Do not load project/home settings implicitly in untrusted runs. |
| Redaction and consented trajectory export | `translated` | `Harness` collector/redactor | Claude transcripts, tool inputs, and file diffs are sensitive artifacts. |

## Provider-only escape hatch

Some Claude fields are useful but do not belong in shared Vidbyte abstractions. Keep
them in an explicitly typed Claude-only options object or an opaque extension field:
`betas`, provider-specific thinking values, plugin paths, Claude setting sources,
native task budgets, raw CLI arguments, and SDK version metadata. Every escape-hatch
field must be version-pinned, redacted where necessary, included in the capability
report, and excluded from claims of cross-provider portability.

# Harness Translation Matrix

Legend: **Exact** means a native documented field/operation; **Policy** means comparable behavior with provider-specific rules; **Emulated** means Vidbyte adds boundary behavior; **No** means no reliable public equivalent is promised.

| Vidbyte concept | Codex | Claude Agent SDK | Adapter rule |
|---|---|---|---|
| System prompt | Exact: developer instructions | Exact: system prompt/preset | Preserve provider precedence rules. |
| Additional context | Emulated in turn input on current stable Python surface | Exact/policy through prompt, streaming input, or appended system prompt | Delimit and bound context; document placement semantics. |
| Structured output | Exact turn JSON Schema plus local validation | Exact output format plus local validation | Always validate provider output locally. |
| Stateful continuation | Exact thread resume | Exact connected client or session resume | Store opaque provider identity only after success. |
| Fork | Exact thread fork | Exact session fork option | Never simulate lineage with copied transcript text. |
| Vidbyte context primitives | Policy: deterministic text rendering | Policy: text or controlled prompt/config source | Preserve content, not unsupported placement promises. |
| Custom tools | Policy through Codex MCP/config/app-server surface | Exact SDK MCP tools and external MCP | Build provider-specific tool translators. |
| MCP servers | Exact configuration surface | Exact SDK configuration surface | Normalize declarations, retain provider transport differences. |
| Tool allow/deny | Policy through sandbox/approval/config | Exact allowed/disallowed tools and callback | Shared policy may narrow, never widen, native restrictions. |
| Middleware/hooks | Policy; Codex hook events differ | Policy; rich SDK hook callbacks | Map each lifecycle event independently; no blanket parity. |
| Max iterations/turns | No general exact phase-one mapping | Exact `max_turns` | Capability-check before a primitive requires it. |
| Monetary budget | Provider/account-owned; service tier is not a budget | Exact `max_budget_usd`/task budget | Never reinterpret service tier as spend cap. |
| Sandbox | Exact native modes/config | Exact native sandbox settings | Keep provider-native meanings; do not flatten names alone. |
| Approval callback | Policy through Codex approval protocol | Exact `can_use_tool`/user input | Default to deny when translation is uncertain. |
| Subagent definitions | Exact provider config/files | Exact programmatic definitions | Keep role-specific controls in provider settings. |
| Subagent selection | Provider-owned | Provider-owned | Observe activity; do not promise deterministic delegation. |
| Usage/cost | Exact usage where returned; pricing normalization separate | Exact usage/cost result fields | Mark missing fields and pricing timestamp/version. |
| Streaming/events | Exact app-server event protocol; SDK coverage version-sensitive | Exact typed async message stream | Translate a stable subset and retain provider type metadata. |
| Compaction | Provider-owned; hooks/config may observe or request | Provider-owned with pre-compact hook | Do not substitute Vidbyte compaction inside the native loop. |
| Checkpoint/file rewind | Provider-specific, verify current app-server | Exact documented checkpointing | Expose only after durable compatibility tests. |
| Hidden reasoning | No | No | Never request, persist, or expose it. |
| Vidbyte model middleware | No direct semantic parity | No direct semantic parity | Keep outside the provider loop or reject. |

## Decision checklist

- [ ] Name the provider surface and reviewed SDK version.
- [ ] Classify the translation level for every public option.
- [ ] Define precedence between Vidbyte settings and host/project settings.
- [ ] Define lifecycle ownership, cancellation, cleanup, and retry behavior.
- [ ] Define safe event/result serialization and bounded metadata.
- [ ] Define permission behavior, including deny/failure defaults.
- [ ] Define persistence and native fork/resume lineage.
- [ ] Reject unsupported requirements before paid admission or process launch.

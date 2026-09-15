# Design Doc: Codex Harness Custom Tools

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

`CodexHarnessAgent` currently has no way to give the Codex model a Vidbyte tool. This change adds a `tools` setting to `CodexHarnessAgentSettings` that accepts `BaseTool` instances, `@tool`-decorated functions, plain callables, or any mix of them. The agent registers them with Codex as **dynamic tools**, the Codex app-server protocol's mechanism for host-defined function tools. When the model calls one, Codex sends an `item/tool/call` request back over the SDK connection. Vidbyte then runs the tool's Python code in the agent's own process and event loop, through the same `ToolExecutor` the direct runtime uses, and returns the result to the model. After this change a Codex agent can call arbitrary Python the same way a direct-runtime `Agent` can.

---

## 2. Goals & Non-Goals

### Goals
- Accept `BaseTool`, `@tool` functions (`FunctionTool`), and plain callables, alone or mixed, through one `tools` field.
- Execute tool calls in-process through `ToolExecutor`, so permission policy, argument validation, activity annotations, and error capture behave exactly as they do for a direct-runtime agent.
- Reject invalid tool declarations (bad names, duplicate names, experimental API disabled) when the agent is constructed, before any Codex process starts.
- Leave agents that declare no tools byte-for-byte unchanged at the transport boundary.
- Keep tools working across `thread_id` resume, fallback retries, and forks.

### Non-Goals
- Running `before_tool_call` / `after_tool_call` middleware around Codex tool calls. Those hooks stay rejected by `CodexMiddlewareValidator`; wiring them is a follow-up.
- Exposing tools over MCP (roadmap U01). Dynamic tools are the in-process path chosen here (roadmap U02/U03).
- Namespaced or deferred-loading dynamic tools.
- Changing tool definitions on an already-started Codex thread. Codex only accepts `dynamicTools` on `thread/start`.
- Tool concurrency controls or a per-agent timeout setting. The timeout is a shared constant.

---

## 3. Background & Context

- **Why now:** the Codex harness is the SDK's provider-native agent, but it cannot call any Vidbyte tool, so a developer who needs one custom action has to leave the harness entirely.
- **The mechanism exists but is hidden.** The Codex Python SDK (`openai-codex`, pinned `>=0.147.0,<0.148.0`) has no tools option on its high-level `AsyncCodex` interface. The underlying app-server protocol does support tools: `thread/start` accepts an experimental `dynamicTools` field, and tool calls arrive as `item/tool/call` server requests. The SDK's sync `CodexClient` forwards every server request to one `_approval_handler` callable and sends every request through `request(...)`. Both are reachable from an open `AsyncCodex` at `client._client._sync`.
- **Protocol facts verified in openai/codex `main`:**
  - Function names must match `^[a-zA-Z0-9_-]+$`, be at most 128 characters, and not be `mcp` or start with `mcp__` (`codex-rs/app-server/src/request_processors/thread_processor.rs`, `validate_dynamic_tools`).
  - Only `ThreadStartParams` carries `dynamic_tools`; `ThreadResumeParams` and `ThreadForkParams` do not (`codex-rs/app-server-protocol/src/protocol/v2/thread.rs`).
  - Codex saves the tools in the thread's session metadata and restores them for both resumed and forked histories (`codex-rs/history/src/lib.rs`, `get_dynamic_tools`).
  - The request is `{callId, turnId, tool, arguments, namespace?}`. The response is `{contentItems: [{type: "inputText", text}], success}` (`codex-rs/protocol/src/dynamic_tools.rs`).
- **Current state:**
  - `CodexHarnessAgentSettings` has no tools field.
  - `CodexTransport.run` opens one `AsyncCodex` per run.
  - `CodexResultSerializer` already keeps `dynamicToolCall` items (`CODEX_SUPPORTED_ITEM_TYPES`), so tool calls will show up in results with no change there.
- **Constraints:**
  - `vidbyte/lib` must not import `vidbyte/tools` or `vidbyte/agents` at runtime (lint A006). Lib records use `TYPE_CHECKING` imports and duck-typed validation.
  - The SDK's reader thread calls the handler synchronously, and an exception there kills the connection's reader loop.

---

## 4. Requirements

### Functional Requirements
1. `CodexHarnessAgentSettings.tools` accepts a tuple whose items are `BaseTool` instances (including `@tool` functions) or plain callables, in any mix. It defaults to `()`.
2. `CodexHarnessAgentSettings.tool_permission_policy` accepts a `PermissionPolicy` and defaults to `PermissionPolicy()`, the same default the direct runtime uses.
3. Construction fails with an error when:
   - `tools` is not a tuple, or contains an item that is neither tool-shaped nor callable;
   - two tools share a name;
   - a tool name breaks Codex's naming rules;
   - tools are declared while `codex.client.experimental_api` is `False`.
4. On a new thread (no `thread_id`), the `thread/start` request carries one `dynamicTools` entry per tool: `{"type": "function", "name", "description", "inputSchema"}`. `inputSchema` is the same JSON schema the SDK sends to OpenAI-family providers.
5. When Codex sends `item/tool/call`, the agent runs the named tool through `ToolExecutor.execute_call` on the event loop that is running `arun`. It answers `{"success": status == SUCCESS, "contentItems": [{"type": "inputText", "text": output}]}`.
6. Every other server request, including command and file-change approvals, goes to the SDK's original handler, so approval behavior is unchanged.
7. Tool failures (unknown tool, permission denied, invalid arguments, the tool raising, a timeout, cancellation, non-object arguments) return `success: false` with a fixed, safe message. The handler never raises.
8. A tool call that runs longer than `CODEX_TOOL_CALL_TIMEOUT_SECONDS` is cancelled and reported as failed.
9. When the run's connection closes (success, failure, or cancellation), any tool coroutine still running is cancelled.
10. A forked `CodexHarnessAgent` inherits `tools` and `tool_permission_policy`. Codex's native fork already inherits the tool definitions, so the child can execute what its model sees.
11. Agents with no tools install no handler and alter no requests.

### Non-Functional Requirements
- **Performance:** construction cost is one `Tools` normalization plus one schema per tool, computed once per agent. Per call, the only overhead is a cross-thread future handoff.
- **Scalability:** Codex tool calls are serialized per connection because the SDK has one reader thread. This is documented, not worked around.
- **Security:** the default `PermissionPolicy` allows only SAFE and READ tools, as in the direct runtime. Tool failure text sent to the model never includes raw exception text from the bridge.
- **Observability:** tool calls appear as `dynamicToolCall` items in `CodexRunResult.items`, which already exist. `ToolResult.metadata["error"]` classifies failures.
- **Reliability:** SDK private-attribute drift fails loudly with `CodexAgentError(CODEX_SDK_UNAVAILABLE)` at attach time, before a thread starts.

---

## 5. High-Level Design

The work splits into three pieces, following the field guide's "separate shared-abstraction translation from provider serialization" rule:

1. **At construction, `CodexToolTranslator` handles the Vidbyte side.** It normalizes `settings.tools` into a `Tools` catalog (reusing `ensure_tool`, so `BaseTool`, `@tool`, and callables all work), validates Codex's naming rules and the experimental-API flag, and returns a `CodexToolBridge`, or `None` when no tools are declared.
2. **Serialization reuses the existing formatter.** A new `ToolsFormatter.to_codex_tool(spec)` sits beside `to_openai_tool` and `to_anthropic_tool`.
3. **At run time, `CodexToolBridge.attach(client, loop)` connects the tools to one live connection.** It installs a per-connection `CodexToolCallHandler` as the SDK client's server-request handler, and wraps the client's `request` method so `thread/start` carries `dynamicTools`.

```
CodexHarnessAgentSettings(tools=(MyTool(), my_fn))
        │  construction
        ▼
CodexVidbyteTranslator ──► CodexToolTranslator ──► CodexToolBridge(Tools, ToolExecutor, dynamic_tools)
        │  arun()
        ▼
CodexTransport.run ── async with AsyncCodex(config) as client, _attached_tools(client, bridge):
        │                         └─ bridge.attach(client, loop) ─► sync._approval_handler = handler.handle
        │                                                        └► sync.request wraps thread/start + dynamicTools
        ▼
thread/start{dynamicTools}  ──►  codex app-server  ──► model calls tool
                                         │
          SDK reader thread ◄── item/tool/call {tool, arguments, callId}
                 │ run_coroutine_threadsafe(executor.execute_call(call), loop)
                 ▼
          agent event loop (idle, awaiting to_thread) runs BaseTool.execute
                 │ ToolResult
                 ▼
          {"success", "contentItems"} ──► codex app-server ──► model continues
```

**Key decisions:**
- **Dynamic tools rather than MCP.** Tools run in the agent's own process, with its live objects and event loop, and no subprocess.
- **A `request` wrapper rather than rebuilding thread-start params.** Wrapping keeps `AsyncCodex.thread_start`'s own translation of approval mode, sandbox, and the other typed fields on the public path, and adds exactly one key.
- **The bridge is `None` when there are no tools.** This guarantees zero behavior change for existing agents.
- **All private-attribute access lives in one method (`CodexToolBridge._sync_client`),** with a contract test against the pinned SDK.

---

## 6. Detailed Design

### 6.1 Codex tool constants

**File(s):** `vidbyte/lib/constants/codex.py`
**Type:** Modified

#### What it does
Declares the protocol literals and bounds once (lint A007).

#### Interface / API
```python
CODEX_DYNAMIC_TOOL_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"
CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH = 128
CODEX_RESERVED_DYNAMIC_TOOL_NAME = "mcp"
CODEX_RESERVED_DYNAMIC_TOOL_PREFIX = "mcp__"
CODEX_DYNAMIC_TOOLS_PARAM = "dynamicTools"
CODEX_THREAD_START_METHOD = "thread/start"
CODEX_TOOL_CALL_METHOD = "item/tool/call"
CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0
```

#### Logic / Algorithm
N/A. These are constants only.

#### Edge Cases & Error Handling
N/A.

### 6.2 `ToolsFormatter.to_codex_tool`

**File(s):** `vidbyte/lib/tools/formatter.py`
**Type:** Modified

#### What it does
Converts one `ToolSpec` into a Codex dynamic function-tool declaration.

#### Interface / API
```python
@staticmethod
def to_codex_tool(spec: ToolSpec) -> dict[str, Any]:
    # Convert a ToolSpec into a Codex app-server dynamic function tool.
```

#### Logic / Algorithm
1. Return `{"type": "function", "name": spec.name, "description": spec.description, "inputSchema": ToolsFormatter._schema_for_spec(spec)}`.

#### Edge Cases & Error Handling
- The schema comes from `_schema_for_spec`, which already merges activity annotations and prefers an explicit `input_schema`. The Codex schema therefore matches the OpenAI one exactly.

### 6.3 Settings and request records

**File(s):** `vidbyte/lib/dataclasses/codex.py`
**Type:** Modified

#### What it does
Adds the public fields and carries the construction-time bridge to the transport.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class CodexHarnessAgentSettings:
    ...
    tools: tuple[ToolInput, ...] = ()
    tool_permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)

@dataclass(frozen=True, slots=True)
class CodexAgentTranslation:
    settings: CodexHarnessAgentSettings
    output_schema: Mapping[str, Any]
    tools: CodexToolBridge | None = None

@dataclass(frozen=True, slots=True)
class CodexTransportRunRequest:
    ...
    tools: CodexToolBridge | None = None
```
`ToolInput` and `CodexToolBridge` are `TYPE_CHECKING`-only imports. `PermissionPolicy` is a lib-layer runtime import from `vidbyte.lib.dataclasses.security`.

#### Logic / Algorithm
1. In `CodexHarnessAgentSettings.__post_init__`:
   - Require `tools` to be a tuple.
   - Require every item to be tool-shaped (callable `spec` and `execute`) or callable. The check is duck-typed because lib cannot import `BaseTool`.
   - Require `tool_permission_policy` to be a `PermissionPolicy`.
2. `None` for `tools` on the two records means "no tools declared". The union is structurally required because lib cannot construct an empty bridge. The docstrings say so.

#### Edge Cases & Error Handling
- A list instead of a tuple raises `ConfigurationError`, matching `middleware` and `capabilities`.
- An empty tuple is valid and yields no bridge.

### 6.4 Tool translation, bridge, and call handler

**File(s):** `vidbyte/agents/codex/tools.py`
**Type:** New file

#### What it does
- `CodexToolTranslator` handles construction-time normalization and validation.
- `CodexToolBridge` attaches one catalog to Codex connections.
- `CodexToolCallHandler` answers server requests for one connection on the SDK reader thread.

#### Interface / API
```python
class CodexToolTranslator:
    @classmethod
    def translate(cls, settings: CodexHarnessAgentSettings) -> CodexToolBridge | None: ...

class CodexToolBridge:
    def __init__(self, tools: Tools, permission_policy: PermissionPolicy) -> None: ...
    tools: Tools
    dynamic_tools: tuple[dict[str, Any], ...]
    def attach(self, codex: object, loop: asyncio.AbstractEventLoop) -> CodexToolCallHandler: ...

class CodexToolCallHandler:
    def __init__(self, executor: ToolExecutor, loop: asyncio.AbstractEventLoop, fallback: ServerRequestHandler) -> None: ...
    def handle(self, method: str, params: Mapping[str, Any] | None) -> dict[str, Any]: ...
    def close(self) -> None: ...
```

#### Logic / Algorithm
`CodexToolTranslator.translate`:
1. Return `None` if `settings.tools` is empty.
2. Raise `ConfigurationError` if `settings.codex.client.experimental_api` is `False`.
3. Build `Tools(settings.tools)`. This normalizes the items and raises `ToolRegistrationError` on duplicate names.
4. Validate each spec name against the pattern, the length bound, and the reserved names.
5. Return `CodexToolBridge(catalog, settings.tool_permission_policy)`.

`CodexToolBridge.attach`:
1. Resolve the sync client with `_sync_client(codex)`, which reads `codex._client._sync` and checks for `_approval_handler` and a callable `request`. If either is missing, raise `CodexAgentError(CODEX_SDK_UNAVAILABLE, operation="attach_tools")`.
2. Build a `CodexToolCallHandler` whose fallback is the client's current `_approval_handler`.
3. Set `sync._approval_handler = handler.handle`.
4. Set `sync.request` to a wrapper that adds `dynamicTools` to the parameters of `thread/start`.
5. Return the handler.

`CodexToolCallHandler.handle`:
1. If `method` is not `item/tool/call`, return `fallback(method, params)`.
2. Otherwise build a `ToolCall` from `tool`, `arguments` (`None` becomes `{}`), and `callId`. A missing tool name or non-object arguments produces an error `ToolResult` immediately.
3. Submit `executor.execute_call(call)` to the loop with `asyncio.run_coroutine_threadsafe` and track the future.
4. Wait with `future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)`.
5. On timeout, cancel the future and return a timeout error. On cancellation or any other exception, return a fixed failure message. Either way, stop tracking the future.
6. Convert the `ToolResult` to `{"success", "contentItems"}`.

`CodexToolCallHandler.close`:
1. Cancel every tracked future.

#### Edge Cases & Error Handling
- **The event loop is closed:** `run_coroutine_threadsafe` raises `RuntimeError`, and the handler returns an error result.
- **The model calls a tool that isn't in the catalog** (for example, a resumed thread started with a different tool set): `ToolExecutor` returns `unknown_tool`.
- **The tool raises:** `ToolExecutor` already converts it to an error result.
- **The handler must never raise** on the reader thread. Every path returns a dict.

### 6.5 Construction wiring

**File(s):** `vidbyte/agents/codex/config.py`
**Type:** Modified

#### What it does
`CodexVidbyteTranslator.translate_agent` calls `CodexToolTranslator.translate(settings)` and stores the result in `CodexAgentTranslation.tools`.

#### Interface / API
There is no signature change.

#### Logic / Algorithm
1. After the existing validators run, compute the bridge and pass it to `CodexAgentTranslation`.

#### Edge Cases & Error Handling
- Translator errors surface through `CodexHarnessAgent.__init__`'s existing `CODEX_VIDBYTE_TRANSLATION_FAILED` wrapper.

### 6.6 Transport attach

**File(s):** `vidbyte/agents/codex/transport.py`
**Type:** Modified

#### What it does
Attaches the bridge to each run's connection and closes it when the run ends.

#### Interface / API
```python
async with sdk.async_codex(config) as client, self._attached_tools(client, request.tools):
    ...

@staticmethod
@asynccontextmanager
async def _attached_tools(client: object, tools: CodexToolBridge | None) -> AsyncIterator[None]: ...
```

#### Logic / Algorithm
1. If `tools` is `None`, yield without doing anything.
2. Otherwise run `handler = tools.attach(client, asyncio.get_running_loop())`, yield, and call `handler.close()` in a `finally` block.
3. Exit order is the attached tools first, then the client, so pending tool calls are cancelled before the process closes.

#### Edge Cases & Error Handling
- An attach failure raises `CodexAgentError`, which the existing `except CodexAgentError: raise` branch preserves.
- `fork_thread` runs no turn, so it attaches nothing.

### 6.7 Agent and fork wiring

**File(s):** `vidbyte/agents/codex/agent.py`, `vidbyte/agents/codex/fork.py`
**Type:** Modified

#### What it does
- `arun` passes `tools=self._translation.tools` into `CodexTransportRunRequest`.
- `CodexFork._prepare_child` copies `tools` and `tool_permission_policy` from the parent.

#### Logic / Algorithm
1. Each change adds one keyword argument at the existing construction site.

#### Edge Cases & Error Handling
- Fallback retries reuse the same request object through `replace(request, settings=...)`, so the tools survive model switches.

---

## 7. Data Model Changes

N/A - no persisted data. The only type changes are the in-memory dataclass fields in §6.3.

---

## 8. API Changes

N/A - no HTTP endpoints. The public Python API gains `CodexHarnessAgentSettings.tools` and `CodexHarnessAgentSettings.tool_permission_policy`. Both are additive and have defaults.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-harness-tools.md` | This design doc |
| MODIFY | `vidbyte/lib/constants/codex.py` | Dynamic-tool protocol constants |
| MODIFY | `vidbyte/lib/tools/formatter.py` | `ToolsFormatter.to_codex_tool` |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | `tools` / `tool_permission_policy` settings; bridge on translation and transport request |
| CREATE | `vidbyte/agents/codex/tools.py` | Translator, bridge, call handler |
| MODIFY | `vidbyte/agents/codex/config.py` | Build the bridge at construction |
| MODIFY | `vidbyte/agents/codex/transport.py` | Attach and close the bridge per run |
| MODIFY | `vidbyte/agents/codex/agent.py` | Pass the bridge to the transport |
| MODIFY | `vidbyte/agents/codex/fork.py` | Children inherit tools |
| MODIFY | `skills/codex-harness-roadmap/references/checklist.md` | Mark U02/U03 delivered |
| MODIFY | `README.md` | Document custom tools; drop the "does not claim tool semantics" statement |
| CREATE | `tests/test_codex_tools.py` | Feature tests |
| CREATE | `scripts/test-codex-tools.py` | Phase-5 verification runner |

---

## 10. Testing Plan

Every test runs offline. The fake SDK client reproduces the pinned SDK's private shape (`_client._sync` with `_approval_handler` and `request`) so the attach path runs for real. One contract test checks that shape against the installed `openai-codex`.

### Unit Tests
- `CodexToolTranslator` → returns `None` when `tools` is empty — [Edge Case]
- `CodexToolTranslator` → accepts a `BaseTool`, a `@tool` function, and a plain callable together, in declaration order — [Edge Case]
- `CodexToolTranslator` → rejects a name with a dot or space — [Hidden Assumption]
- `CodexToolTranslator` → rejects a 129-character name and accepts a 128-character one — [Edge Case]
- `CodexToolTranslator` → rejects `mcp` and `mcp__x` — [Hidden Assumption]
- `CodexToolTranslator` → rejects duplicate names — [Silent Failure]
- `CodexToolTranslator` → rejects tools when `experimental_api=False` — [Hidden Failure]
- `CodexHarnessAgentSettings` → rejects a list, and an item that is neither tool-shaped nor callable — [Hidden Assumption]
- `CodexHarnessAgentSettings` → rejects a non-`PermissionPolicy` policy — [Hidden Assumption]
- `ToolsFormatter.to_codex_tool` → emits `type/name/description/inputSchema` with the same schema as `to_openai_tool` — [Silent Failure]
- `CodexToolCallHandler` → runs a sync-bodied `@tool` and returns `success: true` with its output — happy path
- `CodexToolCallHandler` → runs an async `BaseTool.execute` on the agent loop, not the reader thread — [Hidden Failure]
- `CodexToolCallHandler` → unknown tool returns `success: false` — [Silent Failure]
- `CodexToolCallHandler` → a tool that raises returns `success: false` and the handler itself does not raise — [Hidden Failure]
- `CodexToolCallHandler` → a WRITE-permission tool is denied under the default policy and allowed under `PermissionPolicy.allow_all()` — [Hidden Assumption]
- `CodexToolCallHandler` → `arguments=None` is treated as `{}`; a non-object `arguments` returns an error — [Edge Case]
- `CodexToolCallHandler` → a missing `tool` returns an error — [Edge Case]
- `CodexToolCallHandler` → a timeout cancels the tool coroutine and returns an error (timeout patched small) — [Hidden Failure]
- `CodexToolCallHandler` → `close()` cancels an in-flight call — [Hidden Failure]
- `CodexToolCallHandler` → a closed event loop returns an error instead of raising — [Hidden Failure]
- `CodexToolCallHandler` → non-tool methods (approvals) are delegated to the original handler unchanged — [Silent Failure]

### Integration Tests
- `CodexTransport.run` against a fake `AsyncCodex`:
  - `thread/start` params contain `dynamicTools`.
  - A scripted `item/tool/call` sent through the installed handler during `thread.run` executes the tool.
  - The result reaches the fake server.
- **Resume path** (a `thread_id` is set): no `dynamicTools` is injected, and the handler is still installed — [Hidden Assumption]
- **No tools:** the fake client's handler and `request` are untouched after the run — [Silent Failure]
- **The SDK hook shape is missing:** the run raises `CodexAgentError` with `codex.sdk_unavailable` — [Hidden Failure]
- **Fork:** the child's settings carry the parent's `tools` and `tool_permission_policy` — [Silent Failure]
- **Contract:** the installed `openai-codex` exposes `AsyncCodex(...)._client._sync` with `_approval_handler` and `request` — [Hidden Assumption]

### Manual / QA Test Cases
1. **Given** a Codex login with usage available and an agent with `tools=(secret_hash,)`, **when** `arun("call secret_hash on 'vidbyte'")` runs, **then** the reply contains the host-salted hash, and `CodexRunResult.items` includes a `dynamicToolCall` item — [Hidden Assumption: the live model can call a dynamic tool]
2. **Given** the same agent resumed by `thread_id` in a new process, **when** the model calls the tool again, **then** it still executes, because the definitions are restored from the thread — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | `>=0.147.0,<0.148.0` (existing pin) | App-server client | Private attributes `_client._sync._approval_handler` / `.request` may move in a later release. Mitigated by the pin, the contract test, and a typed attach error. |
| Codex app-server `thread/start.dynamicTools` | experimental protocol field | Tool registration | Experimental. It requires `experimental_api=True`, the SDK default, which is validated at construction. |

---

## 12. Rollout & Deployment

- **Feature flags:** none. The feature is opt-in because `tools` defaults to `()`.
- **Breaking change:** none. Both new fields have defaults, and agents without tools take the unchanged transport path.
- **Deployment order:** N/A. This is a library release.
- **Rollback:** revert the PR. No persisted state depends on it.

---

## 13. Open Questions

- [ ] Should `before_tool_call` / `after_tool_call` middleware run around Codex tool calls now that a tool boundary exists? This is deferred to a follow-up.
- [ ] Should the timeout become a per-agent setting instead of a shared constant?
- [ ] Should the SDK upstream `approval_handler` and `dynamic_tools` options to `openai-codex` so the private-attribute access can be removed?

---

## 14. Alternatives Considered

### Alternative 1: Expose tools through an MCP server
- **What:** start a `McpStudioServer` subprocess per agent and point Codex at it through `mcp_servers` config.
- **Why rejected:** tools would run in a separate process without the agent's live objects, the permission policy would run out of process, and a subprocess lifecycle would have to be managed. Dynamic tools run in-process with the existing executor.

### Alternative 2: Build raw `thread/start` params instead of wrapping `request`
- **What:** call `client._client.thread_start({...})` directly with a hand-built dict.
- **Why rejected:** it would duplicate `AsyncCodex.thread_start`'s approval-mode, sandbox, and enum translation, and could drift from it. Wrapping `request` adds exactly one key.

### Alternative 3: Drop `AsyncCodex` and drive `CodexClient` directly
- **What:** reimplement thread and turn handling on the low-level client.
- **Why rejected:** it would rewrite the transport, result collection, and streaming for one field. The private access is smaller and isolated.

### Alternative 4: Accept any `Sequence` for `tools`
- **What:** allow lists and `Tools` catalogs directly.
- **Why rejected:** the neighboring fields (`middleware`, `capabilities`) require tuples, and frozen settings should not hold a mutable list. A `Tools` catalog can be passed as `tuple(catalog)`.

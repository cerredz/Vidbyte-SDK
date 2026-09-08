# Design Doc: Codex Native Tools

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-08
**Last Updated:** 2026-09-08

## 1. Overview
Expose a Vidbyte Tools catalog as native Codex dynamic functions. Codex waits for each item/tool/call response while Vidbyte authorizes, validates, and executes the existing tool instance.

## 2. Goals & Non-Goals
### Goals
- Register actual native function schemas and execute through ToolExecutor.
- Preserve bound reasoning tools and caller permission policy.
- Bound callback waiting, reject malformed identities, and avoid duplicate execution.
### Non-Goals
- This does not intercept Codex built-in shell, file, hosted, or MCP tools.
- No arbitrary namespace tools, automatic reasoning-tool invocation, or hidden model context replacement.
- External saved-thread resume and forks with dynamic tools are rejected until registration continuity can be verified. Initial native tool runs use fresh threads; ordinary harness behavior remains available without this option.

## 3. Background & Context
PRs #422 and #423 add event observation and continual trace updates. These cannot authorize an action before it happens. The installed openai-codex 0.147 client exposes a synchronous approval_handler that receives all native server requests. Its binary experimental protocol accepts dynamicTools on thread/start, but the Python high-level API and resume/fork schemas omit registration. Public low-level CodexClient accepts raw JSON. The callback runs on the sole reader thread and must never request another operation on the same client.

## 4. Requirements
### Functional Requirements
1. Accept a typed CodexToolBridgeSettings containing Tools and PermissionPolicy; validate before native startup.
2. Convert existing OpenAI tool schemas into native function declarations without changing argument semantics.
3. Register only on a fresh native thread with experimental API enabled; reject resume and dynamic-tool forks before side effects.
4. Dispatch item/tool/call to the existing ToolExecutor on the calling asyncio loop, preserving bound tool objects.
5. Return text contentItems and success matching ToolResult status. Malformed, denied, timed-out, or unexpected calls must not report success.
6. Cache results by call identity; reject conflicting duplicate arguments without repeating side effects.
7. Close the native client and cancel outstanding tool futures on cancellation or failure. Preserve observation and final-result translation.
### Non-Functional Requirements
Only opted-in calls use the low-level adapter. Callback timeout is finite and positive. No raw unexpected exception content is sent to the model. Idempotency memory is per turn. Cooperative cancellation cannot undo tool effects already performed; tools must not synchronously block their event loop or call the same native connection.

## 5. High-Level Design
CodexHarnessAgent forwards tool settings to CodexTransport. With tools configured, CodexNativeToolTransport owns a public CodexClient and passes a CodexToolDispatcher.handle callback at construction. A wire translator uses generated native parameter models and an explicit dynamicTools extension. The native reader callback submits ToolExecutor work onto the owning event loop and waits for its bounded response. The async transport consumes routed notifications with the existing CodexStreamRunner collector.

## 6. Detailed Design
### 6.1 Settings and translation
**Files:** lib/dataclasses/codex.py, agents/codex/config.py, agent.py, fork.py, transport.py, vidbyte/__init__.py
**Type:** Modified
#### What it does
Adds optional tool_bridge configuration and validates concrete Tools/PermissionPolicy contracts at construction. Forking an enabled catalog fails before creating a native child because this protocol cannot register replacement tools on fork.
#### Interface / API
`CodexToolBridgeSettings(tools: Tools, permission_policy: PermissionPolicy = PermissionPolicy(), timeout_seconds: float = 60.0)`
`CodexHarnessAgentSettings(tool_bridge: CodexToolBridgeSettings | None = None)`
#### Logic / Algorithm
Validate catalog and policy; forward settings to the transport; default None preserves existing calls.
#### Edge Cases & Error Handling
Reject empty catalog, invalid timeout, disabled experimental API, resume, and incompatible fork before startup. An application can create another agent with a fresh thread for another tool run.

### 6.2 Native registration and transport
**Files:** agents/codex/native_tools.py, tool_wire.py, stream.py
**Type:** New and modified
#### What it does
Owns low-level SDK lifecycle, native typed parameter serialization, and async notification streaming.
#### Interface / API
`CodexNativeToolTransport.run(request: CodexTransportRunRequest) -> CodexRunResult`
`CodexToolWire.thread(request, sdk) -> dict[str, Any]`
`CodexToolWire.turn(request, sdk, thread_id) -> dict[str, Any]`
#### Logic / Algorithm
Offload blocking SDK start, initialize, thread_start, turn_start, notification reads, and close with asyncio.to_thread. Register dynamicTools on actual thread/start JSON. Use generated field aliases, retaining explicit approval/sandbox controls and high-level default auto-review semantics. Convert all local prompt modalities through native UserInput validation. Collect one turn and unregister its queue in finally. Generalize the collector's handle type to a structural stream protocol.
#### Edge Cases & Error Handling
Unrecognized notification shapes retain existing observation policy. Failed/missing terminal events fail. Startup failure and cancellation still close the client; cleanup cancels outstanding callback futures before joining the reader.

### 6.3 Tool request enforcement
**Files:** agents/codex/tool_dispatch.py, lib/dataclasses/codex.py
**Type:** New and modified
#### What it does
Validates experimental request fields and executes a snapshotted catalog through ToolExecutor.
#### Interface / API
`CodexToolDispatcher.handle(method: str, params: dict[str, Any] | None) -> dict[str, Any]`
`CodexToolDispatcher.close() -> None`
#### Logic / Algorithm
Bind the native thread identity before starting a turn. Validate nonempty call/thread/turn/tool IDs, object arguments, and no namespace. Resolve schema from the catalog. Cache canonical request JSON and response by turn/call identity, rejecting conflicting duplicates. Submit the executor coroutine to the application loop with run_coroutine_threadsafe; cancel on timeout. Return native inputText plus success. Native approval requests are denied, unknown requests rejected, never implicitly approved.
#### Edge Cases & Error Handling
Unexpected executor exceptions return sanitized error class. Explicit ToolResult errors retain the tool's intended validation response except unexpected execution exceptions, whose raw text is withheld. Cancellation prevents a waiting callback from reporting success. The native reader serializes callbacks; tool execution must not synchronously invoke requests on that client.

## 7. Data Model Changes
### 7.1 CodexToolBridgeSettings and CodexDynamicToolCall
**Change type:** New
Frozen settings carry catalog, permission policy, timeout. A Pydantic wire record validates native call fields and aliases. Harness and transport request add optional tool_bridge. No persistent migration; rollback removes the opt-in setting.

## 8. API Changes
### 8.1 Native item/tool/call
**Change type:** New adapter integration
Request: `{arguments:{...},callId:"...",threadId:"...",turnId:"...",tool:"..."}`.
Response: `{contentItems:[{type:"inputText",text:"..."}],success:true}`. Failures use success:false; native command/file approvals return deny decisions. This is an app-server protocol integration, not a new HTTP API.

## 9. File Change Manifest
| Action | File Path | Reason |
|---|---|---|
| CREATE | docs/design/codex-native-tools.md | Design contract |
| CREATE | vidbyte/agents/codex/tool_wire.py | Native request translation |
| CREATE | vidbyte/agents/codex/tool_dispatch.py | Permission/execution callback |
| CREATE | vidbyte/agents/codex/native_tools.py | Public low-level SDK lifecycle |
| CREATE | tests/codex_native_tools/FEATURE.md | Feature contract |
| CREATE | tests/codex_native_tools/test_native_tools.py | Acceptance tests |
| CREATE | scripts/test-codex-native-tools.py | Verification runner |
| MODIFY | vidbyte/lib/dataclasses/codex.py | Settings and wire contract |
| MODIFY | vidbyte/agents/codex/config.py | Pre-start validation |
| MODIFY | vidbyte/agents/codex/agent.py | Forward tool configuration |
| MODIFY | vidbyte/agents/codex/fork.py | Reject unverifiable fork registration |
| MODIFY | vidbyte/agents/codex/transport.py | Opt-in native adapter |
| MODIFY | vidbyte/agents/codex/stream.py | Structural turn stream protocol |
| MODIFY | vidbyte/agents/codex/README.md | Interface, file index, limitations |
| MODIFY | vidbyte/__init__.py | Public settings export |

## 10. Testing Plan
### Unit Tests
- [Edge Case] Empty catalogs and zero/nonfinite/boolean timeouts reject.
- [Hidden Assumption] Invalid catalog/policy and disabled experimental API reject before startup.
- [Silent Failure] Native registration preserves schema, description, approval, sandbox, and output-schema fields.
- [Hidden Assumption] Resume and tool-enabled forks reject before any native operation.
- [Edge Case] Empty arguments and each supported input modality serialize correctly.
- [Hidden Failure] Denied permission and invalid arguments do not execute a tool.
- [Silent Failure] Success and intended tool failure preserve native success polarity and text.
- [Hidden Failure] Duplicate requests execute once; conflicting duplicates fail.
- [Hidden Assumption] Wrong thread, empty identities, namespace, unknown tool, and nonobject arguments fail without effects.
- [Hidden Failure] Timeout cancels execution; unexpected exception text is withheld.
- [Hidden Failure] Closing dispatcher cancels pending calls and rejects later calls.
### Integration Tests
- [Silent Failure] Real ToolExecutor with bound test tools, fake native client, actual SDK generated models proves registration, callback, observation, and final result path.
- [Hidden Failure] Native failure/cancellation closes the client and unregisters streams.
- [Hidden Assumption] Native approval and unknown server requests cannot bypass policy.
### Manual / QA Test Cases
Verification script runs all automated cases. Inspect the installed pinned binary's generated experimental schema for dynamicTools/item/tool/call. No paid native model calls required for acceptance; model willingness to select a tool is not an enforcement guarantee.

## 11. Dependencies & External Services
| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| openai-codex | >=0.147.0,<0.148.0 | Public CodexClient and generated models | Experimental dynamic tool protocol |
| Vidbyte ToolExecutor | Existing | Authorization and execution | Cooperative cancellation of user tools |

## 12. Rollout & Deployment
Opt-in tool_bridge; merge after #423. No changes for ordinary runs. Remove tool_bridge to roll back. Fresh-thread restriction is explicit and checked, not silently ignored.

## 13. Open Questions
Resume/fork cannot re-register dynamicTools in this pinned schema. Persistent registration continuity requires separate native evidence before support. Hooks for built-in tools and final artifact acceptance are subsequent PRs.

## 14. Alternatives Considered
Prompt-only function instructions do not enforce calls. Mutating private AsyncCodex client fields is brittle. Reimplementing JSON-RPC/process management duplicates the public SDK. A public low-level SDK adapter provides the real request boundary without either compromise.

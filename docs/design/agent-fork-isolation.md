# Design Doc: Agent Fork Isolation

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

This change fixes `BaseAgent.fork()` so forked agents are isolated execution branches instead of agents that silently rebind parent-owned stateful tools, drop MCP attachments, and share tracing identity. The implementation will clone only the SDK's agent-bound builtin tools, inherit MCP servers by replayable configuration rather than by live handles, assign a distinct fork run id with lineage metadata, support the documented `trace_option` fork override, and add direct regression coverage for the fork behavior.

---

## 2. Goals & Non-Goals

### Goals

- Prevent `BaseAgent.fork()` from rebinding parent-owned `CreateHandoffTool`, `AttachMcpServerTool`, and `AgentTool` instances to the child.
- Keep custom user tool object identity unchanged unless the SDK knows the tool has agent-bound mutable state.
- Preserve forked agent access to parent MCP attachments without sharing live MCP subprocess handles, clients, or bridged tool objects.
- Preserve pending lazy MCP server configurations on forks.
- Avoid copying already-bridged MCP tools into the child before the child owns its own MCP handle.
- Give every fork a distinct `run_id` by default and attach parent/child lineage metadata for tracing.
- Add `trace_option=` to `BaseAgent.fork()` to match `vidbyte/trace/README.md`.
- Keep existing `trace_option` inheritance when no override is supplied.
- Add direct fork regression tests covering stateful builtin tool isolation, MCP inheritance, run id lineage, and trace option override.

### Non-Goals

- Do not redesign the whole tool execution contract or add call-time agent context to every `BaseTool.execute()` call.
- Do not deep-copy arbitrary user-provided tools. Unknown custom tool state remains caller-owned.
- Do not share live MCP server handles between parent and child.
- Do not make child forks inherit `history`, `handoffs`, `last_trace`, or `last_reply` unless existing `include_history=True` asks for history.
- Do not change non-linear runtime support for continual trace options. Existing constructor validation remains authoritative.
- Do not add new package dependencies.
- Do not implement this design until it is explicitly approved.

---

## 3. Background & Context

`BaseAgent.__init__` normalizes `tools` into `self._agent_tool_items` and `self.tools`, then immediately calls `_bind_agent_tool_context()` for each tool. That binder mutates three SDK tool types: `AgentTool` receives a context getter closure, `AttachMcpServerTool` receives the owning agent, and `CreateHandoffTool` receives the owning agent. `BaseAgent.fork()` currently passes `self._agent_tool_items` directly to the child when `tools` is not overridden. Child construction therefore binds the same tool objects to the child. After a fork, the parent still holds those objects, but their internal agent references now point at the child.

The direct failure is easiest to see for `CreateHandoffTool`: a parent tool call after a fork records handoffs on the child. The same pattern applies to `AttachMcpServerTool`, where a parent tool can attach MCP servers to the child, and to `AgentTool`, where the parent delegation wrapper's context getter can point at child prompt/history after the fork.

MCP attachment has a second fork problem. `BaseAgent.__init__` always initializes `_mcp_handles` and `_pending_mcp_configs` to empty lists. Fork does not pass either through. If a parent has lazy MCP configs registered through `with_mcp_server()`, the child loses them. If the parent has already attached MCP servers, the parent has MCP bridged tools inside `_agent_tool_items`; fork currently passes those tool objects to the child, but child `_mcp_handles` is empty. That creates a stale child tool surface backed by the parent's MCP client lifetime and no child-owned handle for cleanup or card parity.

Tracing has two issues. `fork()` copies `self.runner_config.run_id` into the child, so parent and child traces can be indistinguishable when callers set a run id. If the parent has no run id, both remain `None`. `BaseAgent.generate_reply()` also does not pass `run_id` as a top-level root trace attribute today; it only passes metadata. Runtime LLM span trace inputs likewise omit the runtime's `run_id`.

Finally, `vidbyte/trace/README.md` documents `agent.fork(trace_option=TraceOption.continual(ActionTrace))`, but `BaseAgent.fork()` has no `trace_option` parameter. Existing tests include fork smoke checks in `tests/test_agent_base.py`, `tests/test_tracing.py`, `tests/test_create_handoff_tool.py`, `tests/test_handoff_agent.py`, and `tests/test_continual_trace.py`, but none cover the rebinding bug, MCP inheritance semantics, or run id uniqueness. `tests/test_continual_trace.py` only checks that an existing trace option is preserved.

---

## 4. Requirements

### Functional Requirements

1. Forking an agent with a `CreateHandoffTool` must leave the original tool bound to the parent and bind a distinct cloned tool to the child.
2. Forking an agent with an `AttachMcpServerTool` must leave the original tool bound to the parent and bind a distinct cloned tool to the child.
3. Forking an agent with an `AgentTool` must leave the original wrapper's context getter bound to the parent and bind a distinct cloned wrapper to the child.
4. Forking must not deep-copy or otherwise clone arbitrary custom user tools that do not match the SDK's known agent-bound builtin tool types.
5. Default fork tools must exclude MCP bridged tools that came from the parent's live MCP handles.
6. Default forks must inherit replayable MCP configs for both parent live handles and parent pending lazy configs.
7. Forked agents must not share live `McpServerHandle`, MCP client, MCP transport, or bridged MCP tool objects with their parent.
8. A forked agent with inherited MCP configs must connect its own MCP servers lazily through `_ensure_mcp_connected()` before its first run.
9. Fork must expose an `inherit_mcp: bool = True` option. When `False`, no live or pending parent MCP server configs are copied.
10. Fork must expose `trace_option: TraceOption | None = None`. When supplied, it overrides the parent's `_trace_option`; when omitted or `None`, existing inheritance remains unchanged.
11. Fork must expose `run_id: str | None = None`. When supplied, the child uses that run id. When omitted, the child gets a generated run id that differs from the parent run id.
12. Generated child run ids must encode enough lineage to identify the parent run when one exists, for example `parent-run:fork:<short-uuid>`.
13. Forked child metadata must include lineage fields such as `fork_parent_agent_name`, `fork_parent_run_id`, and `fork_child_run_id`, while preserving caller metadata overrides.
14. Root agent trace attributes must include `run_id`.
15. Runtime model-call trace inputs must include `run_id`.
16. `vidbyte/trace/README.md` must accurately document `agent.fork(trace_option=...)` once the code supports it.
17. Direct tests must prove that parent stateful builtin tools still mutate parent state after a fork.
18. Direct tests must prove that child stateful builtin tools mutate child state only.
19. Direct tests must prove that inherited MCP configs reconnect on the child without sharing parent handles.
20. Direct tests must prove that fork run ids differ and lineage metadata is present.
21. Direct tests must prove that `fork(trace_option=TraceOption.continual(...))` works as documented.

### Non-Functional Requirements

- Performance: fork cloning must be O(number of tools + number of MCP configs) and must not start MCP subprocesses during fork.
- Reliability: if a parent MCP config is invalid, the fork operation still succeeds; the same deferred attach error surfaces when the child run first attempts connection.
- Compatibility: existing fork callers that do not inspect object identity or run id equality should continue to work. The intentional behavior change is that child run id no longer equals parent run id by default.
- Security: inherited MCP configs may include environment mappings. They are already held in memory by `McpServerConfig`; fork copies the config object reference rather than logging or exposing env values.
- Observability: lineage metadata and `run_id` trace attributes must use existing safe trace sanitization paths.

---

## 5. High-Level Design

`BaseAgent.fork()` will stop passing the parent's tool tuple directly into `BaseAgent(...)`. Instead it will build fork tool items through a small helper that filters out parent MCP bridged tools and clones only the known SDK agent-bound builtin tool types. The child constructor will then bind the child-owned clones through the existing `_bind_agent_tool_context()` path.

MCP inheritance will be config-based. The parent will expose replayable fork configs from current live handles and pending lazy configs. After the child is constructed, fork will append those configs to `child._pending_mcp_configs`. The child will have no live MCP handles and no parent bridged tools until its own `_ensure_mcp_connected()` runs and attaches fresh handles/tools.

Run identity will be branch-oriented. `fork()` will derive a new child run id unless the caller passes one explicitly, and it will merge lineage metadata into the child. `BaseAgent.generate_reply()` and `AgentRuntime` trace input generation will include `run_id` so root traces and model-call spans can be associated with the correct branch.

```text
parent BaseAgent
  tools: [custom_tool, create_handoff(parent), mcp_bridged_tool(parent_handle)]
  live MCP handles: [github_config -> parent_handle]
  run_id: run-123

parent.fork()
  - remove parent mcp_bridged_tool from default tool list
  - clone create_handoff into create_handoff(unbound)
  - build child with [custom_tool, cloned_create_handoff]
  - child __init__ binds cloned_create_handoff(child)
  - child._pending_mcp_configs += [github_config]
  - child.run_id = run-123:fork:<uuid>
  - child.metadata includes parent/child lineage
```

---

## 6. Detailed Design

### 6.1 BaseAgent Fork Isolation

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Updates `BaseAgent.fork()` to prepare isolated child state for agent-bound tools, run ids, lineage metadata, trace option overrides, and MCP inheritance.

#### Interface / API

```python
def fork(self, *, name: str | None = None, runner: object | None = None, runners: Mapping[ModelModality | str, object] | None = None, tools: Sequence[object] | Tools | None = None, system_prompt: str | None = None, modality: ModelModality | str | None = None, metadata: dict[str, Any] | None = None, middleware: Sequence[AgentMiddleware] | None = None, context_items: Sequence[ContextItem] | None = None, context_manager: ContextManager | None = None, algorithm: ContextWindowAlgorithm | str | None = None, include_history: bool = False, inherit_mcp: bool = True, run_id: str | None = None, trace_option: TraceOption | None = None) -> BaseAgent: ...
```

New private helpers in `BaseAgent`:

```python
def _fork_tool_items(self, tools: Sequence[object] | Tools | None, *, inherit_mcp: bool) -> tuple[object, ...]: ...
def _clone_tool_for_fork(self, tool: object) -> object: ...
def _mcp_bridged_tool_set(self) -> set[object]: ...
def _fork_run_id(self, explicit_run_id: str | None) -> str: ...
def _fork_metadata(self, child_run_id: str, overrides: Mapping[str, Any] | None) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. `fork()` calls `_fork_tool_items(tools, inherit_mcp=inherit_mcp)` before constructing the child.
2. `_fork_tool_items()` resolves either explicit `tools` or the parent's `_agent_tool_items`.
3. If `tools is None` and `inherit_mcp` is true, `_fork_tool_items()` removes every object from `_mcp_bridged_tool_set()`.
4. `_mcp_bridged_tool_set()` returns the exact bridged tool objects from all parent `self._mcp_handles`.
5. `_fork_tool_items()` maps each remaining tool through `_clone_tool_for_fork()`.
6. `_clone_tool_for_fork()` creates fresh instances for `AgentTool`, `AttachMcpServerTool`, and `CreateHandoffTool`.
7. `_clone_tool_for_fork()` returns unknown custom tools unchanged.
8. `fork()` computes `child_run_id = self._fork_run_id(run_id)`.
9. `fork()` computes child metadata with lineage through `_fork_metadata(child_run_id, metadata)`.
10. `fork()` constructs `BaseAgent` with `tools=fork_tools`, `run_id=child_run_id`, and `trace_option=trace_option or self._trace_option`.
11. If `inherit_mcp` is true, `fork()` appends `self._mcp_configs_for_fork()` to `child._pending_mcp_configs`.
12. If `include_history` is true, existing behavior copies `history` after construction.
13. Fork keeps existing behavior for runner, runners, permission policy, loop settings, middleware, prompt, provider, model, modality, description, capabilities, agent metadata, context items, context manager, algorithm, tracer, output schema, and handoff spec.

#### Edge Cases & Error Handling

- Parent has no run id: child gets a generated fork id such as `fork:<uuid>`.
- Parent has run id: child gets a generated lineage id such as `<parent-run-id>:fork:<uuid>`.
- Explicit `run_id`: child uses exactly the caller-provided value but still records lineage metadata.
- Explicit `tools`: SDK agent-bound builtin tool objects are still cloned so explicit reuse cannot accidentally rebind parent-owned tools.
- `inherit_mcp=False`: no parent MCP bridged tools are included by default and no MCP configs are copied.
- Parent already has stale or closed MCP handles: fork copies their configs only; child connection success or failure is evaluated independently on child run.

### 6.2 AgentTool Clone Support

**File(s):** `vidbyte/tools/agent_tool.py`
**Type:** Modified

#### What it does

Adds a small cloning method so `BaseAgent` can make a fresh wrapper around the same delegated agent without copying the context getter closure.

#### Interface / API

```python
def clone_for_fork(self) -> AgentTool: ...
```

#### Logic / Algorithm

1. Return `AgentTool(self._agent)`.
2. Do not copy `_context_getter`.
3. Let the child `BaseAgent.__init__` bind a new context getter for the cloned wrapper.

#### Edge Cases & Error Handling

- If the delegated agent has stateful tools of its own, its internal `fork()` call will use the fixed `BaseAgent.fork()` path.
- The cloned wrapper keeps the same name and description because those derive from the delegated agent metadata.

### 6.3 CreateHandoffTool Clone Support

**File(s):** `vidbyte/tools/builtins/handoff/create.py`
**Type:** Modified

#### What it does

Adds a cloning method that returns a new unbound `CreateHandoffTool`.

#### Interface / API

```python
def clone_for_fork(self) -> CreateHandoffTool: ...
```

#### Logic / Algorithm

1. Return `CreateHandoffTool()`.
2. Do not copy `_agent`.
3. Let the child `BaseAgent.__init__` bind the clone to the child.

#### Edge Cases & Error Handling

- Parent handoff history remains parent-owned.
- Child handoff history remains empty at construction, matching existing per-run handoff semantics.

### 6.4 AttachMcpServerTool Clone Support

**File(s):** `vidbyte/tools/builtins/mcp/attach_tool.py`
**Type:** Modified

#### What it does

Adds a cloning method that returns a new unbound `AttachMcpServerTool`.

#### Interface / API

```python
def clone_for_fork(self) -> AttachMcpServerTool: ...
```

#### Logic / Algorithm

1. Return `AttachMcpServerTool()`.
2. Do not copy `_agent`.
3. Let the child `BaseAgent.__init__` bind the clone to the child.

#### Edge Cases & Error Handling

- Parent tool calls after fork attach MCP servers to the parent.
- Child tool calls after fork attach MCP servers to the child.

### 6.5 MCP Fork Config Helpers

**File(s):** `vidbyte/agents/mixins.py`
**Type:** Modified

#### What it does

Adds reusable helpers for collecting MCP server configs that can be replayed by a forked object.

#### Interface / API

```python
def _mcp_configs_for_fork(self) -> tuple[McpServerConfig, ...]: ...
def _mcp_bridged_tools_for_fork(self) -> tuple[BaseTool, ...]: ...
```

#### Logic / Algorithm

1. `_mcp_configs_for_fork()` returns `tuple(handle.config for handle in self._mcp_handles) + tuple(self._pending_mcp_configs)`.
2. `_mcp_bridged_tools_for_fork()` returns all bridged tool objects from current live handles.
3. `BaseAgent` uses these helpers during fork.

#### Edge Cases & Error Handling

- Duplicate configs are preserved in order. If a parent intentionally attached the same server twice, the fork attempts the same shape.
- No subprocess is started during config collection.

### 6.6 Trace Attribute Run IDs

**File(s):** `vidbyte/agents/base.py`, `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds run id fields to existing trace payloads so parent and child traces can be distinguished.

#### Interface / API

No public API beyond trace payload shape.

#### Logic / Algorithm

1. In `BaseAgent.generate_reply()`, add `run_id=self.runner_config.run_id` to `self._tracer.start_trace(...)`.
2. In `AgentRuntime._trace_inputs(...)`, add `"run_id": self.run_id`.
3. Keep existing safe metadata handling for metadata maps.

#### Edge Cases & Error Handling

- If `run_id` is `None`, trace payload receives `None`. Forked children should normally have generated non-`None` run ids after this change.
- Trace adapters that ignore unknown attributes continue to work.

### 6.7 Trace README Correction

**File(s):** `vidbyte/trace/README.md`
**Type:** Modified

#### What it does

Keeps the existing documented `agent.fork(trace_option=TraceOption.continual(ActionTrace))` example and, after code support lands, adds one sentence clarifying that omitting `trace_option` preserves the parent's option.

#### Interface / API

```python
agent = agent.fork(trace_option=TraceOption.continual(ActionTrace))
```

#### Logic / Algorithm

1. Confirm the documented call is now valid.
2. Clarify inheritance behavior for no override.

#### Edge Cases & Error Handling

- N/A - documentation only.

### 6.8 Fork Regression Tests

**File(s):** `tests/test_agent_fork_isolation.py`
**Type:** New file

#### What it does

Adds direct unittest coverage for the bugs described in this design.

#### Interface / API

```python
class AgentForkIsolationTests(unittest.IsolatedAsyncioTestCase): ...
```

#### Logic / Algorithm

Test cases:

1. `test_fork_clones_create_handoff_tool_binding`: construct parent with `CreateHandoffTool`, fork, execute parent tool, assert parent `handoffs` changes and child `handoffs` does not.
2. `test_child_create_handoff_tool_records_on_child`: retrieve child clone, execute it, assert child `handoffs` changes and parent `handoffs` does not.
3. `test_fork_clones_attach_mcp_server_tool_binding`: construct parent with `AttachMcpServerTool`, fork, patch parent and child `attach_mcp_server` methods, execute each tool, assert calls route to their owning agent.
4. `test_fork_clones_agent_tool_context_getter`: create an `AgentTool`, bind through parent, fork, assert parent and child wrappers are distinct and serialize their respective prompt/history contexts.
5. `test_fork_preserves_pending_mcp_configs`: parent calls `with_mcp_server`, child fork has equivalent pending config and no live handles.
6. `test_fork_replays_live_mcp_configs_without_sharing_handles`: parent attaches with mocked transport, fork, child run connects its own handle, and parent/child handles are distinct.
7. `test_fork_default_tools_exclude_parent_mcp_bridged_tools`: parent attached MCP bridged tool object is not present in child `_agent_tool_items` before child lazy connection.
8. `test_fork_run_id_is_distinct_and_records_lineage`: parent `run_id="run-123"` yields child run id not equal to parent and child metadata has lineage keys.
9. `test_fork_explicit_run_id_is_used`: `fork(run_id="child-run")` uses exactly `"child-run"`.
10. `test_fork_trace_option_override_matches_docs`: `fork(trace_option=TraceOption.continual(ActionTrace))` sets child `_trace_option`.
11. `test_trace_attributes_include_run_id`: `RecordingTracer` sees child root trace attributes include the child run id.

#### Edge Cases & Error Handling

- MCP tests use the existing fake transport pattern from `tests/test_mcp_attachment.py`; no real subprocess is started.
- Trace option tests use in-repo `ActionTrace` and do not require live model providers.

---

## 7. Data Model Changes

### 7.1 Fork Lineage Metadata

**Change type:** New in-memory metadata keys

```python
{
    "fork_parent_agent_name": "parent-agent",
    "fork_parent_run_id": "run-123",
    "fork_child_run_id": "run-123:fork:abcd1234"
}
```

**Migration strategy:** N/A - metadata is in-memory and additive.

### 7.2 Fork Run IDs

**Change type:** Modified runtime behavior

```python
parent.runner_config.run_id = "run-123"
child.runner_config.run_id = "run-123:fork:<short-uuid>"
```

**Migration strategy:** Existing callers that need a specific child id can pass `fork(run_id="...")`.

---

## 8. API Changes

### 8.1 Python API: `BaseAgent.fork`

**Change type:** Modified

**Request:**

```python
child = agent.fork(
    name="child",
    trace_option=TraceOption.continual(ActionTrace),
    inherit_mcp=True,
    run_id="optional-child-run-id",
)
```

**Response:**

```python
child.runner_config.run_id  # distinct from parent unless explicitly set equal by caller
child._trace_option         # override when trace_option is supplied, otherwise inherited
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python API only; invalid `TraceOption` values are validated by the existing `BaseAgent.__init__` path |
| N/A | MCP connection errors remain deferred until child execution, matching lazy MCP behavior |

### 8.2 Trace Payload Shape

**Change type:** Modified

**Request:**

```python
await child.generate_reply("task")
```

**Response:**

```json
{
  "run_id": "run-123:fork:abcd1234",
  "metadata": {
    "fork_parent_run_id": "run-123",
    "fork_child_run_id": "run-123:fork:abcd1234"
  }
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Trace adapters may ignore unknown attributes |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-fork-isolation.md` | Design doc for the fork bug fixes |
| MODIFY | `vidbyte/agents/base.py` | Isolate fork tools, add trace option override, generate fork run ids, add lineage metadata, include root trace run id |
| MODIFY | `vidbyte/agents/mixins.py` | Add MCP config and bridged tool helpers for fork inheritance |
| MODIFY | `vidbyte/agents/runtime.py` | Include run id in model-call trace inputs |
| MODIFY | `vidbyte/tools/agent_tool.py` | Add clone support without copying parent context getter |
| MODIFY | `vidbyte/tools/builtins/handoff/create.py` | Add clone support without copying parent agent binding |
| MODIFY | `vidbyte/tools/builtins/mcp/attach_tool.py` | Add clone support without copying parent agent binding |
| MODIFY | `vidbyte/trace/README.md` | Align fork trace-option documentation with implemented API |
| CREATE | `tests/test_agent_fork_isolation.py` | Direct regression tests for fork isolation, MCP inheritance, run id lineage, and trace option override |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `uuid` | Python standard library | Generate distinct child fork run ids | Low |
| Existing MCP attachment stack | In-repo | Replay child MCP configs lazily | Medium - invalid configs fail on child first run, as expected |
| Existing trace adapters | In-repo and optional provider packages | Receive added `run_id` attributes | Low - adapters already accept keyword attributes or payload maps |

---

## 11. Rollout & Deployment

- Feature flags: None.
- Breaking change: Small intentional behavior change. Forks no longer reuse the parent run id by default.
- Migration path: Callers that require a specific child id can pass `fork(run_id="...")`.
- Deployment order: Single SDK package release.
- Rollback procedure: Revert the implementation PR. No persisted data or migrations are involved.

---

## 12. Open Questions

- [ ] Should `fork(trace_option=None)` explicitly disable the parent's continual trace option, or should `None` mean "inherit" as designed here? Current default: `None` inherits, non-`None` overrides.
- [ ] Should `inherit_mcp=False` also preserve parent non-MCP tools exactly as currently cloned, or should it include already-bridged MCP tools as ordinary explicit tools? Current default: bridged MCP tools are excluded from default fork tools because they depend on parent live handles.
- [ ] Should generated child run ids use a different format, such as `<parent-run-id>/fork/<uuid>`? Current default: `<parent-run-id>:fork:<uuid>`.

---

## 13. Alternatives Considered

### Alternative 1: Bind Tools Through Call-Time Agent Context

- What: Change the tool execution contract so `BaseTool.execute()` receives the owning agent or execution context every time.
- Why rejected: This would touch the broad tool executor, provider tool-call path, and many tools for a narrow fork bug. Cloning the known agent-bound builtin tools fixes the issue with a smaller blast radius.

### Alternative 2: Deep-Copy Every Tool On Fork

- What: Use `copy.deepcopy()` or similar on the full tool list.
- Why rejected: User tools can hold network clients, file handles, locks, caches, or other resources that are not safe to deep-copy. The SDK only knows how to safely clone its own agent-bound builtin wrappers.

### Alternative 3: Share Parent MCP Handles With Children

- What: Copy `_mcp_handles` directly from parent to child.
- Why rejected: Parent and child would share subprocess/client lifetime and cleanup. Closing one agent could break the other, and agent cards would imply ownership that does not exist.

### Alternative 4: Drop MCP Inheritance Entirely

- What: Exclude MCP bridged tools and leave child MCP lists empty.
- Why rejected: This matches the current bug for pending configs and makes forked agents less capable than their parent. Config replay preserves capability without handle sharing.

### Alternative 5: Keep Shared Run IDs And Only Add Metadata

- What: Leave child `run_id` equal to parent but add lineage metadata.
- Why rejected: Many trace systems group or key by run id. Distinct child run ids are the clearest way to keep parent and child traces distinguishable.

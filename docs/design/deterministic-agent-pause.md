# Design Doc: Deterministic Agent Pause

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-21
**Last Updated:** 2026-08-21

---

## 1. Overview

Add a cooperative, deterministic pause to the SDK's agent API and expose the same behavior as a model-callable `pause_agent` built-in tool. `BaseAgent.pause(seconds)` will yield to the asyncio event loop for a whole-number duration, while the bound tool will validate the requested duration and enforce a developer-configured maximum. The feature is intentionally a timed wait, not durable pause/resume or external run cancellation.

---

## 2. Goals & Non-Goals

### Goals

- Add `async BaseAgent.pause(seconds: int) -> None` as the common pause API inherited by the SDK's main agent classes.
- Use `asyncio.sleep` so pausing does not block the event loop or unrelated tasks.
- Reject invalid direct API inputs, including booleans, non-integers, and negative durations.
- Add an agent-bound `PauseAgentTool` whose model-facing name is `pause_agent`.
- Require the tool to receive an integer `seconds` value and enforce a configurable maximum duration.
- Preserve task cancellation and tool timeout behavior by allowing `CancelledError` and runtime timeout exceptions to propagate.
- Export the built-in from `vidbyte.tools.builtins` so `ComponentRegistry` can discover it for YAML configuration.
- Document how a parent agent can reach a target agent that owns the tool through the existing `AgentTool` composition path.

### Non-Goals

- Do not add a cancellation token, external run-cancel API, durable pause/resume state, or a new run terminal status.
- Do not checkpoint a run before, during, or after the timed wait.
- Do not let one arbitrary agent mutate or pause another agent by passing an agent identifier to the tool.
- Do not change `AgentRuntime`, `RuntimeLimitMiddleware`, `ToolSettings`, session persistence, tracing, or multi-agent ledger state.
- Do not add a team-level tool to `MultiAgent`; its existing ownership rule remains in force.
- Do not add new feature test files in this slice; the existing SDK source and package CI gates remain required.

---

## 3. Background & Context

- `BaseAgent` is the shared public execution abstraction. `arun()` delegates to `generate_reply()`, and the concrete agent variants inherit most of their developer-facing behavior from `BaseAgent`.
- The SDK already executes tools asynchronously and applies optional `ToolSettings.tool_timeout_seconds` around ordinary tool calls.
- `vidbyte.tools.builtins` is the public built-in vocabulary scanned by `ComponentRegistry`; a class that is not exported there cannot be named by declarative configuration.
- Existing agent-bound built-ins use `bind_agent()` and are connected by `BaseAgent._bind_agent_tool_context()`.
- A timed wait is useful for deliberate pacing, coordination, and deterministic simulation, but it must remain clearly separate from the future cancellation/pause-control plumbing discussed for durable runs.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.pause(seconds)` must be an awaitable public method returning `None` after the requested whole-number duration.
2. `BaseAgent.pause()` must reject `bool`, non-`int`, and negative values with `ValueError` before sleeping.
3. A zero-second pause must be accepted and still yield through `asyncio.sleep(0)`.
4. `PauseAgentTool` must expose the stable model-facing name `pause_agent`, a required integer `seconds` argument, and `ToolPermission.SAFE`.
5. `PauseAgentTool` must be bound to a live agent before execution and must call that agent's public `pause()` method.
6. The tool must reject malformed values and values greater than its configured `max_seconds` as `ToolResult.error` results.
7. The tool must return a successful result containing the requested duration after the wait completes.
8. The tool must not catch or convert task cancellation into a normal tool result.
9. `PauseAgentTool` must be exported from `vidbyte.tools.builtins` and appear in the built-in component registry vocabulary.
10. The existing agent and tool documentation must explain the target-agent ownership model and the distinction between a timed wait and durable cancellation.

### Non-Functional Requirements

- **Performance:** The pause must suspend the current task without blocking the event loop; it must add no model or network calls.
- **Scalability:** The implementation must hold no global state and must be safe for many agent instances to pause concurrently.
- **Security:** The built-in is `SAFE`, performs no external side effect, and caps model-requested duration through `max_seconds`.
- **Observability:** The tool result metadata records the accepted `seconds` value; existing tool-call tracing and timeout handling remain authoritative.
- **Reliability:** Cancellation and configured tool timeouts must interrupt the wait instead of being swallowed or reported as successful completion.

---

## 5. High-Level Design

The shared `BaseAgent` class gains one small async method. It validates the direct caller's value, then awaits `asyncio.sleep(seconds)`. Because the concrete agent classes already inherit from `BaseAgent`, no duplicate methods or subclass overrides are needed. A task cancelled while sleeping remains cancelled because the method does not catch `asyncio.CancelledError`.

`PauseAgentTool` is an agent-bound `BaseTool`, matching the existing binding pattern used by handoff, fork, MCP, and sequential-prompt tools. The tool validates the model-facing call, checks the configured cap, and delegates to the bound agent's `pause()` method. A parent agent can invoke a target agent through the existing `AgentTool` path; the target agent's own `pause_agent` tool then pauses the target task. There is no serialized agent lookup or cross-agent mutation API.

The built-in is added to `vidbyte.tools.builtins.__all__`, which also makes it discoverable by `ComponentRegistry`. Documentation will show direct use and parent-to-target composition. Existing runtime timeout, permission, tracing, and session behavior remain unchanged.

```text
[Agent.run/arun]
        |
        v
[target agent owns PauseAgentTool]
        |
        v
[pause_agent(seconds)] --validates/caps--> [target_agent.pause(seconds)]
        |
        v
[asyncio.sleep(seconds), cancellation propagates]
```

---

## 6. Detailed Design

### 6.1 BaseAgent pause API

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds the shared cooperative wait used by all `BaseAgent` subclasses. The method is intentionally independent of model execution, checkpoints, and run status.

#### Interface / API

```python
async def pause(self, seconds: int) -> None
```

#### Logic / Algorithm

1. Reject `bool` and values that are not `int`.
2. Reject negative integers.
3. Await `asyncio.sleep(seconds)`.
4. Return `None` after the sleep completes.

#### Edge Cases & Error Handling

- `seconds=0` is valid and yields control once through `asyncio.sleep(0)`.
- A boolean is rejected even though Python makes `bool` an `int` subclass.
- `asyncio.CancelledError` is not caught, so caller cancellation propagates.
- The method does not impose the built-in's model-facing maximum; direct application calls can use any non-negative integer accepted by the API.

### 6.2 PauseAgentTool

**File(s):** `vidbyte/tools/builtins/pause.py`
**Type:** New file

#### What it does

Provides a model-callable, agent-bound wrapper around `BaseAgent.pause()`. Its constructor accepts `max_seconds: int = 60`; the positive cap is validated at construction and included in the generated input schema.

#### Interface / API

```python
class PauseAgentTool(BaseTool):
    def __init__(self, max_seconds: int = 60) -> None
    def bind_agent(self, agent: Any) -> None
    def clone_for_fork(self) -> "PauseAgentTool"
    def spec(self) -> ToolSpec
    async def execute(self, call: ToolCall) -> ToolResult
```

The model-facing contract is:

```text
name: pause_agent
required argument: seconds (integer, minimum 0, maximum max_seconds)
permission: safe
```

#### Logic / Algorithm

1. Validate and store the positive developer cap during construction.
2. Accept a live agent through `bind_agent()` when `BaseAgent` binds its tools.
3. Return an unbound clone with the same cap from `clone_for_fork()` so a child fork cannot steal the parent's binding.
4. Return a tool error if execution occurs before binding.
5. Validate that `seconds` is a non-boolean integer in the inclusive range `0..max_seconds`.
6. Await `self._agent.pause(seconds)`.
7. Return `ToolResult.success` with a human-readable confirmation and `metadata={"seconds": seconds}`.

#### Edge Cases & Error Handling

- Missing `seconds` is handled by the existing `BaseTool.validate_call()` path; direct `execute()` validation also returns a tool error for malformed input.
- Booleans, strings, floats, and negative integers return `ToolResult.error`.
- Values above `max_seconds` return `ToolResult.error` without sleeping.
- A non-positive `max_seconds` is rejected with `ValueError` at construction.
- Forked agents receive a fresh unbound tool instance; the parent and child keep independent bindings.
- Cancellation from the parent task and `ToolSettings.tool_timeout_seconds` are allowed to propagate through the awaited pause.

### 6.3 Built-in export and agent binding

**File(s):** `vidbyte/tools/builtins/__init__.py`, `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Makes the class public in the built-in namespace and connects it to the existing agent-bound tool lifecycle.

#### Interface / API

No new module-level API beyond the public import:

```python
from vidbyte.tools.builtins import PauseAgentTool
```

#### Logic / Algorithm

1. Import `PauseAgentTool` in `vidbyte.tools.builtins`.
2. Add it to `__all__`.
3. In `BaseAgent._bind_agent_tool_context()`, detect the class and call `bind_agent(self)`.
4. Leave `MultiAgent.add_tool()` unchanged; callers attach the tool to a concrete manager or worker as documented.

#### Edge Cases & Error Handling

- Registry discovery uses the class export name `PauseAgentTool`; the model-facing tool name remains `pause_agent`.
- A manually constructed tool has the same binding behavior as a YAML-constructed tool.
- A tool attached to an ordinary `BaseAgent` subclass is bound once at construction or `add_tool()` time.
- `AggregateAgent` continues to route its `tools` argument to proposer agents; callers that want proposer pauses must include the built-in in that proposer tool set.

### 6.4 Documentation

**File(s):** `vidbyte/agents/README.md`, `vidbyte/tools/README.md`
**Type:** Modified

#### What it does

Documents direct cooperative pauses, the maximum cap, the parent-to-target agent composition path, and the fact that this feature does not create durable cancellation or resume state.

#### Interface / API

Documentation-only; no additional runtime API.

#### Logic / Algorithm

1. Add a concise agent usage example importing `PauseAgentTool` from `vidbyte.tools.builtins`.
2. Explain that the tool pauses the agent to which it is attached.
3. Explain that a parent agent reaches a target through the existing `AgentTool` abstraction rather than passing an agent reference as tool input.
4. Add the pause tool to the built-in tools index.

#### Edge Cases & Error Handling

Documentation must call out the distinction between a timed wait and durable pause/resume or run cancellation so users do not infer unsupported semantics.

---

## 7. Data Model Changes

N/A - The feature stores no pause state, adds no schema, and changes no session or run model.

---

## 8. API Changes

N/A - This is an in-process Python API and built-in tool contract, not an HTTP endpoint.

The public additions are `BaseAgent.pause(seconds: int)` and `PauseAgentTool`, exported from `vidbyte.tools.builtins`. The model-facing tool contract is `pause_agent(seconds: integer)` with a developer-configured maximum.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/deterministic-agent-pause.md` | Source-of-truth design and implementation contract |
| CREATE | `vidbyte/tools/builtins/pause.py` | Agent-bound `pause_agent` built-in implementation |
| MODIFY | `vidbyte/agents/base.py` | Add inherited async pause API and bind the new agent-bound tool |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Public export and declarative component discovery |
| MODIFY | `vidbyte/agents/README.md` | Document direct and parent-to-target pause usage |
| MODIFY | `vidbyte/tools/README.md` | Add the built-in to the tool catalog and semantics note |
| DELETE | N/A | No existing file is replaced |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `asyncio` | Python 3.11+ standard library | Cooperative non-blocking sleep and cancellation propagation | Low; already used by `BaseAgent` and runtime code |
| Existing `BaseTool` / `ToolResult` contracts | Current SDK | Tool declaration, validation, and result lifecycle | Low; no new dependency or provider integration |
| Existing `ComponentRegistry` | Current SDK | Discover the exported built-in for declarative configuration | Low; export omission would make YAML references unavailable |

No external service, database, package, or migration is added.

---

## 11. Rollout & Deployment

- No feature flag is required; the API and built-in are additive and opt-in.
- Existing applications are unaffected unless they import the new class or attach the tool.
- The default tool cap is `60` seconds and can be overridden by `PauseAgentTool(max_seconds=...)` or declarative component options.
- Rollout is the normal SDK package release. No service deployment ordering or data migration is required.
- Rollback is a source/package rollback that removes the method, built-in export, tool module, and documentation; no persisted data needs cleanup.
- Verification gate: `python -m pip install -e ".[dev]"`, then `python scripts/run_ci.py` from the implementation worktree. For worktree diagnosis, follow the field-guide rule to run the source stage with `PYTHONPATH=<worktree>` and the package stage without it.

---

## 12. Open Questions

N/A - The scope decisions are resolved for this slice: the API is async, zero is a valid cooperative yield, the built-in has a positive configurable cap with a 60-second default, and durable cancellation remains a later feature.

---

## 13. Alternatives Considered

### Alternative 1: Add only a standalone stateless sleep tool

- What: Implement `pause_agent` as a tool that calls `asyncio.sleep()` directly and does not bind to an agent.
- Why rejected: It would duplicate the public API's semantics and make the requested agent ownership ambiguous. Binding lets the tool delegate to the same `BaseAgent.pause()` contract and makes parent-to-target composition explicit.

### Alternative 2: Use `time.sleep()` inside the agent API

- What: Add a synchronous blocking sleep for a simple implementation.
- Why rejected: It blocks the event loop, delaying unrelated agents and defeating the SDK's async execution model.

### Alternative 3: Add a run-control token and durable pause state now

- What: Thread cancellation/pause state through `arun()`, checkpoints, sessions, and run status.
- Why rejected: That is the larger cancellation feature from the earlier discussion. It requires control-plane semantics, persistence, interruption outcomes, and status transitions that the current request does not ask to implement.

### Alternative 4: Add per-subclass `pause()` overrides

- What: Implement separate methods on `HandoffAgent`, `AggregateAgent`, `ContinualTraceAgent`, and `MultiAgent`.
- Why rejected: All ordinary subclasses can inherit the same cooperative wait, and duplicate overrides would create inconsistent behavior. `MultiAgent`'s existing team-level tool restriction remains separate from its inherited utility method.

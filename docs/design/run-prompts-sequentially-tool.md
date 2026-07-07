# Design Doc: RunPromptsSequentially Tool

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

This feature exposes the agent's existing sequential-prompt capability (`BaseAgent.run_sequentially()` / `arun_sequentially()`) as a model-callable tool. A new builtin, `RunPromptsSequentiallyTool` (tool name `run_prompts_sequentially`), lets the model queue a list of follow-up prompts during a run. When the current agentic loop and its runtime finish, the agent automatically drains the queue, running each queued prompt as a fresh full run against the same agent (shared history, tools, and context). This turns "run these prompts in order" from a developer-only API into a self-continuation primitive the model can invoke at a self-chosen moment.

---

## 2. Goals & Non-Goals

### Goals

- Add `RunPromptsSequentiallyTool` under `vidbyte/tools/builtins/` following the established builtin-tool contract (`BaseTool`, `ToolSpec`, `ToolResult`).
- Deferred execution semantics: the tool call **queues** prompts; execution happens only after the current run's agentic loop and runtime have finished.
- Queued prompts run through `generate_reply()` in order, on the **same agent instance**, preserving `self.history` across runs — the same semantics as `arun_sequentially()`.
- Bind the live agent into the tool via the existing `BaseAgent._bind_agent_tool_context()` / `bind_agent()` pattern (precedent: `CreateHandoffTool`, `AttachMcpServerTool`).
- Allow chaining (a queued run may itself queue more prompts) with a hard safety cap to prevent unbounded self-continuation.
- Export the tool from `vidbyte.tools.builtins` and the root `vidbyte` namespace, matching `CreateHandoffTool`'s export surface.

### Non-Goals

- **Not** removing or deprecating `run_sequentially()` / `arun_sequentially()`. They remain the developer-facing API (and are covered by existing tests in `tests/test_agent_base.py` and `scripts/test-sequential-prompts.py`). The tool is the model-facing form of the same capability.
- No exposure through the MCP server (`vidbyte/mcp_server/`) in this change.
- No support guarantees for non-linear runtimes (MCTS, actor-model) beyond what `generate_reply()` already provides — the drain hook lives in `generate_reply()`, which is the shared entry point.
- No persistence of the queue across process restarts; the queue is in-memory, per-agent-instance state.
- No `AgentInput` support in tool arguments — the model supplies plain strings (JSON tool arguments cannot carry `ContextManager` objects or context items).
- No tests or verification scripts (per the design-doc-no-tests workflow).

---

## 3. Background & Context

- **Why now:** `run_sequentially()` (added with `arun_sequentially()` at `vidbyte/agents/base.py:527-541`) is only callable by the developer from outside the run. The model itself has no way to say "when I'm done with this run, continue with these follow-up tasks." This tool gives the model that continuation capability.
- **Current state:** `arun_sequentially(prompts)` loops each prompt through `generate_reply()`, appending every reply to `self.history`. `generate_reply()` already has a post-run extension point: `_run_auto_handoff(metadata)` executes after the reply is built and recorded, and mutates the reply's `metadata` dict in place (the reply dataclass is frozen but holds a live reference to the dict).
- **Established patterns this design reuses:**
  - Agent-bound builtins: `CreateHandoffTool.__init__()` starts unbound; `BaseAgent._bind_agent_tool_context()` (base.py:346-357) calls `bind_agent(self)` for recognized tool types, both at construction (base.py:195-196) and in `add_tool()`.
  - JSON-Schema tool inputs: `ToolSpec.input_schema` is used when arguments are non-scalar (`CreateHandoffTool._input_schema()`), because `ToolParameter` only models scalar prompt-rendered parameters.
  - Builtin placement rules: `skills/vidbyte-sdk/context-algorithm-to-tool.md` §6 — one file per tool under `vidbyte/tools/builtins/`, class name is the PascalCase of the file name, export from `builtins/__init__.py`.
  - `ToolPermission.SAFE`: the tool touches no filesystem/network/external state; it only mutates agent-local queue state (same rationale as context-writing tools).
- **Constraint:** `execute()` runs *inside* the agentic loop, while the runtime is mid-run. Running prompts inline would recursively re-enter the agent (and would not match the request: "keep running after the agentic loop and its current runtime has finished"). Hence the queue-then-drain design.

---

## 4. Requirements

### Functional Requirements

1. The model can call `run_prompts_sequentially(prompts=[...])` with a non-empty JSON array of non-empty strings.
2. The tool call itself completes immediately, returning a confirmation listing the queued prompts and stating that they will run in order after the current run finishes.
3. Queued prompts are NOT executed during the current agentic loop; they execute only after the current `generate_reply()` run (runtime + auto-handoff) has completed.
4. Drained prompts run strictly in queue order, each as a full `generate_reply()` run on the same agent instance, so `self.history` accumulates across all runs (identical semantics to `arun_sequentially()`).
5. A drained run may itself call `run_prompts_sequentially`; newly queued prompts are appended and drained in the same drain loop, bounded by a hard cap.
6. A hard cap (`_MAX_QUEUED_PROMPT_RUNS = 25` per outer run) bounds total drained runs; when hit, remaining prompts are discarded and the truncation is recorded in the originating reply's metadata.
7. The tool validates its arguments: missing/empty `prompts`, non-list values, non-string or blank entries, and calls exceeding the per-call limit (`max_prompts_per_call`, default 10) return `ToolResult.error` without queuing anything (all-or-nothing per call).
8. An unbound tool (never attached to an agent) returns `ToolResult.error`, matching `CreateHandoffTool` behavior.
9. If a drained run raises, draining stops, the remaining queue is cleared (no stale prompts leak into the next user-initiated run), the error is recorded in the originating reply's metadata, and the original (already successful) reply is still returned — the outer call does not raise.
10. The originating reply's metadata records `queued_prompt_runs` (count of drained runs) whenever a drain occurred; drained replies are additionally captured on `agent.last_queued_replies`.
11. `BaseAgent` exposes a public `enqueue_prompts(prompts)` method used by the tool (and available to developers), returning the new queue length.
12. The tool is constructible with zero arguments (`RunPromptsSequentiallyTool()`) and is auto-bound when passed via `tools=[...]` or `add_tool()`.
13. `RunPromptsSequentiallyTool` is importable from `vidbyte.tools.builtins` and from the root `vidbyte` namespace.

### Non-Functional Requirements

- **Performance:** `execute()` is O(n) list validation with no I/O and no LLM calls; drain cost is exactly the cost of the runs the model requested. No overhead is added to runs that never call the tool (a single guard check on an empty list).
- **Scalability:** Queue growth is bounded by `max_prompts_per_call` per call and `_MAX_QUEUED_PROMPT_RUNS` per drain.
- **Security:** `ToolPermission.SAFE`. The tool cannot execute anything by itself; it only schedules prompts on the agent it is bound to, and only the already-configured runner/tools execute them. No global mutable tool state (per `skills/vidbyte-sdk/SKILL.md`).
- **Observability:** Each drained run starts its own root `agent.run` trace via the existing tracer path in `generate_reply()` — identical to `arun_sequentially()` today. Drain outcomes (`queued_prompt_runs`, `queued_prompt_error`, `queued_prompts_truncated`) are recorded on the originating reply's metadata.
- **Reliability:** Re-entrancy guard prevents nested drains; failure of a drained run cannot corrupt or fail the already-completed originating run; the queue is always left empty when the outer call returns.

---

## 5. High-Level Design

Two components change. A new builtin tool file, `vidbyte/tools/builtins/run_prompts_sequentially.py`, implements `RunPromptsSequentiallyTool(BaseTool)`: it starts unbound, receives the live agent through `bind_agent()`, and on `execute()` validates the `prompts` array and appends it to the agent's queue via `agent.enqueue_prompts()`. The tool returns immediately with a confirmation — nothing runs inside the current loop.

`BaseAgent` gains a small amount of queue state (`_queued_prompts`, a `_draining_queued_prompts` re-entrancy flag, and `last_queued_replies`) plus two methods: public `enqueue_prompts()` and private `_drain_queued_prompts()`. The drain is invoked at the end of `generate_reply()`, immediately after `_run_auto_handoff()` — i.e., after the runtime has finished, the reply is recorded in history, and the auto-handoff (if any) has run. The drain pops prompts one at a time and awaits `self.generate_reply(prompt)` for each, so every queued prompt gets a complete, independent agentic-loop run with full runtime features (tools, middleware, context algorithms, tracing, auto-handoff). Because drained runs re-enter `generate_reply()`, the `_draining_queued_prompts` flag makes only the outermost call drain; prompts queued *during* a drained run land in the same queue and are picked up by the same outer loop, bounded by the cap.

```
model calls run_prompts_sequentially(prompts=[P1, P2])
        |                                (inside agentic loop, run A)
        v
RunPromptsSequentiallyTool.execute()
        |-- validate --> agent.enqueue_prompts([P1, P2])
        `-- ToolResult.success("Queued 2 prompts...")   <- loop continues normally
        ...
run A finishes: reply built -> history -> auto-handoff
        |
        v
generate_reply() epilogue: _drain_queued_prompts(metadata)
        |-- generate_reply(P1)   (full run B; may enqueue more)
        |-- generate_reply(P2)   (full run C)
        `-- metadata["queued_prompt_runs"] = 2; last_queued_replies = [B, C]
        |
        v
run A's reply returned to the original caller
```

Key decisions: (1) **queue-then-drain, not inline execution** — matches the stated intent ("keep running after the agentic loop and its current runtime has finished") and avoids re-entrant runtime nesting; (2) **drain lives in `generate_reply()`** so every entry point (`run`, `arun`, `arun_sequentially`, pipelines, `AgentTool` children) gets consistent behavior; (3) **drain calls `generate_reply()` directly rather than `arun_sequentially()`** — same primitive `arun_sequentially` uses internally, but a pop-one-loop lets prompts queued mid-drain join the same bounded drain, which a fixed-batch call could not; (4) **the original reply is still the returned reply** — callers of `run()`/`arun()` keep their contract; follow-up results are observable via `history`, `last_queued_replies`, and reply metadata.

---

## 6. Detailed Design

### 6.1 RunPromptsSequentiallyTool

**File(s):** `vidbyte/tools/builtins/run_prompts_sequentially.py`
**Type:** New file

#### What it does

Model-callable builtin that validates a list of prompt strings and queues them on the bound agent for sequential execution after the current run completes. Owns no execution logic itself.

#### Interface / API

```python
class RunPromptsSequentiallyTool(BaseTool):
    """Builtin tool that queues follow-up prompts to run sequentially after the current run."""

    def __init__(self, max_prompts_per_call: int = 10) -> None:
        # Starts unbound; BaseAgent attaches the live agent via bind_agent().

    def bind_agent(self, agent: Any) -> None:
        """Attach the live agent whose queue receives the prompts."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration with a JSON-Schema prompts array."""

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate the prompts array and enqueue it on the bound agent."""

    def _validate_prompts(self, args: Mapping[str, Any]) -> list[str]:
        """Return cleaned prompt strings or raise ValueError describing the problem."""

    def _render_confirmation(self, prompts: list[str], queue_size: int) -> str:
        """Render the queued-prompts confirmation the model reads back."""
```

`spec()` returns:

- `name="run_prompts_sequentially"`
- `description` — explains deferred semantics explicitly, e.g.: queue follow-up prompts that will each run as a fresh full run of this same agent, in order, **after the current run finishes**; history is preserved across runs; use for multi-phase work that should continue after the current task completes; prompts are not executed immediately.
- `permission=ToolPermission.SAFE`
- `input_schema` (the `ToolParameter` path cannot express arrays; precedent: `CreateHandoffTool`):

```python
{
    "type": "object",
    "required": ["prompts"],
    "additionalProperties": False,
    "properties": {
        "prompts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": (
                "Prompts to run in order after the current run completes. "
                "Each becomes a full agent run sharing this agent's history."
            ),
        },
    },
}
```

#### Logic / Algorithm

`execute(call)`:

1. If `self._agent is None`, return `ToolResult.error("run_prompts_sequentially", "run_prompts_sequentially is not bound to an agent.")`.
2. `_validate_prompts(call.arguments)`:
   - `prompts` must be a `list`/`tuple` (a bare string is rejected — a common model mistake, called out in the error message).
   - Must be non-empty; every entry must be a string that is non-blank after `strip()`.
   - `len(prompts) <= self._max_prompts_per_call`, else error naming the limit.
   - Returns the stripped prompt list. Any violation raises `ValueError`; `execute` catches it and returns `ToolResult.error` — nothing is queued (all-or-nothing).
3. `queue_size = self._agent.enqueue_prompts(cleaned)`.
4. Return `ToolResult.success` with `_render_confirmation(...)` as output (numbered list of queued prompts plus "they will run in order after the current run finishes") and `metadata={"queued": len(cleaned), "queue_size": queue_size}`.

#### Edge Cases & Error Handling

- **Unbound tool** → `ToolResult.error`, matching `CreateHandoffTool`.
- **`prompts` passed as a single string** → explicit error telling the model to pass a JSON array of strings.
- **Blank/whitespace entries** → error naming the offending index; nothing queued.
- **Over per-call limit** → error naming the limit; nothing queued.
- **Called when agent is not running** (developer calls `execute` directly): prompts queue and drain on the next `generate_reply()` — harmless by construction.
- The tool never raises out of `execute()`; all failures surface as `ToolResult.error` so the agentic loop continues normally.

### 6.2 BaseAgent queue state, enqueue, and drain

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Owns the pending-prompt queue, exposes `enqueue_prompts()` for the tool, binds the tool in `_bind_agent_tool_context()`, and drains the queue at the end of `generate_reply()`.

#### Interface / API

```python
_MAX_QUEUED_PROMPT_RUNS = 25  # module-level constant, near existing module constants

class BaseAgent(McpAttachableMixin):
    # __init__ additions (alongside existing run-state fields, base.py:184-194):
    #   self._queued_prompts: list[str] = []
    #   self._draining_queued_prompts: bool = False
    #   self.last_queued_replies: list[AgentMessage] = []

    def enqueue_prompts(self, prompts: Sequence[str]) -> int:
        """Append prompts to the pending sequential-run queue and return the queue length."""

    async def _drain_queued_prompts(self, metadata: dict[str, Any]) -> None:
        """Run queued prompts in order after the primary run, recording outcomes into metadata."""
```

#### Logic / Algorithm

`enqueue_prompts(prompts)`:

1. `self._queued_prompts.extend(str(p) for p in prompts)`.
2. Return `len(self._queued_prompts)`.

`_bind_agent_tool_context(tool)` (base.py:346-357) — add, following the existing isinstance chain:

```python
if isinstance(tool, RunPromptsSequentiallyTool):
    tool.bind_agent(self)
```

(local import alongside the existing `CreateHandoffTool` / `AttachMcpServerTool` local imports).

`generate_reply()` epilogue — insert after the `_run_auto_handoff` block (base.py:511-512), before `return reply`:

```python
if self._queued_prompts and not self._draining_queued_prompts:
    await self._drain_queued_prompts(metadata)
```

`_drain_queued_prompts(metadata)`:

1. Set `self._draining_queued_prompts = True`; reset `self.last_queued_replies = []`; `completed = 0`.
2. `while self._queued_prompts and completed < _MAX_QUEUED_PROMPT_RUNS:`
   a. `prompt = self._queued_prompts.pop(0)`
   b. `reply = await self.generate_reply(prompt)` — a full run; the re-entrancy flag stops the nested epilogue from draining, and any prompts it enqueues stay in `self._queued_prompts` for this loop.
   c. Append `reply` to `self.last_queued_replies`; `completed += 1`.
3. On exception from a drained run: record `metadata["queued_prompt_error"] = repr(exc)`, clear `self._queued_prompts`, and stop draining (do not re-raise — the originating run already succeeded). Mirrors `_run_auto_handoff`'s contain-the-failure pattern.
4. If the loop exits with prompts remaining (cap hit): `metadata["queued_prompts_truncated"] = len(self._queued_prompts)`, then clear the queue.
5. `finally`: `self._draining_queued_prompts = False`; if `completed`, set `metadata["queued_prompt_runs"] = completed`.

Metadata mutation after the reply is built is safe and established: `AgentMessage` is frozen but holds a reference to the live `metadata` dict, and `_run_auto_handoff(metadata)` already mutates it post-construction (base.py:565-574).

#### Edge Cases & Error Handling

- **Re-entrancy:** nested `generate_reply()` calls (drained runs, `AgentTool` children on forks) see `_draining_queued_prompts=True` on this instance and skip draining; forks get fresh state from `__init__` (`fork()` builds a new instance, so no queue leakage — see base.py:376-408).
- **Runaway self-continuation:** a drained run that always queues more prompts is stopped by `_MAX_QUEUED_PROMPT_RUNS`; the truncation is visible in metadata.
- **Drained-run failure:** contained (requirement 9); queue cleared so the next user-initiated run starts clean.
- **`last_prompt` / `last_reply` after drain:** these reflect the final drained run (they are per-run cursors updated by each `generate_reply`). The originating caller still receives the original reply object; documented behavior, consistent with how `arun_sequentially` already leaves these cursors on the last prompt.
- **Options propagation:** drained runs use default options (no `**options` forwarding from the originating call). A queued prompt is a fresh run, and forwarding call-specific options (e.g. `recipient`, `trace_metadata`) would mislabel follow-up runs.
- **`run_sequentially(["a", "b"])` where run "a" queues prompts:** the queued prompts drain fully at the end of "a"'s `generate_reply` before "b" starts — ordering stays deterministic.

### 6.3 Builtins export surface

**File(s):** `vidbyte/tools/builtins/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes the tool importable from `vidbyte.tools.builtins` and the root namespace, matching `CreateHandoffTool`'s surface.

#### Logic / Algorithm

1. `vidbyte/tools/builtins/__init__.py`: add `from vidbyte.tools.builtins.run_prompts_sequentially import RunPromptsSequentiallyTool` to the import block and `"RunPromptsSequentiallyTool"` to `__all__` (alphabetical position), and mention it in the Context Protocol Header architecture list.
2. `vidbyte/__init__.py`: add the import next to the `CreateHandoffTool` import (line 154) and the name to `__all__` (line ~293), keeping existing ordering conventions.

#### Edge Cases & Error Handling

N/A — pure re-exports; no import cycles because the tool imports only `vidbyte.tools.base` / `vidbyte.tools.types` at module level and references the agent only through the `bind_agent(Any)` runtime handle (same TYPE_CHECKING-free pattern as `CreateHandoffTool`).

---

## 7. Data Model Changes

N/A — no new dataclasses, no schema changes. The queue (`list[str]`), guard flag, and `last_queued_replies` (`list[AgentMessage]`) are plain per-instance runtime state on `BaseAgent`, alongside existing run-state fields like `handoffs` and `last_reply`. Drain outcomes reuse the existing free-form `AgentMessage.metadata` mapping.

---

## 8. API Changes

N/A — no HTTP/MCP endpoints change. Python surface additions (all additive, no breaking changes):

- `vidbyte.tools.builtins.RunPromptsSequentiallyTool` / `vidbyte.RunPromptsSequentiallyTool` (new class).
- `BaseAgent.enqueue_prompts(prompts: Sequence[str]) -> int` (new public method).
- `BaseAgent.last_queued_replies: list[AgentMessage]` (new public attribute).
- New optional reply-metadata keys: `queued_prompt_runs`, `queued_prompt_error`, `queued_prompts_truncated`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/run-prompts-sequentially-tool.md` | This design doc |
| CREATE | `vidbyte/tools/builtins/run_prompts_sequentially.py` | New `RunPromptsSequentiallyTool` builtin |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Import + `__all__` export of the new tool |
| MODIFY | `vidbyte/__init__.py` | Root-namespace export (matches `CreateHandoffTool`) |
| MODIFY | `vidbyte/agents/base.py` | Queue state, `enqueue_prompts()`, `_drain_queued_prompts()`, bind hook, `generate_reply()` epilogue |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | — | Pure in-SDK change; stdlib + existing SDK modules only | — |

---

## 11. Rollout & Deployment

- **Feature flags:** none. The behavior is inert unless a developer explicitly passes `RunPromptsSequentiallyTool()` into an agent's `tools=[...]`; agents without the tool never populate the queue, and the epilogue guard is a no-op check.
- **Breaking change:** no. All additions are new symbols/attributes; `run_sequentially()`/`arun_sequentially()` are untouched.
- **Deployment order:** single package, ships in the next SDK release.
- **Rollback:** revert the PR; no data or config migration involved.

---

## 12. Open Questions

- [ ] Should the drained follow-up replies also be returned to the *caller* somehow (e.g., a combined reply), or is `history` + `last_queued_replies` + metadata sufficient? (Design assumes sufficient — preserves the `run()`/`arun()` return contract.)
- [ ] Are the defaults right: `max_prompts_per_call=10` (tool constructor) and `_MAX_QUEUED_PROMPT_RUNS=25` (drain cap)?
- [ ] Should `AggregateAgent` (which receives the same `tools=` list, base.py:244) get explicit drain support, or is inheriting `BaseAgent.generate_reply`'s epilogue behavior acceptable? (Design assumes inherited behavior is fine.)

---

## 13. Alternatives Considered

### Alternative 1: Execute prompts inline inside `execute()`

- What: the tool awaits `agent.arun_sequentially(prompts)` (or per-prompt `generate_reply`) directly inside the tool call, like `AgentTool` does with a fork.
- Why rejected: contradicts the stated requirement — the point is to keep running *after* "the agentic loop and its current runtime has finished." Inline execution would nest full runs inside an active runtime iteration on the *same* agent (unlike `AgentTool`, which isolates via `fork()`), interleaving histories and holding the current loop's tool round open for the entire duration of all queued runs.

### Alternative 2: Drain by calling `arun_sequentially()` on the queued batch

- What: the epilogue snapshots the queue and calls `await self.arun_sequentially(batch)`.
- Why rejected: functionally close (it's the same `generate_reply` primitive underneath), but a fixed batch cannot absorb prompts queued *during* drained runs; those would sit in the queue until some later unrelated run. The pop-one `while` loop keeps chaining semantics in one bounded, deterministic drain.

### Alternative 3: Hook the drain into `run()`/`arun()` wrappers instead of `generate_reply()`

- What: only top-level entry points drain the queue.
- Why rejected: `generate_reply()` is the single funnel used by `run`, `arun`, `arun_sequentially`, pipelines, and strategies; hooking wrappers would silently drop queued prompts for callers that invoke `generate_reply()` directly. The re-entrancy flag gives the same "outermost only" effect without fragmenting the logic.

### Alternative 4: Store the queue on the tool instead of the agent

- What: the tool keeps `self._pending` and the agent polls its tool catalog for pending prompts after each run.
- Why rejected: inverts the dependency (agent must know how to introspect a specific tool's private state), breaks when the same tool instance is shared across agents, and violates the repo rule against tool-held orchestration state ("Tools are injected into agents...; avoid global mutable tool state for orchestration" — `skills/vidbyte-sdk/SKILL.md`). The `bind_agent` + agent-owned-state pattern is the established one (`CreateHandoffTool` records onto `agent.handoffs`).

---

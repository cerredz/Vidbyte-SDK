<!-- Context Protocol Header
Description:
    Design document for the agent behavior facade: post-run predicate functions
    exposed via agent.behavior that inspect what an agent did during its last run.
Purpose:
    Establishes the architecture for RunProbe, decomposed Behavior category classes,
    the Behavior facade, BaseAgent wiring, PredicateGrader bridge, and skill docs.
Architecture:
    - RunProbe: frozen snapshot of a completed agent run's observable state.
    - Behavior: facade composed of ToolBehavior, ToolArgumentBehavior, StopBehavior, HandoffBehavior.
    - BaseAgent.behavior property: lazy, invalidated per run.
    - PredicateGrader: bridges behavior predicates into EvalRunner suites.
Relations:
    Blueprint for vidbyte/evals/behavior/, vidbyte/evals/graders/predicate.py,
    tests/test_agent_behavior.py, scripts/test-agent-behavior.py, and skill docs.
-->

# Design Doc: Agent Behavior Facade (agent.behavior)

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-23
**Last Updated:** 2026-06-23

---

## 1. Overview

This feature adds a first-class **behavior introspection layer** to the Vidbyte SDK. After an agent runs, developers can inspect *what the agent did* — not just what it said — via `agent.behavior`, a lazily-built facade that exposes boolean predicates grouped by category: tool presence and outcome (`agent.behavior.tool`), tool argument inspection (`agent.behavior.tool_args`), run-level stop conditions (`agent.behavior.stop`), and handoff occurrence (`agent.behavior.handoff`). The facade reads a single `RunProbe` snapshot built from `agent.last_reply.metadata` and the agent's post-run fields. A `PredicateGrader` bridges the same probes into the existing `EvalRunner` suite pipeline so behavior assertions run at scale alongside text graders.

---

## 2. Goals & Non-Goals

### Goals

- Add a `RunProbe` frozen dataclass that captures a completed agent run's observable state (tool calls, stop reason, iterations, tokens, output, handoff, trace artifact).
- Decompose behavior predicates into category files under `vidbyte/evals/behavior/`: `ToolBehavior`, `ToolArgumentBehavior`, `StopBehavior`, `HandoffBehavior`.
- Add a `Behavior` facade class that initializes the category behaviors and is exposed via `agent.behavior`.
- Wire `BaseAgent` with a `behavior` property that lazily builds and caches the facade, invalidated at the start of each `generate_reply` call.
- Add a `PredicateGrader` that lets `EvalRunner` suites grade agent behavior alongside existing text graders.
- Export `Behavior`, `RunProbe`, and `PredicateGrader` from `vidbyte.evals` and the root `vidbyte` namespace.
- Add skill files documenting the behavior API, function catalog, and how to add new behavior categories.
- Add unit tests, a verification script, and README updates.

### Non-Goals

- No new agent run states or metadata keys — the probe reads only existing fields already populated by `AgentRuntime._runtime_metadata` and `BaseAgent` post-run bookkeeping.
- No mutation of agent state — behavior predicates are read-only.
- No content-level graders (substring, regex, schema) — those already exist in `vidbyte/evals/graders/`. The behavior layer is about *actions*, not *output text*.
- No span/tracer-level predicates (DebugTracer events) — deferred to a future extension; the probe reads run metadata only.
- No changes to non-linear runtimes (MCTS, actor model) — the behavior facade reads `last_reply.metadata` which is populated by all runtime paths, but tool-call predicates will return empty for non-text modalities (correct, since non-text modalities do not run tool loops).
- No persistence or registry for behavior results — `PredicateGrader` results flow through the existing `EvalRegistry` like any other grader.

---

## 3. Background & Context

The SDK's eval subsystem (`vidbyte/evals/`) currently grades agent *outputs* — `BaseGrader.agrade(case, actual: str)` receives only the reply text. There is no way to assert "the agent called `web_search`" or "the agent stopped on `max_iterations`" inside an eval suite or a test. Meanwhile, the agent runtime already records rich behavioral metadata in `reply.metadata` (built at `vidbyte/agents/runtime.py:1418` `_runtime_metadata`):

```
reply.metadata["tool_calls"]        -> tuple[ToolCallContext, ...]
reply.metadata["tool_call_states"]  -> tuple[str, ...]
reply.metadata["tool_call_count"]   -> int
reply.metadata["stop_reason"]       -> str
reply.metadata["iteration_count"]   -> int
reply.metadata["tokens_used"]       -> int | None
```

Each `ToolCallContext` (`vidbyte/lib/dataclasses/tools.py:179`) carries `.tool_name`, `.arguments`, `.state` (`ToolCallState`: REQUESTED/SUCCEEDED/FAILED/DENIED), `.result` (`ToolResult` with `.status` and `.output`). The agent also maintains `last_handoff`, `handoffs`, and `last_trace`. All of this is already populated; the gap is that no SDK surface makes it queryable.

This feature fills that gap with a facade that reads these fields and exposes ergonomic boolean predicates, decomposed by category into separate files under `vidbyte/evals/behavior/`.

---

## 4. Requirements

### Functional Requirements

1. `RunProbe` is a frozen dataclass that captures: `tool_calls`, `tool_call_states`, `tool_call_count`, `stop_reason`, `iteration_count`, `tokens_used`, `output`, `handoff`, `handoffs`, `trace_artifact`.
2. `RunProbe.from_agent(agent)` builds a probe from `agent.last_reply.metadata` plus `agent.last_handoff`, `agent.handoffs`, and `agent.last_trace`; when `last_reply` is `None` (no run yet), all fields default to empty/zero/`None`.
3. `RunProbe.from_reply(reply, agent=None)` builds a probe from a standalone `AgentMessage` with optional agent for handoff/trace fields.
4. `Behavior` is a facade class that takes a `BaseAgent`, lazily builds a `RunProbe`, and initializes four category behavior objects: `ToolBehavior`, `ToolArgumentBehavior`, `StopBehavior`, `HandoffBehavior`.
5. `Behavior.probe` returns the cached `RunProbe`, building it on first access.
6. `Behavior.tool` returns a `ToolBehavior` instance; `Behavior.tool_args` returns `ToolArgumentBehavior`; `Behavior.stop` returns `StopBehavior`; `Behavior.handoff` returns `HandoffBehavior`.
7. `BaseAgent.behavior` is a property that returns a cached `Behavior` instance, building it on first access.
8. `BaseAgent` invalidates the cached `Behavior` at the start of `generate_reply` so each run gets a fresh probe.
9. `ToolBehavior` exposes: `called_tool`, `not_called_tool`, `called_all_tools`, `called_any_tool`, `called_no_tools`, `called_only_tools`, `called_tools_in_order`, `tool_call_count`, `called_tool_names`, `tool_succeeded`, `tool_failed`, `tool_denied`, `all_tool_calls_succeeded`, `tool_returned_containing`, `tool_returned_matching`.
10. `ToolArgumentBehavior` exposes: `tool_called_with`, `tool_called_with_exact`, `tool_never_called_with`, `tool_called_with_matching`.
11. `StopBehavior` exposes: `stop_reason`, `stopped_on`, `stopped_normally`, `did_not_hit_max_iterations`, `did_not_hit_max_tool_calls`, `did_not_hit_max_tokens`, `iteration_count`, `total_tool_calls`, `tokens_used`, `did_not_exceed_tokens`.
12. `HandoffBehavior` exposes: `handoff_occurred`, `handoff_is_filled`, `handoff_count`, `handoff_has_section`, `handoff_section_contains`.
13. `PredicateGrader(BaseGrader)` accepts a `Callable[[RunProbe], bool]` predicate and an optional `name`; `EvalRunner` detects graders implementing `agrade_with_probe` and calls that method with the probe instead of `agrade`.
14. `EvalRunner._invoke_target` builds a `RunProbe` from the forked agent and passes it to graders that implement `agrade_with_probe`.
15. `RunProbe`, `Behavior`, and `PredicateGrader` are exported from `vidbyte.evals` and `vidbyte`.
16. Skill files document the behavior API, function catalog, architecture, and how to add new behavior categories.

### Non-Functional Requirements

- **Backward compatible:** agents without any behavior access are unaffected; the `behavior` property is lazy and adds zero overhead until accessed.
- **Read-only:** behavior predicates never mutate agent state, run state, or reply metadata.
- **No new dependencies:** uses only existing SDK dataclasses and stdlib.
- **Frozen dataclass:** `RunProbe` is frozen with `slots=True`, matching the repo's dataclass conventions.
- **Thread safety:** the `Behavior` cache is per-agent-instance; no shared mutable state.
- **Performance:** `RunProbe.from_agent` is O(1) field reads; predicate methods are O(n) in tool call count, which is bounded by `max_tool_calls`.

---

## 5. High-Level Design

The behavior layer lives under `vidbyte/evals/behavior/` and consists of a snapshot dataclass (`RunProbe`), four category behavior classes, and a composing facade (`Behavior`). The facade is exposed on `BaseAgent` via a `behavior` property that lazily builds and caches the facade, invalidating it at the start of each run so the next access reflects the latest run's data.

```text
[User] -> agent.arun(prompt)
           -> BaseAgent.generate_reply()
              -> invalidates _behavior_view
              -> AgentRuntime populates reply.metadata["tool_calls", "stop_reason", ...]
           -> agent.behavior  (property)
              -> Behavior(agent)  (lazy, cached)
                 -> RunProbe.from_agent(agent)  (lazy, cached)
                 -> self.tool      = ToolBehavior(self)
                 -> self.tool_args = ToolArgumentBehavior(self)
                 -> self.stop      = StopBehavior(self)
                 -> self.handoff   = HandoffBehavior(self)

[Eval Suite] -> EvalRunner._invoke_target
                 -> forked.arun(prompt)
                 -> RunProbe.from_agent(forked)
                 -> if grader has agrade_with_probe: call it with probe
                 -> else: call agrade(case, actual) as today
```

**Key decisions:**

- *Facade with sub-properties* (`agent.behavior.tool.called_tool(...)`) rather than flat methods on `Behavior` or a mixin on `BaseAgent`: keeps `BaseAgent` API surface clean, avoids method name collisions (BaseAgent already has `handoff()`, `tool_specs()`, `add_tool()`), and makes the category decomposition visible in the access pattern.
- *Lazy probe with run-start invalidation*: the probe is only built when `agent.behavior` is first accessed after a run, and is invalidated at the start of `generate_reply` so stale data is never served.
- *`reply.metadata["tool_calls"]` as source of truth*: this is per-run and always correct for text modality. No fallback to `agent._tool_call_contexts` (which accumulates across runs and would serve stale data on multi-run agents).
- *Duck-typed `agrade_with_probe` on PredicateGrader*: the runner checks `hasattr(grader, "agrade_with_probe")` rather than `isinstance`, so any grader can opt into probe access without changing `BaseGrader`'s abstract signature.

---

## 6. Detailed Design

### 6.1 RunProbe

**File(s):** `vidbyte/evals/behavior/probe.py`
**Type:** New file

#### What it does

Frozen snapshot dataclass capturing a completed agent run's observable state. Built from `agent.last_reply.metadata` and the agent's post-run fields.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class RunProbe:
    tool_calls: tuple[ToolCallContext, ...]
    tool_call_states: tuple[str, ...]
    tool_call_count: int
    stop_reason: str
    iteration_count: int
    tokens_used: int | None
    output: str
    handoff: Handoff | None
    handoffs: tuple[Handoff, ...]
    trace_artifact: Mapping[str, Any] | None

    @classmethod
    def from_agent(cls, agent: BaseAgent) -> RunProbe: ...
    @classmethod
    def from_reply(cls, reply: AgentMessage, agent: BaseAgent | None = None) -> RunProbe: ...
```

#### Logic / Algorithm

1. `from_agent`: reads `agent.last_reply`; if `None`, returns a probe with all-empty/zero fields. If present, reads `reply.metadata` for `tool_calls`, `stop_reason`, `iteration_count`, `tokens_used`, `tool_call_count`; reads `agent.last_handoff`, `tuple(agent.handoffs)`, `agent.last_trace` for handoff/trace fields.
2. `from_reply`: same metadata extraction from a standalone `AgentMessage`; if `agent` is provided, also reads handoff/trace fields; otherwise handoff/trace default to `None`/empty.
3. `tool_call_states` is derived from `tool_calls` if not present in metadata: `tuple(c.state.value for c in tool_calls)`.
4. `tool_call_count` defaults to `len(tool_calls)` if not in metadata.

#### Edge Cases & Error Handling

- `last_reply is None` (no run yet) → all fields empty/zero/`None`; predicates return `False`/`0`.
- `reply.metadata` missing `tool_calls` key (non-text modality) → `tool_calls = ()`; correct since non-text modalities don't run tool loops.
- `reply.metadata` missing `stop_reason` → defaults to `"final_response"`.
- `reply.metadata` missing `iteration_count` → defaults to `0`.
- `agent.last_trace is None` (no continual tracing) → `trace_artifact = None`.

---

### 6.2 ToolBehavior

**File(s):** `vidbyte/evals/behavior/tool.py`
**Type:** New file

#### What it does

Predicates over tool presence (category A) and tool outcome/state (category B). Reads `probe.tool_calls` and each call's `.state` / `.result`.

#### Interface / API

```python
class ToolBehavior:
    def __init__(self, behavior: Behavior) -> None: ...

    # Category A — presence / set membership
    def called_tool(self, name: str) -> bool: ...
    def not_called_tool(self, name: str) -> bool: ...
    def called_all_tools(self, names: Sequence[str]) -> bool: ...
    def called_any_tool(self, names: Sequence[str]) -> bool: ...
    def called_no_tools(self) -> bool: ...
    def called_only_tools(self, names: Sequence[str]) -> bool: ...
    def called_tools_in_order(self, names: Sequence[str]) -> bool: ...
    def tool_call_count(self, name: str) -> int: ...
    def called_tool_names(self) -> tuple[str, ...]: ...

    # Category B — outcome / state
    def tool_succeeded(self, name: str) -> bool: ...
    def tool_failed(self, name: str) -> bool: ...
    def tool_denied(self, name: str) -> bool: ...
    def all_tool_calls_succeeded(self) -> bool: ...
    def tool_returned_containing(self, name: str, substring: str) -> bool: ...
    def tool_returned_matching(self, name: str, pattern: str) -> bool: ...
```

#### Logic / Algorithm

1. `called_tool(name)`: `any(c.tool_name == name for c in self._calls)`.
2. `not_called_tool(name)`: `not self.called_tool(name)`.
3. `called_all_tools(names)`: every name in `names` appears in `{c.tool_name for c in self._calls}`.
4. `called_any_tool(names)`: any name in `names` appears in call names.
5. `called_no_tools()`: `len(self._calls) == 0`.
6. `called_only_tools(names)`: every call's `tool_name` is in `set(names)` (subset-closed; extras are allowed only if in `names`).
7. `called_tools_in_order(names)`: the call names contain `names` as a subsequence (order preserved, gaps allowed).
8. `tool_call_count(name)`: `sum(1 for c in self._calls if c.tool_name == name)`.
9. `called_tool_names()`: `tuple(dict.fromkeys(c.tool_name for c in self._calls))` (ordered unique).
10. `tool_succeeded(name)`: `any(c.tool_name == name and c.state == ToolCallState.SUCCEEDED for c in self._calls)`.
11. `tool_failed(name)`: `any(c.tool_name == name and c.state == ToolCallState.FAILED for c in self._calls)`.
12. `tool_denied(name)`: `any(c.tool_name == name and c.state == ToolCallState.DENIED for c in self._calls)`.
13. `all_tool_calls_succeeded()`: `all(c.state == ToolCallState.SUCCEEDED for c in self._calls)`; vacuously `True` when empty.
14. `tool_returned_containing(name, substring)`: any call to `name` with `.result` non-None and `substring in c.result.output` (case-sensitive).
15. `tool_returned_matching(name, pattern)`: any call to `name` with `.result` non-None and `re.search(pattern, c.result.output)`.

#### Edge Cases & Error Handling

- Empty `tool_calls` → `called_tool` returns `False`, `called_no_tools` returns `True`, `all_tool_calls_succeeded` returns `True` (vacuous), `called_all_tools([])` returns `True` (vacuous).
- `called_only_tools([])` with non-empty calls → `False` (calls exist but none allowed).
- Call with `.result is None` → `tool_returned_containing` / `tool_returned_matching` skip that call.
- Invalid regex in `tool_returned_matching` → `re.error` propagates (caller's bug).

---

### 6.3 ToolArgumentBehavior

**File(s):** `vidbyte/evals/behavior/tool_arguments.py`
**Type:** New file

#### What it does

Predicates over tool call arguments (category C). Reads `probe.tool_calls` and each call's `.arguments` mapping.

#### Interface / API

```python
class ToolArgumentBehavior:
    def __init__(self, behavior: Behavior) -> None: ...

    def tool_called_with(self, name: str, **args: Any) -> bool: ...
    def tool_called_with_exact(self, name: str, args: Mapping[str, Any]) -> bool: ...
    def tool_never_called_with(self, name: str, **args: Any) -> bool: ...
    def tool_called_with_matching(self, name: str, arg_name: str, predicate: Callable[[Any], bool]) -> bool: ...
```

#### Logic / Algorithm

1. `tool_called_with(name, **args)`: any call to `name` where `args` is a subset of `c.arguments` (all key-value pairs in `args` match `c.arguments`). Value comparison uses `==`.
2. `tool_called_with_exact(name, args)`: any call to `name` where `dict(c.arguments) == dict(args)`.
3. `tool_never_called_with(name, **args)`: `not self.tool_called_with(name, **args)`.
4. `tool_called_with_matching(name, arg_name, predicate)`: any call to `name` where `arg_name` is in `c.arguments` and `predicate(c.arguments[arg_name])` is `True`.

#### Edge Cases & Error Handling

- Empty `args` kwargs in `tool_called_with` → vacuously `True` if the tool was called at all (every call's args is a superset of `{}`).
- `arg_name` not in `c.arguments` → that call is skipped in `tool_called_with_matching`.
- `predicate` raises → exception propagates (caller's bug).

---

### 6.4 StopBehavior

**File(s):** `vidbyte/evals/behavior/stop.py`
**Type:** New file

#### What it does

Predicates over run-level stop conditions (category D). Reads `probe.stop_reason`, `probe.iteration_count`, `probe.tokens_used`, `probe.tool_call_count`.

#### Interface / API

```python
class StopBehavior:
    def __init__(self, behavior: Behavior) -> None: ...

    def stop_reason(self) -> str: ...
    def stopped_on(self, reason: str) -> bool: ...
    def stopped_normally(self) -> bool: ...
    def did_not_hit_max_iterations(self) -> bool: ...
    def did_not_hit_max_tool_calls(self) -> bool: ...
    def did_not_hit_max_tokens(self) -> bool: ...
    def iteration_count(self) -> int: ...
    def total_tool_calls(self) -> int: ...
    def tokens_used(self) -> int | None: ...
    def did_not_exceed_tokens(self, limit: int) -> bool: ...
```

#### Logic / Algorithm

1. `stop_reason()`: returns `probe.stop_reason` (raw string).
2. `stopped_on(reason)`: `probe.stop_reason == reason`.
3. `stopped_normally()`: `probe.stop_reason == AgentStopReason.FINAL_RESPONSE.value` (i.e. `"final_response"`).
4. `did_not_hit_max_iterations()`: `probe.stop_reason != AgentStopReason.MAX_ITERATIONS.value`.
5. `did_not_hit_max_tool_calls()`: `probe.stop_reason != AgentStopReason.MAX_TOOL_CALLS.value`.
6. `did_not_hit_max_tokens()`: `probe.stop_reason != AgentStopReason.MAX_TOKENS.value`.
7. `iteration_count()`: returns `probe.iteration_count`.
8. `total_tool_calls()`: returns `probe.tool_call_count`.
9. `tokens_used()`: returns `probe.tokens_used`.
10. `did_not_exceed_tokens(limit)`: `probe.tokens_used is None or probe.tokens_used <= limit`.

#### Edge Cases & Error Handling

- `tokens_used is None` (provider didn't report usage) → `did_not_exceed_tokens` returns `True` (can't exceed when unknown).
- Unknown `stop_reason` string → `stopped_on` returns `False` for known reasons; `stopped_normally` returns `False`.

---

### 6.5 HandoffBehavior

**File(s):** `vidbyte/evals/behavior/handoff.py`
**Type:** New file

#### What it does

Predicates over handoff occurrence (category E). Reads `probe.handoff` (the last handoff) and `probe.handoffs` (all handoffs in the run).

#### Interface / API

```python
class HandoffBehavior:
    def __init__(self, behavior: Behavior) -> None: ...

    def handoff_occurred(self) -> bool: ...
    def handoff_is_filled(self) -> bool: ...
    def handoff_count(self) -> int: ...
    def handoff_has_section(self, section_title: str) -> bool: ...
    def handoff_section_contains(self, section_title: str, substring: str) -> bool: ...
```

#### Logic / Algorithm

1. `handoff_occurred()`: `probe.handoff is not None`.
2. `handoff_is_filled()`: `probe.handoff is not None and probe.handoff.is_filled`.
3. `handoff_count()`: `len(probe.handoffs)`.
4. `handoff_has_section(section_title)`: `probe.handoff is not None and section_title in probe.handoff.sections`.
5. `handoff_section_contains(section_title, substring)`: `probe.handoff is not None and section_title in probe.handoff.sections and substring in probe.handoff.sections[section_title]`.

#### Edge Cases & Error Handling

- `probe.handoff is None` → all predicates return `False`/`0` except `handoff_count` which returns `len(probe.handoffs)` (may be `0`).
- `section_title` not in sections → `handoff_has_section` returns `False`; `handoff_section_contains` returns `False`.
- `probe.handoffs` is empty but `probe.handoff` is set → `handoff_count` returns `0` but `handoff_occurred` returns `True` (the last handoff may not be in the list if `record_handoff` wasn't called).

---

### 6.6 Behavior Facade

**File(s):** `vidbyte/evals/behavior/behavior.py`
**Type:** New file

#### What it does

Composing facade that lazily builds a `RunProbe` from a `BaseAgent` and initializes the four category behavior objects. Exposed via `agent.behavior`.

#### Interface / API

```python
class Behavior:
    def __init__(self, agent: BaseAgent) -> None: ...

    @property
    def probe(self) -> RunProbe: ...

    @property
    def tool(self) -> ToolBehavior: ...

    @property
    def tool_args(self) -> ToolArgumentBehavior: ...

    @property
    def stop(self) -> StopBehavior: ...

    @property
    def handoff(self) -> HandoffBehavior: ...
```

#### Logic / Algorithm

1. `__init__`: stores `self._agent = agent`; initializes `self._probe = None`; builds `self._tool = ToolBehavior(self)`, `self._tool_args = ToolArgumentBehavior(self)`, `self._stop = StopBehavior(self)`, `self._handoff = HandoffBehavior(self)`.
2. `probe` property: if `self._probe is None`, builds `self._probe = RunProbe.from_agent(self._agent)`; returns `self._probe`.
3. `tool` / `tool_args` / `stop` / `handoff` properties: return the pre-built category objects. Each category object accesses `self._behavior.probe` on demand.

#### Edge Cases & Error Handling

- Agent has no `last_reply` (never run) → `probe` builds a probe with all-empty fields; all predicates return `False`/`0`.
- Agent run raised an exception → `last_reply` was never set; probe is empty (same as above).

---

### 6.7 BaseAgent Wiring

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds the `behavior` property to `BaseAgent` and invalidates the cache at the start of each run.

#### Logic / Algorithm

1. In `__init__`, add `self._behavior_view: Behavior | None = None` to the initialization block (near `self.last_reply = None` at line 193).
2. Add a `behavior` property:
   ```python
   @property
   def behavior(self) -> Behavior:
       if self._behavior_view is None:
           self._behavior_view = Behavior(self)
       return self._behavior_view
   ```
3. At the top of `generate_reply` (after `self._active_prompt = prompt` at line 421, before the runtime call), set `self._behavior_view = None` to invalidate the cache.
4. Import `Behavior` from `vidbyte.evals.behavior` at the top of the file (or use a lazy import inside the property to avoid circular imports — see Edge Cases).

#### Edge Cases & Error Handling

- **Circular import risk:** `vidbyte/agents/base.py` importing from `vidbyte/evals/behavior/` which imports `vidbyte/lib/dataclasses/tools.py` (ToolCallContext) and `vidbyte/context/handoff/base.py` (Handoff). Neither of these imports `vidbyte/agents/base.py`, so there is no cycle. Use a top-level import. If a cycle is discovered during implementation, fall back to a lazy import inside the `behavior` property.
- `fork()` does not need to forward `_behavior_view` — the fork starts with `None` and builds its own on first access.

---

### 6.8 PredicateGrader

**File(s):** `vidbyte/evals/graders/predicate.py`
**Type:** New file

#### What it does

Bridges behavior predicates into the `EvalRunner` suite pipeline. Accepts a `Callable[[RunProbe], bool]` and implements `agrade_with_probe` so the runner can pass the probe.

#### Interface / API

```python
class PredicateGrader(BaseGrader):
    name: ClassVar[str] = "predicate"

    def __init__(self, predicate: Callable[[RunProbe], bool], *, name: str = "predicate") -> None: ...

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult: ...
    async def agrade_with_probe(self, case: EvalCase, actual: str, probe: RunProbe) -> GraderResult: ...
```

#### Logic / Algorithm

1. `__init__`: stores `self._predicate = predicate`; sets `self.name = name`.
2. `agrade(case, actual)`: fallback when called outside the runner — returns `GraderResult(0.0, False, "PredicateGrader requires a RunProbe; use EvalRunner.")`.
3. `agrade_with_probe(case, actual, probe)`: calls `self._predicate(probe)` in a try/except; on `True` returns `GraderResult(1.0, True, self.name)`; on `False` returns `GraderResult(0.0, False, self.name)`; on exception returns `GraderResult(0.0, False, f"Predicate error: {exc}")`.

#### Edge Cases & Error Handling

- Predicate raises → grader returns a failed result with the error message (does not crash the suite; consistent with existing grader error handling in `runner.py:85-91`).
- Called via standard `agrade` (not the runner) → returns a descriptive failed result so misuse is visible.

---

### 6.9 EvalRunner Integration

**File(s):** `vidbyte/evals/runner.py`
**Type:** Modified

#### What it does

Detects graders that implement `agrade_with_probe` and passes the `RunProbe` to them.

#### Logic / Algorithm

1. In `_invoke_target`, when the target is a `BaseAgent` (line 107-114), after `forked.arun(...)` returns the reply, build `probe = RunProbe.from_agent(forked)`.
2. Store the probe in the returned metadata: `metadata["probe"] = probe`.
3. In `_run_single_case` (line 73-101), after `self._invoke_target(...)` returns `(actual, metadata)`:
   - Extract `probe = metadata.get("probe")`.
   - If `probe is not None and hasattr(grader, "agrade_with_probe")`: call `grader_result = await grader.agrade_with_probe(case, actual, probe)`.
   - Else: call `grader_result = await grader.agrade(case, actual)` (existing path).
4. For non-agent targets (runners), `metadata` has no `"probe"` key, so the standard `agrade` path is used — no behavior change.

#### Edge Cases & Error Handling

- Non-agent target → no probe built; `PredicateGrader.agrade` returns its fallback failed result (visible misuse).
- Agent target but `PredicateGrader` not used → standard `agrade` path; no overhead from probe building (probe is still built and stored in metadata, but only ~O(1) field reads).
- Agent target with `last_reply` missing tool metadata (non-text modality) → probe has empty tool calls; `PredicateGrader` predicate sees empty tool_calls (correct).

---

### 6.10 Package Exports

**File(s):** `vidbyte/evals/behavior/__init__.py`, `vidbyte/evals/__init__.py`, `vidbyte/evals/graders/__init__.py`, `vidbyte/__init__.py`
**Type:** New / Modified

#### Logic / Algorithm

1. `vidbyte/evals/behavior/__init__.py`: exports `RunProbe`, `Behavior`, `ToolBehavior`, `ToolArgumentBehavior`, `StopBehavior`, `HandoffBehavior`.
2. `vidbyte/evals/graders/__init__.py`: adds `PredicateGrader` to imports and `__all__`.
3. `vidbyte/evals/__init__.py`: adds `Behavior`, `RunProbe`, `PredicateGrader` to imports and `__all__`.
4. `vidbyte/__init__.py`: adds `Behavior`, `RunProbe`, `PredicateGrader` to the evals import block and `__all__`.

---

### 6.11 Skill Files

**File(s):** `skills/vidbyte-sdk/agent-behavior.md`, `skills/usage/agent-behavior.md`
**Type:** New files

#### What they do

1. `skills/vidbyte-sdk/agent-behavior.md`: SDK developer reference — architecture, function catalog by category, invariants, how to add new behavior categories. Follows the `continual-tracing.md` pattern (Context Protocol Header, architecture, invariants, verify section).
2. `skills/usage/agent-behavior.md`: user-facing usage guide — how to call `agent.behavior.*`, examples per category, how to use `PredicateGrader` in eval suites. Follows the `usage/create_agent.md` pattern.

---

## 7. Data Model Changes

N/A — no database, persistence, or schema changes. `RunProbe` is an in-memory frozen dataclass. `PredicateGrader` results flow through the existing `EvalRegistry` schema unchanged (grader results are stored as `score`, `passed`, `reason` strings).

---

## 8. API Changes

No HTTP endpoints. SDK API additions:

### 8.1 `BaseAgent.behavior` property

**Change type:** New (additive)

**Returns:** `Behavior` — a facade with `.tool`, `.tool_args`, `.stop`, `.handoff` sub-properties, each exposing boolean predicate methods.

### 8.2 `RunProbe` dataclass

**Change type:** New

**Construction:** `RunProbe.from_agent(agent)` or `RunProbe.from_reply(reply, agent=None)`.

### 8.3 `PredicateGrader(BaseGrader)`

**Change type:** New

**Construction:** `PredicateGrader(predicate, *, name="predicate")`.

**Usage in suites:** `EvalCase(prompt="...", grader=PredicateGrader(lambda p: p.tool_calls and any(c.tool_name == "search" for c in p.tool_calls)))`

### 8.4 EvalRunner probe attachment

**Change type:** Modified

**Behavior:** `EvalRunner` now builds a `RunProbe` per case (when target is a `BaseAgent`) and stores it in `EvalResult.metadata["probe"]`; graders implementing `agrade_with_probe` receive it.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/evals/behavior/__init__.py` | Package exports for behavior module |
| CREATE | `vidbyte/evals/behavior/probe.py` | `RunProbe` frozen dataclass with `from_agent`/`from_reply` |
| CREATE | `vidbyte/evals/behavior/behavior.py` | `Behavior` facade composing category behaviors |
| CREATE | `vidbyte/evals/behavior/tool.py` | `ToolBehavior` — presence (A) + outcome/state (B) |
| CREATE | `vidbyte/evals/behavior/tool_arguments.py` | `ToolArgumentBehavior` — argument predicates (C) |
| CREATE | `vidbyte/evals/behavior/stop.py` | `StopBehavior` — stop reason / iterations / tokens (D) |
| CREATE | `vidbyte/evals/behavior/handoff.py` | `HandoffBehavior` — handoff predicates (E) |
| CREATE | `vidbyte/evals/graders/predicate.py` | `PredicateGrader` bridging probes into eval suites |
| CREATE | `tests/test_agent_behavior.py` | Unit + integration tests for all behavior predicates |
| CREATE | `scripts/test-agent-behavior.py` | Phase 5 verification script |
| CREATE | `skills/vidbyte-sdk/agent-behavior.md` | SDK developer reference for behavior API |
| CREATE | `skills/usage/agent-behavior.md` | User-facing usage guide with examples |
| MODIFY | `vidbyte/agents/base.py` | Add `behavior` property + cache invalidation in `generate_reply` |
| MODIFY | `vidbyte/evals/runner.py` | Build probe for agent targets; dispatch to `agrade_with_probe` |
| MODIFY | `vidbyte/evals/graders/__init__.py` | Export `PredicateGrader` |
| MODIFY | `vidbyte/evals/__init__.py` | Export `Behavior`, `RunProbe`, `PredicateGrader` |
| MODIFY | `vidbyte/__init__.py` | Root-level exports for `Behavior`, `RunProbe`, `PredicateGrader` |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add rule for behavior module location + link to agent-behavior.md |
| MODIFY | `skills/sdk/SKILL.md` | Add "Agent Behavior" row to the SDK Developer Reference table |

---

## 10. Testing Plan

### Unit Tests (`tests/test_agent_behavior.py`)

**RunProbe:**
- `from_agent` with a populated `last_reply` extracts all metadata fields correctly — [Hidden Assumption] (assumes metadata keys match runtime output)
- `from_agent` with `last_reply = None` returns all-empty/zero probe — [Edge Case]
- `from_agent` when `reply.metadata` lacks `tool_calls` (non-text modality) returns empty `tool_calls` — [Edge Case]
- `from_agent` when `reply.metadata` lacks `stop_reason` defaults to `"final_response"` — [Silent Failure] (catches wrong default that makes `stopped_normally` lie)
- `from_agent` reads `agent.last_handoff` and `agent.handoffs` independently — [Hidden Assumption] (assumes they can diverge)
- `from_reply` without an agent returns `handoff=None` and `handoffs=()` — [Edge Case]
- `tool_call_states` is derived from `tool_calls` when not in metadata — [Silent Failure] (catches states not matching actual call states)

**ToolBehavior (Category A — presence):**
- `called_tool` returns `True` when the tool was called, `False` when not — [Edge Case]
- `not_called_tool` is the exact negation of `called_tool` — [Silent Failure]
- `called_all_tools` with all present returns `True`; with one missing returns `False` — [Edge Case]
- `called_all_tools([])` returns `True` (vacuous) — [Edge Case]
- `called_any_tool` with one match returns `True`; with no matches returns `False` — [Edge Case]
- `called_no_tools` returns `True` when no calls, `False` when calls exist — [Edge Case]
- `called_only_tools` returns `True` when all calls are in the set; `False` when an extra call is outside — [Silent Failure] (catches "any" instead of "only" implementation)
- `called_only_tools([])` with non-empty calls returns `False` — [Edge Case]
- `called_tools_in_order` returns `True` for a valid subsequence; `False` when order is wrong — [Silent Failure] (catches "set" instead of "subsequence" implementation)
- `called_tools_in_order([])` returns `True` (vacuous) — [Edge Case]
- `tool_call_count` returns correct count for multiple calls to same tool — [Silent Failure] (catches counting all calls instead of per-tool)
- `called_tool_names` returns ordered unique names preserving first-occurrence order — [Silent Failure] (catches set() destroying order or adding duplicates)

**ToolBehavior (Category B — outcome/state):**
- `tool_succeeded` returns `True` only when a call has state `SUCCEEDED` — [Hidden Assumption]
- `tool_failed` returns `True` only when a call has state `FAILED` — [Hidden Assumption]
- `tool_denied` returns `True` only when a call has state `DENIED` — [Hidden Assumption]
- `all_tool_calls_succeeded` returns `True` when all succeeded; `False` when any failed/denied — [Silent Failure]
- `all_tool_calls_succeeded` returns `True` when there are zero calls (vacuous) — [Edge Case]
- `tool_returned_containing` finds substring in a successful call's result output — [Hidden Assumption] (assumes `.result.output` is the right field)
- `tool_returned_containing` skips calls with `.result is None` — [Hidden Failure]
- `tool_returned_matching` applies regex to result output — [Edge Case]
- `tool_returned_matching` with no matching calls returns `False` — [Edge Case]

**ToolArgumentBehavior (Category C):**
- `tool_called_with` returns `True` when args are a subset of call arguments — [Silent Failure] (catches exact-match instead of subset-match)
- `tool_called_with` with empty kwargs returns `True` if the tool was called at all — [Edge Case]
- `tool_called_with_exact` returns `True` only on exact argument dict match — [Silent Failure] (catches subset instead of exact)
- `tool_never_called_with` is the negation of `tool_called_with` — [Silent Failure]
- `tool_called_with_matching` calls the predicate on the named argument value — [Hidden Assumption] (assumes arg_name exists in arguments)
- `tool_called_with_matching` skips calls where `arg_name` is absent — [Hidden Failure]

**StopBehavior (Category D):**
- `stopped_on` returns `True` for exact reason match — [Edge Case]
- `stopped_normally` returns `True` only for `"final_response"` — [Silent Failure] (catches matching on wrong value)
- `did_not_hit_max_iterations` returns `False` when `stop_reason` is `"max_iterations"` — [Hidden Assumption]
- `did_not_hit_max_tool_calls` returns `False` when `stop_reason` is `"max_tool_calls"` — [Hidden Assumption]
- `did_not_hit_max_tokens` returns `False` when `stop_reason` is `"max_tokens"` — [Hidden Assumption]
- `iteration_count` returns the raw int from probe — [Edge Case]
- `total_tool_calls` returns the raw count from probe — [Edge Case]
- `tokens_used` returns `None` when not reported — [Edge Case]
- `did_not_exceed_tokens` returns `True` when `tokens_used is None` — [Silent Failure] (catches `None <= limit` TypeError or wrong logic)
- `did_not_exceed_tokens` returns `False` when tokens exceed limit — [Silent Failure]

**HandoffBehavior (Category E):**
- `handoff_occurred` returns `True` when `last_handoff` is set — [Edge Case]
- `handoff_occurred` returns `False` when `last_handoff is None` — [Edge Case]
- `handoff_is_filled` returns `True` only when `is_filled` property is `True` — [Silent Failure]
- `handoff_count` returns `len(handoffs)` list, not just checking `last_handoff` — [Hidden Assumption]
- `handoff_has_section` returns `True` for existing section, `False` for missing — [Edge Case]
- `handoff_section_contains` finds substring in the named section — [Silent Failure]
- `handoff_section_contains` returns `False` when section doesn't exist (not raise) — [Hidden Failure]
- All handoff predicates return `False`/`0` when `handoff is None` — [Edge Case]

**Behavior Facade:**
- `agent.behavior` returns a `Behavior` instance — [Edge Case]
- `agent.behavior` returns the same instance on repeated access (cached) — [Silent Failure] (catches rebuilding on every access)
- `agent.behavior.tool` returns a `ToolBehavior` — [Edge Case]
- `agent.behavior.probe` is built lazily (not in `__init__`) — [Hidden Assumption]
- `Behavior.probe` is cached (built once, returned on subsequent access) — [Silent Failure]

**PredicateGrader:**
- `agrade_with_probe` returns passed result when predicate returns `True` — [Edge Case]
- `agrade_with_probe` returns failed result when predicate returns `False` — [Edge Case]
- `agrade_with_probe` returns failed result with error message when predicate raises — [Hidden Failure]
- `agrade` (fallback) returns a descriptive failed result — [Hidden Assumption]

### Integration Tests

- End-to-end with a `MockAgent` (same pattern as `tests/test_evals.py:MockAgent`): run agent, access `agent.behavior.tool.called_tool(...)` and verify it reflects the run's tool calls. Mock: the agent's `arun` to return a reply with metadata containing `ToolCallContext` objects. Real: `RunProbe`, `Behavior`, category classes. — [Silent Failure: probe reads wrong metadata key]
- `EvalRunner` + `MockAgent` + `PredicateGrader`: run a suite where the grader checks `called_tool`; verify `EvalResult.grader_result.passed` reflects the predicate outcome. — [Hidden Assumption: runner passes probe to grader]
- `EvalRunner` + `MockAgent` + standard `ContainsGrader`: verify the standard `agrade` path is unchanged (no probe needed). — [Hidden Failure: runner breaks standard grading path]
- Cache invalidation: run agent once, access `agent.behavior.tool.called_tool("a")` (cached); run agent again with different tools; access `agent.behavior.tool.called_tool("a")` and verify it reflects the *second* run. — [Silent Failure: stale cache after re-run]

### Manual / QA Test Cases

1. Given an agent that ran with no tools, when `agent.behavior.tool.called_no_tools()` is called, then it returns `True` — [Edge Case]
2. Given an agent that hit `max_iterations`, when `agent.behavior.stop.stopped_on("max_iterations")` is called, then it returns `True` — [Hidden Assumption]
3. Given an agent that produced a handoff, when `agent.behavior.handoff.handoff_occurred()` is called, then it returns `True` — [Edge Case]
4. Given a `PredicateGrader` in a suite run against a `MockAgent` that called `search`, when the suite runs, then the case with `lambda p: any(c.tool_name == "search" for c in p.tool_calls)` passes — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.lib.dataclasses.tools.ToolCallContext` | existing | Probe tool call fields | None (already in use) |
| `vidbyte.context.handoff.base.Handoff` | existing | Probe handoff fields | None (already in use) |
| `vidbyte.lib.dataclasses.agents.AgentMessage` | existing | Probe reads `last_reply` | None (already in use) |
| `vidbyte.lib.enums.AgentStopReason` | existing | Stop reason value comparison | None (already in use) |

No external services. No new dependencies.

---

## 12. Rollout & Deployment

- Purely additive SDK change; no feature flag needed.
- Not a breaking change: `BaseAgent.behavior` is a new property; `EvalRunner` changes are additive (duck-typed `agrade_with_probe` dispatch; standard `agrade` path unchanged).
- Existing eval suites, graders, and agents are unaffected.
- Rollback = revert the PR; no migrations, no state, no config changes.

---

## 13. Open Questions

- [ ] Should the `Behavior` facade also expose flat delegation for the most common predicates (e.g. `agent.behavior.called_tool("search")` as an alias for `agent.behavior.tool.called_tool("search")`)? Current design uses sub-properties only for clean decomposition; flat aliases could be added if ergonomics demand it.
- [ ] Should `RunProbe` capture `DebugTracer.events` for span-level predicates (category H from the brainstorm)? Deferred — would require the user to have passed `trace=Trace.debug()`; metadata-only probe is always available.
- [ ] Should the `EvalRunner` always build a probe (small overhead) or only when a `PredicateGrader` is detected? Current design always builds it for agent targets (O(1) field reads); lazy detection could save the build but complicates the flow.

---

## 14. Alternatives Considered

### Alternative 1: Flat methods on `Behavior` (no sub-properties)

- What: `agent.behavior.called_tool("search")` directly, with all ~35 predicates on the `Behavior` class.
- Why rejected: the user explicitly requested decomposition into category files (`ToolBehavior`, `StopBehavior`, etc.) and initialization in the main `Behavior` class. Sub-properties make the decomposition visible in the access pattern and keep each category's method count manageable.

### Alternative 2: Mixin on `BaseAgent` (`agent.called_tool(...)`)

- What: add all predicate methods directly to `BaseAgent` via a mixin.
- Why rejected: `BaseAgent` already has `handoff()`, `tool_specs()`, `add_tool()`, `card()` — adding 35+ predicate methods risks name collisions and bloats the class API. The `behavior.` prefix groups predicates visually and signals "this is an introspection call, not an execution call". Also breaks under `fork()` if not carefully handled.

### Alternative 3: Dynamic monkey-patching after each run

- What: after `generate_reply`, dynamically attach predicate methods to the agent instance.
- Why rejected: mutates the instance, is thread-unsafe, surprises users, and breaks under `fork()` (which the `EvalRunner` relies on). The cached facade achieves the same ergonomics safely.

### Alternative 4: Change `BaseGrader.agrade` signature to accept metadata

- What: add `result_metadata: Mapping[str, Any] | None = None` to `BaseGrader.agrade`.
- Why rejected: breaking change to the abstract `BaseGrader` contract; all existing graders would need updating. The duck-typed `agrade_with_probe` approach is non-breaking and opt-in.

### Alternative 5: Single `behavior.py` file (no folder decomposition)

- What: all behavior logic in one `vidbyte/evals/behavior.py` file.
- Why rejected: the user explicitly requested a `vidbyte/evals/behavior/` folder with decomposed category files (`ToolBehavior`, `StopBehavior`, etc.).

END OF DESIGN DOC

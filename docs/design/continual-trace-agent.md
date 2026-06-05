# Design Doc: Continual Trace Agent (middleware-driven)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-04
**Last Updated:** 2026-06-04

---

## 1. Overview

This feature adds a first-class **`ContinualTraceAgent`** — a dedicated `BaseAgent` subclass that, while a *main* agent runs, periodically reads the main agent's context and incrementally fills a typed, developer-defined trace schema into a structured artifact. The developer opts in with a single option, `TraceOption.continual(schema)`. Internally the option is realized as **runtime middleware** (`ContinualTraceMiddleware`) that fires at fixed lifecycle points (every N iterations and once at run end), delegating each update to the `ContinualTraceAgent`, which fills the schema deterministically through an `updateTrace` tool. The accumulated artifact is returned on `reply.metadata["trace"]` and stored on `agent.last_trace`, mirroring the existing handoff feature. The trace is **never written back into the main agent's context window**.

---

## 2. Goals & Non-Goals

### Goals
- Add a `ContinualTraceAgent(BaseAgent)` subclass that mirrors the `HandoffAgent` pattern (dedicated agent, `from_source_agent`, reuses the source runner/provider).
- Add a public opt-in option `TraceOption.continual(schema, *, every_n_iterations=5, max_trace_iterations=3)`.
- Realize continual tracing as `ContinualTraceMiddleware` injected at fixed runtime lifecycle points (no edits to the hot model/tool loop).
- Fill the schema deterministically via an `updateTrace` tool whose argument shape is validated against the schema, with shape mismatches fed back to the model for self-correction (the existing tool-output retry pattern).
- Support **growable array/object fields** ("option A"): array fields are appended to and object fields deep-merged on each update; scalar fields are replaced; omitted fields are preserved.
- Let developers define custom schemas via a typed Pydantic model, a `TraceSchema`, or a plain `{field: description}` mapping; ship a prebuilt `ActionTrace`.
- Surface the artifact at `reply.metadata["trace"]` and `agent.last_trace`; surface bookkeeping at `reply.metadata["trace_metadata"]`.
- Be fail-open: trace failures never abort or alter the main run.
- Add unit + integration tests, a verification script, README docs, and an SDK skill.

### Non-Goals
- No change to the existing observability tracers (`Trace.off/debug/continual/custom/langfuse/...`). `Trace.continual(...)` (the `ContinualTracer` capture preset) remains an orthogonal low-level utility; this feature is the structured-artifact layer and is selected separately via `trace_option=`.
- No support for non-linear runtimes (MCTS/Actor). Continual tracing is middleware, and the runtime already forbids middleware on non-linear runtimes, which yields the guard for free.
- No persistence, remote storage, or cross-run trace memory.
- No new third-party dependencies (Pydantic is already a dependency).
- No automatic injection of the trace into the main context window (explicitly forbidden).

---

## 3. Background & Context

The SDK already has: (a) a `HandoffAgent` that is a `BaseAgent` subclass producing a structured document from a completed run via prefilled `output_schema`; (b) a rich middleware system (`AgentMiddleware`, `MiddlewarePipeline`) with lifecycle hooks (`before_run`, `after_iteration`, `after_run`, ...) and a per-run mutable `MiddlewareContext.run_state`; (c) tool-output schema validation that, on mismatch, returns a `ToolResult.error` the model can correct on the next iteration (`runtime.py` tool execution).

A prior attempt (PR #107, branch `feat/continual-trace-agent`, now **closed**) implemented continual tracing with a bespoke in-runtime controller before the middleware system and the handoff/trace-facade work landed on `main`. This design supersedes it by:
- building on current `main`;
- using the merged **middleware** system as the injection seam (conceptually "inject logic into the agent at a fixed point");
- making the trace agent a real `BaseAgent` subclass like `HandoffAgent`;
- using a **tool** (not final `output_schema`) for the per-pass fill, because only a tool enables server-side append (growable fields) and the tool-output validation→retry loop, which is also the only schema-enforcement path that fires on Anthropic/Claude (where `response_format` is unsupported).

---

## 4. Requirements

### Functional Requirements
1. `TraceOption.continual(schema, *, every_n_iterations=5, max_trace_iterations=3)` returns a validated continual `TraceOption`.
2. `TraceOption.continual` accepts a `TraceSchema`, a Pydantic `BaseModel` subclass, or a `Mapping[str, str]`.
3. `TraceOption` rejects empty schemas, `every_n_iterations <= 0`, and `max_trace_iterations` outside `1..3`.
4. `TraceSchema` stores an ordered map of `field_name -> TraceField{description, type}` plus a name/description; `initial_artifact()` returns `{field: None for every field}`.
5. `TraceField.type` is one of `string | integer | number | boolean | array | object`.
6. `BaseAgent.__init__` accepts `trace_option: TraceOption | None = None`; when set with a non-linear runtime it raises `ConfigurationError` (delegated to the existing middleware guard).
7. `BaseAgent.fork()` preserves `trace_option` unless overridden.
8. When `trace_option` is enabled, the runtime runs a continual trace update after every `every_n_iterations` completed iterations and exactly once at run end.
9. Each update delegates to a `ContinualTraceAgent` constructed from the source agent's runner/provider.
10. `ContinualTraceAgent` is a `BaseAgent` subclass exposing one model-visible tool, `updateTrace`, and loading `Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT`.
11. `UpdateTraceTool` accepts one required `trace` object argument; its `input_schema` declares the typed schema fields with `additionalProperties: false`.
12. `UpdateTraceTool` drops keys not in the schema, preserves omitted fields' prior values, **appends** to `array` fields, **deep-merges** `object` fields, and **replaces** scalar fields.
13. `UpdateTraceTool` validates each provided value against its declared `TraceField.type`; on mismatch it returns a `ToolResult.error` ("output shape mismatch") so the trace agent can self-correct within `max_trace_iterations`.
14. If the trace agent raises or never calls `updateTrace`, the prior artifact is preserved and a recoverable error/no-op is recorded.
15. The trace artifact is **never** added to the main agent's provider messages, system prompt, or context window.
16. Final `reply.metadata["trace"]` contains the accumulated artifact; `reply.metadata["trace_metadata"]` contains `{mode, schema, update_count, error_count, last_error?}`; `agent.last_trace` holds the artifact dict.
17. `vidbyte.trace.continual.ActionTrace` is a prebuilt schema with `goal`, `actions_taken` (array), `mistakes` (array), `current_status`.
18. `AgentClient.continual_trace(...)` constructs a `ContinualTraceAgent`.
19. Continual tracing helpers never recursively enable tracing on the internal `ContinualTraceAgent`.

### Non-Functional Requirements
- **Backward compatible:** agents without `trace_option` behave exactly as today; existing `trace=`/`tracer=` semantics are unchanged.
- **Fail-open:** the trace middleware sets `fail_closed = False`; any failure is recorded and the main run proceeds.
- **Bounded cost:** updates occur only at the configured interval plus one final update, each bounded to `max_trace_iterations` (1..3) trace-agent iterations.
- **No new dependencies.**
- **Serializable:** the artifact is a JSON-like dict.
- **Decoupled runtime:** the runtime gains one generic, feature-agnostic step that lifts published per-run metadata; it does not import trace internals.

---

## 5. High-Level Design

```
Agent(trace_option=TraceOption.continual(ActionTrace))
  -> BaseAgent.generate_reply()
     -> _runtime() builds ContinualTraceMiddleware(option, source_agent=self)
        and appends it to the runtime middleware pipeline (not to self.middleware)
     -> AgentRuntime loop (UNCHANGED hot path):
          before_run        -> middleware seeds run_state artifact = schema.initial_artifact()
          iteration k ...    -> after_iteration: if k % every_n == 0 -> run one trace update
          isDone final       -> after_run: run one final trace update (forced)
     -> _finish_result lifts run_state["__result_metadata__"] into result.metadata  (generic)
  -> generate_reply copies result.metadata -> reply.metadata["trace"|"trace_metadata"]
     and sets self.last_trace                          (mirrors _run_auto_handoff)

One trace update:
  ContinualTraceMiddleware
    -> ContinualTraceAgent.from_source_agent(source, schema, trace_so_far=current)
    -> agent.update(context_window=<read-only snapshot of main run>)
       -> BaseAgent.arun -> model calls updateTrace({trace: {...}})
          -> UpdateTraceTool validates + appends/merges -> accumulated artifact
    -> middleware stores artifact in run_state (never in provider messages)
```

**Key decisions:**
- *Middleware seam* (not a runtime controller): zero hot-loop edits, reuses lifecycle hooks, and gets the non-linear-runtime guard for free.
- *Dedicated param `trace_option=`* (not overloading `trace=`): `trace=` already aliases the observability tracer; a distinct param keeps both capabilities composable (a dev can have a tracer *and* a trace artifact) and avoids destabilizing existing `trace=`/`tracer=` tests. (See Alternatives.)
- *Tool-based fill* (not `output_schema`): enables growable/append semantics and the validation→retry loop that also works on Claude.
- *Generic metadata lift in `_finish_result`*: a feature-agnostic `run_state["__result_metadata__"]` merge, so the runtime never imports trace code.

---

## 6. Detailed Design

### 6.1 Trace dataclasses
**File(s):** `vidbyte/lib/dataclasses/trace.py`
**Type:** New file

#### What it does
Defines the in-memory contracts: `TraceMode`, `TraceFieldType`, `TraceField` (Pydantic), `TraceSchema`, `TraceOption`.

#### Interface / API
```python
class TraceMode(str, Enum): CONTINUAL = "continual"

class TraceFieldType(str, Enum):
    STRING="string"; INTEGER="integer"; NUMBER="number"
    BOOLEAN="boolean"; ARRAY="array"; OBJECT="object"

class TraceField(BaseModel):
    description: str
    type: TraceFieldType = TraceFieldType.STRING

@dataclass(frozen=True, slots=True)
class TraceSchema:
    name: str
    fields: Mapping[str, TraceField]   # normalized in __post_init__
    description: str = ""
    @classmethod
    def coerce(cls, raw: "TraceSchema | type[BaseModel] | Mapping[str, Any]") -> "TraceSchema": ...
    @classmethod
    def from_model(cls, model: type[BaseModel], *, name=None, description=None) -> "TraceSchema": ...
    def initial_artifact(self) -> dict[str, Any]: ...
    def describe_fields(self) -> str: ...

@dataclass(frozen=True, slots=True)
class TraceOption:
    mode: TraceMode
    schema: TraceSchema
    every_n_iterations: int = 5
    max_trace_iterations: int = 3
    @classmethod
    def continual(cls, schema, *, every_n_iterations=5, max_trace_iterations=3) -> "TraceOption": ...
    @property
    def enabled(self) -> bool: ...
```

#### Logic / Algorithm
1. `TraceField` carries a description and a JSON-like type (default `string`).
2. `TraceSchema.__post_init__` validates a non-empty name and ≥1 field; normalizes each field value (string → `TraceField(description=...)`, mapping → `TraceField(**v)`, `TraceField` passthrough), trimming descriptions.
3. `coerce` accepts a `TraceSchema`, a Pydantic model subclass (→ `from_model`), or a `Mapping`.
4. `from_model` reads each field's `Field(description=...)` (required) and infers `TraceFieldType` from the annotation.
5. `initial_artifact()` returns `{field: None}`.
6. `TraceOption.continual` coerces the schema and validates interval/iteration bounds.

#### Edge Cases & Error Handling
- Empty schema / empty field name / missing field description → `ValueError`.
- `every_n_iterations <= 0`, `max_trace_iterations` outside `1..3` → `ValueError`.
- Pydantic model field lacking a description → `ValueError`.

### 6.2 updateTrace tool
**File(s):** `vidbyte/trace/continual/tools.py`
**Type:** New file

#### What it does
The single model-visible tool the trace agent calls to fill the artifact deterministically.

#### Interface / API
```python
UPDATE_TRACE_TOOL_NAME = "updateTrace"
class UpdateTraceTool(BaseTool):
    def __init__(self, schema: TraceSchema, initial_trace: Mapping[str, Any] | None = None) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def current_trace(self) -> dict[str, Any]: ...
    last_error: str | None
```

#### Logic / Algorithm
1. `__init__` seeds `self._trace = merge(schema.initial_artifact(), initial_trace)`.
2. `spec()` builds `input_schema` = `{trace: {type:object, properties:<typed per field>, additionalProperties:false}}`, `required:["trace"]`, `metadata={"internal": True}`.
3. `execute()`:
   - reject non-object `trace` → `ToolResult.error("trace argument must be an object")`.
   - `validate_types(update)`: each provided field must match `TraceField.type` (array→list, object→Mapping, etc.); on first mismatch return `ToolResult.error("output shape mismatch: <field> expected <type>")` (drives retry).
   - `merge_known(base, update)`: for each schema field present in `update`: array→`base + new` (append, de-duplicate exact repeats), object→`{**base, **new}` (deep-merge one level), scalar→replace; unknown keys dropped; omitted fields keep prior values.
   - store and return `ToolResult.success(json.dumps(trace))`.
4. `current_trace()` returns a dict copy.

#### Edge Cases & Error Handling
- Non-object `trace`, wrong field types → recoverable `ToolResult.error`, prior artifact unchanged.
- Unknown keys → silently dropped (not an error; schema is authoritative).
- Append de-dups exact duplicate scalar list entries to avoid unbounded growth across passes.

### 6.3 ContinualTraceAgent
**File(s):** `vidbyte/trace/continual/agent.py`
**Type:** New file

#### What it does
A `BaseAgent` subclass (mirroring `HandoffAgent`) that performs one trace-update pass.

#### Interface / API
```python
class ContinualTraceAgent(BaseAgent):
    def __init__(self, schema: TraceSchema, *, name="continual-trace",
                 trace_so_far: Mapping[str, Any] | None = None,
                 max_trace_iterations: int = 3, **kwargs) -> None: ...
    @classmethod
    def from_source_agent(cls, source: BaseAgent, schema, *, trace_so_far, max_trace_iterations) -> "ContinualTraceAgent": ...
    async def update(self, *, context_window: str, runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]: ...
    @classmethod
    async def run_update(cls, source, schema, *, context_window, trace_so_far, max_trace_iterations, runtime_metadata=None) -> tuple[dict, str | None]: ...
```

#### Logic / Algorithm
1. `__init__` pops `output_schema`/`tools`/`handoff`/`trace_option`, builds `self._tool = UpdateTraceTool(schema, trace_so_far)`, sets `tools=[self._tool]`, `system_prompt=Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT)`, `max_iterations=max_trace_iterations`. This guarantees no recursive tracing.
2. `from_source_agent` reuses the source runner/provider/model/temperature exactly like `HandoffAgent.from_source_agent`.
3. `update` renders the prompt (`<main_context_window>`, `<trace_schema>`, `<trace_so_far>`, `<runtime_metadata>`), runs `arun`, sets `self.last_error = self._tool.last_error`, returns `self._tool.current_trace()`; on exception sets `last_error` and returns the seeded artifact.
4. `run_update` is the fail-open classmethod the middleware uses: build agent, call `update`, return `(artifact, error)`.

#### Edge Cases & Error Handling
- Model never calls `updateTrace` → returns the seeded artifact unchanged, `last_error=None`.
- `arun` raises → returns the seeded artifact, `last_error` set.

### 6.4 ContinualTraceMiddleware
**File(s):** `vidbyte/trace/continual/middleware.py`
**Type:** New file

#### What it does
Injects the periodic + final trace updates at fixed lifecycle points, accumulating the artifact in `run_state` and publishing it for the runtime to lift.

#### Interface / API
```python
class ContinualTraceMiddleware(AgentMiddleware):
    fail_closed = False
    def __init__(self, option: TraceOption, *, source_agent: BaseAgent) -> None: ...
    async def before_run(self, ctx) -> MiddlewareDecision: ...
    async def after_iteration(self, ctx) -> MiddlewareDecision: ...
    async def after_run(self, ctx) -> MiddlewareDecision: ...
```

#### Logic / Algorithm
1. `before_run`: `ctx.run_state[self.__class__] = _TraceRunState(artifact=schema.initial_artifact())`; publish initial empty trace metadata.
2. `after_iteration`: if `ctx.iteration_count > 0 and ctx.iteration_count % every_n == 0 and last_updated != iteration`, call `_run_update(ctx)`.
3. `after_run`: if not finalized, call `_run_update(ctx, force=True)`; mark finalized.
4. `_run_update`: render a read-only `context_window` from `ctx.agent_context.build_context()` + `ctx.provider_messages`; call `ContinualTraceAgent.run_update(...)`; update `state.artifact`, `update_count`/`error_count`/`last_error`; `_publish(ctx)`.
5. `_publish`: write `ctx.run_state["__result_metadata__"] = {**existing, "trace": state.artifact, "trace_metadata": state.summary()}`. Never returns a `MiddlewareTransform`, so nothing reaches the model.

#### Edge Cases & Error Handling
- `ctx.agent_context is None` → render an empty snapshot; still safe.
- Update exception is caught inside `run_update` (fail-open) and counted; `MiddlewareDecision.continue_()` always returned.
- Duplicate update on the same iteration prevented by `last_updated` guard (avoids double update when final iteration coincides with the interval).

### 6.5 BaseAgent wiring
**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### Logic / Algorithm
1. Add `trace_option: TraceOption | None = None` to `__init__`; store `self._trace_option`; init `self.last_trace: dict | None = None`.
2. In `_runtime()`: if `self._trace_option` and `.enabled`, build `mw = ContinualTraceMiddleware(self._trace_option, source_agent=self)` and pass `middleware=(*self.middleware, mw)`; else `middleware=self.middleware`. (Trace middleware is *not* stored in `self.middleware`, so fork does not double-add and the non-linear guard at construction still applies via the public middleware list — see note.)
3. Non-linear guard: in `__init__`, if `trace_option` enabled and runtime is non-linear, raise `ConfigurationError` (explicit; mirrors the existing middleware guard message).
4. In `generate_reply()`, after building `metadata` and before/around the handoff hook: if `self._trace_option` enabled, set `self.last_trace = metadata.get("trace")` (the artifact is already present via the runtime lift). Keep `metadata["trace"]`/`["trace_metadata"]` as produced.
5. In `fork()`: pass `trace_option=self._trace_option`.

#### Edge Cases & Error Handling
- `trace_option` on non-linear runtime → `ConfigurationError` at construction.
- No `trace_option` → no middleware appended; behavior identical to today.

### 6.6 Runtime generic metadata lift
**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Logic / Algorithm
1. In `_finish_result`, after `_with_context_window_metadata` / `_with_middleware_metadata`, call `result = self._with_run_state_metadata(result, run_state)`.
2. `_with_run_state_metadata(result, run_state)`: if `run_state.get("__result_metadata__")` is a non-empty Mapping, merge it into `result.metadata` and return a new `AgentResult`; else return `result` unchanged.

#### Edge Cases & Error Handling
- Missing/empty key → no-op. Generic and feature-agnostic; no trace imports in runtime.

### 6.7 Public surface, prompts, client
**File(s):** `vidbyte/trace/continual/__init__.py`, `vidbyte/trace/continual/prebuilt.py`, `vidbyte/agents/client.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/prompts/continual_trace/continual_trace.json`, `vidbyte/prompts/prompts/continual_trace/system_prompt.md`
**Type:** New/Modified

#### Logic / Algorithm
1. `Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT = "continual_trace.system_prompt"` + matching JSON/MD assets (the catalog validates enum↔asset sync at import).
2. `vidbyte/trace/continual/__init__.py` re-exports `ContinualTraceAgent`, `ContinualTraceMiddleware`, `ActionTrace`, plus `ContinualTracer` (unchanged) so existing imports keep working.
3. `prebuilt.py` defines `ActionTrace = TraceSchema.from_model(ActionTraceModel, ...)`.
4. `AgentClient.continual_trace(schema, **kwargs)` → `ContinualTraceAgent(schema, **kwargs)`.
5. Root `vidbyte/__init__.py` exports `TraceOption`, `TraceSchema`, `ContinualTraceAgent`, `ActionTrace`.

---

## 7. Data Model Changes

N/A - no database/persistence. New in-memory contracts only (`TraceSchema`, `TraceField`, `TraceOption`), covered in 6.1.

---

## 8. API Changes

No HTTP endpoints. SDK API additions:

### 8.1 `BaseAgent(..., trace_option=TraceOption.continual(schema))`
**Change type:** New (additive, optional keyword)
**Result:** `reply.metadata["trace"]: dict`, `reply.metadata["trace_metadata"]: dict`, `agent.last_trace: dict | None`.

### 8.2 `TraceOption.continual(schema, *, every_n_iterations=5, max_trace_iterations=3)`
**Change type:** New

### 8.3 `AgentClient.continual_trace(schema, **kwargs) -> ContinualTraceAgent`
**Change type:** New

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/dataclasses/trace.py` | `TraceMode/TraceFieldType/TraceField/TraceSchema/TraceOption` |
| CREATE | `vidbyte/trace/continual/tools.py` | `UpdateTraceTool` (typed, append/merge, retry-on-mismatch) |
| CREATE | `vidbyte/trace/continual/agent.py` | `ContinualTraceAgent(BaseAgent)` |
| CREATE | `vidbyte/trace/continual/middleware.py` | `ContinualTraceMiddleware` injection seam |
| CREATE | `vidbyte/trace/continual/prebuilt.py` | `ActionTrace` prebuilt schema |
| CREATE | `vidbyte/prompts/prompts/continual_trace/continual_trace.json` | Prompt asset record |
| CREATE | `vidbyte/prompts/prompts/continual_trace/system_prompt.md` | Trace agent system prompt |
| CREATE | `scripts/test-continual-trace.py` | Verification script (Phase 5) |
| CREATE | `tests/test_continual_trace.py` | Unit + integration tests |
| CREATE | `skills/vidbyte-sdk/continual-tracing.md` | SDK skill doc |
| MODIFY | `vidbyte/trace/continual/__init__.py` | Export agent/middleware/prebuilt (keep `ContinualTracer`) |
| MODIFY | `vidbyte/trace/__init__.py` | Re-export `ContinualTraceAgent`, `TraceOption`, `ActionTrace` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export trace contracts |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `CONTINUAL_TRACE_SYSTEM_PROMPT` |
| MODIFY | `vidbyte/agents/base.py` | `trace_option` param, `_runtime()` injection, guard, `fork`, `last_trace` |
| MODIFY | `vidbyte/agents/runtime.py` | Generic `_with_run_state_metadata` lift in `_finish_result` |
| MODIFY | `vidbyte/agents/client.py` | `AgentClient.continual_trace` |
| MODIFY | `vidbyte/agents/__init__.py` | Export `ContinualTraceAgent` |
| MODIFY | `vidbyte/__init__.py` | Root exports for `TraceOption`/`TraceSchema`/`ContinualTraceAgent`/`ActionTrace` |
| MODIFY | `README.md` | Document continual tracing |

---

## 10. Testing Plan

### Unit Tests (`tests/test_continual_trace.py`)
- `TraceOption.continual` builds from a Pydantic model — [Edge Case]
- `TraceOption.continual` builds from a `{field: description}` mapping (types default to string) — [Hidden Assumption]
- `TraceOption.continual` rejects empty schema mapping — [Edge Case]
- `TraceOption` rejects `every_n_iterations = 0` and `-1` — [Edge Case]
- `TraceOption` rejects `max_trace_iterations = 0` and `4` — [Edge Case]
- `TraceSchema.from_model` raises when a field lacks a description — [Hidden Assumption]
- `TraceSchema.initial_artifact` returns every field set to `None` (0/1/N fields) — [Edge Case]
- `UpdateTraceTool.execute` appends to an array field across two calls without dropping prior entries — [Silent Failure] (catches wholesale-replace regression)
- `UpdateTraceTool.execute` de-duplicates an exact duplicate array entry — [Silent Failure]
- `UpdateTraceTool.execute` deep-merges an object field — [Silent Failure]
- `UpdateTraceTool.execute` replaces a scalar field and preserves omitted fields — [Silent Failure]
- `UpdateTraceTool.execute` drops unknown keys — [Hidden Assumption]
- `UpdateTraceTool.execute` returns `ToolResult.error` ("output shape mismatch") when a value violates its declared type (string into array) — [Hidden Failure]
- `UpdateTraceTool.execute` returns error when `trace` is not an object — [Edge Case]
- `ContinualTraceAgent.update` returns the seeded artifact unchanged when the model never calls `updateTrace` — [Hidden Failure]
- `ContinualTraceAgent.run_update` returns `(seeded_artifact, error_str)` when `arun` raises (fail-open) — [Hidden Failure]
- `ContinualTraceMiddleware.after_iteration` does **not** update on iteration 0 or when `k % every_n != 0` — [Silent Failure] (catches off-by-one cadence)
- `ContinualTraceMiddleware` never returns a transform / never mutates provider messages — [Hidden Assumption] (trace stays out of context)
- `ContinualTraceMiddleware` runs exactly one update at `after_run` and not twice when the final iteration coincides with the interval — [Silent Failure]
- `BaseAgent(trace_option=...)` on a non-linear runtime raises `ConfigurationError` — [Hidden Assumption]
- `BaseAgent.fork()` preserves `trace_option` — [Edge Case]

### Integration Tests
- End-to-end with a `FakeRunner` (same pattern as `tests/test_agent_middleware.py`): a main agent with `trace_option` and a tool runs N+ iterations; assert `reply.metadata["trace"]` accumulates across ≥2 updates, `reply.metadata["trace_metadata"]["update_count"] >= 1`, and `agent.last_trace == reply.metadata["trace"]`. Mock: the runner (scripted responses); real: middleware, runtime, tool, agent.
- Silent-failure path: assert the accumulated artifact string never appears in any recorded runner prompt/`messages` (trace not leaked into the main context window).
- Hidden-assumption the integration surfaces: a trace-agent runner that raises on every update — the main run still completes successfully and `trace_metadata["error_count"] >= 1`.

### Manual / QA Test Cases
1. Given a real provider key and `trace_option=TraceOption.continual(ActionTrace, every_n_iterations=2)`, when a multi-step task runs, then `reply.metadata["trace"]["actions_taken"]` is a growing list and `current_status` reflects the latest step — [Silent Failure: append vs replace].
2. Given `trace_option` plus a separate observability `tracer=Trace.debug()`, when the agent runs, then both work independently (artifact present; debug events recorded) — [Hidden Assumption: composability].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| pydantic | already pinned | Typed `TraceField`, model-derived schemas | None (already used by `output_schema`/handoff) |

No external services.

---

## 12. Rollout & Deployment

- Purely additive SDK change; no feature flag. Agents without `trace_option` are unaffected.
- Not a breaking change. Existing `trace=`/`tracer=`/`Trace.continual()` semantics unchanged.
- Rollback = revert the PR; no migrations or state.

---

## 13. Open Questions

- [ ] Should `Trace.continual()` (the observability `ContinualTracer`) eventually be folded into / deprecated in favor of the artifact agent? (This PR keeps them orthogonal.)
- [ ] Should the trace agent optionally *consume* a `ContinualTracer` capture buffer as its input instead of the rendered run snapshot? (Deferred; snapshot is sufficient for v1.)
- [ ] Confirmation of *why* PR #107 was closed, in case there was a deliberate "no trace-as-agent" decision. (Proceeding per explicit user direction.)

---

## 14. Alternatives Considered

### Alternative 1: Overload `trace=` to accept `TraceOption | TracerBase`
- What: single param dispatching by type.
- Why rejected: `trace=` already aliases the observability tracer with a "not both `trace=`/`tracer=`" guard; overloading muddies semantics, prevents using a tracer *and* a trace artifact together, and risks existing tests. A dedicated `trace_option=` is clearer and composable.

### Alternative 2: In-runtime trace controller (the PR #107 approach)
- What: a bespoke controller invoked from inside the model/tool loop.
- Why rejected: edits the hot loop, duplicates lifecycle scheduling the middleware system already provides, and a reviewer previously flagged multi-point loop invocation. Middleware is the idiomatic "inject at a fixed point" seam and yields the non-linear guard for free.

### Alternative 3: Fill via final `output_schema` (the handoff mechanism)
- What: reuse `output_schema` on the trace agent.
- Why rejected: `output_schema` can't express server-side append (growable fields), its final-output validation has no retry, and `response_format` is unsupported on Anthropic/Claude. A tool gets the validation→retry loop that fires on all providers.

END OF DESIGN DOC

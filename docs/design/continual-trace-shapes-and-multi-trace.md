# Design Doc: Continual Trace Shapes & Multi-Trace

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

This feature extends the continual-trace-artifact system (the `feat/continual-trace-agent-v2` foundation) in two ways. First, it ships seven new prebuilt trace schemas and substantially expands the existing one, so the SDK offers eight rich "lenses" over an agent run — `ActionTrace`, `PlanTrace`, `ReasoningTrace`, `HistoryTrace`, `ToolTrace`, `DecisionTrace`, `ArtifactTrace`, and `KnowledgeTrace` — each with at least 20 typed, described fields. Second, it lets a single agent run **multiple continual traces at once** (e.g. a `PlanTrace` and a `ReasoningTrace` together), by accepting a sequence of `TraceOption`s and attaching one trace middleware per option. Traces remain pure read-only observers that never enter the main agent's context window; multiple traces simply stack their (independent) cost linearly and publish into a keyed `metadata["traces"]` map.

---

## 2. Goals & Non-Goals

### Goals

- Add 7 new prebuilt `TraceSchema`s: `PlanTrace`, `ReasoningTrace`, `HistoryTrace`, `ToolTrace`, `DecisionTrace`, `ArtifactTrace`, `KnowledgeTrace`.
- Expand the existing `ActionTrace` from 4 fields to **≥20** typed fields.
- Every new/expanded schema has **at least 20 fields**, each with a `TraceFieldType` (via Python annotation) and a 4–5 sentence `Field(description=...)`.
- Convert `vidbyte/trace/continual/prebuilt.py` (single module) into a `prebuilt/` **package**, one module per schema, with `ActionTrace` import paths preserved.
- Let `BaseAgent(trace_option=...)` accept **either** a single `TraceOption` **or** a `Sequence[TraceOption]`.
- Attach one `ContinualTraceMiddleware` per enabled option; each maintains its own per-run state and accumulates its own artifact independently.
- Publish all artifacts under `metadata["traces"]` (keyed by schema name) and `metadata["traces_metadata"]`, while preserving the single-trace `metadata["trace"]` / `metadata["trace_metadata"]` back-compat keys (mirrored from the first option).
- Expose `agent.last_traces` alongside the existing `agent.last_trace`.
- Reject duplicate schema names within one agent (the output map is keyed by name).
- Export all eight schemas (and their `*Model` classes) from `vidbyte.trace.continual`, `vidbyte.trace`, and root `vidbyte`.
- Generalize the continual-trace system prompt so it is schema-agnostic (drives off the provided field list, not hardcoded `goal/actions/mistakes/status`).
- Update tests, the verification script, the README, and the relevant skills.

### Non-Goals

- **No** change to the merge engine in `UpdateTraceTool` (append-unique arrays / deep-merge objects / replace scalars already exists and is reused as-is).
- **No** trace *registry* (a `TraceRegistry` paralleling `HandoffRegistry`) in this PR — listed as an open question / possible follow-up.
- **No** cross-trace synthesis or merging into a single unified artifact (each trace stays a separate named lens).
- **No** support for continual tracing on non-linear runtimes (MCTS/actor) — still rejected at construction, unchanged.
- **No** combined single-trace-agent-run-with-K-tools optimization. Each trace is its own bounded agent run (linear cost stacking, per the requested design).
- **No** new third-party dependencies; **no** change to observability tracers (`Trace`, `DebugTracer`, `ContinualTracer`).
- **No** persistence/storage of trace artifacts beyond returned run metadata.

---

## 3. Background & Context

The continual-trace-artifact foundation lives on `feat/continual-trace-agent-v2` (the confirmed base branch for this work — it is **not** on `main`; `main`'s `vidbyte/trace/` is the unrelated observability-tracer facade). The foundation provides:

- `vidbyte/lib/dataclasses/trace.py` — `TraceField`, `TraceFieldType`, `TraceSchema` (with `from_model`), `TraceOption.continual(schema, every_n_iterations, max_trace_iterations)`.
- `vidbyte/trace/continual/tools.py` — `UpdateTraceTool`, the single model-visible tool, with per-type merge: **append-unique** arrays, **deep-merge** objects, **replace** scalars, drop unknown keys, preserve omitted fields, and shape-mismatch self-correction.
- `vidbyte/trace/continual/agent.py` — `ContinualTraceAgent(BaseAgent)`, built via `from_source_agent(...)` to reuse the source runner/provider, recursion-guarded.
- `vidbyte/trace/continual/middleware.py` — `ContinualTraceMiddleware`, the injection seam: updates every `every_n_iterations` (`after_iteration`) plus one final update (`after_run`), `fail_closed = False`, publishes to `run_state["__result_metadata__"]`.
- `vidbyte/agents/base.py` — `trace_option=` param, non-linear-runtime guard, `_runtime_middleware()` injection, `fork` forwarding, `last_trace`.
- `vidbyte/agents/runtime.py` — `_with_run_state_metadata` generically lifts `run_state["__result_metadata__"]` into `AgentResult.metadata` (feature-agnostic; no trace imports).

Two facts make this change small and safe:

1. **Traces are pure observers.** The middleware writes only to `run_state` and returns `MiddlewareDecision.continue_()` with no transform; the artifact never re-enters the main context window. Therefore N traces cannot interact — there is no ordering, interference, or merge-conflict concern between them. They are N independent read-only lenses.
2. **Field type already encodes merge policy.** `list` → append-unique (running log), `dict` → deep-merge, scalar → replace (latest snapshot). So designing a 20-field schema is purely a matter of choosing the right type per field; the existing tool handles accumulation correctly.

The user-facing motivation: one lens is rarely enough. A coding agent wants `PlanTrace + ArtifactTrace + ToolTrace`; a research agent wants `ReasoningTrace + KnowledgeTrace`. Today only one trace can run per agent.

---

## 4. Requirements

### Functional Requirements

1. `TraceOption.continual(schema)` continues to accept a `TraceSchema`, a Pydantic `BaseModel` subclass, or a `{field: description}` mapping (unchanged).
2. Eight prebuilt schemas are importable from `vidbyte.trace.continual`, `vidbyte.trace`, and `vidbyte`: `ActionTrace`, `PlanTrace`, `ReasoningTrace`, `HistoryTrace`, `ToolTrace`, `DecisionTrace`, `ArtifactTrace`, `KnowledgeTrace`.
3. Each prebuilt schema defines **≥20** fields; every field has a non-empty description and a resolvable `TraceFieldType`.
4. Each prebuilt `*Model` is a Pydantic `BaseModel`; each schema constant is built via `TraceSchema.from_model(...)` with an explicit snake_case `name`.
5. `from vidbyte.trace.continual.prebuilt import ActionTrace, ActionTraceModel` still works after the module→package conversion.
6. `BaseAgent(trace_option=...)` accepts a single `TraceOption`, a `Sequence[TraceOption]`, or `None`.
7. A single `TraceOption` behaves exactly as today (full backward compatibility), including `metadata["trace"]`, `metadata["trace_metadata"]`, and `agent.last_trace`.
8. When multiple options are supplied, the agent attaches one `ContinualTraceMiddleware` per enabled option.
9. Each middleware maintains isolated per-run state keyed by `(class, schema_name)`; one trace's updates/errors never affect another's artifact.
10. Each option respects its own `every_n_iterations` and `max_trace_iterations`.
11. Final run metadata contains `metadata["traces"]` = `{schema_name: artifact}` for every configured trace.
12. Final run metadata contains `metadata["traces_metadata"]` = `{schema_name: {mode, schema, update_count, error_count, last_error?}}`.
13. The first configured option is the "primary": its artifact and summary are mirrored to `metadata["trace"]` and `metadata["trace_metadata"]` for back-compat.
14. `agent.last_trace` mirrors the primary artifact; `agent.last_traces` mirrors the full `{schema_name: artifact}` map (or `None` when tracing is disabled).
15. Constructing an agent with two options whose schemas share a `name` raises `ConfigurationError`.
16. `fork()` propagates the full set of trace options.
17. Non-linear runtimes still reject any enabled trace option at construction.
18. The continual-trace system prompt drives off the supplied schema's field list (schema-agnostic), not hardcoded action fields.
19. A failure in any single trace update is fail-open: it increments that trace's `error_count`, records `last_error`, preserves that trace's prior artifact, and never aborts or alters the main run or the other traces.

### Non-Functional Requirements

- **Backward compatible:** agents without `trace_option`, and agents with a single `trace_option`, behave byte-for-byte as before (same metadata keys, same `last_trace`).
- **Bounded, linear cost:** K traces cost ≈ `Σ_k (floor(I / every_n_k) + 1) × max_trace_iterations_k` extra trace-agent model calls; strictly additive in K.
- **Fail-open & isolated:** per-trace try/except; `fail_closed = False` preserved.
- **No context-window leakage:** no trace artifact ever enters provider messages or the system prompt (invariant #1 of the existing skill).
- **Style:** Context Protocol Header on new modules; one-line signatures with an immediate 1–2 line comment on every method; class-first design.
- **No new dependencies.**

---

## 5. High-Level Design

Two largely independent workstreams.

**(A) Trace shapes.** Convert `vidbyte/trace/continual/prebuilt.py` into a `prebuilt/` package, one module per schema (`action.py`, `plan.py`, `reasoning.py`, `history.py`, `tool.py`, `decision.py`, `artifact.py`, `knowledge.py`). Each module declares a `*Model(BaseModel)` with ≥20 described, typed fields and a module-level `TraceSchema.from_model(...)` constant, mirroring the existing `ActionTraceModel`/`ActionTrace` pattern exactly. Field *type* is chosen to get the right accumulation behavior under the existing merge engine: `list[str]` for running logs (append-unique), `dict` for status maps (deep-merge), `str`/`int` for latest-value snapshots (replace). No engine changes.

**(B) Multi-trace.** `BaseAgent` normalizes `trace_option` to a tuple `self._trace_options`. `_runtime_middleware()` appends one `ContinualTraceMiddleware` per enabled option, tagging index 0 as `primary`. `ContinualTraceMiddleware` is made multi-instance-safe: it keys its per-run state by `(self.__class__, schema_name)` instead of `self.__class__`, and `_publish` writes into keyed `traces` / `traces_metadata` maps (plus the flat `trace` / `trace_metadata` keys when `primary`). The runtime's generic `_with_run_state_metadata` lift already surfaces whatever the middleware published — no runtime change needed.

```
Agent(trace_option=[opt_plan, opt_reasoning])
  └─ BaseAgent._trace_options = (opt_plan, opt_reasoning)
       └─ _runtime_middleware() -> (*user_mw,
                                     ContinualTraceMiddleware(opt_plan,      primary=True),
                                     ContinualTraceMiddleware(opt_reasoning, primary=False))
  run loop:
    after_iteration (every N_k)  ─┐  each mw: ContinualTraceAgent.run_update(...)  [independent]
    after_run (final)            ─┘  -> run_state["__result_metadata__"]["traces"][schema] = artifact
  runtime._with_run_state_metadata -> AgentResult.metadata:
       traces            = {"plan_trace": {...}, "reasoning_trace": {...}}
       traces_metadata   = {"plan_trace": {...}, "reasoning_trace": {...}}
       trace             = {...plan_trace...}      # primary, back-compat
       trace_metadata    = {...plan_trace meta...} # primary, back-compat
```

Key decisions: (1) one middleware instance per trace (rather than a manager object) — minimal, reuses all existing scheduling/fail-open logic, isolates failures for free. (2) Sequential execution via the natural middleware chain — gives the requested linear cost stacking and gentle rate-limit behavior. (3) Keyed output map keyed by `schema.name` — forces (and we validate) unique names, gives stable, self-describing result keys.

---

## 6. Detailed Design

### 6.1 Prebuilt schema package

**File(s):** `vidbyte/trace/continual/prebuilt/__init__.py` (new), `vidbyte/trace/continual/prebuilt/{action,plan,reasoning,history,tool,decision,artifact,knowledge}.py` (new); `vidbyte/trace/continual/prebuilt.py` (deleted)
**Type:** New package replacing a module

#### What it does

Defines the eight prebuilt trace schemas, one module each, and re-exports all schema constants and their `*Model` classes from the package `__init__`.

#### Interface / API

```python
# vidbyte/trace/continual/prebuilt/plan.py
class PlanTraceModel(BaseModel):
    """Plan-oriented continual trace: intended structure and execution progress."""
    goal: str = Field(description="...4-5 sentences...")
    plan_steps: list[str] = Field(default_factory=list, description="...")
    # ... >=20 fields total ...

PlanTrace = TraceSchema.from_model(PlanTraceModel, name="plan_trace", description="...")

# vidbyte/trace/continual/prebuilt/__init__.py re-exports:
from vidbyte.trace.continual.prebuilt.action import ActionTrace, ActionTraceModel
# ... all 8 ...
__all__ = ["ActionTrace", "ActionTraceModel", "PlanTrace", "PlanTraceModel", ...]
```

#### Logic / Algorithm

1. Each module declares a Pydantic model whose fields encode merge policy by type: `list[...]` for append-style logs, `dict`/`Mapping` for status maps, `str`/`int` for latest-value snapshots.
2. Each field carries a `Field(description=...)` of 4–5 sentences (required by `from_model`, which raises on empty descriptions) telling the trace agent what to record and whether to append vs replace.
3. Each module builds its schema constant via `TraceSchema.from_model(Model, name="<snake_case>", description="...")`.
4. The package `__init__` re-exports every schema and model.

#### Edge Cases & Error Handling

- A field missing a description raises `ValueError` at import (caught by import tests).
- An annotation `from_model` cannot map falls back to `STRING` (existing behavior); we avoid exotic annotations.
- Duplicate field names within a model are impossible (Python). Duplicate schema *names* across modules are prevented by code review + a test asserting all eight names are distinct.

#### Field specifications (≥20 each; `[]` = `list[str]` append, `{}` = `dict` merge, `#` = `int` replace, plain = `str` replace)

- **ActionTrace** (`action_trace`): goal; subgoals[]; success_criteria[]; constraints[]; actions_taken[]; current_action; next_action; completed_steps[]; pending_steps[]; mistakes[]; recoveries[]; blockers[]; assumptions[]; decisions[]; inputs_received[]; outputs_produced[]; tools_used[]; external_resources[]; progress_summary; current_status; iteration_notes[]; open_questions[]; confidence; time_sensitive_notes[]. *(24)*
- **PlanTrace** (`plan_trace`): goal; plan_summary; plan_steps[]; current_step; current_step_index#; completed_steps[]; remaining_steps[]; skipped_steps[]; blocked_steps[]; step_dependencies[]; milestones[]; milestones_reached[]; deviations[]; replans[]; assumptions[]; risks[]; contingencies[]; success_criteria[]; estimated_remaining_effort; blockers[]; next_action; plan_confidence; status. *(23)*
- **ReasoningTrace** (`reasoning_trace`): goal; question; reasoning_steps[]; key_inferences[]; evidence[]; assumptions[]; hypotheses[]; confirmed_hypotheses[]; rejected_hypotheses[]; dead_ends[]; alternatives_considered[]; tradeoffs[]; counterarguments[]; contradictions[]; open_questions[]; uncertainties[]; decisions[]; rationale; revisions[]; mental_model; confidence; current_direction. *(22)*
- **HistoryTrace** (`history_trace`): goal; timeline[]; iteration_log[]; model_turns[]; tool_invocations[]; tool_results[]; user_messages[]; system_events[]; state_changes[]; errors[]; retries[]; decisions[]; files_touched[]; external_calls[]; inputs[]; outputs[]; checkpoints[]; token_usage_log[]; notable_quotes[]; environment_notes[]; current_event; last_known_state; event_count#. *(23)* — append-heavy by design (lossless log).
- **ToolTrace** (`tool_trace`): goal; available_tools[]; calls[]; successful_calls[]; failed_calls[]; call_results[]; errors[]; retries[]; arguments_used[]; side_effects[]; files_created[]; files_modified[]; files_deleted[]; api_calls[]; tool_sequence[]; most_used_tools[]; unused_tools[]; permission_denials[]; pending_calls[]; tool_state{}; current_tool; next_tool_action; tool_call_count#; error_count#. *(24)*
- **DecisionTrace** (`decision_trace`): goal; decisions[]; pending_decisions[]; decision_points[]; options_considered[]; rejected_options[]; rationale[]; criteria[]; assumptions[]; tradeoffs[]; constraints[]; reversibility[]; dependencies[]; reversed_decisions[]; deferred_decisions[]; risks[]; stakeholders[]; evidence[]; confidence[]; open_questions[]; current_decision; next_decision; decision_count#. *(23)*
- **ArtifactTrace** (`artifact_trace`): goal; artifacts[]; files_created[]; files_modified[]; files_deleted[]; code_changes[]; documents_produced[]; data_outputs[]; descriptions[]; artifact_status{}; verification[]; tests_added[]; tests_passing[]; tests_failing[]; dependencies_added[]; configuration_changes[]; side_effects[]; locations[]; pending_artifacts[]; rework[]; quality_notes[]; final_deliverables[]; current_artifact; artifact_count#. *(24)*
- **KnowledgeTrace** (`knowledge_trace`): goal; question; sub_questions[]; facts_learned[]; sources[]; source_reliability[]; evidence[]; confirmations[]; contradictions[]; open_questions[]; answered_questions[]; hypotheses[]; assumptions[]; gaps[]; entities[]; relationships[]; definitions[]; quotes[]; dead_ends[]; uncertainties[]; next_queries[]; summary; confidence. *(23)*

---

### 6.2 BaseAgent multi-trace wiring

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Accepts one-or-many trace options, validates them, attaches one middleware per option, propagates on `fork`, and lifts both single and multi result metadata onto the agent.

#### Interface / API

```python
def __init__(self, ..., trace_option: TraceOption | Sequence[TraceOption] | None = None) -> None: ...
self._trace_options: tuple[TraceOption, ...]          # normalized, validated
self._primary_trace_option: TraceOption | None        # first enabled, or None
self.last_trace: dict[str, Any] | None                # primary (unchanged)
self.last_traces: dict[str, dict[str, Any]] | None    # NEW: {schema_name: artifact}
```

#### Logic / Algorithm

1. `_normalize_trace_options(trace_option)` — coerce `None`→`()`, a single `TraceOption`→`(opt,)`, a sequence→`tuple(...)`; raise `ConfigurationError` if any element is not a `TraceOption`.
2. `_validate_trace_options(options)` — raise `ConfigurationError` on duplicate `schema.name`; apply the existing non-linear-runtime guard if any option is enabled.
3. Store `self._trace_options`; set `self._primary_trace_option` to the first enabled option (or `None`).
4. `_runtime_middleware()` — if no enabled options, return `self.middleware`; else append `ContinualTraceMiddleware(opt, source_agent=self, primary=(opt is primary))` for each enabled option.
5. `fork(...)` — pass `trace_option=self._trace_options` (a tuple is an accepted input).
6. In `generate_reply` post-processing (current lines ~377-379): set `self.last_trace = metadata.get("trace")` (unchanged) and `self.last_traces = dict(metadata["traces"]) if isinstance(metadata.get("traces"), Mapping) else None`.

#### Edge Cases & Error Handling

- Empty sequence `trace_option=[]` → tracing disabled, identical to `None`.
- Sequence containing a disabled option (none exist today since `continual` is the only mode) → filtered by `enabled`.
- Duplicate names → `ConfigurationError` at construction (before any run).
- Non-linear runtime + any enabled option → existing `ConfigurationError` message path, now driven by "any enabled".

---

### 6.3 ContinualTraceMiddleware multi-instance safety

**File(s):** `vidbyte/trace/continual/middleware.py`
**Type:** Modified

#### What it does

Makes the middleware safe to instantiate multiple times on one run and publish into a keyed map, while preserving the single-trace flat keys.

#### Interface / API

```python
def __init__(self, option: TraceOption, *, source_agent: "BaseAgent", primary: bool = True) -> None: ...
```

#### Logic / Algorithm

1. Store `self.primary`.
2. State key: replace `ctx.run_state[self.__class__]` with a per-schema key `self._state_key = (type(self), option.schema.name)` used everywhere `_state`/`before_run` touch `run_state`.
3. `_publish(ctx, state)`:
   - `published = ctx.run_state.setdefault(RESULT_METADATA_KEY, {})` (dict).
   - `published.setdefault("traces", {})[schema_name] = dict(state.artifact)`.
   - `published.setdefault("traces_metadata", {})[schema_name] = self._summary(state)`.
   - if `self.primary`: `published["trace"] = dict(state.artifact)`; `published["trace_metadata"] = self._summary(state)`.
4. All scheduling (`_is_interval_due`, `after_iteration`, `after_run`, fail-open `_run_update`) is unchanged.

#### Edge Cases & Error Handling

- Two instances with the same schema name cannot occur (validated in 6.2), so keyed entries never collide.
- If `before_run` is skipped for one instance, `_state` recreates that instance's state under its own key (existing self-heal, now per-key).
- A hook running before `before_run` seeds `published` as a dict via `setdefault`; concurrent middleware run sequentially in the chain, so no race on the shared dict.

---

### 6.4 Schema-agnostic system prompt

**File(s):** `vidbyte/prompts/prompts/continual_trace/system_prompt.md`
**Type:** Modified

#### What it does

Generalizes the "Checklist" and "Goal" sections so the agent fills *whatever* schema it is given, instead of assuming `goal/actions/mistakes/current_status`.

#### Logic / Algorithm

1. Replace field-specific checklist steps with schema-driven steps: "for each declared field, decide if the snapshot adds new information; for array fields append only genuinely new items; for scalar fields write the single latest value; for object fields update only changed keys."
2. Keep the existing identity, fail-open, append-not-clobber, type-correctness, and one-call-per-turn guidance verbatim.

#### Edge Cases & Error Handling

- Prompt remains valid for `ActionTrace` (the prior behavior is a special case of the generalized instructions).
- Prompt catalog test still resolves `Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT`.

---

### 6.5 Exports

**File(s):** `vidbyte/trace/continual/__init__.py`, `vidbyte/trace/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### Logic / Algorithm

1. `vidbyte/trace/continual/__init__.py` — import the 8 schemas + 8 models from `prebuilt` and add to `__all__`.
2. `vidbyte/trace/__init__.py` — re-export the 8 schemas (and models) and add to `__all__`.
3. `vidbyte/__init__.py` — root-export the 8 schema constants (models optional) and add to `__all__`.

#### Edge Cases & Error Handling

- Import smoke test asserts every public path resolves and points at the same object.

---

### 6.6 AgentClient (optional convenience)

**File(s):** `vidbyte/agents/client.py`
**Type:** Modified (optional, low-risk)

#### What it does

`continual_trace(schema, ...)` already builds a single-trace agent. Optionally accept a sequence of schemas/options and forward as `trace_option=[...]`. If this complicates the signature, it is dropped from scope (the public `Agent(trace_option=[...])` path is sufficient).

---

## 7. Data Model Changes

### 7.1 Prebuilt `TraceSchema` constants

**Change type:** New (7) + Expanded (1)

In-memory module constants only; see §6.1 for field lists. No persistence, DB, or wire schema. `TraceField`/`TraceFieldType`/`TraceSchema`/`TraceOption` dataclasses are **unchanged**.

**Migration strategy:** N/A — additive in-memory constants. Forward: add modules + exports. Rollback: delete the package, restore `prebuilt.py` with only `ActionTrace`.

### 7.2 `AgentResult.metadata` / `AgentMessage.metadata`

**Change type:** Modified (additive)

```python
metadata["traces"]          = {schema_name: artifact_dict}          # NEW, always when tracing
metadata["traces_metadata"] = {schema_name: summary_dict}           # NEW, always when tracing
metadata["trace"]           = primary artifact_dict                 # unchanged (mirrors first)
metadata["trace_metadata"]  = primary summary_dict                  # unchanged (mirrors first)
```

**Migration strategy:** Backward-compatible additive keys. Single-trace consumers keep using `trace`/`trace_metadata`. Rollback: stop publishing `traces`/`traces_metadata`.

---

## 8. API Changes

N/A - no HTTP endpoints. The Python SDK surface change:

### 8.1 `BaseAgent(trace_option=...)` accepts a sequence

**Change type:** Modified (additive, backward compatible)

**Request:**

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.continual import PlanTrace, ReasoningTrace

agent = Agent(
    name="worker", system_prompt="...", runner=runner,
    trace_option=[
        TraceOption.continual(PlanTrace, every_n_iterations=4),
        TraceOption.continual(ReasoningTrace, every_n_iterations=6),
    ],
)
reply = await agent.arun("task")
```

**Response:**

```python
reply.metadata["traces"]["plan_trace"]        # PlanTrace artifact
reply.metadata["traces"]["reasoning_trace"]   # ReasoningTrace artifact
reply.metadata["trace"]                       # == traces["plan_trace"] (primary)
agent.last_traces                             # {"plan_trace": {...}, "reasoning_trace": {...}}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Non-`TraceOption` element in the sequence → `ConfigurationError`. |
| N/A | Two options with the same `schema.name` → `ConfigurationError`. |
| N/A | Any enabled option on a non-linear runtime → `ConfigurationError`. |
| N/A | A single trace update failing → recorded in that trace's `traces_metadata[...].error_count`; main run unaffected. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/continual-trace-shapes-and-multi-trace.md` | This design doc |
| CREATE | `vidbyte/trace/continual/prebuilt/__init__.py` | Re-export 8 schemas + models |
| CREATE | `vidbyte/trace/continual/prebuilt/action.py` | Expanded ActionTrace (≥20 fields) |
| CREATE | `vidbyte/trace/continual/prebuilt/plan.py` | PlanTrace |
| CREATE | `vidbyte/trace/continual/prebuilt/reasoning.py` | ReasoningTrace |
| CREATE | `vidbyte/trace/continual/prebuilt/history.py` | HistoryTrace |
| CREATE | `vidbyte/trace/continual/prebuilt/tool.py` | ToolTrace |
| CREATE | `vidbyte/trace/continual/prebuilt/decision.py` | DecisionTrace |
| CREATE | `vidbyte/trace/continual/prebuilt/artifact.py` | ArtifactTrace |
| CREATE | `vidbyte/trace/continual/prebuilt/knowledge.py` | KnowledgeTrace |
| DELETE | `vidbyte/trace/continual/prebuilt.py` | Replaced by `prebuilt/` package |
| MODIFY | `vidbyte/agents/base.py` | Accept sequence, normalize/validate, inject N middleware, fork, `last_traces` |
| MODIFY | `vidbyte/trace/continual/middleware.py` | Per-schema state key, `primary` flag, keyed publish |
| MODIFY | `vidbyte/trace/continual/__init__.py` | Export 8 schemas + models |
| MODIFY | `vidbyte/trace/__init__.py` | Export 8 schemas + models |
| MODIFY | `vidbyte/__init__.py` | Root-export 8 schemas |
| MODIFY | `vidbyte/prompts/prompts/continual_trace/system_prompt.md` | Schema-agnostic checklist |
| MODIFY | `vidbyte/agents/client.py` | (Optional) `continual_trace` multi support |
| MODIFY | `tests/test_continual_trace.py` | Schema + multi-trace coverage |
| MODIFY | `scripts/test-continual-trace.py` | Verification cases for new behavior |
| MODIFY | `README.md` | Document new schemas + multi-trace |
| MODIFY | `skills/vidbyte-sdk/continual-tracing.md` | New schemas, prebuilt package, multi-trace, publish keys |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Structure rules (prebuilt package, `traces` metadata) |

Summary: **9 created, 1 deleted, 12 modified** (`client.py` optional).

---

## 10. Testing Plan

Tests extend `tests/test_continual_trace.py` (unittest, fake runners — no live providers) and the standalone `scripts/test-continual-trace.py`.

### Unit Tests

- `PrebuiltSchemaTests.test_all_eight_schemas_importable` — [Edge Case] All 8 schemas + models import from all three public paths and are the same object.
- `PrebuiltSchemaTests.test_each_schema_has_at_least_20_fields` — [Hidden Assumption] Every schema meets the ≥20-field requirement; guards against a stripped-down model.
- `PrebuiltSchemaTests.test_every_field_has_description_and_type` — [Silent Failure] A field with an empty description would silently degrade trace quality; `from_model` must have rejected it, and every field has a `TraceFieldType`.
- `PrebuiltSchemaTests.test_schema_names_are_unique_and_snake_case` — [Silent Failure] Two schemas sharing a name would collide in `metadata["traces"]`.
- `PrebuiltSchemaTests.test_initial_artifact_keys_match_fields` — [Silent Failure] `initial_artifact()` must contain exactly the declared fields (no missing/extra keys).
- `PrebuiltSchemaTests.test_list_fields_default_to_empty_not_none` — [Edge Case] Append-style fields behave correctly from an empty start.
- `MergePolicyTests.test_array_field_appends_unique` — [Silent Failure] Re-sending an existing list item must not duplicate it (reuses existing tool; asserts on a new schema's list field).
- `MergePolicyTests.test_object_field_deep_merges` — [Edge Case] `tool_state` / `artifact_status` dict fields merge keys rather than replace.
- `MergePolicyTests.test_scalar_field_replaces` — [Edge Case] `current_status`-style scalar holds latest value.
- `MergePolicyTests.test_integer_counter_replaces_not_appends` — [Hidden Failure] `event_count`/`decision_count` are integers; must replace, not coerce to a list.
- `BaseAgentTraceOptionsTests.test_single_option_backward_compatible` — [Hidden Assumption] A single `TraceOption` still yields `metadata["trace"]`, `trace_metadata`, and `last_trace`.
- `BaseAgentTraceOptionsTests.test_sequence_of_options_normalized` — [Edge Case] A list of two options is stored as a 2-tuple.
- `BaseAgentTraceOptionsTests.test_empty_sequence_disables_tracing` — [Edge Case] `trace_option=[]` behaves like `None` (no middleware, no metadata).
- `BaseAgentTraceOptionsTests.test_duplicate_schema_names_rejected` — [Hidden Failure] Two options with the same schema name raise `ConfigurationError`.
- `BaseAgentTraceOptionsTests.test_non_trace_option_element_rejected` — [Hidden Assumption] A non-`TraceOption` in the sequence raises `ConfigurationError`.
- `BaseAgentTraceOptionsTests.test_non_linear_runtime_rejects_any_option` — [Hidden Assumption] MCTS/actor runtime + any enabled option raises.
- `BaseAgentTraceOptionsTests.test_fork_propagates_all_options` — [Silent Failure] Forked agent keeps both traces, not just the first.
- `MiddlewareKeyingTests.test_two_instances_use_distinct_state_keys` — [Hidden Failure] Two middleware on one run do not overwrite each other's `run_state` entry.
- `MiddlewareKeyingTests.test_primary_mirrors_flat_keys` — [Silent Failure] Only the primary writes `trace`/`trace_metadata`; non-primary does not clobber them.

### Integration Tests

- `MultiTraceRuntimeTests.test_two_traces_both_present_in_metadata` — [Edge Case] A run with `PlanTrace + ReasoningTrace` produces `metadata["traces"]` with both keys populated. *Silent-failure path:* a regression that drops the second trace is caught by asserting both keys.
- `MultiTraceRuntimeTests.test_independent_update_counts` — [Silent Failure] With different `every_n_iterations`, each trace's `traces_metadata[...].update_count` differs as expected (off-by-one / shared-scheduler bugs caught).
- `MultiTraceRuntimeTests.test_one_trace_failure_isolates` — [Hidden Failure] Forcing the trace agent to raise for one schema increments only that schema's `error_count`, preserves its prior artifact, leaves the other trace and the main result intact.
- `MultiTraceRuntimeTests.test_primary_backcompat_keys_match_first_option` — [Hidden Assumption] `metadata["trace"]` equals `metadata["traces"][first_schema]`.
- `MultiTraceRuntimeTests.test_trace_never_enters_context_window` — [Hidden Failure] Assert the rendered main context / provider messages never contain trace artifact content (invariant #1), with two traces active.
- `MultiTraceRuntimeTests.test_disabled_tracing_unchanged_metadata_shape` — [Hidden Assumption] No `trace*`/`traces*` keys appear when `trace_option` is `None`.

### Manual / QA Test Cases

1. Given an agent with `trace_option=[TraceOption.continual(PlanTrace, every_n_iterations=2), TraceOption.continual(ToolTrace, every_n_iterations=3)]`, when it runs 6 iterations, then `metadata["traces"]` has `plan_trace` and `tool_trace`, with `plan_trace` update_count ≥ tool_trace update_count. — [Silent Failure]
2. Given a single `TraceOption.continual(ActionTrace)` (legacy usage), when it runs, then `metadata["trace"]` and `agent.last_trace` are populized exactly as before this change. — [Hidden Assumption]
3. Given two options with the same schema (`ActionTrace` twice), when constructing the agent, then a `ConfigurationError` is raised immediately. — [Hidden Failure]
4. Given a trace agent that returns invalid `updateTrace` arguments for `KnowledgeTrace`, when the run completes, then the main answer still returns and `traces_metadata["knowledge_trace"].error_count > 0`. — [Hidden Failure]

### Verification Script

Extend `scripts/test-continual-trace.py` to cover: all 8 schemas construct and have ≥20 typed/described fields; single-trace back-compat; two-trace metadata presence + independent counts; duplicate-name rejection; per-trace failure isolation. Print `PASS`/`FAIL` per case, a final `X/Y tests passed`, and exit non-zero on any failure.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | >=3.11 | dataclasses, enum, json, unittest | Existing only |
| pydantic | Existing `>=2,<3` | `BaseModel`/`Field` for prebuilt models | Reuses existing pattern |

No new external services or packages.

---

## 12. Rollout & Deployment

- Package-only SDK change; no feature flag.
- Branch: `feat/continual-trace-multi-and-shapes`, **based on `feat/continual-trace-agent-v2`**; PR **targets `feat/continual-trace-agent-v2`** (stacked) so the diff shows only this work and merges into `main` after the foundation lands.
- Additive and backward compatible: single-trace and no-trace agents are unchanged.
- Rollback: revert the PR; the foundation branch is untouched. Granular rollback: delete the `prebuilt/` package (restore single-`ActionTrace` module) and revert the `base.py`/`middleware.py` multi-trace edits.

---

## 13. Open Questions

- [ ] **Trace registry?** Should we add a `TraceRegistry` (slug→schema, `describe()`, `from_handoff` adapter) paralleling `HandoffRegistry`? Recommendation: **defer** to a follow-up PR; out of scope here.
- [ ] **`traces_metadata` naming.** Keyed sibling is named `traces_metadata` to parallel `trace_metadata`. Acceptable, or prefer `trace_metadata_by_schema`? Recommendation: `traces_metadata`.
- [ ] **AgentClient multi support.** Include sequence support in `continual_trace(...)` now, or leave only `Agent(trace_option=[...])`? Recommendation: include only if it stays a one-line signature; otherwise defer.
- [ ] **HistoryTrace fidelity.** `HistoryTrace` wants near-lossless logging, which fights the trace agent's summarization instinct. v1 keeps it LLM-driven with append-heavy fields + a prompt note; a mechanical (non-LLM) history producer is a possible future enhancement. Recommendation: ship LLM-driven now.

---

## 14. Alternatives Considered

### Alternative 1: A `ContinualTraceManager` object holding N controllers
- What: One manager wired into the runtime, looping over controllers.
- Why rejected: The v2 architecture is middleware-based, not controller-based. One middleware instance per option reuses all existing scheduling, fail-open, and publish logic with near-zero new code and free failure isolation. A manager would reintroduce the controller concept v2 deliberately replaced.

### Alternative 2: Single trace agent run with K `updateTrace` tools
- What: One model call per interval that updates all K schemas via K tools.
- Why rejected: Couples schemas, forces a shared interval, and complicates partial-failure handling. The requested model is independent traces with linearly-stacked cost; per-trace isolation is more valuable than the token savings.

### Alternative 3: Merge all traces into one flat artifact
- What: One combined dict spanning all schemas.
- Why rejected: Immediate field-name collisions (`goal` in every schema) and loss of which lens produced which value. Keyed-by-schema `metadata["traces"]` keeps lenses clean and self-describing.

### Alternative 4: Keep `prebuilt.py` as one growing module
- What: Add all 8 schemas (160+ described fields) to the single existing file.
- Why rejected: At ~20 rich-described fields each, one file becomes thousands of lines and hard to review/maintain. A module-per-schema package matches the handoff-catalog precedent and keeps each lens isolated. Import paths are preserved via the package `__init__`.

---

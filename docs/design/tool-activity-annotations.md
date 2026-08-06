# Design Doc: Tool Activity Annotations

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-05
**Last Updated:** 2026-08-05

---

## 1. Overview

Tool activity annotations let an application ask the same model that is already choosing a tool to provide one small, typed explanation of the high-level action represented by that call. An SDK user binds a `ToolActivity` schema to an existing tool with `tool.with_activity(...)`; the provider sees one nested `activity` input, the SDK validates and separates that input from the tool's business arguments, and the completed `ToolCallContext` exposes a normalized `ToolCallActivity`. This creates product-safe action evidence without a second agent, a separate reporting tool, raw chain-of-thought, or changes to the wrapped tool's execution and billing contracts.

---

## 2. Goals & Non-Goals

### Goals

- Add one small, public `ToolActivity` component that can be attached to any existing `BaseTool`.
- Render the activity's Pydantic schema as a nested `activity` object in OpenAI-compatible, Anthropic, and Gemini tool declarations.
- Validate and normalize activity before a tool executes, returning the normal tool validation error path when it is missing or invalid.
- Keep activity separate from business arguments so permissions, identical-call limits, middleware policy, and concrete tool implementations continue to see the original tool contract.
- Expose the normalized value and static consumer metadata on `ToolCall` and `ToolCallContext` for application middleware and final agent results.
- Preserve the identity and usage accounting of wrapped priced-operation tools such as `BraveSearchTool` and `FirecrawlFetchTool`.
- Document the feature in the public README and `llms.txt`.

### Non-Goals

- Running an activity summarizer model, continual-trace agent, or any additional model call.
- Creating a special "report activity" tool that competes with the domain tool the model actually needs to call.
- Capturing hidden reasoning, chain-of-thought, provider-native messages, or raw tool results.
- Giving the SDK product-specific action names, persistence, display copy, sampling rules, or MongoDB knowledge.
- Supporting `run_every`, tool-count cadence, or arbitrary runtime conditions in the SDK. Tool schemas are static for one agent run; applications control cost by attaching activity only to high-signal tools and decide after execution which domain event to emit.
- Changing provider operation pricing, provider clients, retry policy, or usage records.
- Adding new test files; existing SDK test modules will be extended.

---

## 3. Background & Context

Vidbyte SDK tools currently expose `ToolSpec`, execute a `ToolCall`, and leave a `ToolCallContext` in the final `AgentResult.metadata["tool_calls"]`. The formatter builds provider schemas once from the registered tool specs, while the runtime applies tool limits and middleware before calling the implementation. Applications can inspect ordinary arguments, but adding a product explanation directly to a concrete tool's parameters has three problems: it reaches the tool implementation even though it is not an execution argument, it changes identical-call and permission policy inputs, and each application must rebuild the same schema/capture plumbing.

The research harness is the first consumer. It needs the discovery model to label why it is searching and why it selected candidates, but it must keep using the SDK's executing `BraveSearchTool` so provider transport, normalized payloads, retries, and usage metadata remain SDK-owned. The harness also needs the activity in `after_tool_call` middleware while the run is active, not only after a second summarization pass.

The current SDK already depends on Pydantic 2 and already translates Pydantic output schemas. Requiring a Pydantic model for an activity schema therefore produces a smaller and more deterministic API than introducing a second JSON Schema validation system. `ToolActivity.metadata` is static application metadata, not model-authored data; it identifies a schema version or downstream consumer without being rendered as an input field.

The important runtime constraint is priced-operation wrapping. A generic activity-bound tool is still a wrapper rather than a `PricedOperationTool` subclass, so usage accounting must unwrap it before checking the operation type. No application should subclass or reimplement `BraveSearchTool` merely to gain activity capture.

---

## 4. Requirements

### Functional Requirements

1. `BaseTool.with_activity(activity)` returns a tool with the same name, description, permission, output schema, and execution behavior as the original tool.
2. A `ToolActivity` declares a non-empty description, a Pydantic `BaseModel` schema, whether the annotation is required, and immutable static metadata.
3. A bound tool schema contains exactly one reserved top-level `activity` property whose value is the activity model's JSON Schema.
4. Binding fails immediately if the original tool already declares an `activity` parameter or input-schema property.
5. When activity is required, a missing, non-object, or Pydantic-invalid value is a normal `validation_error`; the underlying tool and priced provider are not called.
6. When activity is optional and omitted, the underlying call executes with `ToolCall.activity is None`.
7. A valid model-authored activity is normalized through `model_validate(...).model_dump(mode="json")` and stored as `ToolCallActivity.payload`.
8. The underlying tool receives its original business arguments with the reserved `activity` key removed; the normalized annotation is available separately on `ToolCall.activity`.
9. Tool settings and permission checks evaluate the prepared call's business arguments, so changing an explanation cannot bypass identical-call limits.
10. `before_tool_call` and `after_tool_call` middleware receive the prepared `ToolCall`, including `ToolCall.activity`.
11. `ToolCallContext` retains the normalized activity in final runtime metadata for successful, failed, and denied calls that reached preparation.
12. `ToolExecutor` and `AgentRuntime` use the same preparation helper and validation behavior.
13. Usage accounting unwraps activity binding before detecting `PricedOperationTool`; operation usage and result metadata are not copied, altered, or re-priced by the wrapper.
14. Provider schemas remain valid for OpenAI-compatible, Anthropic, and Gemini formats, including tools that already use `input_schema`.

### Non-Functional Requirements

- **Performance:** Activity adds no network round trip and no model invocation. Preparation is one Pydantic validation per annotated tool call.
- **Scalability:** The component is stateless and safe for concurrent calls. No global registry or per-call mutable state is added.
- **Security:** Static metadata is never rendered to the model. Activity payloads are bounded by the consumer's Pydantic schema and are not treated as trusted execution arguments.
- **Reliability:** Invalid activity fails before provider/tool execution. A wrapper cannot suppress the wrapped tool's result status, output, metadata, exception normalization, or usage hooks.
- **Compatibility:** Unannotated tools produce byte-for-byte-equivalent provider input schemas and retain existing runtime behavior. New dataclass fields have defaults.
- **Observability:** Normal runtime tracing may show the prepared `ToolCall.activity`, but the SDK does not automatically publish it as an `ActionTrace` or product event.

---

## 5. High-Level Design

`ToolActivity` is a declarative subcomponent of a tool, not a tool and not a tracer. `BaseTool.with_activity(...)` returns a private delegating wrapper whose `ToolSpec` carries the activity declaration. `ToolsFormatter` merges that declaration into the provider-facing schema under the fixed key `activity`. Keeping the key fixed makes prompts and middleware uniform and avoids a second naming configuration that every consumer would otherwise have to discover.

After provider tool-call parsing, the catalog prepares each call against its registered tool. Preparation removes `activity` from `arguments`, validates it with the configured Pydantic model, and places the normalized record on `ToolCall.activity`. From that point onward, tool settings, middleware, permission checks, validation, and execution operate on the prepared call. The wrapped tool sees the original arguments plus the new separate dataclass field, so ordinary implementations and `FunctionTool` call signatures are unchanged.

The wrapper delegates `spec`, `validate_call`, and `execute`. Runtime usage accounting unwraps the wrapper before its `isinstance(PricedOperationTool)` check, preserving SDK-owned search/fetch metering. Applications consume `ctx.tool_call.activity` in middleware and translate it to their own events, conditions, summaries, and persistence shapes.

```text
Application
  BraveSearchTool(client=...).with_activity(ToolActivity(SearchActivityDto, ...))
                                      |
                                      v
Provider schema: { query, count, activity: { ...typed fields... } }
                                      |
                               model tool call
                                      |
                                      v
Tools.prepare_call -> ToolCall(arguments={query, count}, activity=ToolCallActivity(...))
                         |                         |
                         v                         v
              BraveSearchTool.execute      application middleware
                         |
                  unchanged ToolResult
                         |
                 priced usage accounting
```

---

## 6. Detailed Design

### 6.1 Activity Contracts

**File(s):** `vidbyte/lib/dataclasses/tools.py`, `vidbyte/tools/types.py`, `vidbyte/lib/dataclasses/__init__.py`
**Type:** Modified

#### What it does

Defines the public declaration and normalized per-call record, then adds optional activity fields to the existing tool contracts.

#### Interface / API

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel

@dataclass(frozen=True, slots=True)
class ToolActivity:
    schema: type[BaseModel]
    description: str
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ToolCallActivity:
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ToolSpec:
    # existing fields omitted
    activity: ToolActivity | None = None

@dataclass(frozen=True, slots=True)
class ToolCall:
    # existing fields omitted
    activity: ToolCallActivity | None = None

@dataclass(frozen=True, slots=True)
class ToolCallContext:
    # existing fields omitted
    activity: ToolCallActivity | None = None
```

#### Logic / Algorithm

1. `ToolActivity.__post_init__` rejects blank descriptions and anything other than a Pydantic `BaseModel` subclass.
2. Static metadata is copied at construction/preparation boundaries so callers cannot mutate a captured record through a shared dictionary.
3. `ToolCallActivity.payload` contains only the normalized JSON-mode model dump.
4. Existing constructors remain source compatible because every new field defaults to `None` or an empty mapping.

#### Edge Cases & Error Handling

- A Pydantic dataclass or arbitrary callable is not accepted as the schema; consumers declare an explicit `BaseModel` boundary.
- Schema bounds such as enum values, maximum list size, and maximum text length are enforced by the consumer model.
- The SDK does not interpret activity field names or values.

---

### 6.2 Activity Binding and Call Preparation

**File(s):** `vidbyte/tools/activity.py`, `vidbyte/tools/base.py`, `vidbyte/tools/catalog.py`
**Type:** New file and modified files

#### What it does

Adds the ergonomic binding method, a delegating wrapper, a common call-preparation helper, and a common unwrap helper.

#### Interface / API

```python
class BaseTool(ABC):
    def with_activity(self, activity: ToolActivity) -> BaseTool: ...

class ActivityToolFormatter:
    @staticmethod
    def bind(tool: BaseTool, activity: ToolActivity) -> BaseTool: ...

    @staticmethod
    def prepare_call(tool: BaseTool, call: ToolCall) -> ToolCall: ...

    @staticmethod
    def unwrap(tool: BaseTool) -> BaseTool: ...

    @staticmethod
    def declared(tool: BaseTool) -> ToolActivity | None: ...

class Tools(Sequence[BaseTool]):
    def prepare_call(self, call: ToolCall) -> ToolCall: ...
```

Example:

```python
search_tool = BraveSearchTool(client=brave_client).with_activity(
    ToolActivity(
        schema=ResearchSearchActivity,
        description="Describe the user-visible research action this search advances.",
        metadata={"schema_version": 1, "consumer": "research_action_trace"},
    )
)
```

#### Logic / Algorithm

1. `with_activity` delegates to `ActivityToolFormatter.bind`, which rejects double binding and returns an activity-bound delegating tool.
2. Its `spec()` uses `dataclasses.replace` to add the declaration to the wrapped spec without changing other fields.
3. `ActivityToolFormatter.prepare_call` pops the reserved `activity` value from a copied argument dictionary.
4. If present, it validates with the activity model and creates `ToolCallActivity(normalized_payload, copied_metadata)`.
5. It returns a new immutable `ToolCall` with business arguments, the same name/call ID/metadata, and the normalized activity.
6. The wrapper validates and executes the prepared call by delegating to the underlying tool via `ActivityToolFormatter` helpers.
7. `ActivityToolFormatter.unwrap` follows only SDK activity wrappers and returns the original tool; it does not generically traverse arbitrary application wrappers.

#### Edge Cases & Error Handling

- A tool that already owns an `activity` input cannot be bound; this avoids silently replacing a domain parameter.
- Missing required activity and Pydantic validation failures produce a bounded validation message through the existing tool error path.
- Optional missing activity leaves the call unannotated.
- Unknown tools cannot be prepared and continue to the existing `unknown_tool` result.
- Binding does not mutate the original tool, so one instance may be used unannotated while another binding wraps it only when the caller deliberately shares the instance.

---

### 6.3 Provider Schema Rendering

**File(s):** `vidbyte/lib/tools/formatter.py`
**Type:** Modified

#### What it does

Merges the nested activity schema into the best available business-input schema before provider-specific wrapping.

#### Interface / API

```python
class ToolsFormatter:
    @staticmethod
    def _schema_for_spec(spec: ToolSpec) -> dict[str, Any]: ...

    @staticmethod
    def _schema_with_activity(
        schema: Mapping[str, Any],
        activity: ToolActivity,
    ) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Build the existing schema from `ToolSpec.input_schema` or `ToolParameter` declarations.
2. Deep-copy it before modification.
3. Require an object schema and reject an existing `properties.activity`.
4. Resolve `activity.schema.model_json_schema()` and place it at `properties.activity`, adding the declaration description to the nested schema.
5. Add `activity` to `required` only when `ToolActivity.required` is true.
6. Keep the original `additionalProperties` policy.
7. OpenAI-compatible, Anthropic, and Gemini formatters reuse this one merged schema.

#### Edge Cases & Error Handling

- A non-object top-level input schema cannot accept the reserved field and raises configuration error during schema construction.
- `$defs` emitted inside the nested Pydantic schema remain inside the activity property and are not merged with unrelated tool definitions.
- Unannotated schemas follow the existing code path unchanged.

---

### 6.4 Runtime, Middleware, and Usage Preservation

**File(s):** `vidbyte/agents/runtime.py`, `vidbyte/tools/executor.py`
**Type:** Modified

#### What it does

Prepares calls before policy/execution, exposes the activity to middleware and results, and preserves priced-operation detection.

#### Interface / API

```python
# AgentRuntime, after provider parsing and before _process_tool_call policy:
prepared_call = self.tools.prepare_call(raw_call)

# Middleware:
activity = ctx.tool_call.activity
if activity is not None:
    domain_activity = ResearchSearchActivity.model_validate(activity.payload)
```

#### Logic / Algorithm

1. The runtime prepares each parsed call before tool settings, `before_tool_call`, permission, tool validation, or execution.
2. The assistant's provider-native tool-call history is preserved unchanged; only the local execution call is prepared.
3. `_build_tool_call_context` copies `call.activity` into `ToolCallContext.activity` for every terminal call state.
4. `ToolExecutor` resolves the tool, prepares the call, and then applies its existing permission/validation/execution sequence.
5. `_record_operation_usage` unwraps an activity-bound tool and performs the existing `PricedOperationTool` logic against the original instance and unchanged result.

#### Edge Cases & Error Handling

- Activity validation fails before billing because no provider operation is attempted.
- Tool middleware denial retains a valid prepared activity on the denied context, allowing a product to explain that an intended action was blocked without claiming it executed.
- Middleware retries reuse the same normalized activity and call ID.
- Activity never enters operation-usage metadata, so it cannot affect units, attempts, mode, or reported cost.

---

### 6.5 Public Exports and Documentation

**File(s):** `vidbyte/tools/__init__.py`, `vidbyte/__init__.py`, `README.md`, `llms.txt`
**Type:** Modified

#### What it does

Makes `ToolActivity` and `ToolCallActivity` available from the normal tool namespaces and documents the intended attachment/capture pattern.

#### Interface / API

```python
from vidbyte import ToolActivity, ToolCallActivity
# or
from vidbyte.tools import ToolActivity, ToolCallActivity
```

#### Logic / Algorithm

1. Re-export both public contracts through `vidbyte.tools` and the root namespace.
2. Add one concise README example using `.with_activity(...)`.
3. Add an `llms.txt` section that tells agents to attach activities only to semantically meaningful tools and consume them from middleware/context.
4. State that activity is not chain-of-thought and must use bounded, product-safe fields.

#### Edge Cases & Error Handling

- The private delegating wrapper is not exported; users should not depend on its type.
- Existing import paths remain unchanged.

---

### 6.6 Existing Test Coverage

**File(s):** `tests/test_tool_core.py`, `tests/test_provider_tool_schema_translation.py`, `tests/test_agent_runtime.py`
**Type:** Modified

#### What it does

Extends existing test modules without creating a new test file.

#### Interface / API

```text
test_tool_core.py
  - binding and collision behavior
  - required/optional validation
  - underlying argument separation

test_provider_tool_schema_translation.py
  - nested activity schemas for OpenAI, Anthropic, and Gemini
  - unannotated schemas unchanged

test_agent_runtime.py
  - middleware receives normalized activity
  - ToolCallContext retains activity
  - identical-call policy uses business arguments
  - activity-bound priced tool remains metered
```

#### Logic / Algorithm

1. Define small local Pydantic activity models inside existing tests.
2. Use deterministic fake runners/tool results.
3. Assert on public contracts rather than the private wrapper class.
4. Run the full SDK CI script after targeted tests.

#### Edge Cases & Error Handling

- Tests include invalid enum and over-bound text failures.
- Tests prove that tool execution is not invoked on invalid activity.

---

## 7. Data Model Changes

### 7.1 In-Memory Tool Contracts

**Change type:** Modified

```python
ToolSpec.activity: ToolActivity | None = None
ToolCall.activity: ToolCallActivity | None = None
ToolCallContext.activity: ToolCallActivity | None = None
```

**Migration strategy:**

- Forward migration: additive defaulted dataclass fields and public exports; no serialized database schema changes.
- Rollback plan: remove activity bindings in consumers first, then deploy the prior SDK. Calls made without bindings remain compatible throughout.

---

## 8. API Changes

N/A - this SDK feature changes Python tool contracts and provider tool schemas; it adds no HTTP endpoint.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/activity.py` | Activity binding, preparation, and unwrap behavior |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add declaration, record, and optional tool-call fields |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export tool activity dataclasses |
| MODIFY | `vidbyte/tools/types.py` | Preserve the public compatibility import path |
| MODIFY | `vidbyte/tools/base.py` | Add `BaseTool.with_activity` |
| MODIFY | `vidbyte/tools/catalog.py` | Prepare calls against registered activity bindings |
| MODIFY | `vidbyte/tools/executor.py` | Apply the same preparation path outside AgentRuntime |
| MODIFY | `vidbyte/lib/tools/formatter.py` | Merge the nested activity schema into provider declarations |
| MODIFY | `vidbyte/agents/runtime.py` | Prepare calls, expose activity to middleware/context, and unwrap priced tools |
| MODIFY | `vidbyte/tools/__init__.py` | Export public activity contracts |
| MODIFY | `vidbyte/__init__.py` | Export public activity contracts from the root namespace |
| MODIFY | `README.md` | Document attachment and consumption |
| MODIFY | `llms.txt` | Add agent-oriented usage guidance |
| MODIFY | `tests/test_tool_core.py` | Cover binding, validation, and argument separation |
| MODIFY | `tests/test_provider_tool_schema_translation.py` | Cover all provider schema shapes |
| MODIFY | `tests/test_agent_runtime.py` | Cover runtime capture, policy, and priced-tool preservation |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Pydantic | Existing `>=2,<3` dependency | Define and validate bounded activity payloads | Low; already required by the SDK |
| OpenAI-compatible tool schema | Existing provider adapter | Render nested activity input | Low; ordinary JSON Schema object property |
| Anthropic tool schema | Existing provider adapter | Render nested activity input | Low; shares the same schema builder |
| Gemini function schema | Existing provider adapter | Render nested activity input | Medium; provider schema compatibility is covered by existing translation tests |

---

## 11. Rollout & Deployment

- This is additive for unannotated users but changes the model-facing input schema of a tool once an application opts in.
- Merge and publish the SDK PR before deploying any consumer that imports `ToolActivity` or calls `.with_activity(...)`.
- The Vidbyte research-harness PR pins its SDK dependency to the reviewed SDK commit, so it does not rely on an ambient editable install.
- Required SDK verification in the implementation worktree:
  - `python -m pip install -e ".[dev]"`
  - source stage with the worktree on `PYTHONPATH`
  - package stage without the source-tree override
  - `python scripts/run_ci.py` as the full canonical gate
- Roll back the consumer bindings first. The SDK can then be rolled back without data migration because activity is not persisted by the SDK.

---

## 12. Open Questions

N/A - the API deliberately fixes the input key to `activity`, uses Pydantic-only schemas, and leaves cadence/conditions to consumers; no implementation-blocking SDK decision remains.

---

## 13. Alternatives Considered

### Alternative 1: Separate Continual-Trace Agent

- What: Send tool history to another agent that periodically interprets the run.
- Why rejected: Adds model calls, latency, duplicate context, ordering races, and hallucination risk while the primary model already knows why it chose the tool.

### Alternative 2: Separate Activity Reporting Tool

- What: Register a `report_activity` tool and ask the model to call it alongside domain tools.
- Why rejected: Adds extra tool calls, creates unenforceable ordering, consumes tool budgets, and can report an action that never executes.

### Alternative 3: Add Product Fields Directly to Brave/Firecrawl

- What: Add research-specific purpose and reason arguments to the built-in provider tools.
- Why rejected: Pollutes reusable provider contracts, sends non-execution inputs into provider tool implementations, and cannot generalize to other domains.

### Alternative 4: SDK Cadence and Conditions

- What: Configure `run_every=5` or arbitrary conditions on `ToolActivity`.
- Why rejected: Provider schemas are static for a run, cadence creates hidden mutable state, and the SDK cannot know which activity is product-significant. Applications should attach only to chosen tools and conditionally translate the captured record.

### Alternative 5: Leave Activity Inside `ToolCall.arguments`

- What: Expose the extra nested object but let every tool ignore it.
- Why rejected: Breaks strict function tools, changes permission and identical-call inputs, and turns a product annotation into an accidental execution parameter.

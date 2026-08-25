# Design Doc: Tool Specification Customization

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-25
**Last Updated:** 2026-08-25

---

## 1. Overview

Add an immutable, opt-in `BaseTool.customize()` API that lets SDK users replace a built-in tool description and the descriptions of existing top-level parameters for their application context. Customization returns a wrapper around the original tool, updates both prompt-facing and provider-facing schema representations, and delegates validation and execution unchanged. This gives prebuilt tools useful local presentation flexibility without allowing a schema-only parameter extension to promise behavior the tool does not implement.

---

## 2. Goals & Non-Goals

### Goals

- Add `BaseTool.customize()` as the single public entry point for model-facing description customization.
- Support replacing the full tool description.
- Support replacing descriptions for existing top-level parameters by name.
- Preserve the wrapped tool's name, permission, metadata, output schema, activity declaration, validation, execution, and result behavior.
- Update both `ToolSpec.parameters` and explicit `ToolSpec.input_schema` properties so prompt and provider schema output stay aligned.
- Make customization wrappers compose with `with_activity()` in either order.
- Preserve priced-operation identity through the existing activity unwrapping path.
- Keep the original tool object unchanged so one built-in instance can safely be reused by multiple agents with different descriptions.
- Extend existing tool contract tests rather than creating a new test feature directory.

### Non-Goals

- Adding new parameters to an existing tool.
- Changing parameter names, types, requiredness, defaults, permission, output schemas, or tool names.
- Renaming tools or introducing aliases.
- Changing tool execution, validation, middleware, billing, or context behavior.
- Adding a global mutable customization registry.
- Adding a new dependency, persistence model, migration, or feature flag.

---

## 3. Background & Context

Vidbyte tools expose two related model-facing representations: a `ToolSpec.parameters` tuple used by prompt rendering and a possible explicit `ToolSpec.input_schema` used by provider schema formatting. `ToolsFormatter._schema_for_spec()` prefers the explicit schema when present, so an override that edits only `ToolParameter.description` would silently fail for tools such as `FunctionTool` and several built-ins with explicit JSON Schema.

The existing `BaseTool.with_activity()` wrapper demonstrates the repository's preferred extension shape: return a new delegating wrapper, preserve the wrapped behavior, add a controlled model-facing declaration, validate it separately, and remove the extension before execution. Its current unwrapping path is activity-specific. A generic customization wrapper must participate in the same unwrapping path or a customized `PricedOperationTool` would no longer be recognized for operation accounting.

The PR #343 reasoning tools use explicit `ToolParameter` declarations and rich descriptions, so they will work with this API without any changes to their individual tool files. The feature remains independent of those built-ins and is implemented at the shared tool contract boundary.

---

## 4. Requirements

### Functional Requirements

1. Every `BaseTool` subclass exposes `customize()` with optional `description` and `parameter_descriptions` keyword arguments.
2. `customize(description=...)` returns a new delegating tool whose `spec().description` contains the replacement while the original tool's spec is unchanged.
3. `customize(parameter_descriptions={...})` replaces descriptions for matching top-level parameter names in `ToolSpec.parameters`.
4. When the wrapped spec has `input_schema`, the same parameter description replacements appear in the schema's top-level `properties` mapping.
5. Unknown parameter names, blank replacement descriptions, and blank tool descriptions fail immediately with `ValueError`.
6. The customization wrapper preserves the wrapped tool's stable name and delegates `validate_call()` and `execute()` without changing their arguments or results.
7. Customization composes with activity binding in both call orders, and activity remains separated from business arguments before the wrapped tool executes.
8. `ActivityToolFormatter.unwrap()` unwraps both activity and customization wrappers so priced operation accounting remains intact.
9. Provider schemas and prompt descriptions expose customized text for OpenAI-compatible, Anthropic, and Gemini formatting through the existing formatter path.
10. No built-in tool file needs to be edited to gain customization support.

### Non-Functional Requirements

- No runtime or network dependency is added.
- Customization is instance-local, deterministic, and side-effect free with respect to the original tool.
- Explicit input schemas are deep-copied before modification so caller-owned mappings are not mutated.
- The wrapper adds no database state, unbounded storage, concurrency primitive, or retry behavior.
- Existing provider schema formatting and operation billing remain backward compatible for uncustomized tools.
- The canonical verification command is `PYTHONPATH=<worktree> python scripts/run_ci.py --stage source`, followed by `python scripts/run_ci.py --stage package` with no `PYTHONPATH`, and finally the full `python scripts/run_ci.py` gate when the source and package stages are individually green.

---

## 5. High-Level Design

`BaseTool.customize()` will lazily construct a private `_CustomizedTool` wrapper. The wrapper stores the original `BaseTool` and the requested description changes. Its `spec()` method obtains the wrapped spec and creates a new spec with copied description fields; its `validate_call()` and `execute()` methods delegate unchanged. The original tool remains the execution and validation source of truth.

The shared `ToolSpec` transformation will patch both metadata representations. Parameter descriptions are resolved against the effective top-level schema and validated before the wrapper is returned. The transformation will not add or remove properties, which prevents model-visible contract drift from the runtime implementation.

`BaseTool` will also own a private wrapper base and unwrapping helper. `_ActivityBoundTool` and `_CustomizedTool` will use that common wrapper contract. `ActivityToolFormatter.unwrap()` will call the common helper, preserving the existing runtime pricing hook without adding a second identity mechanism.

```text
BaseTool.customize()
        |
        v
_CustomizedTool.spec()
        |
        +--> copy ToolSpec.parameters descriptions
        +--> copy input_schema.properties descriptions
        |
        v
Tools.provider_schemas() / Tools.describe()
        |
        v
_CustomizedTool.validate_call() / execute() -> original BaseTool
```

---

## 6. Detailed Design

### 6.1 BaseTool customization entry point and wrapper contract

**File(s):** `vidbyte/tools/base.py`
**Type:** Modified

#### What it does

Adds the public `BaseTool.customize()` method and a private wrapper contract shared by activity and specification wrappers. The method is inherited by every native tool and by `FunctionTool` without modifying individual built-ins.

#### Interface / API

```python
def customize(self, *, description: str | None = None, parameter_descriptions: Mapping[str, str] | None = None) -> "BaseTool": ...
```

#### Logic / Algorithm

1. Import the customization wrapper lazily to keep the existing base-module dependency direction.
2. Validate and store the requested replacement values in the customization wrapper.
3. Return the wrapper without changing `self`.
4. Define a private `_ToolWrapper` base with a `wrapped_tool` property.
5. Define a private `_unwrap_tool()` helper that follows wrapper links to the underlying implementation.

#### Edge Cases & Error Handling

- No overrides returns a behaviorally equivalent wrapper or the original tool, as selected by the implementation without changing public semantics.
- Validation errors are raised at customization time rather than when the model first receives a schema.
- Wrapper unwrapping stops at the first non-wrapper `BaseTool`.

### 6.2 Specification customization implementation

**File(s):** `vidbyte/tools/customization.py`
**Type:** New file

#### What it does

Implements the private `_CustomizedTool` delegating wrapper and the pure spec transformation that replaces tool and top-level parameter descriptions.

#### Interface / API

```python
class _CustomizedTool(_ToolWrapper): ...
```

#### Logic / Algorithm

1. Validate that a supplied tool description is a non-blank string.
2. Validate that every supplied parameter description is non-blank and names an existing top-level parameter.
3. Call the wrapped tool's `spec()`.
4. Replace matching `ToolParameter` objects with copied descriptions.
5. Deep-copy and patch matching `input_schema.properties` entries when an explicit schema exists.
6. Return a dataclass replacement of the wrapped `ToolSpec`, preserving all non-description fields.
7. Delegate `validate_call()` and `execute()` directly to the wrapped tool.

#### Edge Cases & Error Handling

- An unknown parameter name raises `ValueError` and identifies the tool and parameter.
- An explicit schema without an object-shaped top-level `properties` mapping raises `ValueError` when parameter descriptions are requested.
- A malformed property schema that cannot receive a description raises `ValueError` rather than mutating it partially.
- Caller-owned input schemas are never mutated.

### 6.3 Generic wrapper unwrapping for activity and pricing

**File(s):** `vidbyte/tools/activity.py`
**Type:** Modified

#### What it does

Routes `ActivityToolFormatter.unwrap()` through the common private wrapper helper so nested customization and activity wrappers expose the original tool to operation accounting.

#### Interface / API

```python
def unwrap(tool: BaseTool) -> BaseTool: ...
```

#### Logic / Algorithm

1. Ask the base-tool wrapper helper to follow all SDK wrapper links.
2. Return the underlying implementation unchanged.

#### Edge Cases & Error Handling

- Existing non-wrapper tools are returned unchanged.
- Both `customize().with_activity()` and `with_activity().customize()` resolve to the same original implementation.
- Activity declaration and captured activity payload behavior remain unchanged.

### 6.4 Existing tool contract tests

**File(s):** `tests/test_tool_core.py`, `tests/test_provider_tool_schema_translation.py`
**Type:** Modified

#### What it does

Extends existing core and provider contract tests without creating a new feature test directory. The tests verify immutable customization, unknown-name rejection, explicit-schema synchronization, provider rendering, activity composition, and delegation behavior.

#### Interface / API

N/A - test modules exercise the public `BaseTool.customize()` contract.

#### Logic / Algorithm

1. Customize a parameter-based echo tool and assert its original spec is unchanged.
2. Assert customized prompt and provider descriptions use the replacement values.
3. Customize an explicit-schema tool and assert both schema properties and prompt parameters are synchronized.
4. Assert unknown names and blank descriptions fail at customization time.
5. Compose customization with activity in both orders and assert the original tool receives only business arguments.

#### Edge Cases & Error Handling

- Tests use observable execution arguments rather than private wrapper implementation details.
- Existing provider tests cover OpenAI-compatible, Anthropic, and Gemini schema paths.
- No new feature test folder is created because the repository already has the relevant tool contract suites and the user selected the no-tests design workflow.

### 6.5 Tools documentation

**File(s):** `vidbyte/tools/README.md`
**Type:** Modified

#### What it does

Documents the customization entry point, its description-only boundary, and the rule that behavior-changing parameters require a real custom tool or adapter.

#### Interface / API

N/A - documentation only.

#### Logic / Algorithm

N/A - documentation only.

#### Edge Cases & Error Handling

N/A - documentation only.

---

## 7. Data Model Changes

### 7.1 Persistent data

**Change type:** N/A - customization is an in-memory wrapper over `ToolSpec`; it introduces no database, serialized document, or migration changes.

---

## 8. API Changes

### 8.1 `BaseTool.customize`

**Change type:** New public Python API

**Request:**

```python
tool.customize(
    description="Application-specific tool guidance.",
    parameter_descriptions={"query": "Use the application's terminology."},
)
```

**Response:**

```python
BaseTool
```

The returned object preserves the original tool name and runtime behavior while exposing customized model-facing descriptions.

**Error cases:**

| Error | Condition |
|-------|-----------|
| `ValueError` | Tool description is blank |
| `ValueError` | Parameter description is blank |
| `ValueError` | Parameter name is not a declared top-level parameter |
| `ValueError` | Explicit input schema cannot be safely patched |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/customization.py` | Implement the private description-customizing wrapper and pure spec transformation. |
| MODIFY | `vidbyte/tools/base.py` | Add `BaseTool.customize()` and the shared private wrapper/unwrapping contract. |
| MODIFY | `vidbyte/tools/activity.py` | Reuse generic unwrapping for nested activity and customization wrappers. |
| MODIFY | `tests/test_tool_core.py` | Protect immutable customization, validation, delegation, and wrapper composition. |
| MODIFY | `tests/test_provider_tool_schema_translation.py` | Protect customized descriptions across explicit schemas and provider formats. |
| MODIFY | `vidbyte/tools/README.md` | Document the public customization boundary and non-goals. |
| DELETE | N/A | No existing file is replaced. |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `copy`, `dataclasses`, and `types` | Existing runtime | Copy and replace immutable tool specification data safely. | Low; no new third-party dependency. |
| Existing Pydantic/provider formatter path | Existing SDK contract | Existing activity and explicit-schema tests continue to validate provider output. | Low; no formatter protocol change. |

---

## 11. Rollout & Deployment

- No feature flag is needed because the API is opt-in and uncustomized tools retain their current behavior.
- This is additive and backward compatible; existing tools, constructors, schemas, and execution paths remain valid.
- Rollout is the normal SDK release process after source and package CI pass.
- Rollback is reverting the feature commits. Existing callers do not need migration because the new method is optional.

---

## 12. Open Questions

- [ ] Should a future release add a catalog-level `Tools.customize(name, ...)` convenience method? This change intentionally limits the public entry point to `BaseTool.customize()`.
- [ ] If repeated use cases require behavior-changing parameters, should the follow-up API be a typed `ToolAdapter` or a controlled nested input extension similar to `with_activity()`? This change intentionally does not decide that future feature.

---

## 13. Alternatives Considered

### Alternative 1: Let `customize()` add arbitrary parameters

- What: Merge caller-supplied `ToolParameter` objects into the wrapped tool's schema.
- Why rejected: The wrapped `execute()` and `validate_call()` would not automatically consume the new arguments, allowing the model to send parameters that are silently ignored.

### Alternative 2: Modify every built-in tool constructor and `spec()` method

- What: Add override arguments to each built-in tool class and manually merge them in every `spec()` implementation.
- Why rejected: Repeats one cross-cutting concern across the entire built-in catalog, creates inconsistent semantics, and makes PR #343-style tool additions needlessly expensive.

### Alternative 3: Mutate a shared built-in spec or global registry

- What: Store overrides in the built-in instance or a process-wide customization map.
- Why rejected: One agent's application-specific wording could leak into another agent using the same tool, creating order-dependent behavior and unsafe global state.

### Alternative 4: Add a full generic tool adapter now

- What: Introduce a public adapter protocol for spec transforms, argument transforms, validation, and execution hooks.
- Why rejected: It is the right future boundary for semantic extensions but exceeds the current description-only requirement. The smaller wrapper fully solves the immediate need and leaves the runtime contract unchanged.

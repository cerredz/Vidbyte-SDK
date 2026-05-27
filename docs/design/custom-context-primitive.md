# Design Doc: Custom Context Primitive

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

Adds a `CustomContextItem` primitive and a `ContextDefineTool` builtin that lets agents define their own structured context window primitives at runtime. Unlike the six typed primitives (`text`, `task`, `plan`, `document`, `memory`, `progress`), a custom primitive carries a developer-or-agent-defined field schema: the agent names each field, gives it a human-readable description, and supplies its value. The resulting primitive appears in Zone 3 of the context window and persists across all future turns, keeping domain-specific state organized and visible without needing a new Python class for every use case.

---

## 2. Goals & Non-Goals

### Goals
- Add `CustomContextItem` to `vidbyte/context/primitives.py` with `fields: Mapping[str, Any]` and `schema: Mapping[str, str]` fields
- Add `ContextDefineTool` to `vidbyte/tools/builtins/context_primitives/` with Option A param surface (`primitive_id`, `title`, `fields` as JSON, `schema` as JSON)
- Validate that every key in `schema` also appears in `fields` (drift detection)
- Export `CustomContextItem` and `ContextDefineTool` from the root SDK namespace
- Render custom primitives in a self-documenting way: `field_name (description): value`
- Support all value types: strings, numbers, booleans, lists, dicts (rendered as inline JSON)
- Keep the tool description concise — teach the agent HOW to call the tool, not what primitives are

### Non-Goals
- Partial field update tool (`context_set_field`) — not in scope; agents update by re-calling `context_define` with the full field set
- Integrating custom primitive support into `context_upsert` — it stays a separate tool with a distinct param surface
- Runtime schema enforcement or type-checking of field values beyond JSON parseability
- Nested custom primitives or references between primitives

---

## 3. Background & Context

The existing `ContextUpsertTool` supports six typed primitives with fixed shapes. Each shape is useful for its domain (task tracking, multi-step plans, reference documents) but forces agents into a predetermined structure. In practice, a coding agent's "task" has `files_touched`, `current_error`, and `test_commands`; a research agent's "plan" has `sources_to_check`, `hypotheses`, and `open_questions`. Neither maps cleanly to the existing types.

The previous `feat/context-window-primitives` PR (PR #61) established the foundational layer — `ContextManager._registry`, `primitive_id`, `primitive_frozen`, and the Zone 3 injection into the system string. This feature builds directly on top of that infrastructure without touching any of it. `CustomContextItem` is a new primitive type that conforms to the existing `ContextItem` protocol and slots into the registry using the same `upsert()` method.

The design choice (Option A) was confirmed in conversation: `fields` and `schema` are separate JSON string params. The separation keeps schema (slow state: field descriptions) distinct from fields (fast state: live values), matching the SkillOpt slow/fast split discussed when designing this layer.

**Dependency:** This feature branches off `feat/context-window-primitives`, not `main`. The `ContextManager` registry, `primitive_id`/`primitive_frozen` fields, and `ContextDefineTool` all depend on infrastructure that is in PR #61 and not yet on `main`.

---

## 4. Requirements

### Functional Requirements
1. `CustomContextItem` MUST implement the `ContextItem` protocol: `kind`, `title`, `metadata`, and `to_context_text()`.
2. `CustomContextItem.to_context_text()` MUST render each field on its own line as `  field_name (description): value` when a schema entry exists, or `  field_name: value` when it does not.
3. List values MUST render as a comma-separated string; dict values MUST render as compact inline JSON; all other values MUST render as `str(value)`.
4. `CustomContextItem` MUST have `primitive_id`, `primitive_frozen` fields matching the pattern of every other primitive.
5. `ContextDefineTool` MUST accept four parameters: `primitive_id` (required), `title` (required), `fields` (required JSON string), `schema` (optional JSON string, defaults to `{}`).
6. `ContextDefineTool` MUST return a `ToolResult.error` if `fields` is not valid JSON.
7. `ContextDefineTool` MUST return a `ToolResult.error` if `schema` is not valid JSON.
8. `ContextDefineTool` MUST return a `ToolResult.error` if `fields` does not parse to a `dict`.
9. `ContextDefineTool` MUST return a `ToolResult.error` if `schema` does not parse to a `dict`.
10. `ContextDefineTool` MUST return a `ToolResult.error` if any key in `schema` is not present in `fields` (drift guard).
11. `ContextDefineTool` MUST return a `ToolResult.error` if `fields` is empty (a primitive with zero fields has no value).
12. `ContextDefineTool` MUST return a `ToolResult.error` if `primitive_id` or `title` is empty after stripping whitespace.
13. On success, `ContextDefineTool` MUST call `self._manager.upsert(item)` and return a success result referencing the `primitive_id`.
14. If `upsert()` raises `ValueError` (primitive is frozen), `ContextDefineTool` MUST surface that as a `ToolResult.error`.
15. `CustomContextItem` and `ContextDefineTool` MUST be importable from `vidbyte` root namespace.

### Non-Functional Requirements
- `to_context_text()` MUST complete in O(n) time with respect to the number of fields; no external I/O
- No new third-party dependencies — only the Python standard library `json` module
- Tool permission level: `ToolPermission.SAFE` (no filesystem or network access)
- The tool description MUST be ≤ 80 words — concise enough to not inflate Zone 2 token cost

---

## 5. High-Level Design

`CustomContextItem` is a new frozen dataclass in `vidbyte/context/primitives.py`. It stores two mappings: `fields` (live data) and `schema` (field descriptions). Its `to_context_text()` method zips them together during rendering, producing a self-documenting block that the model sees in Zone 3 each iteration.

`ContextDefineTool` is a new `BaseTool` subclass in `vidbyte/tools/builtins/context_primitives/define.py`. It holds a live reference to the shared `ContextManager` (same pattern as `ContextUpsertTool`, `ContextRemoveTool`, `ContextListTool`). On `execute()`, it parses and validates the `fields` and `schema` JSON strings, checks schema-field drift, constructs a `CustomContextItem`, and calls `self._manager.upsert()`.

```
Agent tool call
    -> ContextDefineTool.execute()
        -> _parse_and_validate()       # JSON parse, type check, drift guard
        -> _build_custom_primitive()   # construct CustomContextItem
        -> ContextManager.upsert()     # store in registry
        -> ToolResult.success()
                                       # next iteration:
                                       # AgentRuntime._build_system_string()
                                       #   -> ContextManager.render_primitives_zone()
                                       #       -> CustomContextItem.to_context_text()
                                       #           -> Zone 3 in system string
```

The data flow is entirely local: no network, no filesystem, no async coordination. The primitive is visible to the model on the very next agent loop iteration because `_build_system_string()` calls `render_primitives_zone()` fresh each turn from the live `ContextManager` reference.

---

## 6. Detailed Design

### 6.1 CustomContextItem

**File:** `vidbyte/context/primitives.py`
**Type:** Modified (new class added at bottom, before `_extend_section` helper)

#### What it does
Stores a developer- or agent-defined set of named fields with optional per-field descriptions. Renders them into a structured, self-documenting block for Zone 3 injection.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class CustomContextItem:
    fields: Mapping[str, Any]
    schema: Mapping[str, str] = field(default_factory=dict)
    kind: str = "custom"
    title: str = "Custom"
    primitive_id: str | None = None
    primitive_frozen: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context_text(self) -> str: ...

def _format_field_value(value: Any) -> str: ...
```

#### Logic / Algorithm

`to_context_text()`:
1. Emit header line `Custom: {self.title}`
2. If `self.fields` is empty, emit `  (no fields defined)` and return
3. For each `(field_name, value)` in `self.fields.items()`:
   a. Look up `desc = self.schema.get(field_name, "")`
   b. Format description suffix: `f" ({desc})"` if desc else `""`
   c. Format value via `_format_field_value(value)`
   d. Emit `f"  {field_name}{desc_suffix}: {formatted_value}"`
4. Join lines with `\n` and return

`_format_field_value(value)`:
- `list` → `", ".join(str(v) for v in value)` (empty list → `"[]"`)
- `dict` → `json.dumps(value, separators=(",", ":"))` (compact)
- anything else → `str(value)`

#### Edge Cases & Error Handling
- `fields` is empty → `to_context_text()` renders `(no fields defined)` (this won't happen via `ContextDefineTool` due to validation, but the class itself must not crash)
- `schema` has keys not in `fields` → the class itself does NOT validate this; validation lives in `ContextDefineTool`
- Values containing special characters in lists or dicts → handled by `str()` and `json.dumps()`
- `None` value → renders as `"None"` via `str()`

---

### 6.2 ContextDefineTool

**File:** `vidbyte/tools/builtins/context_primitives/define.py`
**Type:** New file

#### What it does
Agent-facing tool that constructs a `CustomContextItem` from JSON-encoded `fields` and optional `schema`, validates input, and upserts it into the live `ContextManager`.

#### Interface / API

```python
class ContextDefineTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _parse_and_validate(self, args: dict) -> tuple[str, str, dict, dict] | ToolResult: ...
    def _build_custom_primitive(self, primitive_id: str, title: str, fields: dict, schema: dict) -> CustomContextItem: ...
```

#### Logic / Algorithm

`spec()` returns a `ToolSpec` with:
- `name`: `"context_define"`
- `description`: ≤ 80 words, action-focused — what it does, when to use it, param format hint
- `parameters`: `primitive_id` (required), `title` (required), `fields` (required), `schema` (optional, default `"{}"`)
- `permission`: `ToolPermission.SAFE`

`execute(call)`:
1. Call `_parse_and_validate(call.arguments)` — returns either `(primitive_id, title, fields_dict, schema_dict)` or a `ToolResult.error`
2. If error result, return it immediately
3. Call `_build_custom_primitive(primitive_id, title, fields_dict, schema_dict)` → `CustomContextItem`
4. Try `self._manager.upsert(item)`; if `ValueError`, return `ToolResult.error(call.tool_name, str(exc))`
5. Return `ToolResult.success(call.tool_name, f"Custom primitive '{primitive_id}' defined with {len(fields_dict)} fields.")`

`_parse_and_validate(args)`:
1. Extract and strip `primitive_id` — error if empty
2. Extract and strip `title` — error if empty
3. Parse `fields` string as JSON — error if invalid JSON or not a dict
4. Error if `fields` dict is empty
5. Parse `schema` string as JSON (default `"{}"`) — error if invalid JSON or not a dict
6. Check schema drift: error if any key in `schema` is not in `fields`
7. Return `(primitive_id, title, fields_dict, schema_dict)`

`_build_custom_primitive(primitive_id, title, fields, schema)`:
1. Return `CustomContextItem(fields=fields, schema=schema, title=title, primitive_id=primitive_id)`

#### Edge Cases & Error Handling
- `fields` JSON is a list → error (must be a dict)
- `schema` JSON is a list → error (must be a dict)
- `fields` value is a nested dict → accepted, rendered via `_format_field_value`
- `primitive_id` contains only whitespace → treated as empty, error returned
- Frozen primitive collision → `upsert()` raises `ValueError`, surfaced as `ToolResult.error`
- Missing `fields` key entirely → `args.get("fields", "")` → empty string → JSON parse error

---

### 6.3 context_primitives package exports

**File:** `vidbyte/tools/builtins/context_primitives/__init__.py`
**Type:** Modified

Add import and `__all__` entry for `ContextDefineTool`.

---

### 6.4 builtins package exports

**File:** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

Add import and `__all__` entry for `ContextDefineTool`.

---

### 6.5 context package exports

**File:** `vidbyte/context/__init__.py`
**Type:** Modified

Add `CustomContextItem` to imports from `vidbyte.context.primitives` and to `__all__`.

---

### 6.6 Root SDK exports

**File:** `vidbyte/__init__.py`
**Type:** Modified

Add `CustomContextItem` to context imports and `ContextDefineTool` to `context_primitives` imports. Add both to `__all__`.

---

## 7. Data Model Changes

### 7.1 CustomContextItem

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class CustomContextItem:
    fields: Mapping[str, Any]                        # live field data
    schema: Mapping[str, str] = field(...)           # field descriptions (optional)
    kind: str = "custom"
    title: str = "Custom"
    primitive_id: str | None = None
    primitive_frozen: bool = False
    metadata: Mapping[str, Any] = field(...)
```

**Migration strategy:** N/A — new type, no existing data to migrate.

---

## 8. API Changes

N/A — this is a tool-layer addition, not an HTTP API change. The "API" is the tool spec presented to the model:

### 8.1 `context_define` tool

**Change type:** New

**Arguments:**
```json
{
  "primitive_id": "string (required) — stable identifier, e.g. 'coding_task:auth.py'",
  "title": "string (required) — display name shown in context window",
  "fields": "string (required) — JSON object {field_name: value, ...}",
  "schema": "string (optional) — JSON object {field_name: description, ...}, default '{}'"
}
```

**Success result:**
```
Custom primitive '{primitive_id}' defined with {N} fields.
```

**Error cases:**
| Condition | Error message |
|-----------|--------------|
| `primitive_id` empty | `"primitive_id cannot be empty."` |
| `title` empty | `"title cannot be empty."` |
| `fields` invalid JSON | `"fields must be a valid JSON object."` |
| `fields` not a dict | `"fields must be a JSON object, not a list or scalar."` |
| `fields` empty dict | `"fields cannot be empty — define at least one field."` |
| `schema` invalid JSON | `"schema must be a valid JSON object."` |
| `schema` not a dict | `"schema must be a JSON object, not a list or scalar."` |
| schema key not in fields | `"schema key '{key}' has no corresponding entry in fields."` |
| frozen primitive collision | (ValueError message from `upsert()`) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/context/primitives.py` | Add `CustomContextItem` and `_format_field_value` |
| MODIFY | `vidbyte/context/__init__.py` | Export `CustomContextItem` |
| MODIFY | `vidbyte/__init__.py` | Export `CustomContextItem`, `ContextDefineTool` |
| CREATE | `vidbyte/tools/builtins/context_primitives/define.py` | New `ContextDefineTool` |
| MODIFY | `vidbyte/tools/builtins/context_primitives/__init__.py` | Export `ContextDefineTool` |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export `ContextDefineTool` |
| CREATE | `tests/test_context_primitives_define.py` | Unit tests for all new behavior |
| CREATE | `scripts/test_custom_context_primitive.py` | Verification script |

**Total: 2 new files, 6 modified files**

---

## 10. Testing Plan

### Unit Tests — `CustomContextItem`

- `test_renders_field_with_description_when_schema_present` — `  field (desc): value` format — [Silent Failure: missing description silently drops from render]
- `test_renders_field_without_description_when_schema_missing` — `  field: value` with no parens — [Edge Case: partial schema]
- `test_renders_list_value_as_comma_separated` — `["a", "b"]` → `"a, b"` — [Silent Failure: list could render as Python repr]
- `test_renders_empty_list_as_bracket_pair` — `[]` → `"[]"` — [Edge Case: empty list]
- `test_renders_dict_value_as_compact_json` — `{"x": 1}` → `'{"x":1}'` — [Silent Failure: could render as Python dict repr]
- `test_renders_none_value_as_none_string` — `None` → `"None"` — [Edge Case: None value]
- `test_renders_no_fields_message_when_fields_empty` — `(no fields defined)` sentinel — [Edge Case: empty fields dict]
- `test_renders_header_with_title` — title appears in first line — [Silent Failure: title could be swapped with kind]
- `test_schema_keys_not_in_fields_do_not_appear_in_render` — schema-only keys are silently ignored at render time — [Hidden Assumption: render doesn't crash on extra schema keys]
- `test_kind_is_custom` — `item.kind == "custom"` — [Silent Failure: kind could silently default to wrong value]

### Unit Tests — `ContextDefineTool`

- `test_valid_call_creates_custom_primitive_in_registry` — happy path, primitive appears in manager — [Hidden Failure: tool could succeed without actually upserting]
- `test_valid_call_returns_success_with_primitive_id_in_output` — output string references the id — [Silent Failure: success message could reference wrong id]
- `test_field_count_in_success_message` — output includes correct field count — [Silent Failure: off-by-one]
- `test_error_when_primitive_id_empty` — whitespace-only primitive_id returns error — [Edge Case: whitespace id]
- `test_error_when_title_empty` — empty title returns error — [Edge Case]
- `test_error_when_fields_invalid_json` — `"not json"` returns error — [Hidden Assumption: agent always sends valid JSON]
- `test_error_when_fields_is_json_list` — `"[]"` (list not dict) returns error — [Hidden Assumption: fields is always a JSON object]
- `test_error_when_fields_empty_dict` — `"{}"` returns error — [Edge Case: empty dict]
- `test_error_when_schema_invalid_json` — bad schema JSON returns error — [Hidden Assumption]
- `test_error_when_schema_is_json_list` — `"[]"` as schema returns error — [Hidden Assumption]
- `test_error_when_schema_key_not_in_fields` — schema has `"missing_key"` not in fields — [Hidden Failure: drift guard could be inverted or skipped]
- `test_schema_keys_subset_of_fields_passes_validation` — schema has fewer keys than fields — [Edge Case: partial schema is valid]
- `test_error_when_frozen_primitive_is_overwritten` — returns error, old primitive untouched — [Hidden Assumption: frozen protection applies]
- `test_schema_default_empty_when_omitted` — no schema param → primitive has empty schema — [Hidden Assumption: default wiring works]
- `test_fields_with_nested_dict_value_accepted` — `{"config": {"timeout": 30}}` passes — [Edge Case: nested structure]

### Unit Tests — exports

- `test_custom_context_item_importable_from_root` — `from vidbyte import CustomContextItem` — [Hidden Assumption: root namespace wiring]
- `test_context_define_tool_importable_from_root` — `from vidbyte import ContextDefineTool` — [Hidden Assumption]
- `test_context_define_tool_importable_from_builtins` — `from vidbyte.tools.builtins import ContextDefineTool` — [Hidden Assumption]

### Integration Tests

- End-to-end: create a `ContextManager`, instantiate `ContextDefineTool(manager)`, call `execute()`, assert the primitive appears in `manager.get_by_id()` and in `manager.render_primitives_zone()` output — verifies the full path from tool call to context window render.
- Silent failure path: after upsert, call `render_primitives_zone()` and assert the field descriptions appear verbatim — catches cases where schema is stored but not passed to `to_context_text()`.

### Manual / QA Test Cases

1. Given a `ContextDefineTool` with a live `ContextManager`, when an agent calls it with `fields='{"objective":"fix auth","files":["auth.py"]}'` and `schema='{"objective":"high-level goal","files":"files touched"}'`, then `render_primitives_zone()` must contain `objective (high-level goal): fix auth` — [Silent Failure: description could be omitted]
2. Given an existing custom primitive with `primitive_frozen=True`, when `context_define` is called with the same `primitive_id`, then the result status must be `error` and the original primitive must be unchanged — [Hidden Assumption: frozen enforcement applies to custom primitives]
3. Given a call with `schema` containing a key not in `fields`, when `execute()` is called, then a `ToolResult.error` is returned referencing the drifting key — [Hidden Failure: drift guard could silently pass]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `json` (stdlib) | Python 3.11+ | Parse `fields` and `schema` JSON strings | None — stdlib, always available |
| `feat/context-window-primitives` (PR #61) | in-review | Provides `ContextManager._registry`, `primitive_id`, `render_primitives_zone()` | Must be merged to `main` before this branch can be merged |

---

## 12. Rollout & Deployment

- No feature flags — this is a purely additive new type and tool
- Not a breaking change — no existing public API is modified
- Deployment order: PR #61 (`feat/context-window-primitives`) must merge first; this PR targets `feat/context-window-primitives` as base until then
- Rollback: remove `CustomContextItem` from `primitives.py` and delete `define.py`; no state migration needed since primitives are ephemeral (not persisted to disk)

---

## 13. Open Questions

- [ ] Should `_format_field_value` for nested dicts use pretty-print (`json.dumps(..., indent=2)`) or compact inline (`separators=(",",":")`)? Compact is chosen for now to keep the context window dense, but the model may find pretty-print easier to read for complex objects.
- [ ] Should `ContextDefineTool` support updating only specific fields (patch semantics) rather than always requiring the full field set? Current answer: no — whole-object replacement keeps the tool surface simple and avoids partial-update ambiguity. Add `context_set_field` as a follow-up if agents find re-emitting large objects painful in practice.

---

## 14. Alternatives Considered

### Alternative 1: Extend `context_upsert` with `type="custom"`
- What: Add `fields` and `schema` params to the existing `ContextUpsertTool` alongside the existing `content` param for typed primitives
- Why rejected: The param signature is genuinely different — typed primitives take a flat `content` string while custom takes two JSON objects. A single tool handling both paradigms would produce a confusing description and awkward conditional validation logic. A dedicated tool with a clean, purpose-built spec is more learnable for the model and easier to maintain.

### Alternative 2: Option B — fields as array of `{name, description, value}` objects
- What: Pass a single `fields` param as a JSON array where each element has all three components co-located
- Why rejected: The array form is less natural for the model to produce (JSON arrays of objects are more verbose to write than two parallel JSON objects), and it makes partial schema (describing only some fields) harder to express. Option A's separation of `fields` and `schema` also maps to the SkillOpt slow/fast split discussed in design: schema is slow state (rarely changed), fields are fast state (updated each turn).

### Alternative 3: `context_define_schema` + `context_upsert` two-step
- What: One tool defines the schema, a second populates the values; the schema is immutable after definition
- Why rejected: Requires two tool calls for every new custom primitive, with the schema definition being a pure side-effect with no visible output until a second call. More complex for the agent to learn and more expensive in terms of tool call budget.

---

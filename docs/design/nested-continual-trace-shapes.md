# Design Doc: Nested Continual Trace Shapes

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-01
**Last Updated:** 2026-09-01

---

## 1. Overview

This change extends the continual-trace schema contract (`vidbyte/lib/dataclasses/trace.py`, `vidbyte/tools/continual_trace.py`) so an OBJECT or ARRAY trace field can declare its internal shape as real typed sub-fields instead of only a prose "Shape: {...}" description, and adds five new prebuilt trace schemas — `HierarchicalTaskTreeTrace`, `CalibrationTrace`, `ErrorTaxonomyTrace`, `SelfConsistencyEnsembleTrace`, and `CounterfactualAlternativesTrace` — built on that capability. All five score pure agent task performance (goal completion, path quality, answer correctness) with the three axes always kept as separate fields, never combined into one number, continuing the pattern of every prebuilt trace schema in this module.

---

## 2. Goals & Non-Goals

### Goals
- Let `TraceField` declare a nested mapping of named sub-fields (`fields`) for OBJECT-typed fields and a single item shape (`items`) for ARRAY-typed fields, each themselves a typed `TraceField`, recursively.
- Let `TraceSchema.from_model` build that nested shape automatically from a nested Pydantic submodel or `list[SubModel]` annotation, the same way it already builds flat fields from `Field(description=...)`.
- Make `UpdateTraceTool` show the model that real nested structure in the JSON Schema it emits (`properties`/`items`, not a flat `{"type": "object"}`), and validate incoming updates against it recursively.
- Add five new prebuilt schemas using this capability, with deep, general (non-example-based) field descriptions.
- Correct the continual-tracing skill file's "deep-merge" claim and document the new capability's real limits.

### Non-Goals
- Changing the merge policy. Arrays still append-with-exact-dedupe; objects are still a one-level shallow `dict.update()`. This change is additive to *typing and validation*, not to *merge semantics* — see §5 for why that distinction matters and stays load-bearing.
- Adding a `TraceFieldType.ENUM` wire type. Closed vocabularies (verdicts, error types) are modeled as `str, Enum` Python classes per `field-guide/vidbyte-sdk/model-facing-tool-contracts.md`'s categorical-vocabulary rule; they still serialize as JSON Schema `"type": "string"`, same as any other string field.
- A YAML-loader (`ContinualTraceAgentDescriptor`) entry point for the five new schemas — out of scope, same as PR #397.
- New pytest test files (per the `design-doc-no-tests` workflow). A standalone verification script extension is added instead, mirroring `scripts/test-continual-trace.py`'s existing pattern, since it materially de-risks a core-contract change and is not itself a test file.

---

## 3. Background & Context

Earlier in this session, five flat trace schemas were sketched with fields typed `dict[str, Any]` / `list[dict[str, Any]]` whose internal shape was described only in prose ("Shape: {node_id, parent_node_id, ...}"). Two problems with that, found by reading the actual code rather than assuming:

1. `TraceSchema.from_model`'s `_annotation_to_type` (`vidbyte/lib/dataclasses/trace.py:132-149`) only recognizes `bool`/`int`/`float`/`str`/`list`/`Mapping`. A nested Pydantic submodel annotation isn't one of those, so it silently falls through to `TraceFieldType.STRING` — which is why every earlier sketch used `dict[str, Any]` rather than a real submodel; a submodel wasn't usable yet.
2. `UpdateTraceTool._input_schema()` (`vidbyte/tools/continual_trace.py:101-119`) builds a flat `{"type": ..., "description": ...}` JSON Schema per field regardless — so even a correctly-typed OBJECT/ARRAY field shows the model no `properties`/`items`, only whatever the description says in prose.

The user asked for the shape to live in real declared subfields instead. That requires extending the core contract, not just adding more prebuilt schemas — this design doc is that extension, plus the five schemas built on top of it.

PR #397 (branch `feat/symmetric-continual-trace-schemas`, open, unmerged) added six earlier "Symmetric*" schemas from this same conversation using the current flat contract. This change does not depend on it and is not blocked by it — it works directly off `main`'s existing `ActionTrace` pattern. If PR #397 merges first, this branch's `prebuilt.py` additions land alongside the Symmetric* ones with no interaction between them.

---

## 4. Requirements

### Functional Requirements
1. `TraceField` gains `fields: Mapping[str, TraceField] | None` (valid only when `type is OBJECT`) and `items: TraceField | None` (valid only when `type is ARRAY`), both defaulting to `None`.
2. `TraceField` validates, on construction: non-empty `description` (moved onto the field itself, the single source of truth, rather than only externally in `TraceSchema._normalize_field_value`); `fields` set only on OBJECT; `items` set only on ARRAY; nesting depth ≤ `MAX_TRACE_FIELD_NESTING_DEPTH`.
3. `TraceSchema.from_model` recognizes a nested `BaseModel` annotation and recursively builds `fields` from it (every submodel field must carry `Field(description=...)`, exactly like the top level today); recognizes `list[SubModel]` and builds `items` the same way, with the item's own description taken from the submodel's docstring or a generated fallback if that docstring is empty.
4. Plain `dict[str, Any]` and `list[dict[str, Any]]` (or any list-of-non-BaseModel) annotations keep mapping to opaque OBJECT/ARRAY with `fields`/`items` left `None` — unchanged from current behavior. `ActionTrace` and any schema built from PR #397's Symmetric* models must construct and behave identically to before this change.
5. `UpdateTraceTool._input_schema()` recursively renders `properties` for an OBJECT field with declared `fields` (plus `additionalProperties: False`) and `items` for an ARRAY field with declared `items`.
6. `UpdateTraceTool`'s validation recursively checks declared sub-field/item types when present, returning the existing `"output shape mismatch: ..."` error (now with a dotted/indexed path, e.g. `task_nodes[0].goal_success_verdict expected string`) on the first mismatch found, at any depth.
7. Five new prebuilt schemas are added to `vidbyte/trace/continual/prebuilt.py` and exported through `vidbyte/trace/continual/__init__.py` → `vidbyte/trace/__init__.py` → `vidbyte/__init__.py`, matching `ActionTrace`'s existing export chain exactly.
8. `skills/vidbyte-sdk/continual-tracing.md` line 49's "deep-merge objects" wording is corrected, and a new subsection documents `fields`/`items` and the merge-semantics caveat in §5 below.

### Non-Functional Requirements
- Nesting is capped at `MAX_TRACE_FIELD_NESTING_DEPTH = 5`, a named constant in a new `vidbyte/lib/constants/trace.py`, matching the existing precedent set by `ContinualTraceAgentDescriptor._MAX_SCHEMA_DEPTH` (`vidbyte/lib/dataclasses/continual_trace_descriptor.py:28`).
- Closed string vocabularies introduced by the five new schemas (verdicts, error taxonomies, calibration trend/axis) are `str, Enum` classes in a new `vidbyte/lib/enums/continual_trace.py`, per the categorical-vocabulary rule in `field-guide/vidbyte-sdk/model-facing-tool-contracts.md`.
- Every new/modified `.py` file carries a complete A001-compliant header (`PURPOSE:`/`ROLE IN CODEBASE:`/`ARCHITECTURE NOTE:`/`COMMON MODIFICATION PATTERNS:`/`KNOWN EDGE CASES:`/`RELATED DOCS:`/`TESTS:`, each with a same-line value) — `trace.py` and `continual_trace.py`'s existing older-style headers are upgraded to this format while being touched, since PR #397 already had to do this once for `prebuilt.py`.
- New field descriptions are general (not tied to one narrow scenario) and multi-sentence, per the same field guide's "consistent 4-5 sentence general description... omit concrete examples from model-facing prose" rule, applied here even though `S025` (the lint rule enforcing that numerically) only statically scopes to literal `ToolParameter(...)` call sites and doesn't reach these dynamically-embedded descriptions.

---

## 5. High-Level Design

Two independent layers change. The **contract layer** (`vidbyte/lib/dataclasses/trace.py`, `vidbyte/tools/continual_trace.py`) gains the ability to describe and validate nested shape. The **content layer** (`vidbyte/trace/continual/prebuilt.py`) uses that ability to add five schemas.

```
TraceSchema.from_model(PydanticModel)
        |
        v
_field_from_annotation(annotation, description, depth)  -- recurses on nested BaseModel / list[BaseModel]
        |
        v
TraceField(type=OBJECT, fields={...})   or   TraceField(type=ARRAY, items=TraceField(...))
        |
        v
UpdateTraceTool._input_schema()  -- walks the same tree into JSON Schema properties/items
        |
        v
UpdateTraceTool._first_type_error()  -- walks the same tree to validate an incoming update
```

The critical design decision, made explicit rather than left implicit: **this only changes what shape is declared and validated, not how it merges.** `UpdateTraceTool._merge_field` (`vidbyte/tools/continual_trace.py:154-164`) still does exactly what it does today — append-with-exact-dedupe for a top-level ARRAY field, a one-level shallow key-union `dict.update()` for a top-level OBJECT field, replace for a scalar. That key-union means a sub-key an update omits keeps its prior value untouched (sibling keys are not clobbered), but a sub-key an update *does* include — even one shaped as an ARRAY — is replaced with the new value whole, never merged element-wise with what was there before. So giving an OBJECT field declared `fields` that happen to include an ARRAY-typed sub-field does not make that inner array accumulate across separate updates that resend it; it only preserves history for updates that leave it out entirely. This was already true before this change (a `dict[str, Any]` object field with an undeclared nested list had the exact same problem, just silently) — the difference is that it's now typed and documented instead of invisible. Every new schema in this doc that puts an array-shaped sub-field inside an OBJECT field does so only for fields explicitly designed as whole-object snapshots (resent in full every pass), never for fields meant to accumulate incrementally; anything meant to grow across passes is its own top-level ARRAY field, per the lesson already learned and documented from PR #397's audit.

The recursive builder is a straightforward generalization of the existing flat one: `_annotation_to_type` keeps handling every leaf case unchanged (including the `Mapping`→OBJECT and generic-list→ARRAY fallbacks that keep `dict[str, Any]`/`list[dict[str, Any]]` opaque); a new dispatch step runs first and only fires when the annotation (or a `list[...]`'s single type argument) is itself a `BaseModel` subclass.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/constants/trace.py` (new file)

#### What it does
Owns the nesting-depth bound for `TraceField.fields`/`TraceField.items`.

#### Interface / API
```python
MAX_TRACE_FIELD_NESTING_DEPTH = 5
__all__ = ["MAX_TRACE_FIELD_NESTING_DEPTH"]
```

#### Edge Cases & Error Handling
N/A — a single named constant; the consuming validator raises.

---

### 6.2 `vidbyte/lib/enums/continual_trace.py` (new file)

#### What it does
Centralizes the closed string vocabularies used by the five new prebuilt schemas: verdict states for each of the three axes, per-axis error taxonomies, calibration trend/axis names, path-decision regret assessment, and judgment-stability states.

#### Interface / API
```python
class GoalSuccessVerdict(str, Enum): ...       # ACHIEVED, FAILED, PARTIAL, IN_PROGRESS, NOT_ATTEMPTED
class PathQualityVerdict(str, Enum): ...       # EFFICIENT, INEFFICIENT, RISKY, BLOCKED
class AnswerCorrectnessVerdict(str, Enum): ... # VERIFIED, UNVERIFIED, CONTRADICTED, PARTIAL
class GoalSuccessErrorType(str, Enum): ...
class PathQualityErrorType(str, Enum): ...
class AnswerCorrectnessErrorType(str, Enum): ...
class CalibratedAxis(str, Enum): ...           # GOAL, PATH, CORRECTNESS, INSUFFICIENT_DATA
class CalibrationTrend(str, Enum): ...          # IMPROVING, WORSENING, STABLE
class JudgmentStability(str, Enum): ...         # CONVERGING, DIVERGING, STABLE
class PathRegretAssessment(str, Enum): ...      # CORRECT_CHOICE, ALTERNATIVE_WOULD_HAVE_BEEN_BETTER, UNCLEAR
```

#### Logic / Algorithm
Plain `str, Enum` classes; `_field_from_annotation`'s existing `issubclass(target, str)` check already maps these to `TraceFieldType.STRING` with no special-casing needed, since a `str, Enum` member is a `str` subclass.

---

### 6.3 `vidbyte/lib/dataclasses/trace.py` (modified)

#### What it does
Adds nested shape to `TraceField` and the recursive builder to `TraceSchema.from_model`.

#### Interface / API
```python
class TraceField(BaseModel):
    description: str
    type: TraceFieldType = TraceFieldType.STRING
    fields: Mapping[str, "TraceField"] | None = None
    items: "TraceField | None" = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "TraceField": ...
    def _nesting_depth(self) -> int: ...

TraceField.model_rebuild()
```
```python
class TraceSchema:
    @classmethod
    def from_model(cls, model: type[BaseModel], *, name: str | None = None, description: str | None = None) -> "TraceSchema": ...
    @classmethod
    def _fields_from_model(cls, model: type[BaseModel], *, depth: int) -> dict[str, TraceField]: ...
    @classmethod
    def _field_from_annotation(cls, annotation: Any, description: str, *, depth: int) -> TraceField: ...
    @staticmethod
    def _annotation_to_type(annotation: Any) -> TraceFieldType: ...  # unchanged, still the leaf-type resolver
```

#### Logic / Algorithm
1. `from_model` now delegates field-building to `_fields_from_model(model, depth=1)` instead of inlining the loop.
2. `_fields_from_model` keeps the existing "every field needs `Field(description=...)`" check, then calls `_field_from_annotation` per field instead of `_annotation_to_type` directly.
3. `_field_from_annotation`: if the (origin-resolved) annotation is a `BaseModel` subclass, return an OBJECT `TraceField` with `fields=_fields_from_model(target, depth=depth+1)`. Else if it's a `list`/`tuple`/`set`/`frozenset` whose single type argument resolves to a `BaseModel` subclass, return an ARRAY `TraceField` with `items` built the same recursive way (item description = submodel docstring, stripped, or a generated fallback naming the field if the docstring is empty). Otherwise, fall through to the unchanged `_annotation_to_type` for a flat leaf `TraceField`.
4. `TraceField._validate_shape` (a `model_validator(mode="after")`, so it runs only once every nested `fields`/`items` value is already a fully-constructed, already-validated `TraceField`): rejects empty `description`; rejects `fields` on non-OBJECT or `items` on non-ARRAY; computes `_nesting_depth()` (1 + the max depth of any child, 0 children → depth 1) and rejects depth beyond `MAX_TRACE_FIELD_NESTING_DEPTH`.

#### Edge Cases & Error Handling
- A submodel field without its own `Field(description=...)` raises the exact same `ValueError` message shape as today's top-level check, just from the recursive call — no new error type.
- A `list[SubModel]` whose `SubModel` has an empty docstring gets an auto-generated, non-empty item description (`"One entry in this list, each describing a single {SubModel.__name__} record."`) rather than failing construction — this only fires for the internal `items` field, not anything user-facing that could silently ship with an empty description.
- `dict[str, Any]`, `list[dict[str, Any]]`, `list[str]`, and every other pre-existing annotation shape from `ActionTrace` and the six PR #397 Symmetric* schemas resolve through the unchanged `_annotation_to_type` fallback exactly as before — verified by constructing all of them from `main` in the verification script (§5d).

---

### 6.4 `vidbyte/tools/continual_trace.py` (modified)

#### What it does
Surfaces nested shape in the model-facing JSON Schema and validates incoming updates against it.

#### Interface / API
```python
class UpdateTraceTool(BaseTool):
    def _input_schema(self) -> dict[str, Any]: ...           # now builds nested properties/items
    def _json_schema_for_field(self, spec: TraceField) -> dict[str, Any]: ...   # new, recursive
    def _first_type_error(self, update: Mapping[str, Any]) -> str | None: ...   # now recurses
    def _first_shape_error(self, value: Any, spec: TraceField, path: str) -> str | None: ...  # new, recursive
    @staticmethod
    def _value_matches_type(value: Any, field_type: TraceFieldType) -> bool: ...  # unchanged, leaf check only
```

#### Logic / Algorithm
1. `_json_schema_for_field(spec)`: builds `{"type": spec.type.value, "description": spec.description}`; if `spec.type is OBJECT` and `spec.fields`, adds `"properties"` (recursing per sub-field) and `"additionalProperties": False`; if `spec.type is ARRAY` and `spec.items is not None`, adds `"items"` (recursing once). `_input_schema` replaces its flat `properties = {name: {"type": ..., "description": ...}}` comprehension with `properties = {name: self._json_schema_for_field(spec) for name, spec in self.schema.fields.items()}`.
2. `_first_type_error` keeps its top-level loop shape (skip absent/`None` fields) but delegates each present field to `_first_shape_error(value, spec, field_name)`.
3. `_first_shape_error(value, spec, path)`: returns a mismatch message if the leaf type check fails; else, for OBJECT with `fields`, checks each present declared sub-key recursively (absent/`None` sub-keys skipped, undeclared sub-keys ignored — same "extra keys pass through validation, get dropped at merge" policy the top level already has); for ARRAY with `items`, checks every element recursively with an indexed path.
4. The merge path (`_merge_known_fields`, `_merge_field`, `_append_unique`) is untouched — deliberately, per §5.

#### Edge Cases & Error Handling
- A deeply nested mismatch produces a path like `task_nodes[2].correctness_verdict expected string`, still wrapped in the existing `"output shape mismatch: {detail}"` `ToolResult.error`, so the model still gets one self-correcting message per call, just a more specific one.
- An OBJECT/ARRAY field with no declared `fields`/`items` (every pre-existing schema) skips the new recursive branches entirely and behaves exactly as before — confirmed by the verification script's `case_tool_deep_merges_object`-style checks continuing to pass unmodified.

---

### 6.5 `vidbyte/trace/continual/prebuilt.py` (modified)

#### What it does
Adds five new Pydantic model + `TraceSchema` pairs, each with real nested submodels for every structured field, and general 3-5 sentence field descriptions.

#### Interface / API (top-level field counts, per Requirement 7)
- `HierarchicalTaskTreeTraceModel` / `HierarchicalTaskTreeTrace` — 14 fields (`TaskNodeEvent`, `ReworkEvent` submodels).
- `CalibrationTraceModel` / `CalibrationTrace` — 13 fields (6 prediction/resolution-pair submodels).
- `ErrorTaxonomyTraceModel` / `ErrorTaxonomyTrace` — 12 fields (3 per-axis error-event submodels).
- `SelfConsistencyEnsembleTraceModel` / `SelfConsistencyEnsembleTrace` — 12 fields (3 per-axis judgment submodels).
- `CounterfactualAlternativesTraceModel` / `CounterfactualAlternativesTrace` — 12 fields (6 per-axis event/alternative submodels).

Exact field names and submodel shapes match the versions already worked out earlier in this conversation; this doc does not repeat them verbatim — see the implementation commit for the literal field list. The only content change from those earlier sketches: every `dict[str, Any]` / `list[dict[str, Any]]` field becomes a real submodel (using the new capability above), and every description is rewritten to be general rather than tied to one example.

#### Edge Cases & Error Handling
- Every submodel field requires its own `Field(description=...)` — a missing one fails construction at import time (`TraceSchema.from_model` raising `ValueError`), the same fail-fast behavior `ActionTrace` already relies on.

---

### 6.6 Export chain (modified)

`vidbyte/trace/continual/__init__.py` → `vidbyte/trace/__init__.py` → `vidbyte/__init__.py` each gain the five new `*Trace`/`*TraceModel` names in their imports and `__all__`, in the same position/pattern `ActionTrace`/`ActionTraceModel` already occupy in all three files.

---

### 6.7 `skills/vidbyte-sdk/continual-tracing.md` (modified)

#### What it does
Fixes the "deep-merge objects" wording and documents the nested-shape capability.

#### Logic
Line 49's merge-policy bullet is reworded to state the real one-level shallow `dict.update()` for OBJECT fields (matching `UpdateTraceTool`'s own `_TOOL_DESCRIPTION`, which already said "shallow-merged" correctly — the skill file was the one that disagreed with the code). A new bullet under "Architecture" documents `TraceField.fields`/`.items`, points at `MAX_TRACE_FIELD_NESTING_DEPTH`, and states the merge-semantics caveat from §5 explicitly, so a future reader doesn't have to rediscover it a third time.

---

## 7. Data Model Changes

### 7.1 `TraceField` (pydantic model, not a DB schema)

**Change type:** Modified (additive)

```python
fields: Mapping[str, "TraceField"] | None = None   # new, OBJECT only
items: "TraceField | None" = None                   # new, ARRAY only
```

**Migration strategy:** N/A — both new attributes default to `None`; every existing constructed `TraceField` (including ones already serialized inside a running agent's `run_state` from an in-flight trace) remains valid, since `None` was already the implicit state for "no declared inner shape."

---

## 8. API Changes

N/A — this is an SDK library change, not an HTTP API. The only "wire" surface affected is the JSON Schema `UpdateTraceTool.spec().input_schema` presents to model providers, covered in §6.4.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/constants/trace.py` | `MAX_TRACE_FIELD_NESTING_DEPTH` bound |
| CREATE | `vidbyte/lib/enums/continual_trace.py` | Closed vocabularies for the five new schemas |
| MODIFY | `vidbyte/lib/dataclasses/trace.py` | `TraceField.fields`/`.items`, recursive `from_model` builder, A001 header upgrade |
| MODIFY | `vidbyte/tools/continual_trace.py` | Recursive `_input_schema`/type validation, A001 header upgrade |
| MODIFY | `vidbyte/trace/continual/prebuilt.py` | Five new schemas |
| MODIFY | `vidbyte/trace/continual/__init__.py` | Export the five new schemas |
| MODIFY | `vidbyte/trace/__init__.py` | Export the five new schemas |
| MODIFY | `vidbyte/__init__.py` | Export the five new schemas |
| MODIFY | `skills/vidbyte-sdk/continual-tracing.md` | Fix "deep-merge" wording, document nested shape |
| MODIFY | `scripts/test-continual-trace.py` | Extend the existing standalone verification script with nested-shape cases |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `pydantic` | `>=2,<3` (already a dependency; installed `2.13.4`) | `model_validator(mode="after")`, self-referential `TraceField` model | None — already exercised elsewhere in the SDK |

---

## 11. Rollout & Deployment

Not a breaking change — no feature flag needed; every existing construction path is unaffected (§9's Non-Goals, §6.3's Edge Cases). No deployment ordering concerns; this is a single-package SDK release path, same as PR #397.

---

## 12. Open Questions

- [ ] Should `_first_shape_error`'s recursive validation also reject an ARRAY field's element when it's a `Mapping` but has an extra key not present in `items.fields`? Current design lets it through (matching the top level's existing "unknown keys silently dropped at merge" policy) rather than erroring, on the theory that adding a stricter rule here should be a deliberate follow-up decision, not something bundled into this change.
- [ ] Whether to also emit a real `additionalProperties: false` at the very top level (the `trace` parameter's own schema, `_input_schema()`'s outer object) already exists as `additionalProperties: False` today, unchanged, and is not part of this change — flagging only for visibility, not as a decision needed here.

## 13. Alternatives Considered

### Alternative 1: Add a `TraceFieldType.ENUM` wire type
- What: A dedicated enum type in the six-member `TraceFieldType` for closed string vocabularies, surfaced as JSON Schema `"enum": [...]`.
- Why rejected: The user's ask was specifically about OBJECT/ARRAY internal shape ("subfields"), not scalar value constraints. `str, Enum` Python classes already satisfy the repo's categorical-vocabulary convention and require zero changes to `TraceFieldType`/`_annotation_to_type`. Adding a seventh wire type is a larger, separate change with its own merge/validation implications (is an enum mismatch a shape error or a value error?) better scoped on its own.

### Alternative 2: Make `TraceField.fields`/`.items` a separate dataclass rather than self-referential `TraceField`
- What: A distinct `NestedFieldShape` type instead of reusing `TraceField` recursively.
- Why rejected: `TraceField` already carries exactly the two attributes (`description`, `type`) every nested sub-field needs; a second parallel type would duplicate that shape and force two validation paths instead of one recursive one. Self-reference is the smaller change and the one that makes `_json_schema_for_field`/`_first_shape_error` naturally recursive with no type-juggling.

### Alternative 3: Enforce depth at `_field_from_annotation` construction time instead of `TraceField`'s own validator
- What: Reject over-deep nesting while walking pydantic model annotations, before any `TraceField` is built.
- Why rejected: Violates the "Strict Config Dataclasses" field-guide principle of validation living in one place. A `TraceField` constructed directly (not via `from_model` — e.g. from a raw mapping, the way `TraceSchema.coerce` already supports) would bypass a check that only lived in the builder. Putting it on `TraceField._validate_shape` makes every construction path — `from_model`, a raw `{field: {"type": "object", "fields": {...}}}` mapping, or direct Python construction — provably within bounds.

# Design Doc: SDK Agent Lint Regression Repair

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-29
**Last Updated:** 2026-08-29

---

## 1. Overview

This change repairs all eight SDK lint rules that regressed after their baselines were established. It supplies complete maintenance context to 204 newly noncompliant Python files, removes the customization edge that enlarged a dependency cycle, decomposes and types the shared reasoning-trace boundary, redacts raw exception disclosure, deepens ten model-facing tool descriptions, and replaces SHA-1 ledger identifiers with SHA-256. Public tool names, arguments, execution behavior, schema immutability, context placement, and package exports remain stable.

---

## 2. Goals & Non-Goals

### Goals

- Restore A001, A006, S008, S009, S016, S017, S025, and S050 to or below their accepted baselines without suppressions.
- Give every newly added reasoning/context/COT/customization module a specific canonical header with purpose, ownership, architecture, modification, edge-case, documentation, and verification context.
- Keep `BaseTool.customize()` immutable and behavior-preserving while removing customization from the existing base/activity cycle.
- Split reasoning trace normalization into small class-bound helpers with stable typed errors and narrow return contracts.
- Return stable, redacted tool errors instead of raw caught exception text.
- Preserve all model-facing tool semantics while rewriting the ten shallow descriptions as four or five general sentences.
- Run source, package, and full canonical CI gates without adding feature tests.

### Non-Goals

- No new tool, parameter, provider, context primitive, or public package export.
- No change to model-authored strategy data, context placement, billing, permissions, or execution delegation.
- No attempt to eliminate unrelated historical lint debt; genuine improvements are ratcheted into `lint/baseline.json`.
- No new test files under the user-selected no-tests workflow.

---

## 3. Background & Context

The repository's new agent-native policies are count-ratcheted against `lint/baseline.json`. Main currently exceeds eight baselines: A001 by 204 files, A006 by two findings, S008 by two findings, S009 by two net findings, S016 by seventeen, S017 by twelve, S025 by ten, and S050 by one. Exact comparison against the commits that established the affected baselines showed that the new source is concentrated in the reasoning-trace family, deep-COT tools, context primitives, customization wrapper, and two CI contract scripts. The SDK field guide requires model-facing descriptions to be general four-to-five-sentence contracts, helper state to stay class-bound, customization to remain immutable, and CI to validate both worktree source and built artifacts.

---

## 4. Requirements

### Functional Requirements

1. All 204 newly noncompliant Python files must contain non-empty canonical A001 fields specific to their actual ownership and verification path.
2. `BaseTool.customize()` must still validate through `ToolCustomization`, return a `BaseTool`, delegate validation/execution to the original tool, and replace descriptions in both `ToolSpec.parameters` and explicit `input_schema` properties.
3. The customization implementation must no longer import `vidbyte.tools.base`, restoring A006 to its pre-customization graph allowance.
4. Reasoning trace definitions and argument normalization must raise typed SDK errors with safe structured details rather than built-in `ValueError`.
5. Reasoning trace normalization must accept/reject the same string, number, integer, boolean, and array inputs and keep confidence in the inclusive 0.0-to-1.0 range.
6. `ReasoningTraceContextItem` construction must use statically narrow `str` and `float | None` values.
7. Context-manager rejections in the shared trace tool, ten named reasoning tools, and deep-COT recorder must return stable safe text without copying the caught exception.
8. The ten named reasoning tool descriptions must each contain four or five meaningful general sentences without usage examples.
9. Content-keyed COT ledger IDs must use SHA-256 while preserving normalized input, twelve hexadecimal characters, prefix shape, and same-process overwrite semantics.
10. Any rule count improved below baseline must update the baseline in the same change; no rule may regress.

### Non-Functional Requirements

- Performance: normalization remains linear in parameter and array size; hashing remains constant-time for bounded statement input.
- Scalability: no new shared registries, network calls, locks, or persistent state.
- Security: raw `ValueError` text and model-supplied values are not copied into public error text or exception metadata.
- Observability: successful `ToolResult` metadata and context primitive rendering remain unchanged.
- Reliability: wrappers remain immutable, input schemas are deep-copied, and source/package CI verifies both editable and built distributions.

---

## 5. High-Level Design

The repair treats the reasoning family as one maintained subsystem. All 195 files in `vidbyte/tools/builtins/reasoning/` receive canonical headers: shared modules and the ten hand-maintained tools get role-specific context, while each of the 182 generated-style trace modules gets a strategy-specific header derived from its existing class/definition. Nine other newly added files receive or correct their missing canonical fields. Three already-existing files touched for the wrapper/error repair also receive canonical headers, allowing A001 to ratchet downward rather than leaving edited historical debt in place.

The customization wrapper moves beside the shared `_ToolWrapper` base in `vidbyte.tools.base`; `vidbyte.tools.customization` becomes a pure immutable spec transformer and no longer imports base. The shared reasoning trace class uses two new SDK error types, class-bound normalization helpers, and explicit canonical-field helpers. Existing context write catches keep internal exception objects private and emit a stable remediation-oriented `ToolResult.error` message.

The ten model-facing descriptions are rewritten, not padded: each states when the reasoning form applies, its central operation, the evidence/uncertainty discipline it imposes, and what a useful record enables. COT statement IDs switch to SHA-256 with the existing normalization/truncation contract. Focused lint runs precede the canonical source, package, and full CI gates.

```text
Model call -> BaseTool wrapper -> unchanged validation/execution
                    |
                    +-> pure immutable ToolSpec customization

Reasoning call -> typed normalization helpers -> context primitive -> ContextManager
                         | invalid                         | rejected
                         +-> typed safe error             +-> stable redacted result
```

---

## 6. Detailed Design

### 6.1 Canonical File Context

**File(s):** `scripts/check_context_primitive_introductions.py`, `scripts/check_reasoning_trace_contracts.py`, `vidbyte/context/primitives/*.py` listed in the manifest, `vidbyte/lib/{constants,enums}/cot_events.py`, `vidbyte/tools/builtins/cot_events.py`, `vidbyte/tools/customization.py`, and all 195 `vidbyte/tools/builtins/reasoning/*.py` files
**Type:** Modified

#### What it does

Adds exact A001 markers with module-specific ownership, architecture, modification patterns, edge cases, docs, and verification guidance.

#### Interface / API

```text
PURPOSE:
ROLE IN CODEBASE:
ARCHITECTURE NOTE:
COMMON MODIFICATION PATTERNS:
KNOWN EDGE CASES:
RELATED DOCS:
TESTS:
```

#### Logic / Algorithm

1. Preserve each module's existing purpose and class/tool identity.
2. Convert existing `Description`/`Purpose`/`Architecture` prose to canonical markers.
3. Give trace modules strategy-specific purpose text and accurate shared-boundary references.
4. Name the existing contract scripts and canonical CI gates as verification; do not claim nonexistent feature tests.

#### Edge Cases & Error Handling

- Headers remain opening module docstrings so `from __future__` placement is valid.
- Generated-style modules retain their strategy names and are not mislabeled as runtime-generated.
- `TEST FILES:` is replaced by the exact required `TESTS:` marker where needed.

### 6.2 Customization Dependency Boundary

**File(s):** `vidbyte/tools/base.py`, `vidbyte/tools/customization.py`
**Type:** Modified

#### What it does

Keeps the delegating wrapper with the base wrapper hierarchy and leaves customization as a base-independent pure spec transformer.

#### Interface / API

```python
class BaseTool(ABC):
    def customize(
        self, *, description: str,
        parameter_descriptions: Mapping[str, str] = ...,
    ) -> BaseTool: ...

class _CustomizedTool(_ToolWrapper): ...
class _ToolSpecCustomizer: ...
```

#### Logic / Algorithm

1. Validate the requested descriptions against the current `ToolSpec`.
2. Construct `_CustomizedTool` in `base.py`.
3. Delegate `spec()` transformation to `_ToolSpecCustomizer`.
4. Delegate `validate_call()` and `execute()` unchanged to the wrapped tool.

#### Edge Cases & Error Handling

- Explicit schema properties and tuple parameters remain synchronized.
- Caller-owned schema mappings remain unmodified.
- Wrapper composition and unwrapping still recover the original executable tool.

### 6.3 Typed Reasoning Trace Contracts

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`, `vidbyte/tools/builtins/reasoning/_base.py`
**Type:** Modified

#### What it does

Introduces distinct definition and argument error types, decomposes value normalization, and narrows context-item construction.

#### Interface / API

```python
class ReasoningTraceDefinitionError(ToolRegistrationError): ...
class ReasoningTraceArgumentError(ToolExecutionError): ...

class ReasoningTraceTool(BaseTool):
    def _normalize_value(self, declaration: ToolParameter, value: Any) -> NormalizedReasoningValue: ...
    def _normalize_string(self, declaration: ToolParameter, value: Any) -> str: ...
    def _normalize_number(self, declaration: ToolParameter, value: Any) -> float: ...
    def _normalize_array(self, declaration: ToolParameter, value: Any) -> tuple[str, ...]: ...
    def _normalize_integer(self, declaration: ToolParameter, value: Any) -> int: ...
    def _normalize_boolean(self, declaration: ToolParameter, value: Any) -> bool: ...
```

#### Logic / Algorithm

1. Validate immutable definitions with `ReasoningTraceDefinitionError` and safe reason/name details.
2. Dispatch one declaration to a class-bound type-specific normalizer.
3. Raise `ReasoningTraceArgumentError` with parameter/expectation metadata, preserving parse causes with exception chaining.
4. Materialize canonical string fields and confidence through narrow helpers before constructing the context item.

#### Edge Cases & Error Handling

- Boolean values remain invalid for numeric/integer declarations.
- NaN and infinity remain invalid.
- Empty arrays and arrays that normalize entirely to blank strings remain invalid.
- Unsupported declaration types fail with a typed contract error.

### 6.4 Redacted Context Write Failures

**File(s):** `vidbyte/tools/builtins/cot_events.py`, `vidbyte/tools/builtins/reasoning/_base.py`, and the ten named reasoning tool files listed in the manifest
**Type:** Modified

#### What it does

Stops caught `ValueError` objects from becoming model/user-visible text.

#### Interface / API

```python
return ToolResult.error(
    call.tool_name,
    "The reasoning record could not be stored because its values were invalid.",
    metadata={"error": "invalid_reasoning_context"},
)
```

#### Logic / Algorithm

1. Keep the catch at the context-manager boundary.
2. Do not interpolate or convert the caught exception.
3. Return stable category metadata and actionable safe text.

#### Edge Cases & Error Handling

- Secret-bearing or path-bearing exception text cannot leak into public results.
- Validation messages intentionally authored by the SDK remain available before the context write.

### 6.5 Model-Facing Description Depth

**File(s):** the ten named reasoning tool files (`abduce.py`, `analogy.py`, `bayesian_update.py`, `causal_chain.py`, `deduce.py`, `differential_diagnosis.py`, `falsify.py`, `fermi_estimate.py`, `induce.py`, `steelman.py`)
**Type:** Modified

#### What it does

Rewrites each top-level `ToolSpec.description` as four or five general sentences that explain the reasoning operation and its limits.

#### Interface / API

```python
ToolSpec(name=<unchanged>, description=<four-or-five-sentence contract>, ...)
```

#### Logic / Algorithm

1. State the condition under which the reasoning form is appropriate.
2. State its central operation.
3. State required evidence, alternatives, uncertainty, or falsification discipline.
4. State what the resulting record should make inspectable.

#### Edge Cases & Error Handling

- Tool and parameter names remain unchanged.
- Descriptions avoid concrete usage examples and do not promise execution or truth verification.

### 6.6 COT Ledger Hash

**File(s):** `vidbyte/tools/builtins/cot_events.py`
**Type:** Modified

#### What it does

Uses SHA-256 for deterministic content-keyed statement IDs.

#### Interface / API

```python
def statement_primitive_id(prefix: str, statement: str) -> str: ...
```

#### Logic / Algorithm

1. Strip and lowercase the statement exactly as before.
2. Hash UTF-8 bytes with SHA-256.
3. Keep the first twelve hexadecimal characters and the existing prefix separator.

#### Edge Cases & Error Handling

- Repeated normalized statements still overwrite the same record in one runtime.
- Existing in-memory context has no cross-release migration requirement.
- Primitive IDs remain opaque, fixed-length strings.

### 6.7 Lint Ratchet and Verification

**File(s):** `lint/baseline.json`
**Type:** Modified

#### What it does

Records only genuine count improvements after all source fixes pass.

#### Interface / API

```json
{"A001": 655, "S009": 252}
```

Exact final values are generated by focused `--update-baseline` runs and may be lower if the implementation removes additional genuine findings.

#### Logic / Algorithm

1. Run each affected rule without updating the baseline.
2. Confirm every finding removed corresponds to repaired source rather than analyzer failure.
3. Update only rules reported `IMPROVED`.
4. Run the complete lint and canonical CI gates.

#### Edge Cases & Error Handling

- Regressed or errored rules are never baseline-updated.
- Worktree source verification explicitly points `PYTHONPATH` at the worktree; package verification removes it.

---

## 7. Data Model Changes

### 7.1 Reasoning Trace SDK Errors

**Change type:** New exception types

```python
class ReasoningTraceDefinitionError(ToolRegistrationError): ...
class ReasoningTraceArgumentError(ToolExecutionError): ...
```

**Migration strategy:**

- Forward migration: callers may catch the more specific errors; both remain inside the existing public SDK hierarchy.
- Rollback plan: restore parent error use; no serialized or persisted data changes.

### 7.2 COT Statement Primitive IDs

**Change type:** Modified ephemeral identifier derivation

```text
<prefix>:<first 12 hex characters of SHA-256(normalized statement)>
```

**Migration strategy:**

- Forward migration: N/A - ContextManager records are in-memory and IDs are recomputed on write.
- Rollback plan: restore SHA-1 only by reverting code; no durable store migration exists.

---

## 8. API Changes

N/A - public methods, tool names, parameters, schemas, exports, and result object shapes are unchanged. Public failure text becomes stable/redacted, and opaque in-memory statement IDs use a stronger digest.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-lint-regression-repair.md` | Record the reviewed repair contract and verification plan. |
| MODIFY | `lint/baseline.json` | Ratchet genuine A001/S009 improvements after verification. |
| MODIFY | `scripts/check_context_primitive_introductions.py` | Add complete canonical maintenance context. |
| MODIFY | `scripts/check_reasoning_trace_contracts.py` | Add complete canonical maintenance context. |
| MODIFY | `vidbyte/context/primitives/cot_events.py` | Correct the canonical TESTS header field. |
| MODIFY | `vidbyte/context/primitives/reasoning_strategies.py` | Add missing canonical maintenance fields. |
| MODIFY | `vidbyte/context/primitives/reasoning_traces.py` | Correct the canonical TESTS header field. |
| MODIFY | `vidbyte/lib/constants/cot_events.py` | Correct the canonical TESTS header field. |
| MODIFY | `vidbyte/lib/enums/cot_events.py` | Correct the canonical TESTS header field. |
| MODIFY | `vidbyte/lib/errors/base.py` | Add typed reasoning errors and canonical maintenance context. |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export typed reasoning errors and canonical maintenance context. |
| MODIFY | `vidbyte/tools/base.py` | Own the customized wrapper and canonical maintenance context. |
| MODIFY | `vidbyte/tools/builtins/cot_events.py` | Correct header, redact context errors, and replace SHA-1. |
| MODIFY | `vidbyte/tools/customization.py` | Become a base-independent pure spec transformer and correct its header. |
| MODIFY | `vidbyte/tools/builtins/reasoning/__init__.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/_base.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/_parsing.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/a3_problem_solving_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/ab_testing_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/abduce.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/abductive_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/adaptive_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/affect_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/after_action_review_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/alternative_futures_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/analogical_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/analogy.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/analysis_of_competing_hypotheses_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/analytic_hierarchy_process_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/ansoff_matrix_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/argument_map_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/assumption_ladder_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/backward_chaining_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/balanced_scorecard_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/base_rate_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/bayesian_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/bayesian_update.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/bcg_matrix_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/biomimicry_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/blue_ocean_strategy_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/bottleneck_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/bowtie_risk_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/business_model_canvas_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/causal_chain.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/causal_loop_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/causal_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/comparative_case_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/concept_mapping_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/cone_of_plausibility_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/constraint_removal_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/constraint_satisfaction_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/correlation_causation_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/cost_benefit_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/counterfactual_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/customer_journey_mapping_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/cynefin_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/data_quality_audit_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/deception_detection_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/decision_matrix_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/decision_tree_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/deduce.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/deductive_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/default_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/defeasible_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/delphi_method_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/dependency_mapping_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/design_thinking_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/devils_advocacy_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/dialectical_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/differential_diagnosis.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/dmaic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/double_diamond_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/double_loop_learning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/elimination_by_aspects_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/empathy_mapping_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/error_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/ethical_matrix_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/ethnographic_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/event_tree_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/evidence_triangulation_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/expected_value_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/experimental_design_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fairness_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/falsify.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/familiarity_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fast_and_frugal_trees_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fault_tree_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/feedback_loop_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fermi_estimate.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fermi_estimation_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/first_principles_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fishbone_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/five_whys_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fluency_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fmea_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/force_field_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/forward_chaining_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/fuzzy_logic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/game_theory_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/gemba_walk_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/hazop_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/hermeneutic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/historical_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/horizon_scanning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/hypothesis_testing_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/iceberg_model_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/incentive_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/indicators_signposts_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/induce.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/inductive_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/influence_diagram_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/inversion_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/issue_tree_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/jobs_to_be_done_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/key_assumptions_check_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/kolb_learning_cycle_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/lateral_thinking_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/legal_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/leverage_points_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/linchpin_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/mece_decomposition_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/mental_simulation_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/metacognitive_audit_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/mind_map_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/minimax_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/minto_pyramid_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/modal_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/morphological_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/multi_attribute_utility_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/naive_diversification_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/narrative_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/nine_windows_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/nonmonotonic_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/nth_order_effects_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/null_hypothesis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/occams_razor_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/ooda_loop_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/ooda_red_team_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/opportunity_cost_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/outside_view_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/pareto_principle_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/pdca_cycle_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/peak_end_rule_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/pestle_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/phenomenology_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/policy_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/porters_five_forces_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/postmortem_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/pragmatism_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/precautionary_principle_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/predicate_logic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/premortem_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/probabilistic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/proof_by_cases_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/proof_by_contradiction_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/propositional_logic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/provocation_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/quasi_experimental_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/random_stimulus_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/randomized_control_trial_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/recognition_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/red_team_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/reference_class_forecasting_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/reframing_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/regression_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/regret_minimization_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/reverse_brainstorming_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/root_cause_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/rubber_duck_debugging_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/satisficing_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/scamper_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/scarcity_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/scenario_planning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/scientific_method_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/second_order_effects_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/sensitivity_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/simulation_heuristic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/six_thinking_hats_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/social_proof_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/socratic_questioning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/spatial_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/speed_accuracy_tradeoff_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/spider_mapping_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/stakeholder_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/steelman.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/steelman_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/stock_and_flow_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/storyboarding_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/swot_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/syllogistic_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/synectics_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/systematic_inventive_thinking_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/systems_thinking_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/take_the_best_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/tallying_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/temporal_reasoning_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/theory_of_constraints_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/tradeoff_matrix_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/trial_and_error_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/triz_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/uncertainty_quantification_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/utility_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/value_chain_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/value_focused_thinking_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/value_stream_mapping_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/values_tradeoff_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/vrio_framework_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/what_if_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |
| MODIFY | `vidbyte/tools/builtins/reasoning/why_because_analysis_trace.py` | Add canonical context; apply shared or tool-specific lint repairs where relevant. |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `hashlib.sha256` | Standard library | Deterministic content-keyed IDs | Low; opaque ephemeral IDs change across the upgrade. |
| Existing SDK error hierarchy | Repository source | Stable typed boundary failures | Low; new types subclass existing public parents. |
| Ruff / mypy / repository lint runner | Pinned by `pyproject.toml` | Static verification and count ratchet | Low; canonical CI owns versions. |

---

## 11. Rollout & Deployment

- No feature flag or external service ordering is required.
- The package remains backward-compatible at method and schema boundaries.
- Publish only after source and built-package stages both pass.
- Rollback is a normal package/code revert; no durable data migration is required.

---

## 12. Open Questions

- [x] Should customization introduce a new wrapper module? No; placing the private wrapper beside `_ToolWrapper` removes the new cycle edge with the smallest ownership change.
- [x] Should raw context-manager errors be sanitized excerpts? No; callers only need a stable invalid-context category, while arbitrary exception detail creates disclosure risk.
- [x] Should the SHA-1-derived IDs be migrated? No; they exist only in the caller-owned in-memory context lifecycle.
- [x] Are new tests required? No; the user selected the no-tests workflow and the canonical source/package suites plus existing contract scripts exercise the boundaries.

---

## 13. Alternatives Considered

### Alternative 1: Raise the eight baselines

- What: Accept all new findings as frozen debt.
- Why rejected: It would preserve missing ownership context, unsafe errors, shallow model contracts, and an enlarged dependency cycle.

### Alternative 2: Add generic copied headers

- What: Insert identical boilerplate into all 204 files.
- Why rejected: A001 exists to provide file-specific ownership and repair context; generic prose satisfies syntax but not maintenance intent.

### Alternative 3: Keep customization's reciprocal base import

- What: Update only the A006 baseline.
- Why rejected: The wrapper can live with its base contract while the transformer stays pure, removing the newly introduced graph edge without changing behavior.

### Alternative 4: Pad descriptions with filler sentences

- What: Append generic prose until the sentence counter passes.
- Why rejected: Model-facing descriptions are runtime context; each sentence must clarify operation, evidence discipline, limits, or output usefulness.

### Alternative 5: Truncate raw exception strings

- What: Return a shortened `str(exc)`.
- Why rejected: Truncation does not remove secrets, paths, payload fragments, or unstable dependency wording.

# Design Doc: Reasoning Deep Observability Tools

**Status:** Draft
**Author:** OpenCode
**Created:** 2026-08-26
**Last Updated:** 2026-08-26

---

## 1. Overview

This feature adds 182 model-callable reasoning trace tools to the Vidbyte SDK,
based on the complete default reasoning-trace families in `vidbyte-skills`.
Each tool exposes the same eight-field deep-observability contract while
specializing its model-facing description and strategy identity to one source
skill. Each call writes a bounded, immutable context-window primitive so the
agent and downstream monitors can inspect the public reasoning record across
iterations. This extends the context-aware built-in tool pattern reviewed in
SDK PR #361 without introducing a private chain-of-thought store or a second
context management system.

---

## 2. Goals & Non-Goals

### Goals

- Add one model-facing `BaseTool` subclass per complete `*-trace` reasoning family in `vidbyte-skills`.
- Preserve the source skill's strategy identity and purpose in every tool description, primitive, result, and catalog entry.
- Give every tool exactly eight meaningful parameters: `question`, `strategy_application`, `evidence`, `assumptions`, `alternatives`, `disconfirming_signals`, `confidence`, and `next_action`.
- Give the tool description and every parameter description four or more complete sentences of example-free general guidance.
- Write every successful call into a corresponding bounded context-window primitive through the injected `ContextManager`.
- Export the generated tool classes and primitive class from the normal SDK public built-in and context-primitives packages.
- Keep the implementation dependency-free, permission-safe, and compatible with `ComponentRegistry` discovery.
- Verify the entire repository with the canonical SDK CI command and add focused smoke validation without adding a new feature test file.

### Non-Goals

- Do not copy the Markdown skill files, slash-command variants, or skill execution scripts into `vidbyte-sdk`.
- Do not implement the 21 specialized default-only orchestration traces that lack the complete size-variant family in `vidbyte-skills`.
- Do not execute a reasoning framework, call another model, resolve predictions, or score the truth of model-authored reasoning.
- Do not persist private hidden chain-of-thought, external telemetry, or application-owned data.
- Do not add new dependencies, pricing entries, middleware, provider adapters, or runtime algorithms.
- Do not add new feature test files under `tests/`; existing tests and CI remain mandatory.

---

## 3. Background & Context

`vidbyte-skills` is the source repository for portable agent workflows. Its
reasoning catalog contains 203 base `*-trace` skills. The 182 families selected
for this feature each have a default, small, medium, and large variant and
therefore provide a consistent source identity for an SDK tool catalog. The
remaining 21 default-only traces are specialized orchestration strategies with
companion engines or atypical contracts; they are intentionally deferred so
this batch stays within the requested 100–200 tool range and does not invent
execution APIs for those strategies.

SDK PR #361 established the relevant review standard for model-facing tools:
fields must decompose the event meaningfully, tool and parameter descriptions
must be long general-purpose instructions without concrete examples, and
structured categorical values should have a typed source of truth. This feature
uses one universal observability contract rather than pretending that all 182
strategies have identical internal algorithms. The strategy-specific purpose is
kept in the description and context metadata, while the shared fields enforce
the cross-strategy evidence, uncertainty, alternative, disconfirmation, and
next-action signals needed for deep monitoring.

The SDK already provides `BaseTool`, `ToolSpec`, `ToolParameter`, `ToolResult`,
`ToolPermission.SAFE`, `ContextManager.upsert`, immutable slotted context
primitives, public package exports, and lazy `ComponentRegistry` discovery.
`ContextManager` owns placement and managed primitive identity; the new tools
only validate, construct, upsert, and render their own primitive records.

---

## 4. Requirements

### Functional Requirements

1. The SDK SHALL expose 182 reasoning trace tool classes whose tool names match the 182 selected source skill slugs.
2. Every tool SHALL be a `BaseTool` subclass that accepts a `ContextManager` and requests `ToolPermission.SAFE`.
3. Every tool SHALL expose exactly eight parameters named `question`, `strategy_application`, `evidence`, `assumptions`, `alternatives`, `disconfirming_signals`, `confidence`, and `next_action`.
4. Every parameter SHALL have a non-empty description of at least four full sentences, and no model-facing description SHALL contain concrete examples or example markers.
5. Every tool description SHALL have at least four full sentences describing when the strategy is used, why the record exists, how it supports observability, and the limits of self-authored reasoning telemetry.
6. The four text fields that establish the record (`question`, `strategy_application`, `evidence`, and `next_action`) SHALL reject missing, blank, or whitespace-only values with an actionable `ToolResult.error`.
7. The remaining text fields SHALL also reject blank values when supplied as required deep-observability fields; all eight parameters are required to prevent shallow event emission.
8. `confidence` SHALL accept a numeric value in the inclusive range 0.0 through 1.0 and reject malformed or out-of-range values rather than silently clamping them.
9. Each successful call SHALL create one `ReasoningTraceContextItem`, upsert it into the injected `ContextManager`, and return its rendered context text plus strategy, confidence, and primitive identity metadata.
10. Primitive IDs SHALL be unique within a manager for repeated calls of the same strategy and SHALL preserve the strategy slug in their readable prefix.
11. The context primitive SHALL render the strategy, all eight recorded fields, and the source skill identity in deterministic order under a bounded character limit.
12. All generated classes, the shared tool base, the definition catalog, and the context primitive SHALL be importable through the package exports used by existing built-in tools and context primitives.
13. A catalog lookup SHALL resolve a source skill slug to its generated tool class without importing arbitrary modules or reading a caller-provided path.

### Non-Functional Requirements

- **Description quality:** A repository-local validation command SHALL inspect all 182 tool specs, confirm eight parameters, count sentence-delimited prose, and reject concrete-example markers.
- **Context safety:** Primitive text SHALL be bounded at 4,000 characters and SHALL use the existing `ContextManager.upsert` path; no bespoke context assembly or compaction algorithm is permitted.
- **Runtime cost:** Tool construction SHALL be constant-time per instance, spec construction SHALL be deterministic, and no model or network call SHALL occur during specification or execution.
- **Scalability:** The catalog SHALL be data-driven so the 182 public class names do not require 182 copies of execution logic, while each class remains independently discoverable and instantiable.
- **Security:** Tools remain `SAFE`, do not execute user code, do not read skill files at runtime, and do not treat model-authored evidence as verified fact.
- **Reliability:** Invalid calls return structured tool errors, manager rejection is surfaced without masking the cause, and failed upserts do not claim a successful context write.
- **Compatibility:** Existing built-in imports, context primitive imports, provider schema generation, YAML component discovery, and package installation SHALL remain valid.

---

## 5. High-Level Design

The implementation adds a data-driven reasoning trace module under
`vidbyte.tools.builtins` and a matching immutable primitive module under
`vidbyte.context.primitives`. A frozen definition catalog records the selected
skill slug and a concise source-grounded purpose for each strategy. One shared
`ReasoningTraceTool` class builds the eight-field `ToolSpec`, validates calls,
constructs the primitive, and records the result. A generated public subclass
is created for each catalog definition so callers and `ComponentRegistry` see
normal class-based SDK components rather than one opaque multiplexer.

The data flow is:

```text
[Model tool call]
       |
       v
[Generated strategy tool]
       |
       v
[Required-field and confidence validation]
       |
       v
[ReasoningTraceContextItem]
       |
       v
[ContextManager.upsert]
       |
       +--> [bounded model-visible context primitive]
       +--> [ToolResult text and observability metadata]
```

Every tool uses the same public trace shape, but its name, description, class
identity, primitive strategy field, and metadata are strategy-specific. This
keeps the contract deep enough to expose reasoning quality without creating
182 incompatible schemas. The primitive remains model-authored telemetry: the
SDK records what was stated and does not claim that the stated reasoning is
faithful, correct, or independently verified.

---

## 6. Detailed Design

### 6.1 Reasoning Definition Catalog

**File(s):** `vidbyte/tools/builtins/reasoning_traces.py`

**Type:** New file

#### What it does

`ReasoningTraceDefinition` stores the source skill slug and purpose summary.
`REASONING_TRACE_DEFINITIONS` contains the 182 complete families selected from
`vidbyte-skills`. `ReasoningTraceCatalog` provides deterministic class-name
conversion, public class generation, slug lookup, and shared description
construction. No runtime file-system access is used; the copied source
understanding is represented as committed SDK metadata.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ReasoningTraceDefinition:
    skill_name: str
    purpose: str


class ReasoningTraceCatalog:
    @classmethod
    def definitions(cls) -> tuple[ReasoningTraceDefinition, ...]: ...

    @classmethod
    def tool_class(cls, skill_name: str) -> type[ReasoningTraceTool]: ...

    @classmethod
    def tool_classes(cls) -> Mapping[str, type[ReasoningTraceTool]]: ...
```

#### Logic / Algorithm

1. Store the selected slugs in a stable alphabetical tuple.
2. Build one frozen definition for each slug and source-grounded purpose.
3. Derive a valid public class name by converting slug segments to PascalCase and appending `Tool`.
4. Create a subclass bound to its definition and expose it in module globals and the module `__all__`.
5. Build each spec from the bound definition, using five tool-description sentences and eight four-sentence parameter descriptions.
6. Resolve lookups only against the in-memory definition/class map and raise a clear `KeyError` for unknown names.

#### Edge Cases & Error Handling

- Duplicate skill slugs are rejected while the catalog is initialized.
- Unknown lookup names raise an error listing the requested name and the supported catalog boundary.
- A source purpose that is blank is rejected during definition validation.
- A class name collision is rejected rather than silently replacing an existing public class.

### 6.2 Shared Reasoning Trace Tool

**File(s):** `vidbyte/tools/builtins/reasoning_traces.py`

**Type:** New file

#### What it does

`ReasoningTraceTool` is the class-first execution implementation inherited by
all 182 generated classes. It creates a strategy-specific `ToolSpec` with eight
required fields and long, example-free prose. It rejects incomplete records and
invalid confidence values, then upserts one primitive and returns a structured
success result. The tool does not execute the named reasoning method; it records
the model's public application of that method for context and observability.

#### Interface / API

```python
class ReasoningTraceTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. Copy call arguments into a local dictionary and validate all eight required text fields.
2. Parse `confidence` as a finite float and reject values outside the inclusive zero-to-one interval.
3. Increment the instance sequence and choose an unused readable primitive ID for the bound strategy.
4. Construct `ReasoningTraceContextItem` with the source slug, purpose, all fields, and the bounded rendering limit.
5. Upsert through `ContextManager.upsert` and convert manager `ValueError` failures into `ToolResult.error`.
6. Return `ToolResult.success` with rendered text and metadata containing strategy name, confidence, and primitive ID.

#### Edge Cases & Error Handling

- Missing or blank text returns the first named field that cannot support an observable record.
- Non-numeric, non-finite, or out-of-range confidence returns an error naming the field and accepted range.
- A primitive ID collision advances the local sequence until the manager has no matching entry.
- A frozen or otherwise rejected existing primitive returns the manager's error and no success result.
- Long field content is preserved in the primitive data but bounded only at rendering time by the existing text helper.

### 6.3 Reasoning Trace Context Primitive

**File(s):** `vidbyte/context/primitives/reasoning_traces.py`

**Type:** New file

#### What it does

`ReasoningTraceContextItem` is a frozen, slotted context primitive that stores a
single public reasoning checkpoint. Its renderer emits the strategy identity,
purpose, question, applied method, evidence, assumptions, alternatives,
disconfirming signals, confidence, and next action in stable order. The shared
`_truncate_text` helper bounds the final model-visible representation at 4,000
characters. It is deliberately descriptive and does not validate truth,
resolve uncertainty, or enforce the next action.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ReasoningTraceContextItem:
    primitive_id: str
    strategy_name: str
    strategy_purpose: str
    question: str
    strategy_application: str
    evidence: str
    assumptions: str
    alternatives: str
    disconfirming_signals: str
    confidence: float
    next_action: str
    title: str = "Reasoning Trace"
    max_chars: int = 4000
    kind: str = "reasoning_trace"

    def to_context_text(self) -> str: ...
```

#### Logic / Algorithm

1. Render the strategy and purpose before the trace fields so the note remains interpretable after compaction or review.
2. Render the eight fields in the same order as the tool schema to preserve validation and rendering parity.
3. Format confidence with two decimal places for stable comparison across runs.
4. Apply `_truncate_text` exactly once after the full text is assembled.

#### Edge Cases & Error Handling

- Empty optional metadata is not rendered as a hidden claim; all trace fields are required by the tool.
- A caller-created primitive can still provide a custom title, metadata, or maximum character limit when using the dataclass directly.
- Truncation may shorten the tail of a long trace, so the primitive remains bounded rather than exceeding the context budget.
- The primitive does not infer missing evidence or turn confidence into a correctness score.

### 6.4 Package Exports and Documentation

**File(s):** `vidbyte/tools/builtins/__init__.py`,
`vidbyte/context/primitives/__init__.py`, `vidbyte/tools/README.md`,
`vidbyte/context/primitives/README.md`

**Type:** Modified files

#### What it does

The package exports make the generated classes, catalog, shared base, and
primitive available through established public namespaces. The tools README will
document construction and the deep-observability contract without listing every
class inline. The primitive README will add the new module to the file index and
explain its model-authored telemetry boundary.

#### Logic / Algorithm

1. Import the new shared module from `vidbyte.tools.builtins`.
2. Extend `__all__` with the shared symbols and every generated tool class name.
3. Import `ReasoningTraceContextItem` from `vidbyte.context.primitives` and extend its `__all__`.
4. Keep the existing exports and import order stable enough for current consumers.
5. Ensure `ComponentRegistry` can discover the generated subclasses through the public builtins module.

#### Edge Cases & Error Handling

- Existing names must not be replaced or aliased to a generated tool.
- Exporting all classes must not cause a tool instance to be constructed at import time.
- Catalog lookup remains explicit even though public class exports support normal direct construction.

---

## 7. Data Model Changes

### 7.1 `ReasoningTraceContextItem`

**Change type:** New in-memory dataclass

```python
@dataclass(frozen=True, slots=True)
class ReasoningTraceContextItem:
    primitive_id: str
    strategy_name: str
    strategy_purpose: str
    question: str
    strategy_application: str
    evidence: str
    assumptions: str
    alternatives: str
    disconfirming_signals: str
    confidence: float
    next_action: str
    title: str = "Reasoning Trace"
    max_chars: int = 4000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "reasoning_trace"
    primitive_frozen: bool = False
```

**Migration strategy:** N/A - this is an additive in-memory context primitive;
there is no database schema, serialized session migration, or persistent data
format change.

---

## 8. API Changes

### 8.1 `ReasoningTraceTool`

**Change type:** New additive Python tool API

**Request:**

```json
{
  "question": "string",
  "strategy_application": "string",
  "evidence": "string",
  "assumptions": "string",
  "alternatives": "string",
  "disconfirming_signals": "string",
  "confidence": "number between 0.0 and 1.0",
  "next_action": "string"
}
```

**Response:**

```json
{
  "status": "success",
  "output": "bounded rendered reasoning trace",
  "metadata": {
    "strategy": "source skill slug",
    "confidence": "number",
    "primitive_id": "manager-local readable identifier"
  }
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| error | Any required text field is missing, blank, or whitespace-only. |
| error | `confidence` is malformed, non-finite, or outside 0.0 through 1.0. |
| error | The context manager rejects the primitive because its identity is frozen or invalid. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/reasoning-deep-observability-tools.md` | Source-of-truth design and selected skill inventory. |
| CREATE | `vidbyte/tools/builtins/reasoning_traces.py` | Definition catalog, shared tool implementation, generated public classes, and description contract. |
| CREATE | `vidbyte/context/primitives/reasoning_traces.py` | Bounded immutable primitive corresponding to every reasoning trace tool call. |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export the shared reasoning tool API and 182 generated classes. |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Export the reasoning trace context primitive. |
| MODIFY | `vidbyte/tools/README.md` | Document the reasoning trace built-in family and observability boundary. |
| MODIFY | `vidbyte/context/primitives/README.md` | Add the reasoning trace primitive to the context primitive index. |

**Summary:** 3 files created, 4 files modified, 0 files deleted. The design
document is counted in the created-file total because it is committed first on
the feature branch; no implementation code is written before that commit.

### Selected tool inventory

The following 182 source skill slugs each receive one generated public tool
class and one corresponding `ReasoningTraceContextItem` record:

```text
a3-problem-solving-trace
ab-testing-trace
abductive-trace
adaptive-reasoning-trace
affect-heuristic-trace
after-action-review-trace
alternative-futures-trace
analogical-trace
analysis-of-competing-hypotheses-trace
analytic-hierarchy-process-trace
ansoff-matrix-trace
argument-map-trace
assumption-ladder-trace
backward-chaining-trace
balanced-scorecard-trace
base-rate-trace
bayesian-trace
bcg-matrix-trace
biomimicry-trace
blue-ocean-strategy-trace
bottleneck-trace
bowtie-risk-trace
business-model-canvas-trace
causal-loop-trace
causal-trace
comparative-case-trace
concept-mapping-trace
cone-of-plausibility-trace
constraint-removal-trace
constraint-satisfaction-trace
correlation-causation-trace
cost-benefit-trace
counterfactual-trace
customer-journey-mapping-trace
cynefin-trace
data-quality-audit-trace
deception-detection-trace
decision-matrix-trace
decision-tree-trace
deductive-trace
default-heuristic-trace
defeasible-reasoning-trace
delphi-method-trace
dependency-mapping-trace
design-thinking-trace
devils-advocacy-trace
dialectical-trace
dmaic-trace
double-diamond-trace
double-loop-learning-trace
elimination-by-aspects-trace
empathy-mapping-trace
error-analysis-trace
ethical-matrix-trace
ethnographic-reasoning-trace
event-tree-trace
evidence-triangulation-trace
expected-value-trace
experimental-design-trace
fairness-analysis-trace
familiarity-heuristic-trace
fast-and-frugal-trees-trace
fault-tree-trace
feedback-loop-trace
fermi-estimation-trace
first-principles-trace
fishbone-trace
five-whys-trace
fluency-heuristic-trace
fmea-trace
force-field-trace
forward-chaining-trace
fuzzy-logic-trace
game-theory-trace
gemba-walk-trace
hazop-trace
hermeneutic-trace
historical-reasoning-trace
horizon-scanning-trace
hypothesis-testing-trace
iceberg-model-trace
incentive-analysis-trace
indicators-signposts-trace
inductive-trace
influence-diagram-trace
inversion-trace
issue-tree-trace
jobs-to-be-done-trace
key-assumptions-check-trace
kolb-learning-cycle-trace
lateral-thinking-trace
legal-reasoning-trace
leverage-points-trace
linchpin-analysis-trace
mece-decomposition-trace
mental-simulation-trace
metacognitive-audit-trace
mind-map-trace
minimax-trace
minto-pyramid-trace
modal-reasoning-trace
morphological-analysis-trace
multi-attribute-utility-trace
naive-diversification-trace
narrative-reasoning-trace
nine-windows-trace
nonmonotonic-reasoning-trace
nth-order-effects-trace
null-hypothesis-trace
occams-razor-trace
ooda-loop-trace
ooda-red-team-trace
opportunity-cost-trace
outside-view-trace
pareto-principle-trace
pdca-cycle-trace
peak-end-rule-trace
pestle-trace
phenomenology-trace
policy-analysis-trace
porters-five-forces-trace
postmortem-trace
pragmatism-trace
precautionary-principle-trace
predicate-logic-trace
premortem-trace
probabilistic-trace
proof-by-cases-trace
proof-by-contradiction-trace
propositional-logic-trace
provocation-trace
quasi-experimental-trace
random-stimulus-trace
randomized-control-trial-trace
recognition-heuristic-trace
red-team-trace
reference-class-forecasting-trace
reframing-trace
regression-reasoning-trace
regret-minimization-trace
reverse-brainstorming-trace
root-cause-trace
rubber-duck-debugging-trace
satisficing-trace
scamper-trace
scarcity-heuristic-trace
scenario-planning-trace
scientific-method-trace
second-order-effects-trace
sensitivity-analysis-trace
simulation-heuristic-trace
six-thinking-hats-trace
social-proof-trace
socratic-questioning-trace
spatial-reasoning-trace
speed-accuracy-tradeoff-trace
spider-mapping-trace
stakeholder-analysis-trace
steelman-trace
stock-and-flow-trace
storyboarding-trace
swot-trace
syllogistic-trace
synectics-trace
systematic-inventive-thinking-trace
systems-thinking-trace
take-the-best-trace
tallying-trace
temporal-reasoning-trace
theory-of-constraints-trace
tradeoff-matrix-trace
trial-and-error-trace
triz-trace
uncertainty-quantification-trace
utility-trace
value-chain-analysis-trace
value-focused-thinking-trace
value-stream-mapping-trace
values-tradeoff-trace
vrio-framework-trace
what-if-analysis-trace
why-because-analysis-trace
```

The 21 deferred default-only source skills are:

```text
agent-as-judge-trace
codeact-trace
contrastive-cot-trace
cross-lingual-consistency-trace
curriculum-learning-trace
divide-and-conquer-trace
dynamic-agent-generation-trace
elastic-reasoning-trace
focused-cot-trace
graph-of-thoughts-trace
iteration-of-thought-trace
least-to-most-trace
meta-prompting-trace
mixture-of-agents-trace
multi-agent-debate-trace
paradigm-routing-trace
parallel-thinking-trace
self-consistency-trace
self-rag-trace
sketch-of-thought-trace
step-back-trace
```

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `dataclasses`, `math`, `re` | Python 3.11+ | Definitions, validation, class-name generation, and finite-number checks. | Low; already available. |
| Existing `vidbyte.tools` contracts | Current SDK source | Tool metadata, calls, results, and permissions. | Medium; contract drift would affect every generated tool. |
| Existing `vidbyte.context` contracts | Current SDK source | Context manager upsert and bounded primitive rendering. | Medium; manager identity and placement behavior must remain unchanged. |
| `vidbyte-skills` source catalog | Local audit source only | Purpose summaries and selected skill slugs. | Low at runtime; future source changes require an intentional catalog refresh. |

No network service, credential, package installation, or external runtime
integration is introduced.

---

## 11. Rollout & Deployment

- No feature flag is required because tools are additive and opt-in through the existing `tools=[...]` agent configuration.
- Existing agents and imports remain unchanged unless an application explicitly attaches one of the new tools.
- The design doc is committed first, followed by implementation commits and a refinement commit if the adversarial review finds a gap.
- Rollout is the normal SDK package release path after the complete source and package CI gates pass.
- Rollback is a normal package rollback or revert of the feature commits; no data migration is required.
- The branch is pushed as `feat/reasoning-deep-observability-tools` and opened as a draft PR against `main`.

---

## 12. Open Questions

- [ ] Should the 21 deferred specialized orchestration traces receive dedicated multi-field schemas in a follow-up, or should they remain behind their existing companion engines?
- [ ] Should a future release add an optional monitor-owned resolution channel for predictions and confidence calibration rather than changing this self-reporting tool contract?
- [ ] Should the SDK eventually expose a grouped factory that returns selected trace tools by category instead of requiring direct class imports?

These questions do not block the current additive implementation.

---

## 13. Alternatives Considered

### Alternative 1: Implement all 203 base reasoning traces

- **What:** Include the 182 complete families plus the 21 default-only orchestration traces in one generic contract.
- **Why rejected:** The request caps the batch at 100–200, and the default-only traces have specialized companion-engine semantics that a generic record would misrepresent.

### Alternative 2: Create 182 independent source files

- **What:** Put each tool and primitive in its own Python module.
- **Why rejected:** It would duplicate execution and rendering logic, make description quality harder to audit, and create a large import surface without improving runtime behavior.

### Alternative 3: Expose one `run_reasoning_trace` multiplexer

- **What:** Use one tool with a strategy-name parameter to select all 182 methods.
- **Why rejected:** It weakens provider schemas, makes tool discovery less explicit, prevents normal class-based registry discovery, and allows the model to select an arbitrary strategy string instead of a concrete public capability.

### Alternative 4: Use a hidden trace store instead of context primitives

- **What:** Record calls only in metadata or an external observability sink.
- **Why rejected:** The requirement is a corresponding context-window primitive, and the SDK already provides `ContextManager` as the managed, inspectable context boundary.

### Alternative 5: Reuse the PR #361 six-field event schema

- **What:** Add 182 tools by copying the batch-2 CoT event fields.
- **Why rejected:** Those fields describe predictions, goal checks, assumptions, failures, and retrospectives; the reasoning-trace catalog needs a stable cross-strategy record that also captures method application, evidence, alternatives, disconfirmation, confidence, and next action.

---

## Canonical Verification Command

The required complete SDK gate is:

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

For worktree source verification, the field guide requires the source stage to
run with the worktree on `PYTHONPATH` and the package stage without it:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python scripts/run_ci.py --stage source
Remove-Item Env:PYTHONPATH
python scripts/run_ci.py --stage package
```

The complete `python scripts/run_ci.py` command remains the final gate after
refinement, and any focused smoke validation is diagnostic only.

END OF DESIGN DOC

# Design Doc: Reasoning Strategy Tools (Family K, tools 1-10)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-18
**Last Updated:** 2026-08-18

---

## 1. Overview

This change adds ten new model-callable prebuilt tools to the Vidbyte SDK, each one
anchored to a single named strategy from the scientific/philosophical reasoning
literature: deduction, induction, abduction, analogical transfer, causal-chain
reasoning, Bayesian updating, differential diagnosis, Fermi estimation, steelmanning,
and Popperian falsification. Unlike a generic "think step by step" prompt, each tool
forces the model to fill in the specific fields that make that reasoning pattern
checkable — premises and the named inference rule for deduction, a falsifying case for
induction, competing hypotheses for abduction, a mechanism for causation, explicit
prior/posterior numbers for Bayesian updates, and so on. The tool's parameter schema
*is* the leverage: the description does not need to teach the model the reasoning
pattern, it only needs to demand the pattern's output shape.

Each tool follows the SDK's existing "pure cognitive tool" pattern already used by
`ReflexionTool` and `TrajectoryCheckpointTool`: it writes a frozen `ContextItem`
dataclass into the caller-supplied `ContextManager` and returns the rendered text so
the model can confirm what was recorded.

---

## 2. Goals & Non-Goals

### Goals
- Implement the first 10 tools of the "Reasoning Strategies" family (`deduce`,
  `induce`, `abduce`, `analogy`, `causal_chain`, `bayesian_update`,
  `differential_diagnosis`, `fermi_estimate`, `steelman`, `falsify`) as builtin SDK
  tools, following the existing `ReflexionTool` / `TrajectoryCheckpointTool` pattern.
- Give every parameter a rich, precise, constraint-bearing description, since
  parameter descriptions are the primary lever on tool-calling behavior.
- Add one shared `ContextItem` primitive per tool so the recorded reasoning persists
  in the context window and can be read back by the model or a harness.
- Keep the 10 tools individually importable (`from vidbyte.tools.builtins.reasoning
  import DeduceTool`) and collectively re-exported from
  `vidbyte.tools.builtins`, matching how every other builtin tool family is exposed.
- Update the SDK's tool catalog docs (`skills/usage/available_tools.md`, `llms.txt`)
  so the new family is discoverable the same way `ReflexionTool` is documented today.

### Non-Goals
- No algorithm-triggered counterpart (no `DeductionAlgorithm`, etc.). These are pure
  tool-form primitives with no `InnerContextWindowAlgorithm` equivalent, the same way
  the `epistemics.py` / `framing.py` / `decisions.py` primitives exist without a tool
  wrapper today — we are doing the mirror case (tool without algorithm).
- No new tests. Per the `design-doc-no-tests` workflow, no new test files are added.
  `tests/test_context_algorithm_tools.py` is left untouched; existing suite must
  still pass unmodified.
- No changes to `vidbyte/__init__.py` or `vidbyte/context/__init__.py` top-level
  re-exports. `ReflexionTool`/`ReflexionContextItem` are themselves not re-exported
  at those levels today (only `TrajectoryCheckpointContextItem` partially is), so
  matching that existing (inconsistent) precedent keeps this change's blast radius
  equivalent to the tools it mirrors. Documented as an explicit decision, not an
  oversight, in Section 13.
- The remaining 25 reasoning strategies proposed in the prior conversation are
  explicitly out of scope for implementation — user asked for those to be listed and
  explained only, not built.
- No convenience "mount all 10 at once" factory (unlike
  `ContextWindowFactory`/`context_window_tools()`). `ReflexionTool` and
  `TrajectoryCheckpointTool`, the closest precedent, are each constructed
  individually; the new tools follow that same standalone-construction convention.

---

## 3. Background & Context

The SDK already ships two "pure cognitive" tools that let the *primary* model author
structured self-reflection directly into its own context window:
`vidbyte/tools/builtins/reflexion.py` (self-critique) and
`vidbyte/tools/builtins/trajectory_checkpoint.py` (compressed progress checkpoint).
Both are documented in `skills/vidbyte-sdk/context-algorithm-to-tool.md` as the
worked examples of the "algorithm-to-tool" conversion pattern, but they establish a
more general house style for *any* tool that exists purely to force a structured,
model-authored reasoning artifact into context: constructor-injected
`ContextManager`, per-instance counter for stable primitive IDs, required-field
validation before construction, and `item.to_context_text()` returned as
`ToolResult.output` so the model can verify what was stored.

This request extends that same house style to ten new reasoning-pattern tools drawn
from classical scientific-reasoning literature (deduction, induction, abduction,
analogy, causal inference, Bayesian updating, differential diagnosis, Fermi
estimation, steelmanning, falsification). These were scoped in a prior conversation
as "Family K" of a larger 60-tool brainstorm; only the first 10 (Family K) are being
implemented now, per explicit user instruction. The other 25 candidate reasoning
strategies are to be listed and explained in this reply, not implemented.

No related open PR or in-flight work touches this area; `vidbyte-sdk` is currently
clean on `main`.

---

## 4. Requirements

### Functional Requirements
1. Ten new `BaseTool` subclasses exist under `vidbyte/tools/builtins/reasoning/`,
   one file per tool: `deduce.py`, `induce.py`, `abduce.py`, `analogy.py`,
   `causal_chain.py`, `bayesian_update.py`, `differential_diagnosis.py`,
   `fermi_estimate.py`, `steelman.py`, `falsify.py`.
2. Each tool's `spec()` returns a `ToolSpec` with a detailed `description` and a
   fully-specified `parameters` tuple of `ToolParameter`s; every parameter's
   `description` states its purpose, its expected shape (plain string, JSON
   array, or `0.0`-`1.0` numeric string), and any enum constraint in prose (the SDK's
   `ToolParameter` dataclass has no native `enum` field, so constraints are
   documented and enforced in `execute()`, matching `ContextUpsertTool` /
   `DeclareOutputSchemaTool` precedent).
3. Each tool's `execute()` validates required fields, constructs the matching
   `ContextItem` dataclass, calls `self._manager.upsert(item)`, and returns
   `ToolResult.success(call.tool_name, item.to_context_text())`; a validation or
   frozen-primitive failure returns `ToolResult.error(...)` with an actionable
   message naming the offending field.
4. Each tool auto-generates its own `primitive_id` as `f"{tool_name}:{counter}"`
   via a per-instance counter — the model never supplies an ID.
5. Ten new frozen, slotted `ContextItem` dataclasses exist in a new module
   `vidbyte/context/primitives/reasoning_strategies.py`, exported from
   `vidbyte/context/primitives/__init__.py`.
6. List-shaped and object-list-shaped arguments (e.g. `premises`, `hypotheses`,
   `confounders`) accept either a native JSON array or a JSON-encoded string,
   matching the `DeclareOutputSchemaTool._normalize_fields` precedent.
7. Probability/likelihood arguments (`prior`, `posterior`, `likelihood_if_true`,
   `likelihood_if_false`, `confidence`) are passed as strings and parsed to a float
   clamped to `[0.0, 1.0]`, matching `TrajectoryCheckpointTool._parse_score`; unlike
   `score` (optional there), the Bayesian-update tool treats an unparsable required
   probability as a validation error, since those numbers are the semantic core of
   that tool rather than optional self-assessment.
8. A shared, package-private static helper class, `ReasoningToolInput`, in
   `vidbyte/tools/builtins/reasoning/_parsing.py`, centralizes the argument-parsing
   concerns reused across the 10 tool files (required-field checking, string-list
   parsing, object-list parsing, probability parsing) as `@staticmethod` methods on
   one class, per the repo's documented "class-bound helpers" convention (field-guide:
   `class-bound-helpers.md`, PR #328/#329) rather than as scattered free functions.
9. `vidbyte/tools/builtins/reasoning/__init__.py` imports and re-exports all 10 tool
   classes; `vidbyte/tools/builtins/__init__.py` imports from that subpackage and adds
   the 10 class names to its `__all__`.
10. `skills/usage/available_tools.md` gains a new "Reasoning Strategy Tools" section
    (mirroring the existing "Context Algorithm Tools" section's format) listing all
    10 tools with a one-line description each.
11. `llms.txt` gains the 10 new `ContextItem` names in its context-primitives summary
    table and the 10 new tool names in its tools summary table.

### Non-Functional Requirements
- **Determinism:** rendering (`to_context_text()`) must be pure and deterministic —
  no randomness, no wall-clock reads (consistent with every existing primitive).
- **Bounded size:** every primitive takes a `max_chars` field (default `2000`,
  matching the majority default across `checkpoints.py` / `reasoning.py` /
  `epistemics.py`) and truncates via the shared `_truncate_text` helper.
- **No I/O in `execute()`:** none of the 10 tools call an LLM, the filesystem, or the
  network — pure argument-to-primitive transforms, matching the "pure form" guidance
  in `context-algorithm-to-tool.md` Section 7.
- **Permission:** all 10 tools declare `ToolPermission.SAFE` (context-window writes
  only), matching every other context-primitive-writing tool.
- **CI:** `python scripts/run_ci.py` (source stage: bytecode-tracking check, compile
  check, `scripts/check_context_write_paths.py`, full `pytest`) must stay green. The
  new files live under `vidbyte/tools/builtins/reasoning/`, which is *not* one of
  `check_context_write_paths.py`'s `CWP001_PREFIXES`, and every write goes through the
  public `ContextManager.upsert()` method (never `_registry`/`_placements` directly),
  so the write-path check applies the same way it already does to `reflexion.py`.

---

## 5. High-Level Design

```
Primary model
   |
   |  calls e.g. deduce(premises=[...], inference_rule="modus ponens",
   |               conclusion="...", soundness_caveat="...")
   v
DeduceTool.execute(call)                     [vidbyte/tools/builtins/reasoning/deduce.py]
   |  1. ReasoningToolInput.* parses/validates the raw arguments
   |  2. builds DeductionContextItem(primitive_id=f"deduce:{n}", ...)
   |  3. self._manager.upsert(item)
   v
ContextManager                               [vidbyte/context/manager.py -- unmodified]
   |  stores the frozen primitive in its registry zone, enforces primitive_frozen
   v
DeductionContextItem.to_context_text()       [vidbyte/context/primitives/reasoning_strategies.py]
   |  renders a deterministic, bounded text block
   v
ToolResult.success(call.tool_name, rendered_text)  -> back to the model
```

Each of the other 9 tools follows the identical shape, swapping in its own
`ContextItem` subclass and field set. All 10 tool files share one private parsing
helper (`ReasoningToolInput`, `_parsing.py`) for the argument-normalization concerns
that repeat across files (list parsing, probability parsing, required-field
checking) — the class-bound-helper pattern the project's field guide documents.

No existing component (`ContextManager`, `BaseTool`, `ToolSpec`, `AgentRuntime`,
YAML `ComponentRegistry`) is modified. `ReflexionTool` and `TrajectoryCheckpointTool`
are not wired into the YAML `ComponentRegistry` either (verified: no match for
either name in `vidbyte/lib/registries/components.py`), so the new tools are not
wired in either — they are constructed directly by SDK consumers, exactly like their
two precedents.

---

## 6. Detailed Design

### 6.1 `vidbyte/context/primitives/reasoning_strategies.py` (NEW)

**File(s):** `vidbyte/context/primitives/reasoning_strategies.py`
**Type:** New file

#### What it does
Defines the 10 frozen, slotted `ContextItem` dataclasses shared between each tool and
(should one ever be added later) an algorithm-triggered form. Mirrors the structure
of `checkpoints.py` exactly.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class DeductionContextItem:
    primitive_id: str
    premises: tuple[str, ...]
    inference_rule: str
    conclusion: str
    soundness_caveat: str
    title: str = "Deductive Chain"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "deduction"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class InductionContextItem:
    primitive_id: str
    observations: tuple[str, ...]
    pattern: str
    generalization: str
    sample_bias_risk: str
    falsifying_case: str
    confidence: float | None = None
    title: str = "Inductive Generalization"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "induction"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class AbductionContextItem:
    primitive_id: str
    evidence: tuple[str, ...]
    hypotheses: tuple[Mapping[str, Any], ...]
    best: str
    discriminating_test: str
    runner_up: str | None = None
    title: str = "Abductive Inference"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "abduction"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class AnalogyContextItem:
    primitive_id: str
    source_domain: str
    target_domain: str
    mapped_relations: tuple[str, ...]
    breaks_down_at: str
    carries_weight: str
    title: str = "Analogical Transfer"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "analogy"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class CausalChainContextItem:
    primitive_id: str
    cause: str
    mechanism: str
    effect: str
    confounders: tuple[str, ...]
    intervention_test: str
    title: str = "Causal Chain"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "causal_chain"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class BayesianUpdateContextItem:
    primitive_id: str
    hypothesis: str
    prior: float
    evidence: str
    likelihood_if_true: float
    likelihood_if_false: float
    posterior: float
    shift_explanation: str
    title: str = "Bayesian Update"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "bayesian_update"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class DifferentialDiagnosisContextItem:
    primitive_id: str
    candidate_set: tuple[str, ...]
    remaining: tuple[str, ...]
    next_discriminator: str
    ruled_out: tuple[Mapping[str, Any], ...] = ()
    title: str = "Differential Diagnosis"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "differential_diagnosis"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class FermiEstimateContextItem:
    primitive_id: str
    quantity: str
    decomposition: tuple[str, ...]
    arithmetic: str
    estimate: str
    sanity_band: str
    anchor_risk: str
    title: str = "Fermi Estimate"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "fermi_estimate"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class SteelmanContextItem:
    primitive_id: str
    my_position: str
    strongest_opposition: str
    survives: str
    revision: str = ""
    title: str = "Steelman"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "steelman"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...

@dataclass(frozen=True, slots=True)
class FalsifyContextItem:
    primitive_id: str
    claim: str
    test_design: str
    riskiest_prediction: str
    status: str
    title: str = "Falsification Test"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "falsify"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...
```

#### Logic / Algorithm
Each `to_context_text()` renders its fields in a fixed, deterministic order as
labeled sections (`### Premises`, `### Conclusion`, ...), reusing
`_extend_section` from `base.py` for every `tuple[str, ...]` field (bullet list) and
inline `key: value` formatting for `tuple[Mapping[str, Any], ...]` fields
(`hypotheses`, `ruled_out`) — each mapping rendered as one bullet joining its present
keys (`hypothesis: ...; explains: ...; simplicity: ...; assumptions_required: ...`),
skipping keys the model omitted rather than erroring, since these are free-form
model-authored objects. Every render ends with
`_truncate_text(text, self.max_chars)`.

#### Edge Cases & Error Handling
- Primitives never validate their own fields (matches every other primitive in the
  package — validation is the tool's job, primitives are dumb data + a renderer).
- `runner_up` (abduction) and `ruled_out` (differential diagnosis) may be empty/None;
  their sections are omitted from the rendered text rather than printed empty.
- `confidence` (induction) may be `None`; renders as `N/A`, matching the existing
  `TrajectoryCheckpointContextItem.score` pattern exactly.

---

### 6.2 `vidbyte/tools/builtins/reasoning/_parsing.py` (NEW)

**File(s):** `vidbyte/tools/builtins/reasoning/_parsing.py`
**Type:** New file (package-private, not exported from `__init__.py`)

#### What it does
One static helper class, `ReasoningToolInput`, holding the argument-normalization
methods shared by 8+ of the 10 tool files. Applies the field-guide's class-bound-
helper convention instead of module-level free functions.

#### Interface / API
```python
class ReasoningToolInput:
    @staticmethod
    def missing_required(args: Mapping[str, Any], names: tuple[str, ...]) -> str | None: ...
    @staticmethod
    def text(args: Mapping[str, Any], key: str, default: str = "") -> str: ...
    @staticmethod
    def string_list(raw: Any) -> tuple[str, ...]: ...
    @staticmethod
    def object_list(raw: Any) -> tuple[Mapping[str, Any], ...]: ...
    @staticmethod
    def probability(raw: Any) -> float | None: ...
    @staticmethod
    def enum_error(value: str, allowed: tuple[str, ...], field_name: str) -> str | None: ...
```

#### Logic / Algorithm
- `missing_required` mirrors `ReflexionTool._validate_required_fields`, generalized
  to an arbitrary field-name tuple; returns the same
  `"Missing or empty required field: '<name>'."` message shape.
- `string_list` / `object_list` mirror `DeclareOutputSchemaTool._normalize_fields`:
  accept `None` (empty), a JSON string (parsed via `json.loads`, falling back to a
  single-element tuple on decode failure for `string_list` only), a single
  `Mapping`/string, or a `Sequence`.
- `probability` mirrors `TrajectoryCheckpointTool._parse_score`: best-effort
  `float(str(raw).strip())`, clamped to `[0.0, 1.0]`, `None` on any failure.
- `enum_error` mirrors the inline check in `ContextUpsertTool.execute()`: returns a
  formatted "Unknown `<field_name>` '<value>'. Supported: ..." message or `None`.

#### Edge Cases & Error Handling
- Never raises; every method degrades to `None` / empty tuple / error string so
  calling tools stay branch-free on the happy path.

---

### 6.3 `vidbyte/tools/builtins/reasoning/{deduce,induce,abduce,analogy,causal_chain,bayesian_update,differential_diagnosis,fermi_estimate,steelman,falsify}.py` (NEW, 10 files)

**Type:** New files, one `BaseTool` subclass each.

#### What each does
Validates arguments via `ReasoningToolInput`, builds its `ContextItem`, upserts it,
returns the rendered text — identical shape to `ReflexionTool`/
`TrajectoryCheckpointTool`, split into `spec()`, `execute()`, and 2-4 private helper
methods (`_validate`, `_next_primitive_id`, `_build_item`).

#### Interface / API (per-tool parameter tables)

**`deduce`** — class `DeduceTool`, kind `deduction`
| param | type | required | notes |
|---|---|---|---|
| `premises` | array | yes | Ordered claims assumed true for this inference; JSON array or JSON string. |
| `inference_rule` | string | yes | Named rule connecting premises to conclusion (e.g. modus ponens, contrapositive, transitivity) — naming it is what makes the deduction checkable. |
| `conclusion` | string | yes | What necessarily follows under that rule. |
| `soundness_caveat` | string | yes | Validity ≠ truth: names the single weakest/least-certain premise, or states none is doubtful. |
| `title` | string | no | Default `"Deductive Chain"`. |

**`induce`** — class `InduceTool`, kind `induction`
| param | type | required | notes |
|---|---|---|---|
| `observations` | array | yes | Concrete individual data points, not a summary. |
| `pattern` | string | yes | The raw regularity noticed, before generalizing it. |
| `generalization` | string | yes | The inductive leap projected beyond the observations. |
| `sample_bias_risk` | string | yes | How the observation set could be unrepresentative (size, self-selection, single source/time, survivorship bias). |
| `falsifying_case` | string | yes | A concrete observation that would break the generalization; if none can be named, the claim isn't falsifiable yet. |
| `confidence` | string | no | `0.0`-`1.0`; inductive conclusions are never certain, rarely above `0.9`. |

**`abduce`** — class `AbduceTool`, kind `abduction`
| param | type | required | notes |
|---|---|---|---|
| `evidence` | array | yes | Observed facts needing explanation. |
| `hypotheses` | array | yes | 2-4 objects `{hypothesis, explains, simplicity, assumptions_required}`; genuine competitors, not one idea plus strawmen — `execute()` errors if fewer than 2 parse. |
| `best` | string | yes | Which hypothesis wins, chosen for explanatory power *and* simplicity. |
| `discriminating_test` | string | yes | What would distinguish `best` from the runner-up if evidence is ambiguous between them. |
| `runner_up` | string | no | Second-best hypothesis and why it lost. |

**`analogy`** — class `AnalogyTool`, kind `analogy`
| param | type | required | notes |
|---|---|---|---|
| `source_domain` | string | yes | The familiar thing being reasoned from. |
| `target_domain` | string | yes | The unfamiliar thing being reasoned to. |
| `mapped_relations` | array | yes | Specific "X in source corresponds to Y in target" correspondences — vague resemblance is not enough. |
| `breaks_down_at` | string | yes | Where source and target diverge; mandatory because unlimited analogies justify anything. |
| `carries_weight` | string | yes | Enum `explains_only \| justifies_action`; validated, error on other values. |

**`causal_chain`** — class `CausalChainTool`, kind `causal_chain`
| param | type | required | notes |
|---|---|---|---|
| `cause` | string | yes | Proposed causal factor. |
| `mechanism` | string | yes | Step-by-step causal pathway — "no mechanism, no causation." |
| `effect` | string | yes | The claimed outcome, stated measurably. |
| `confounders` | array | yes | Other variables that could produce the same correlation without real causation; state explicitly if none are plausible. |
| `intervention_test` | string | yes | The experiment/perturbation that would confirm the mechanism versus mere correlation. |

**`bayesian_update`** — class `BayesianUpdateTool`, kind `bayesian_update`
| param | type | required | notes |
|---|---|---|---|
| `hypothesis` | string | yes | The belief whose probability is being updated. |
| `prior` | string | yes | `P(hypothesis)` before the evidence, `0.0`-`1.0`; unparsable value is a validation error (core content, not optional). |
| `evidence` | string | yes | The new observation triggering the update. |
| `likelihood_if_true` | string | yes | `P(evidence \| hypothesis true)`, `0.0`-`1.0`. |
| `likelihood_if_false` | string | yes | `P(evidence \| hypothesis false)`, `0.0`-`1.0`; the gap to `likelihood_if_true` is what does the updating. |
| `posterior` | string | yes | `P(hypothesis)` after the evidence, `0.0`-`1.0`. |
| `shift_explanation` | string | yes | Plain-language account of why the posterior moved the amount it did. |

**`differential_diagnosis`** — class `DifferentialDiagnosisTool`, kind `differential_diagnosis`
| param | type | required | notes |
|---|---|---|---|
| `candidate_set` | array | yes | Full initial list of plausible candidates, cast wide. |
| `remaining` | array | yes | Candidates from `candidate_set` still consistent with all evidence. |
| `next_discriminator` | string | yes | The next check that best splits the remaining candidates, not merely confirms the leading one. |
| `ruled_out` | array | no | Objects `{candidate, ruled_out_by}`; only candidates a concrete observation contradicts, not ones merely "less likely." |

**`fermi_estimate`** — class `FermiEstimateTool`, kind `fermi_estimate`
| param | type | required | notes |
|---|---|---|---|
| `quantity` | string | yes | The unknown quantity, with units. |
| `decomposition` | array | yes | Factored sub-estimates — the core Fermi move: guess the inputs, never the answer directly. |
| `arithmetic` | string | yes | How the factors combine, shown explicitly. |
| `estimate` | string | yes | Resulting point estimate, with units. |
| `sanity_band` | string | yes | Order-of-magnitude range to catch a 10x-off estimate. |
| `anchor_risk` | string | yes | Enum `none \| anchored_low \| anchored_high`; validated. |

**`steelman`** — class `SteelmanTool`, kind `steelman`
| param | type | required | notes |
|---|---|---|---|
| `my_position` | string | yes | Current claim/plan, stated falsifiably. |
| `strongest_opposition` | string | yes | Best case against it, built as carefully as `my_position` itself. |
| `survives` | string | yes | Enum `yes \| no \| weakened`; validated. |
| `revision` | string | no (conditionally required) | `execute()` errors if `survives != "yes"` and `revision` is empty — the position must actually change when it loses or is weakened. |

**`falsify`** — class `FalsifyTool`, kind `falsify`
| param | type | required | notes |
|---|---|---|---|
| `claim` | string | yes | Precise enough that some observation could contradict it. |
| `test_design` | string | yes | Designed to fail if `claim` is false, not merely to confirm it. |
| `riskiest_prediction` | string | yes | The boldest consequence `claim` forbids — a claim that forbids nothing risky is barely a claim. |
| `status` | string | yes | Enum `falsified \| survived \| untested`; validated. `untested` is the default posture for a designed-but-not-run test. |

#### Logic / Algorithm (shared shape across all 10)
1. `execute()` copies `call.arguments` into a plain `dict`.
2. Calls the tool's `_validate(args)`, which uses `ReasoningToolInput.missing_required`
   for required scalar fields, plus any tool-specific cross-field or enum rule
   (abduction's ≥2-hypotheses rule; steelman's conditional-revision rule; the enum
   checks on `carries_weight` / `anchor_risk` / `survives` / `status`; the
   required-and-must-parse rule on the four Bayesian probability fields). Returns an
   error string or `None`.
3. On error, returns `ToolResult.error(call.tool_name, message)` immediately.
4. Increments `self._counter`, builds `primitive_id = f"{tool_name}:{self._counter}"`.
5. Builds the `ContextItem` via `_build_item(args, primitive_id)`, using
   `ReasoningToolInput.text` / `.string_list` / `.object_list` / `.probability` to
   coerce each field.
6. Calls `self._manager.upsert(item)`; catches `ValueError` (frozen primitive) and
   returns `ToolResult.error`.
7. Returns `ToolResult.success(call.tool_name, item.to_context_text())`.

#### Edge Cases & Error Handling
- Missing/empty required string field -> `ToolResult.error` naming the field.
- Fewer than 2 parsed `hypotheses` objects in `abduce` -> `ToolResult.error`.
- Invalid enum value (`carries_weight`, `anchor_risk`, `survives`, `status`) ->
  `ToolResult.error` naming the field, the bad value, and the allowed set.
- `survives in {"no", "weakened"}` with empty `revision` in `steelman` ->
  `ToolResult.error`.
- Unparsable/missing probability field in `bayesian_update` -> `ToolResult.error`
  naming the field (deliberately stricter than the optional, silently-`None`
  `score` field on `TrajectoryCheckpointTool`, since these numbers are this tool's
  entire point).
- Frozen primitive at the same `primitive_id` (only possible if a caller pre-seeded
  the manager, since IDs are auto-generated per counter) -> `ToolResult.error`,
  matching `ReflexionTool`.

---

### 6.4 `vidbyte/tools/builtins/reasoning/__init__.py` (NEW)

**File(s):** `vidbyte/tools/builtins/reasoning/__init__.py`
**Type:** New file

#### What it does
Re-exports the 10 tool classes as the package's public surface, matching the shape
of `vidbyte/tools/builtins/context_primitives/__init__.py`. Does **not** export
`ReasoningToolInput` (package-private).

#### Interface / API
```python
from vidbyte.tools.builtins.reasoning.abduce import AbduceTool
from vidbyte.tools.builtins.reasoning.analogy import AnalogyTool
from vidbyte.tools.builtins.reasoning.bayesian_update import BayesianUpdateTool
from vidbyte.tools.builtins.reasoning.causal_chain import CausalChainTool
from vidbyte.tools.builtins.reasoning.deduce import DeduceTool
from vidbyte.tools.builtins.reasoning.differential_diagnosis import DifferentialDiagnosisTool
from vidbyte.tools.builtins.reasoning.falsify import FalsifyTool
from vidbyte.tools.builtins.reasoning.fermi_estimate import FermiEstimateTool
from vidbyte.tools.builtins.reasoning.induce import InduceTool
from vidbyte.tools.builtins.reasoning.steelman import SteelmanTool

__all__ = [
    "AbduceTool", "AnalogyTool", "BayesianUpdateTool", "CausalChainTool",
    "DeduceTool", "DifferentialDiagnosisTool", "FalsifyTool", "FermiEstimateTool",
    "InduceTool", "SteelmanTool",
]
```

---

### 6.5 `vidbyte/tools/builtins/__init__.py` (MODIFIED)

**File(s):** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

#### What it does
Adds one import line (`from vidbyte.tools.builtins.reasoning import (...)`) and the
10 new class names to `__all__`, alongside the existing `ReflexionTool` /
`TrajectoryCheckpointTool` entries. Module docstring's `Architecture:` bullet list
gets one new line noting the reasoning-strategy family.

---

### 6.6 `vidbyte/context/primitives/__init__.py` (MODIFIED)

**File(s):** `vidbyte/context/primitives/__init__.py`
**Type:** Modified

#### What it does
Adds one import line pulling all 10 new `ContextItem` classes from
`reasoning_strategies.py`, and inserts their names into the alphabetized `__all__`
list, matching the existing pattern exactly.

---

### 6.7 `vidbyte/context/primitives/README.md` (MODIFIED)

Adds one bullet to the file index:
`- \`reasoning_strategies.py\` - deduction, induction, abduction, analogy, causal-chain, Bayesian-update, differential-diagnosis, Fermi-estimate, steelman, and falsification primitives.`

---

### 6.8 `skills/usage/available_tools.md` (MODIFIED)

Adds a new `## Reasoning Strategy Tools` section immediately after the existing
`## Context Algorithm Tools` section, following that section's exact format
(intro paragraph, import block, `| Tool | Description |` table), listing all 10
tools with a one-line description drawn from their `ToolSpec.description`.

---

### 6.9 `llms.txt` (MODIFIED)

Two existing summary tables get the 10 new names appended:
- The context-items row (~line 770, "Tasks and reasoning") gains the 10 new
  `ContextItem` class names.
- The tools row (~line 802, "Context and reflection") gains the 10 new tool class
  names.

---

## 7. Data Model Changes

N/A - no database/schema changes. The only "data model" additions are the 10 new
in-process, frozen `dataclass` `ContextItem` types described in Section 6.1; they are
not persisted outside the in-memory `ContextManager` registry, same as every existing
primitive.

---

## 8. API Changes

N/A - this is a Python SDK library change (new importable classes), not a network
API. No HTTP endpoints are added or modified. The "API" surface added is the 10 new
tool names now callable by any model wired to a `ContextManager`-backed agent:
`deduce`, `induce`, `abduce`, `analogy`, `causal_chain`, `bayesian_update`,
`differential_diagnosis`, `fermi_estimate`, `steelman`, `falsify` (documented fully
in Section 6.3's parameter tables).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/context/primitives/reasoning_strategies.py` | 10 new `ContextItem` dataclasses |
| MODIFY | `vidbyte/context/primitives/__init__.py` | export the 10 new primitives |
| MODIFY | `vidbyte/context/primitives/README.md` | file index entry |
| CREATE | `vidbyte/tools/builtins/reasoning/_parsing.py` | shared `ReasoningToolInput` static helper class |
| CREATE | `vidbyte/tools/builtins/reasoning/deduce.py` | `DeduceTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/induce.py` | `InduceTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/abduce.py` | `AbduceTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/analogy.py` | `AnalogyTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/causal_chain.py` | `CausalChainTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/bayesian_update.py` | `BayesianUpdateTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/differential_diagnosis.py` | `DifferentialDiagnosisTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/fermi_estimate.py` | `FermiEstimateTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/steelman.py` | `SteelmanTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/falsify.py` | `FalsifyTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/__init__.py` | package export surface |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | import + `__all__` for the 10 new tools |
| MODIFY | `skills/usage/available_tools.md` | new "Reasoning Strategy Tools" doc section |
| MODIFY | `llms.txt` | append to the two builtin-catalog summary tables |

13 files created, 5 files modified.

---

## 10. Dependencies & External Services

None. Pure stdlib (`dataclasses`, `json`, `typing`) plus existing SDK internals
(`vidbyte.tools.base.BaseTool`, `vidbyte.tools.types.*`,
`vidbyte.context.manager.ContextManager`, `vidbyte.context.primitives.base`).

---

## 11. Rollout & Deployment

- No feature flag — matches `ReflexionTool`/`TrajectoryCheckpointTool`, which ship
  unconditionally as opt-in-by-import tools; a developer must explicitly construct
  and attach them to an agent's toolset for them to be callable.
- Purely additive: no existing class, function, or exported name changes shape or
  behavior. Not a breaking change.
- No deployment ordering concerns (single-repo Python package change, standard PR
  flow to `main`).
- Rollback: revert the PR; nothing else depends on the new names within this change.

---

## 12. Open Questions

- [ ] Should `ReflexionTool`/`ReflexionContextItem`'s missing top-level
  `vidbyte/__init__.py` re-export be treated as a pre-existing gap worth fixing in a
  follow-up, now that a second (much larger) family of tools follows the same
  non-re-exported pattern? Left as-is here to keep this change's surface equivalent
  to its closest precedent; flagged for a possible separate follow-up PR.
- [ ] Should the remaining 25 reasoning strategies (to be listed in the chat reply,
  not this PR) eventually become "Family K, batch 2"? No code implication now; the
  file layout (`vidbyte/tools/builtins/reasoning/`, one file per tool) already scales
  to additional tools without restructuring.

---

## 13. Alternatives Considered

### Alternative 1: One flat file with all 10 tool classes
- What: put all 10 `BaseTool` subclasses in a single
  `vidbyte/tools/builtins/reasoning_strategies.py`, mirroring `epistemics.py`'s
  multi-class-per-file primitive style.
- Why rejected: the established *tool* convention (as opposed to primitive-module
  convention) is one file per tool class (`reflexion.py`, `trajectory_checkpoint.py`,
  and every file under `context_primitives/`). `context-algorithm-to-tool.md`
  Section 6 states this explicitly: "One file per tool. Follow the naming of
  existing builtins." Ten tools in one file would also make the per-tool parameter
  richness the user asked for much harder to scan in review.

### Alternative 2: Duplicate the parsing helpers per-file (no shared class)
- What: copy a `_validate_required_fields`/`_parse_*` set into each of the 10 files,
  exactly as `reflexion.py` and `trajectory_checkpoint.py` each do independently
  today for their two small helpers.
- Why rejected: those two existing files only duplicate ~10 lines each of trivial
  logic. Our 10 files share 4 non-trivial parsing concerns (JSON list parsing,
  JSON object-list parsing, probability parsing, enum validation) that would mean
  ~40+ duplicated lines repeated up to 8 times. The field guide's
  `class-bound-helpers.md` entry (learned from PR #328 review feedback) directly
  covers this shape: "several related free functions that share one concern... put
  the public surface and private helpers on one class." A private
  `ReasoningToolInput` static-method class is the documented resolution.

### Alternative 3: Add algorithm-triggered counterparts too
- What: also ship `DeductionAlgorithm`, etc., so a runtime could inject these
  reasoning notes on a fixed cadence, mirroring `TrajectoryCheckpointAlgorithm`.
- Why rejected: explicitly out of scope per the user's request (tools only). It is
  also not obviously meaningful for most of these — a secondary summarizer LLM
  "deciding" what the primary model's premises or Bayesian prior should have been
  doesn't fit the pattern the way checkpoint/reflexion summarization does. Left as a
  possible future direction, not attempted here.

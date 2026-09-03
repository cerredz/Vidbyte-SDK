# Design Doc: Reasoning Strategy Tools Batch 2 (Family K, tools 11-35)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-19
**Last Updated:** 2026-08-19

---

## 1. Overview

This change adds twenty-five new model-callable prebuilt tools to the Vidbyte SDK,
extending the "Reasoning Strategies" family (Family K) that PR #343 introduced with
its first ten tools (`deduce`, `induce`, `abduce`, `analogy`, `causal_chain`,
`bayesian_update`, `differential_diagnosis`, `fermi_estimate`, `steelman`,
`falsify`).

Batch 2 anchors each tool to a named inference pattern from formal logic,
epistemology, and argumentation theory — the foundational moves a reasoner actually
performs: disproof by counterexample, consistency auditing, proof by exhaustive
cases, quantifier-scope analysis, transitivity chains, identity criteria, partition
checking, modality, equivocation detection, necessary/sufficient conditions,
composition/division fallacies, circularity detection, justification regress,
burden of proof, testimony evaluation, absence-of-evidence inference, defeasible
reasoning, statistical syllogisms, Socratic elenchus, dialectic, paradox dissection,
strawman auditing, deductive-nomological prediction, thought experiments, and
universal instantiation. The two tools the user explicitly named — `dialectic` and
`paradox` — carry extra cross-field validation rigor (Section 6.3.20 / 6.3.21).

Every tool follows the exact house pattern established in PR #343 and mirrored from
`ReflexionTool`/`TrajectoryCheckpointTool`: constructor-injected `ContextManager`,
per-instance primitive-ID counter, required-field validation before construction,
`_manager.upsert(item)`, and `item.to_context_text()` returned as `ToolResult.output`
so the model can observe exactly what was recorded.

The family carries a deliberate **maximum-extraction / maximum-observability bias**:
nearly every parameter is required; every tool ends in an explicit commitment/enum
field that forces a position rather than a hedge; and every parameter description
states its purpose, its expected shape, what a vague value looks like, and why it
cannot be skipped. Parameter descriptions are the moat — the schema is the leverage.

---

## 2. Goals & Non-Goals

### Goals
- Implement 25 additional Reasoning Strategy tools (`counterexample`, `consistency`,
  `dilemma`, `quantifier`, `transitivity`, `identity`, `partition`, `modal`,
  `equivocation`, `necessary_sufficient`, `composition_division`, `circularity`,
  `regress`, `burden_of_proof`, `testimony`, `absence_evidence`, `defeasible`,
  `statistical_syllogism`, `socratic`, `dialectic`, `paradox`, `strawman`,
  `predict`, `thought_experiment`, `instantiate`) as builtin SDK tools, stacked
  directly on top of PR #343's `feat/reasoning-strategy-tools` branch.
- Follow the exact PR #343 house pattern: one `BaseTool` subclass per file in
  `vidbyte/tools/builtins/reasoning/`, one frozen `ContextItem` per tool appended to
  `vidbyte/context/primitives/reasoning_strategies.py`, shared parsing via the
  existing `ReasoningToolInput` static helper class, `ToolPermission.SAFE`.
- Bias every tool toward **maximum extraction** (rich required fields; descriptions
  that set the quality bar per value) and **maximum observability** (every tool
  returns its rendered `ContextItem` text, writes a frozen primitive into the
  `ContextManager`, and ends in an explicit commitment/enum field).
- Implement `dialectic` and `paradox` with extra cross-field validation: `antithesis`
  must differ from `thesis`; `premise_to_drop` must name one of the stated premises.
- Keep the 25 tools individually importable from `vidbyte.tools.builtins.reasoning`
  and collectively re-exported from `vidbyte.tools.builtins`.
- Update catalog docs (`skills/usage/available_tools.md`, `llms.txt`,
  `vidbyte/context/primitives/README.md`) so the expanded family is discoverable.

### Non-Goals
- No algorithm-triggered counterparts (no `CounterexampleAlgorithm`, etc.) — same
  stance as PR #343: pure tool-form primitives, no `InnerContextWindowAlgorithm`
  equivalent.
- No new test files. Per the `design-doc-no-tests` workflow, existing tests must
  pass unmodified; the new files are verified by CI plus an ad-hoc smoke script that
  is deleted before commit.
- No changes to `vidbyte/__init__.py` or `vidbyte/context/__init__.py` top-level
  re-exports — same (deliberately matched) gap as `ReflexionTool` and the 10 PR #343
  tools.
- No changes to `_parsing.py` — the existing six static methods cover every parsing
  need of the 25 new tools.
- No changes to `ContextManager`, `BaseTool`, `ToolSpec`, `AgentRuntime`, or the YAML
  `ComponentRegistry`.
- The "abstract thinking and thinking in systems" strategies are out of scope for
  implementation — proposed in the chat handoff as a future batch, mirroring how
  PR #343 handled the then-remaining 25.
- No convenience "mount all 35 at once" factory — standalone construction holds.

---

## 3. Background & Context

PR #343 shipped Family K tools 1-10 and established the house style: a `BaseTool`
subclass per file, a frozen `ContextItem` per tool, shared parsing through the
package-private `ReasoningToolInput` class in `_parsing.py` (per the field guide's
`class-bound-helpers.md` convention from PR #328), enum validation in `execute()`,
deterministic bounded rendering, and `ToolPermission.SAFE`.

PR #343's chat reply listed 25 further candidate strategies (not implemented). The
user reviewed a revised set of 25 proposals grounded in formal logic, epistemology,
and argumentation — rejecting domain frameworks and heuristics as "not actually
reasoning methods" — explicitly named `dialectic` and `paradox` as required, and
asked for a bias toward maximum extraction and observability from the model.

The `reasoning/` package layout (one file per tool) scales without restructuring;
this PR adds 25 files to the same package and 25 dataclasses to the same primitives
module. `feat/reasoning-strategy-tools` is currently a green draft PR (#343) that is
unmerged, so this branch stacks directly on its head and targets it as the PR base
(Section 11).

Field-guide constraints applied: `class-bound-helpers.md` (already satisfied by
`ReasoningToolInput` — no new free functions); `local-ci-verification.md` (worktree
CI: source stage with `PYTHONPATH` set to the worktree, package stage without it).

---

## 4. Requirements

### Functional Requirements
1. Twenty-five new `BaseTool` subclasses exist under `vidbyte/tools/builtins/reasoning/`,
   one file per tool: `counterexample.py`, `consistency.py`, `dilemma.py`,
   `quantifier.py`, `transitivity.py`, `identity.py`, `partition.py`, `modal.py`,
   `equivocation.py`, `necessary_sufficient.py`, `composition_division.py`,
   `circularity.py`, `regress.py`, `burden_of_proof.py`, `testimony.py`,
   `absence_evidence.py`, `defeasible.py`, `statistical_syllogism.py`, `socratic.py`,
   `dialectic.py`, `paradox.py`, `strawman.py`, `predict.py`,
   `thought_experiment.py`, `instantiate.py`.
2. Each tool's `spec()` returns a `ToolSpec` with a rich `description` (what the
   strategy is, when to use it, what the tool forces) and fully-specified
   `parameters`. Every parameter description states: purpose, expected shape (plain
   string / JSON array / JSON object-list / `0.0`-`1.0` numeric string), the quality
   bar (what a vague value looks like), and why it cannot be skipped.
3. Each tool's `execute()` validates via `ReasoningToolInput`, builds its
   `ContextItem`, calls `self._manager.upsert(item)`, and returns
   `ToolResult.success(call.tool_name, item.to_context_text())`; validation or
   frozen-primitive failure returns `ToolResult.error(...)` naming the field.
4. Each tool auto-generates `primitive_id` as `f"{tool_name}:{self._counter}"`.
5. Twenty-five new frozen, slotted `ContextItem` dataclasses are appended to
   `vidbyte/context/primitives/reasoning_strategies.py` and exported from
   `vidbyte/context/primitives/__init__.py`.
6. Object-list fields (e.g. `pairwise_conflicts`, `case_reasoning`,
   `membership_rules`, `occurrences`, `dependency_map`, `reliability_factors`,
   `defeaters`, `conditions_met`) accept a native JSON array or a JSON-encoded
   string via `ReasoningToolInput.object_list`, matching the PR #343 precedent.
7. Probability fields (`frequency`, `confidence`) parse via
   `ReasoningToolInput.probability`; `frequency` is required and must parse (like
   `bayesian_update`'s probability fields), `confidence` is optional and may be
   `None`.
8. Enum fields validate against a fixed allowed tuple via
   `ReasoningToolInput.enum_error`, returning an error naming the field, the bad
   value, and the allowed set.
9. Cross-field validation rules (extra rigor per tool):
   - `consistency`: at least 2 `claims`.
   - `dilemma`: at least 2 `alternatives`.
   - `equivocation`: at least 2 `senses`.
   - `paradox`: at least 2 `premises`; `premise_to_drop` must exactly match one of
     the stated `premises` (case-sensitive trimmed comparison).
   - `dialectic`: `antithesis` must differ from `thesis` (case-insensitive trimmed
     comparison) — a self-contradictory antithesis is a validation error.
10. `vidbyte/tools/builtins/reasoning/__init__.py` re-exports all 25 new tool
    classes; `vidbyte/tools/builtins/__init__.py` imports them and extends `__all__`;
    `vidbyte/context/primitives/__init__.py` adds the 25 new `ContextItem` names to
    its alphabetized `__all__`.
11. `skills/usage/available_tools.md` extends the "Reasoning Strategy Tools" section
    (import block + table) with all 25 tools; `llms.txt` extends both summary
    tables; `vidbyte/context/primitives/README.md` extends the
    `reasoning_strategies.py` bullet.

### Non-Functional Requirements
- **Determinism:** rendering (`to_context_text()`) is pure — no randomness, no
  wall-clock reads.
- **Bounded size:** every primitive keeps `max_chars` (default `2000`) and truncates
  via the shared `_truncate_text` helper.
- **No I/O in `execute()`:** no LLM, filesystem, or network calls.
- **Permission:** all 25 tools declare `ToolPermission.SAFE`.
- **Maximum extraction:** only `title` (and `statistical_syllogism.confidence`) are
  optional across the family; everything else is required.
- **Maximum observability:** every tool returns the rendered primitive text; every
  tool ends with a commitment field (enum or required conclusion field).
- **CI:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then
  `python scripts/run_ci.py --stage package` (no `PYTHONPATH`), then full
  `python scripts/run_ci.py` (per `local-ci-verification.md`). New files live under
  `vidbyte/tools/builtins/reasoning/`, which is not in `CWP001_PREFIXES`, and every
  write goes through the public `ContextManager.upsert()`.

---

## 5. High-Level Design

```
Primary model
   |
   |  calls e.g. paradox(paradox=..., premises=[...], hidden_assumption=...,
   |              premise_to_drop=..., resolution=..., what_it_reveals=...)
   v
ParadoxTool.execute(call)                    [vidbyte/tools/builtins/reasoning/paradox.py]
   |  1. ReasoningToolInput.* parses/validates raw arguments
   |  2. cross-field checks (premises >= 2, premise_to_drop in premises)
   |  3. builds ParadoxContextItem(primitive_id=f"paradox:{n}", ...)
   |  4. self._manager.upsert(item)
   v
ContextManager                               [vidbyte/context/manager.py -- unmodified]
   |  stores the frozen primitive, enforces primitive_frozen
   v
ParadoxContextItem.to_context_text()         [vidbyte/context/primitives/reasoning_strategies.py]
   |  renders a deterministic, bounded text block
   v
ToolResult.success(call.tool_name, rendered_text)  -> back to the model
```

All 24 other tools follow the identical shape. The two structural additions over
PR #343 are: (a) 25 new frozen dataclasses appended to the existing
`reasoning_strategies.py` module (multi-primitive modules are the norm, cf.
`checkpoints.py`), and (b) `_validate` methods that combine `ReasoningToolInput`
with per-tool membership/arity rules. `_parsing.py` itself is untouched.

**Extraction / observability stance** — realized through four uniform mechanisms:
1. **Required-first schemas.** Only `title` (cosmetic) and `confidence` (genuinely
   optional self-assessment) are optional. "Why" fields (`grounds`, `reasoning`,
   `residual_uncertainty`, `what_it_reveals`) block hand-waving.
2. **Commitment fields.** 18 enum fields across the family force a verdict:
   `consistency_status`, `quantifier`, `verdict` (on quantifier/identity/partition/
   circularity/necessary_sufficient/burden_of_proof), `consistency` (transitivity),
   `modal_status`, `fallacy_present`, `validity`, `style`, `trust_verdict`,
   `significance`, `rule_applies`, `match`, `criticism_applies`.
3. **Quality-bar descriptions.** Each parameter description names its expected shape
   and states what an insufficient value looks like (e.g. `constructed_case`: "a
   vague 'there might be a case' is not a counterexample"), so the description does
   the extraction work.
4. **Observable round-trip.** Every tool returns `item.to_context_text()`, so the
   model sees the frozen record it just wrote; the record persists in the
   `ContextManager` for the rest of the run.

---

## 6. Detailed Design

### 6.1 `vidbyte/context/primitives/reasoning_strategies.py` (MODIFIED — append 25 dataclasses)

**File(s):** `vidbyte/context/primitives/reasoning_strategies.py`
**Type:** Modified

#### What it does
Gains 25 frozen, slotted `ContextItem` dataclasses in the existing shape
(`primitive_id`, fields, `title` default, `max_chars=2000`, `metadata`, `kind`,
`primitive_frozen`, `to_context_text()`). Module docstring's `Architecture:` list is
extended; `__all__` grows to 35 names. Object-list rendering reuses the existing
`_render_object_bullets` helper with new module-level key tuples.

#### New dataclasses (render order = field order)
1. `CounterexampleContextItem` — kind `counterexample`, title `"Counterexample"`.
   Fields: `claim`, `intended_scope`, `constructed_case`, `violated_condition`,
   `generalizes`, `refined_claim`.
2. `ConsistencyContextItem` — kind `consistency`, title `"Consistency Audit"`.
   Fields: `claims`, `pairwise_conflicts` (objects), `consistency_status`, `resolution`.
3. `DilemmaContextItem` — kind `dilemma`, title `"Proof by Cases"`. Fields:
   `alternatives`, `case_reasoning` (objects), `conclusion`, `exhaustiveness`.
4. `QuantifierContextItem` — kind `quantifier`, title `"Quantifier Analysis"`.
   Fields: `claim`, `quantifier`, `instance_checked`, `counterexample`,
   `scope_restriction`, `verdict`.
5. `TransitivityContextItem` — kind `transitivity`, title `"Transitive Chain"`.
   Fields: `entities`, `relation`, `pairwise_links` (objects), `derived_chain`,
   `cycle_detected`, `consistency`.
6. `IdentityContextItem` — kind `identity`, title `"Identity Check"`. Fields:
   `entity_a`, `entity_b`, `shared_properties`, `distinguishing_property`, `grounds`,
   `verdict`.
7. `PartitionContextItem` — kind `partition`, title `"Partition Check"`. Fields:
   `items`, `categories`, `membership_rules` (objects), `coverage`, `overlap`,
   `verdict`.
8. `ModalContextItem` — kind `modal`, title `"Modal Analysis"`. Fields: `claim`,
   `modal_status`, `possible_world_evidence`, `actuality`, `reasoning`.
9. `EquivocationContextItem` — kind `equivocation`, title `"Equivocation Audit"`.
   Fields: `term`, `senses`, `occurrences` (objects), `drift`, `corrected_argument`,
   `fallacy_present`.
10. `NecessarySufficientContextItem` — kind `necessary_sufficient`,
    title `"Condition Analysis"`. Fields: `condition`, `target`,
    `necessity_direction`, `sufficiency_direction`, `verdict`, `implications`.
11. `CompositionDivisionContextItem` — kind `composition_division`,
    title `"Part-Whole Check"`. Fields: `parts`, `whole`, `property`,
    `aggregation_claim`, `validity`, `counterexample`.
12. `CircularityContextItem` — kind `circularity`, title `"Circularity Audit"`.
    Fields: `argument`, `premises`, `conclusion`, `dependency_map` (objects),
    `circle_found`, `fix`, `verdict`.
13. `RegressContextItem` — kind `regress`, title `"Justification Regress"`. Fields:
    `claim`, `justification_chain`, `terminates_at`, `style`, `adequacy`.
14. `BurdenOfProofContextItem` — kind `burden_of_proof`, title `"Burden of Proof"`.
    Fields: `claim`, `default_presumption`, `supporting_evidence`,
    `opposing_evidence`, `burden_holder`, `verdict`, `decision`.
15. `TestimonyContextItem` — kind `testimony`, title `"Testimony Evaluation"`.
    Fields: `source`, `claim`, `reliability_factors` (objects), `corroboration`,
    `conflicts`, `trust_verdict`, `residual_uncertainty`.
16. `AbsenceEvidenceContextItem` — kind `absence_evidence`, title `"Absence of Evidence"`.
    Fields: `hypothesis`, `expected_evidence_if_true`, `search_conducted`,
    `search_adequacy`, `significance`, `conclusion`.
17. `DefeasibleContextItem` — kind `defeasible`, title `"Defeasible Reasoning"`.
    Fields: `default_rule`, `case`, `rule_applies`, `defeaters` (objects),
    `final_conclusion`, `retraction_note`.
18. `StatisticalSyllogismContextItem` — kind `statistical_syllogism`,
    title `"Statistical Syllogism"`. Fields: `population_claim`, `frequency`,
    `individual`, `membership`, `defeater`, `probable_conclusion`,
    `confidence: float | None = None`.
19. `SocraticContextItem` — kind `socratic`, title `"Socratic Elenchus"`. Fields:
    `claim`, `probing_question`, `assumption_surfaced`, `contradiction_found`,
    `revised_claim`, `depth_reached`.
20. `DialecticContextItem` — kind `dialectic`, title `"Dialectic"`. Fields: `thesis`,
    `antithesis`, `synthesis`, `preserved_insight`, `discarded_insight`,
    `synthesis_stability`.
21. `ParadoxContextItem` — kind `paradox`, title `"Paradox Dissection"`. Fields:
    `paradox`, `premises`, `hidden_assumption`, `premise_to_drop`, `resolution`,
    `what_it_reveals`.
22. `StrawmanContextItem` — kind `strawman`, title `"Strawman Audit"`. Fields:
    `original_argument`, `restated_argument`, `distortion`, `fair_restatement`,
    `criticism_applies`, `residual_critique`.
23. `PredictContextItem` — kind `predict`, title `"Deductive-Nomological Prediction"`.
    Fields: `theory`, `initial_conditions`, `derived_prediction`, `observed_outcome`,
    `match`, `revision`.
24. `ThoughtExperimentContextItem` — kind `thought_experiment`,
    title `"Thought Experiment"`. Fields: `setup`, `manipulation`, `predicted_outcome`,
    `insight`, `limits`.
25. `InstantiateContextItem` — kind `instantiate`, title `"Instantiation"`. Fields:
    `general_rule`, `case`, `applicability_conditions`, `conditions_met` (objects),
    `derived_conclusion`, `scope_check`.

#### Edge Cases & Error Handling
- Primitives never validate their own fields (validation is the tool's job —
  primitives are dumb data plus a renderer), matching every existing primitive.
- Optional/None fields (`confidence`) render as `N/A`, matching
  `TrajectoryCheckpointContextItem.score`.
- Object-bullet rendering skips absent keys (existing `_render_object_bullets`
  behavior); each new key tuple only includes keys the model is told to supply.

---

### 6.2 `vidbyte/tools/builtins/reasoning/_parsing.py` (UNMODIFIED)

No changes. `ReasoningToolInput` already covers: required-field checking
(`missing_required`), text coercion (`text`), string lists (`string_list`), object
lists (`object_list`), clamped probabilities (`probability`), and enum errors
(`enum_error`). All 25 tools use only these six methods.

---

### 6.3 `vidbyte/tools/builtins/reasoning/{25 files}.py` (NEW)

**Type:** New files, one `BaseTool` subclass each.

#### What each does
Identical shape to the PR #343 tools: `spec()` returns a rich `ToolSpec`;
`execute()` validates, increments the counter, builds the item, upserts, returns
rendered text; `_validate(args)` runs `ReasoningToolInput` checks plus tool-specific
cross-field rules; `_build_item(args, primitive_id)` constructs the `ContextItem`.
Each file carries the Context Protocol Header (Description / Purpose / Architecture
/ Relations), the same import set, `_REQUIRED_FIELDS` / enum-value module constants,
and `ToolPermission.SAFE`. Every parameter description is written in the PR #343
style: purpose, shape, quality bar, and why it cannot be skipped.

#### Per-tool parameter tables and validation rules

**`counterexample`** — `CounterexampleTool`, kind `counterexample`
| param | type | req | notes |
|---|---|---|---|
| `claim` | string | yes | The general/universal claim under attack, stated so a single case could break it. |
| `intended_scope` | string | yes | The domain the claim governs; a counterexample outside scope does not count. |
| `constructed_case` | string | yes | A concrete, fully-specified case inside `intended_scope` that violates `claim` — "there might be a case" is not one. |
| `violated_condition` | string | yes | Exactly which part of `claim` the case breaks. |
| `generalizes` | string | yes | Whether the failure is structural (many such cases) or an isolated exception. |
| `refined_claim` | string | yes | The corrected claim that survives the case; may be "claim is false as stated". |

Validation: `missing_required` on all six fields.

**`consistency`** — `ConsistencyTool`, kind `consistency`
| param | type | req | notes |
|---|---|---|---|
| `claims` | array | yes | The belief set under audit, each claim stated singly; at least two — a one-claim set cannot be inconsistent. |
| `pairwise_conflicts` | array | yes | Objects `{claim_a, claim_b, conflict}` — concrete pairs where both cannot hold, contradiction spelled out. |
| `consistency_status` | string | yes | Enum `consistent \| contradictory \| unresolved`. |
| `resolution` | string | yes | Which claim must yield (or what evidence would decide) and why. |

Validation: `missing_required`; `string_list(claims)` >= 2; `enum_error` on `consistency_status`.

**`dilemma`** — `DilemmaTool`, kind `dilemma`
| param | type | req | notes |
|---|---|---|---|
| `alternatives` | array | yes | Exhaustive set of cases/branches; at least two — a one-branch dilemma is a monologue. |
| `case_reasoning` | array | yes | Objects `{case, leads_to}` — one per alternative, the argument from that branch to the shared conclusion. |
| `conclusion` | string | yes | What follows in every branch; if branches land differently, state the split. |
| `exhaustiveness` | string | yes | Why no further branch exists — the exclusion argument is what makes this a proof. |

Validation: `missing_required`; `string_list(alternatives)` >= 2; `object_list(case_reasoning)` non-empty.

**`quantifier`** — `QuantifierTool`, kind `quantifier`
| param | type | req | notes |
|---|---|---|---|
| `claim` | string | yes | The quantified claim, quantifier word visible. |
| `quantifier` | string | yes | Enum `all \| some \| none \| most` — the claim's actual quantifier, not the speaker's intent. |
| `instance_checked` | string | yes | The single concrete instance examined. |
| `counterexample` | string | yes | For `all`: a violating instance. For `none`: a confirming instance. For `some`/`most`: a non-example. If none exists, say so explicitly. |
| `scope_restriction` | string | yes | How the domain is bounded — unstated restrictions hide quantifier errors. |
| `verdict` | string | yes | Enum `holds \| fails \| unverifiable`. |

Validation: `missing_required`; `enum_error` on `quantifier` and `verdict`.

**`transitivity`** — `TransitivityTool`, kind `transitivity`
| param | type | req | notes |
|---|---|---|---|
| `entities` | array | yes | The items being ordered. |
| `relation` | string | yes | The relation claimed transitive (e.g. "is before", "outranks"). |
| `pairwise_links` | array | yes | Objects `{from, to, holds}` — the known pairwise comparisons. |
| `derived_chain` | array | yes | The transitive conclusions forced by the links. |
| `cycle_detected` | string | yes | Any loop `a > b > ... > a`, stated explicitly, or "none". |
| `consistency` | string | yes | Enum `consistent \| cyclic \| intransitive`. |

Validation: `missing_required`; `enum_error` on `consistency`.

**`identity`** — `IdentityTool`, kind `identity`
| param | type | req | notes |
|---|---|---|---|
| `entity_a` | string | yes | First entity under comparison. |
| `entity_b` | string | yes | Second entity under comparison. |
| `shared_properties` | array | yes | Properties both entities share. |
| `distinguishing_property` | string | yes | A property one has and the other lacks — by Leibniz's law that settles sameness; if none, say "none found". |
| `grounds` | string | yes | Why that property counts as identity-relevant rather than incidental. |
| `verdict` | string | yes | Enum `same \| different \| indeterminate`. |

Validation: `missing_required`; `enum_error` on `verdict`.

**`partition`** — `PartitionTool`, kind `partition`
| param | type | req | notes |
|---|---|---|---|
| `items` | array | yes | The objects being classified. |
| `categories` | array | yes | The proposed buckets. |
| `membership_rules` | array | yes | Objects `{category, rule}` — the membership criterion per category. |
| `coverage` | string | yes | Items fitting no category (gaps), or "none". |
| `overlap` | string | yes | Items fitting several categories (overlaps), or "none". |
| `verdict` | string | yes | Enum `exhaustive_disjoint \| gaps \| overlaps`. |

Validation: `missing_required`; `enum_error` on `verdict`.

**`modal`** — `ModalTool`, kind `modal`
| param | type | req | notes |
|---|---|---|---|
| `claim` | string | yes | The claim whose modal status is under analysis. |
| `modal_status` | string | yes | Enum `necessary \| possible \| contingent \| impossible`. |
| `possible_world_evidence` | string | yes | The world construction (or impossibility argument) supporting the status. |
| `actuality` | string | yes | Whether the claim holds in the actual world, stated separately from its modal status. |
| `reasoning` | string | yes | The modal argument tying `modal_status` to the world evidence. |

Validation: `missing_required`; `enum_error` on `modal_status`.

**`equivocation`** — `EquivocationTool`, kind `equivocation`
| param | type | req | notes |
|---|---|---|---|
| `term` | string | yes | The term whose meaning is in play. |
| `senses` | array | yes | Distinct meanings of `term`; at least two — one sense cannot equivocate. |
| `occurrences` | array | yes | Objects `{context, sense_used}` — where each sense appears in the argument. |
| `drift` | string | yes | How the meaning shifts across the argument, step by step. |
| `corrected_argument` | string | yes | The argument rewritten with a single consistent sense per occurrence. |
| `fallacy_present` | string | yes | Enum `yes \| no \| uncertain`. |

Validation: `missing_required`; `string_list(senses)` >= 2; `enum_error` on `fallacy_present`.

**`necessary_sufficient`** — `NecessarySufficientTool`, kind `necessary_sufficient`
| param | type | req | notes |
|---|---|---|---|
| `condition` | string | yes | The condition being analyzed. |
| `target` | string | yes | The outcome the condition is claimed to relate to. |
| `necessity_direction` | string | yes | Case where `target` holds but `condition` is absent — or argument that none exists. |
| `sufficiency_direction` | string | yes | Case where `condition` holds but `target` does not — or argument that none exists. |
| `verdict` | string | yes | Enum `necessary_only \| sufficient_only \| both \| neither`. |
| `implications` | string | yes | What the verdict means for using `condition` to control or detect `target`. |

Validation: `missing_required`; `enum_error` on `verdict`.

**`composition_division`** — `CompositionDivisionTool`, kind `composition_division`
| param | type | req | notes |
|---|---|---|---|
| `parts` | array | yes | The components. |
| `whole` | string | yes | The aggregate. |
| `property` | string | yes | The property being transferred between parts and whole. |
| `aggregation_claim` | string | yes | The exact claim that transfers the property. |
| `validity` | string | yes | Enum `valid \| fallacy_of_composition \| fallacy_of_division \| unknown`. |
| `counterexample` | string | yes | The case showing why transfer fails (or why it holds). |

Validation: `missing_required`; `enum_error` on `validity`.

**`circularity`** — `CircularityTool`, kind `circularity`
| param | type | req | notes |
|---|---|---|---|
| `argument` | string | yes | The argument under audit, stated in full. |
| `premises` | array | yes | Its stated premises. |
| `conclusion` | string | yes | Its conclusion. |
| `dependency_map` | array | yes | Objects `{premise, depends_on}` — what each premise silently presupposes. |
| `circle_found` | string | yes | The closed loop where a premise depends (directly or through others) on the conclusion, or "none". |
| `fix` | string | yes | The independent justification that would break the circle. |
| `verdict` | string | yes | Enum `circular \| not_circular \| partially`. |

Validation: `missing_required`; `enum_error` on `verdict`.

**`regress`** — `RegressTool`, kind `regress`
| param | type | req | notes |
|---|---|---|---|
| `claim` | string | yes | The claim whose justification chain is under analysis. |
| `justification_chain` | array | yes | The ordered chain of justifications, one link per entry. |
| `terminates_at` | string | yes | Where the chain bottoms out — the last link that is accepted without further justification. |
| `style` | string | yes | Enum `foundational \| circular \| infinite`. |
| `adequacy` | string | yes | Whether that termination is adequate for the purpose at hand. |

Validation: `missing_required`; `enum_error` on `style`.

**`burden_of_proof`** — `BurdenOfProofTool`, kind `burden_of_proof`
| param | type | req | notes |
|---|---|---|---|
| `claim` | string | yes | The claim whose burden is under analysis. |
| `default_presumption` | string | yes | What holds while the claim is unproven (the status quo presumption). |
| `supporting_evidence` | array | yes | Evidence establishing the claim. |
| `opposing_evidence` | array | yes | Evidence against it; "none" is acceptable only if genuinely searched. |
| `burden_holder` | string | yes | Who must establish the claim and why the burden sits there. |
| `verdict` | string | yes | Enum `established \| not_established \| contested`. |
| `decision` | string | yes | What to do while the claim is undecided (act on presumption, gather evidence, suspend). |

Validation: `missing_required`; `enum_error` on `verdict`.

**`testimony`** — `TestimonyTool`, kind `testimony`
| param | type | req | notes |
|---|---|---|---|
| `source` | string | yes | Who/what is testifying. |
| `claim` | string | yes | The claim the testimony supports. |
| `reliability_factors` | array | yes | Objects `{factor, assessment}` — competence, honesty, track record, incentives. |
| `corroboration` | array | yes | Independent sources of the same claim; "none" is a finding, not an omission. |
| `conflicts` | array | yes | Opposing testimony; "none" if genuinely searched. |
| `trust_verdict` | string | yes | Enum `high \| moderate \| low \| withheld`. |
| `residual_uncertainty` | string | yes | What would still be unknown even if this testimony is true. |

Validation: `missing_required`; `enum_error` on `trust_verdict`.

**`absence_evidence`** — `AbsenceEvidenceTool`, kind `absence_evidence`
| param | type | req | notes |
|---|---|---|---|
| `hypothesis` | string | yes | The hypothesis whose absence of evidence is being weighed. |
| `expected_evidence_if_true` | string | yes | What evidence the hypothesis predicts. |
| `search_conducted` | string | yes | What was actually examined. |
| `search_adequacy` | string | yes | Whether the search would have detected the evidence if present — absence is evidence only if the search was adequate. |
| `significance` | string | yes | Enum `evidence_against \| neutral \| evidence_for`. |
| `conclusion` | string | yes | The adjusted assessment of the hypothesis. |

Validation: `missing_required`; `enum_error` on `significance`.

**`defeasible`** — `DefeasibleTool`, kind `defeasible`
| param | type | req | notes |
|---|---|---|---|
| `default_rule` | string | yes | The default ("generally, A implies B") being applied. |
| `case` | string | yes | The concrete case. |
| `rule_applies` | string | yes | Enum `yes \| no \| borderline`. |
| `defeaters` | array | yes | Objects `{defeater, applies}` — exceptions that would retract the default conclusion; "none" is a finding. |
| `final_conclusion` | string | yes | The conclusion after applying default plus defeaters. |
| `retraction_note` | string | yes | What changed from the default conclusion, or "unchanged". |

Validation: `missing_required`; `enum_error` on `rule_applies`.

**`statistical_syllogism`** — `StatisticalSyllogismTool`, kind `statistical_syllogism`
| param | type | req | notes |
|---|---|---|---|
| `population_claim` | string | yes | The frequency claim ("most A are B") in plain language. |
| `frequency` | string | yes | The proportion as a `0.0`-`1.0` number, e.g. `'0.85'`; required and must parse. |
| `individual` | string | yes | The single case. |
| `membership` | string | yes | Evidence the individual belongs to the frequency class. |
| `defeater` | string | yes | Known facts about the individual that override the frequency — or "none". |
| `probable_conclusion` | string | yes | The probability-transfer conclusion. |
| `confidence` | string | no | Optional `0.0`-`1.0` self-assessment; renders as N/A when absent. |

Validation: `missing_required`; `probability(frequency)` must parse; `probability(confidence)` optional.

**`socratic`** — `SocraticTool`, kind `socratic`
| param | type | req | notes |
|---|---|---|---|
| `claim` | string | yes | The claim under interrogation. |
| `probing_question` | string | yes | The sharpest question to ask of the claim. |
| `assumption_surfaced` | string | yes | The hidden premise the question exposes. |
| `contradiction_found` | string | yes | Where the assumption clashes with other commitments, or "none yet". |
| `revised_claim` | string | yes | The claim after the assumption is made explicit. |
| `depth_reached` | string | yes | How many layers of assumption were peeled before hitting bedrock. |

Validation: `missing_required`.

**`dialectic`** — `DialecticTool`, kind `dialectic`
| param | type | req | notes |
|---|---|---|---|
| `thesis` | string | yes | The starting position, stated at its strongest. |
| `antithesis` | string | yes | The genuine opposition, built as carefully as the thesis; must differ from `thesis` — a dialectic against a strawman is a validation error. |
| `synthesis` | string | yes | The resolution that preserves what is true in both; if no synthesis exists, state the standoff explicitly. |
| `preserved_insight` | string | yes | What the synthesis keeps from the thesis and the antithesis. |
| `discarded_insight` | string | yes | What each side had to give up. |
| `synthesis_stability` | string | yes | What new pressure could unseat the synthesis. |

Validation: `missing_required`; `antithesis.lower() != thesis.lower()` — else error
"Field 'antithesis' must differ from 'thesis' — a dialectic between identical
positions is not a contradiction."

**`paradox`** — `ParadoxTool`, kind `paradox`
| param | type | req | notes |
|---|---|---|---|
| `paradox` | string | yes | The contradiction, stated so both incompatible conclusions are visible. |
| `premises` | array | yes | The claims that jointly produce the contradiction; at least two — a paradox needs at least two incompatible commitments. |
| `hidden_assumption` | string | yes | The premise nobody examined, whose rejection dissolves the paradox. |
| `premise_to_drop` | string | yes | Which premise must go; must exactly match one of `premises`. |
| `resolution` | string | yes | The repaired position after dropping the premise. |
| `what_it_reveals` | string | yes | What the paradox taught about the remaining premises. |

Validation: `missing_required`; `string_list(premises)` >= 2;
`premise_to_drop` must match a stated premise (case-sensitive, trimmed) — else error
"Field 'premise_to_drop' must name one of the stated 'premises'."

**`strawman`** — `StrawmanTool`, kind `strawman`
| param | type | req | notes |
|---|---|---|---|
| `original_argument` | string | yes | The argument as actually given. |
| `restated_argument` | string | yes | The argument as the critic rendered it. |
| `distortion` | string | yes | Exactly what changed between the two, or "none". |
| `fair_restatement` | string | yes | The version that would survive a charity audit. |
| `criticism_applies` | string | yes | Enum `yes \| no \| partially` — does the critique still land against the fair version. |
| `residual_critique` | string | yes | What survives against the fair restatement, or "nothing". |

Validation: `missing_required`; `enum_error` on `criticism_applies`.

**`predict`** — `PredictTool`, kind `predict`
| param | type | req | notes |
|---|---|---|---|
| `theory` | string | yes | The general claim from which the prediction is derived. |
| `initial_conditions` | array | yes | The specific conditions the theory is applied to. |
| `derived_prediction` | string | yes | What must be observed if the theory holds — stated before any observation. |
| `observed_outcome` | string | yes | What was actually observed. |
| `match` | string | yes | Enum `yes \| no \| partial`. |
| `revision` | string | yes | How the theory, conditions, or prediction must change. |

Validation: `missing_required`; `enum_error` on `match`.

**`thought_experiment`** — `ThoughtExperimentTool`, kind `thought_experiment`
| param | type | req | notes |
|---|---|---|---|
| `setup` | string | yes | The imagined world, fully specified enough to reason about. |
| `manipulation` | string | yes | The controlled change introduced. |
| `predicted_outcome` | string | yes | What must happen under the principle being tested. |
| `insight` | string | yes | What the experiment reveals about the principle. |
| `limits` | string | yes | Where the thought experiment's authority ends — what it does not show. |

Validation: `missing_required`.

**`instantiate`** — `InstantiateTool`, kind `instantiate`
| param | type | req | notes |
|---|---|---|---|
| `general_rule` | string | yes | The universal statement being applied. |
| `case` | string | yes | The specific case. |
| `applicability_conditions` | array | yes | The conditions the rule requires before it applies. |
| `conditions_met` | array | yes | Objects `{condition, satisfied}` — one per condition. |
| `derived_conclusion` | string | yes | What the rule yields for the case. |
| `scope_check` | string | yes | Why the case genuinely falls inside the rule's scope. |

Validation: `missing_required`; `object_list(conditions_met)` non-empty.

#### Edge Cases & Error Handling (shared)
- Missing/empty required field -> `ToolResult.error` naming the field.
- Arity failures (`claims`/`alternatives`/`senses`/`premises` < 2) -> `ToolResult.error`
  naming the field and the minimum.
- Enum failures -> `ToolResult.error` naming the field, bad value, and allowed set.
- Cross-field failures (`premise_to_drop` not in `premises`; `antithesis` == `thesis`)
  -> `ToolResult.error` with the tool-specific message.
- Unparsable `frequency` -> `ToolResult.error` (like `bayesian_update`).
- Frozen primitive at the same `primitive_id` -> `ToolResult.error`, matching
  `ReflexionTool`.

---

### 6.4 `vidbyte/tools/builtins/reasoning/__init__.py` (MODIFIED)

**File(s):** `vidbyte/tools/builtins/reasoning/__init__.py`
**Type:** Modified

#### What it does
Imports and re-exports the 25 new tool classes (alphabetical import order by file
name), extends the module docstring's `Architecture:` list with the batch-2 groups,
and grows `__all__` to 35 names. `ReasoningToolInput` stays package-private.

---

### 6.5 `vidbyte/tools/builtins/__init__.py` (MODIFIED)

**File(s):** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

#### What it does
Extends the existing `from vidbyte.tools.builtins.reasoning import (...)` block with
the 25 new class names and adds them to `__all__`. The module docstring's
`Architecture:` bullet for reasoning strategy tools is unchanged (same family).

---

### 6.6 `vidbyte/context/primitives/__init__.py` (MODIFIED)

**File(s):** `vidbyte/context/primitives/__init__.py`
**Type:** Modified

#### What it does
Adds one import line pulling the 25 new `ContextItem` classes from
`reasoning_strategies.py` (extending the existing import), and inserts their names
into the alphabetized `__all__` list.

---

### 6.7 `vidbyte/context/primitives/README.md` (MODIFIED)

**File(s):** `vidbyte/context/primitives/README.md`
**Type:** Modified

#### What it does
Extends the existing `reasoning_strategies.py` bullet with the batch-2 family names.

---

### 6.8 `skills/usage/available_tools.md` (MODIFIED)

**File(s):** `skills/usage/available_tools.md`
**Type:** Modified

#### What it does
Extends the "Reasoning Strategy Tools" section: 25 new names in the import block
and 25 new rows in the tool table, one line each drawn from the tool's
`ToolSpec.description`.

---

### 6.9 `llms.txt` (MODIFIED)

**File(s):** `llms.txt`
**Type:** Modified

#### What it does
Extends both summary tables: the context-items "Reasoning strategies" row gains the
25 new `ContextItem` names; the tools "Reasoning strategies" row gains the 25 new
tool class names.

---

## 7. Data Model Changes

N/A - no database or schema changes. The only additions are 25 in-process, frozen
`dataclass` `ContextItem` types (Section 6.1); they are not persisted outside the
in-memory `ContextManager` registry, same as every existing primitive.

---

## 8. API Changes

N/A - this is a Python SDK library change (new importable classes), not a network
API. No HTTP endpoints are added or modified. The added surface is the 25 new tool
names callable by any model wired to a `ContextManager`-backed agent, documented
fully in Section 6.3.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/reasoning-strategy-tools-batch-2.md` | this design doc |
| MODIFY | `vidbyte/context/primitives/reasoning_strategies.py` | 25 new `ContextItem` dataclasses + `__all__` |
| MODIFY | `vidbyte/context/primitives/__init__.py` | export the 25 new primitives |
| MODIFY | `vidbyte/context/primitives/README.md` | extend `reasoning_strategies.py` bullet |
| CREATE | `vidbyte/tools/builtins/reasoning/counterexample.py` | `CounterexampleTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/consistency.py` | `ConsistencyTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/dilemma.py` | `DilemmaTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/quantifier.py` | `QuantifierTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/transitivity.py` | `TransitivityTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/identity.py` | `IdentityTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/partition.py` | `PartitionTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/modal.py` | `ModalTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/equivocation.py` | `EquivocationTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/necessary_sufficient.py` | `NecessarySufficientTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/composition_division.py` | `CompositionDivisionTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/circularity.py` | `CircularityTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/regress.py` | `RegressTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/burden_of_proof.py` | `BurdenOfProofTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/testimony.py` | `TestimonyTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/absence_evidence.py` | `AbsenceEvidenceTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/defeasible.py` | `DefeasibleTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/statistical_syllogism.py` | `StatisticalSyllogismTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/socratic.py` | `SocraticTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/dialectic.py` | `DialecticTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/paradox.py` | `ParadoxTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/strawman.py` | `StrawmanTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/predict.py` | `PredictTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/thought_experiment.py` | `ThoughtExperimentTool` |
| CREATE | `vidbyte/tools/builtins/reasoning/instantiate.py` | `InstantiateTool` |
| MODIFY | `vidbyte/tools/builtins/reasoning/__init__.py` | re-export the 25 new tools |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | import + `__all__` for the 25 new tools |
| MODIFY | `skills/usage/available_tools.md` | extend "Reasoning Strategy Tools" section |
| MODIFY | `llms.txt` | extend both builtin-catalog summary tables |

26 files created, 8 files modified.

---

## 10. Dependencies & External Services

None. Pure stdlib (`dataclasses`, `json`, `typing`) plus existing SDK internals
(`vidbyte.tools.base.BaseTool`, `vidbyte.tools.types.*`,
`vidbyte.context.manager.ContextManager`, `vidbyte.context.primitives.base`,
`vidbyte.tools.builtins.reasoning._parsing.ReasoningToolInput`). No new
dependencies.

---

## 11. Rollout & Deployment

- **Stacking deviation:** this branch is created from `origin/feat/reasoning-strategy-tools`
  (PR #343's head) and the PR targets that branch as base, because the user asked to
  stack on the previous PR and #343 is still a draft. Once #343 merges to `main`,
  this PR's base can be retargeted to `main` with no code change.
- No feature flag — matches `ReflexionTool`/`TrajectoryCheckpointTool` and the 10 PR
  #343 tools: opt-in-by-import.
- Purely additive: no existing class, function, or exported name changes shape or
  behavior. Not a breaking change.
- Rollback: revert the PR; nothing else depends on the new names within this change.
- **CI gate:** from the worktree — `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
  (the editable install resolves `vidbyte` to the canonical checkout, so the source
  stage must run against the worktree), then `python scripts/run_ci.py --stage package`
  with no `PYTHONPATH`, then the full `python scripts/run_ci.py`.

---

## 12. Open Questions

- [ ] Once PR #343 merges, retarget this PR's base from `feat/reasoning-strategy-tools`
  to `main`.
- [ ] Should the "abstract thinking and thinking in systems" strategies (proposed in
  the chat handoff) become batch 3? No code implication now; the file layout already
  scales.
- [ ] Should a future follow-up add the missing top-level `vidbyte/__init__.py`
  re-export gap flagged in PR #343's open questions? Left as-is here to match
  precedent.

---

## 13. Alternatives Considered

### Alternative 1: One flat file with all 25 tool classes
- What: put all 25 `BaseTool` subclasses in a single
  `vidbyte/tools/builtins/reasoning_strategies.py`, mirroring `epistemics.py`'s
  multi-class-per-file primitive style.
- Why rejected: the established *tool* convention is one file per tool class
  (`reflexion.py`, `trajectory_checkpoint.py`, every file in `context_primitives/`,
  and PR #343's 10). `context-algorithm-to-tool.md` Section 6 states this
  explicitly; 25 tools in one file would also make per-tool parameter richness
  impossible to review.

### Alternative 2: A shared `ReasoningStrategyTool` base class to cut boilerplate
- What: extract the counter/enumerate/upsert/return flow into one abstract base for
  all 35 tools.
- Why rejected: no such base exists in the codebase today; PR #343 deliberately
  repeated the ~40-line flow per file, and reviewers accepted that shape. Introducing
  a new base class mid-family would make this PR's diff inconsistent with the 10
  tools it extends and would touch `reflexion.py`/`trajectory_checkpoint.py`-adjacent
  conventions without a design conversation. Flagged as a possible future
  refactor, not this PR.

### Alternative 3: New primitives module `reasoning_strategies_batch2.py`
- What: a separate module for the 25 new dataclasses.
- Why rejected: `checkpoints.py` and `reasoning.py` already hold many primitives per
  file; splitting the family across two modules would fragment `__all__` exports and
  make the catalog tables harder to scan. One family, one module.

### Alternative 4: Soft errors for arity/cross-field violations (log, still record)
- What: record the item even when `premises < 2` or `premise_to_drop` is absent.
- Why rejected: this directly fights the maximum-extraction/observability mandate —
  a paradox record without a dropped premise is an uncommitted record. Hard
  validation errors are the mechanism that forces the model to complete the
  reasoning.

---

END OF DESIGN DOC
# Design Doc: Resolve PR #72 Review Comments

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This change resolves all five inline review comments on PR #72 (`feat/llm-as-a-judge-strategies`). It introduces a centralized `TemplatesRegistry` backed by a `templates.py` config module that replaces the 32+ scattered `_DEFAULT_*_TEMPLATE` module-level strings across the 19 LLM-as-a-judge grader files. It adds a typed config dataclass per judge class — with exhaustive `__post_init__` validation — so every constructor now takes a single dataclass argument instead of 4–8 keyword params. All 26 LLM-as-a-judge prompt `.md` files are expanded to richer 6–7-sentence introductory sections. Finally, a new `skills/evals/` skill tree is added covering the full eval subsystem workflow.

---

## 2. Goals & Non-Goals

### Goals
- Create `vidbyte/lib/config/templates.py` containing all 32+ default judge prompt templates keyed by `"<judge>.<slot>"`.
- Create `vidbyte/lib/eval/__init__.py` and `vidbyte/lib/eval/template_registry.py` containing `TemplatesRegistry` with `get()`, `search()`, `create()`, `exists()`, and `names()`.
- Create `vidbyte/lib/dataclasses/llm_judge.py` with 19 frozen `@dataclass` config classes, one per judge, each with exhaustive `__post_init__` validation.
- Refactor all 19 judge `__init__` methods to accept a single config dataclass argument.
- Update all 19 judge files to resolve templates from `TemplatesRegistry` instead of module-level `_DEFAULT_*` constants.
- Expand all 26 LLM-as-a-judge prompt `.md` files with 6–7-sentence introductory sections.
- Add `skills/evals/SKILL.md`, `skills/evals/adding-llm-judge.md`, `skills/evals/using-llm-judge.md`, and `skills/evals/eval-pipeline.md`.
- Update `tests/test_llm_as_a_judge.py` and `scripts/test-llm-as-a-judge.py` to use config dataclasses.

### Non-Goals
- Changing `agrade()` scoring logic or algorithms.
- Modifying the `Prompt` enum, JSON manifest, or prompt `.md` file names.
- Adding new judge strategies.
- Changing `BaseGrader`, `EvalCase`, or `GraderResult` contracts.
- Adding backwards-compatibility shims for the old keyword-only constructor form (PR #72 is not yet merged).

---

## 3. Background & Context

PR #72 adds 19 LLM-as-a-judge grader strategies. The reviewer identified four structural gaps before merge:

1. **Template scatter**: Each judge file has 1–3 `_DEFAULT_*_TEMPLATE` module-level strings and corresponding `_resolve_*_template()` methods. Templates are not discoverable, auditable, or globally overridable.
2. **Constructor ergonomics**: Each judge has 4–8 keyword-only constructor parameters with validation logic inline in `__init__`. Config dataclasses push validation to construction time, make configs inspectable, and establish a consistent pattern across all 19 classes.
3. **Prompt quality**: The 26 `.md` prompt files have 1–3-sentence introductory sections with insufficient context for maintainers and for models reading the prompt at eval time.
4. **Developer guidance**: No skill files exist for the `vidbyte.evals` subsystem, leaving developers without a reference for adding or using eval strategies.

---

## 4. Requirements

### Functional Requirements
1. `TemplatesRegistry.get(name)` returns the template string for the given name; raises `KeyError` if not found.
2. `TemplatesRegistry.search(keyword)` returns a sorted list of template names containing `keyword` (case-insensitive).
3. `TemplatesRegistry.create(name, template)` registers a new template or overwrites an existing one; raises `ValueError` if either argument is empty.
4. `TemplatesRegistry.exists(name)` returns `True` if the name is registered.
5. `TemplatesRegistry.names()` returns a sorted list of all registered template names.
6. Every judge's `__init__` accepts exactly one positional argument: a typed config dataclass instance.
7. Each config dataclass raises `ValueError` in `__post_init__` for invalid field values, with a message identifying the field and the violation.
8. Runner arguments validate for at least one of `arun`, `generate_reply`, or `run` via duck-typing; invalid runners raise `TypeError` at construction.
9. Each judge resolves its template via: user-supplied override in config → SDK `Prompts()` catalog → `TemplatesRegistry` default.
10. All 26 prompt `.md` files have ≥ 6 introductory sentences before the first template variable placeholder.
11. All 57 existing tests in `test_llm_as_a_judge.py` continue to pass after the refactor.

### Non-Functional Requirements
- Validation is eager: errors raise at `XxxConfig(...)` instantiation, not inside `agrade()`.
- `TemplatesRegistry` is stateless beyond its internal template dict; it does not hold runners or SDK state.
- No circular imports: `vidbyte/lib/eval/` must not import from `vidbyte/evals/`.

---

## 5. High-Level Design

The change restructures the initialization and template-resolution layers of the 19 judge classes without touching grading logic.

**Layer 1 — Templates** (`vidbyte/lib/config/templates.py` + `vidbyte/lib/eval/template_registry.py`): All inline `_DEFAULT_*_TEMPLATE` strings migrate to a single `JUDGE_TEMPLATES` dict keyed by `"<judge_name>.<slot>"`. `TemplatesRegistry` wraps this dict, copies it at instantiation, and exposes a CRUD-style interface. Each judge module keeps a module-level `_registry = TemplatesRegistry()` instance for default lookups.

**Layer 2 — Config Dataclasses** (`vidbyte/lib/dataclasses/llm_judge.py`): 19 frozen dataclasses replace keyword-only constructor signatures. Each carries identical fields with type annotations and a `__post_init__` method enforcing value ranges, non-empty collections, key–set consistency, and runner interface contracts. Judge constructors change from multi-param keyword signatures to `def __init__(self, config: XxxConfig) -> None`.

**Layer 3 — Prompt Assets** (26 `.md` files): Introductory prose expanded to 6–7 sentences covering role, task scope, reasoning process, output format contract, neutrality requirements, and edge handling.

**Layer 4 — Skill Files** (`skills/evals/`): Four new Markdown files provide developer guidance on the eval subsystem.

```
[Developer]
    |
    v
[XxxConfig(__post_init__)]  — validates all inputs eagerly at construction
    |
    v
[XxxJudge.__init__(config)]  — stores config, creates module-level TemplatesRegistry
    |
    v
[XxxJudge.agrade(case, actual)]  — grading logic unchanged
    |
    +---> config.prompt_template (user override, highest priority)
    +---> Prompts().get(Prompt.LLM_AS_A_JUDGE_*)  (SDK catalog, second)
    +---> _registry.get("judge.slot")  (TemplatesRegistry default, fallback)
```

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/config/templates.py`

**File:** `vidbyte/lib/config/templates.py`
**Type:** New file

#### What it does
Defines `JUDGE_TEMPLATES: dict[str, str]` with all default prompt templates for every judge/slot combination. This is a pure data module with no classes or logic.

#### Interface / API
```python
JUDGE_TEMPLATES: dict[str, str] = {
    "chain_of_thought.user": "...",
    "binary.user": "...",
    "few_shot.user": "...",
    "pairwise.user": "...",
    "self_reference.generation": "...",
    "self_reference.eval": "...",
    "self_eval.user": "...",
    "criteria_decomposition.decompose": "...",
    "criteria_decomposition.eval": "...",
    "chain_of_aspects.user": "...",
    "branch_solve_merge.branch": "...",
    "branch_solve_merge.merge": "...",
    "llm_rubric.generate": "...",
    "llm_rubric.eval": "...",
    "structured_rubric.user": "...",
    "atomic_claims.decompose": "...",
    "atomic_claims.verify": "...",
    "constitutional.check": "...",
    "panel.user": "...",
    "multi_agent_rubric.agent": "...",
    "multi_agent_rubric.merge": "...",
    "multi_agent_debate.initial": "...",
    "multi_agent_debate.round": "...",
    "meta_judge.user": "...",
    "peer_review.user": "...",
    "mixture_of_prompts.router": "...",
}

__all__ = ["JUDGE_TEMPLATES"]
```

#### Logic / Algorithm
1. Copy the exact text from each `_DEFAULT_*_TEMPLATE` constant in its source judge file.
2. Key each template as `"<judge_name>.<slot>"` using the snake-case judge name and the slot name.
3. No logic, no imports beyond stdlib (the strings are self-contained).

#### Edge Cases & Error Handling
Pure data module; no runtime errors expected.

---

### 6.2 `vidbyte/lib/eval/template_registry.py`

**File(s):** `vidbyte/lib/eval/__init__.py`, `vidbyte/lib/eval/template_registry.py`
**Type:** New files

#### What it does
`TemplatesRegistry` wraps `JUDGE_TEMPLATES` in a discoverable, mutable-per-instance interface. Each judge module instantiates its own registry so user `create()` calls don't bleed across modules.

#### Interface / API
```python
class TemplatesRegistry:
    def __init__(self) -> None: ...
    def get(self, name: str) -> str: ...
    def search(self, keyword: str) -> list[str]: ...
    def create(self, name: str, template: str) -> None: ...
    def exists(self, name: str) -> bool: ...
    def names(self) -> list[str]: ...
```

#### Logic / Algorithm
1. `__init__`: shallow-copy `JUDGE_TEMPLATES` into `self._templates: dict[str, str]`.
2. `get(name)`: return `self._templates[name]`; raise `KeyError(f"Template '{name}' not found. Call .names() to list available templates.")` if absent.
3. `search(keyword)`: return `sorted(k for k in self._templates if keyword.lower() in k.lower())`.
4. `create(name, template)`: validate both args are non-empty strings; raise `ValueError` if not; set `self._templates[name] = template`.
5. `exists(name)`: return `name in self._templates`.
6. `names()`: return `sorted(self._templates.keys())`.

#### Edge Cases & Error Handling
- `get` with unknown name: descriptive `KeyError` with lookup hint.
- `create` with empty name or template: `ValueError("Template name and body must be non-empty strings.")`.

---

### 6.3 `vidbyte/lib/dataclasses/llm_judge.py`

**File:** `vidbyte/lib/dataclasses/llm_judge.py`
**Type:** New file

#### What it does
Defines 19 frozen `@dataclass` config classes, one per judge. Each mirrors the old `__init__` keyword parameters as typed fields, plus a `__post_init__` that validates all semantic constraints eagerly.

#### Interface / API — representative sample

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.evals.base import BaseGrader

def _validate_runner(runner: object, field: str) -> None:
    # Raises TypeError if runner lacks arun/generate_reply/run interface.
    ...

@dataclass(frozen=True, slots=True)
class ChainOfThoughtJudgeConfig:
    judge_runner: object
    cot_length: Literal["short", "medium", "long"] = "medium"
    system_prompt: str | None = None
    prompt_template: str | None = None
    def __post_init__(self) -> None: ...

@dataclass(frozen=True, slots=True)
class BinaryJudgeConfig:
    judge_runner: object
    criterion: str
    system_prompt: str | None = None
    prompt_template: str | None = None
    def __post_init__(self) -> None: ...

# ... 17 more classes
```

#### Validation Rules Per Class

| Config Class | Validated Constraints |
|---|---|
| `ChainOfThoughtJudgeConfig` | `judge_runner` has run interface; `cot_length` in `{"short","medium","long"}` |
| `BinaryJudgeConfig` | `judge_runner` run interface; `criterion` non-empty and non-whitespace |
| `FewShotJudgeConfig` | `judge_runner` run interface; `examples` non-empty list; each item is a dict with `"prompt"`, `"response"`, and `"score"` keys; `score` casts to `float` in `[0,1]` |
| `PairwiseJudgeConfig` | `judge_runner` run interface; `swap_check` is `bool` |
| `SelfReferenceJudgeConfig` | `judge_runner` run interface; `num_self_generations >= 1` |
| `SelfEvalJudgeConfig` | `judge_runner` run interface; `framing` in `{"third_person","anonymous"}` |
| `CriteriaDecompositionJudgeConfig` | `judge_runner` run interface; `criterion` non-empty; `num_sub_criteria >= 2` |
| `ChainOfAspectsJudgeConfig` | `judge_runner` run interface; `aspects` non-empty list of non-empty strings; `words_per_aspect >= 1` |
| `BranchSolveMergeJudgeConfig` | `judge_runner` run interface; `branches` non-empty dict with non-empty-string values; `branch_weights` keys == `branches` keys if provided; all weights `> 0`; `merge_strategy` in `{"weighted_mean","llm"}`; if `"llm"` then `judge_runner` provided |
| `LLMRubricJudgeConfig` | `judge_runner` run interface; `task_description` non-empty; `rubric_scale >= 2` |
| `StructuredRubricJudgeConfig` | `judge_runner` run interface; `dimensions` non-empty dict; each value a non-empty `{int: str}` dict; `weights` keys == `dimensions` keys if provided; all weights `> 0`; `0.0 < threshold <= 1.0` |
| `AtomicClaimsJudgeConfig` | `judge_runner` run interface; `0.0 < threshold <= 1.0` |
| `ConstitutionalJudgeConfig` | `judge_runner` run interface; `principles` non-empty list of non-empty strings; `0.0 < threshold <= 1.0` |
| `PanelJudgeConfig` | all items in `judge_runners` have run interface; `len(judge_runners) >= 2`; `aggregation` in `{"mean","median","majority_vote"}`; `0.0 < threshold <= 1.0` |
| `MultiAgentRubricJudgeConfig` | each `agents` item is a `(runner, str)` tuple with valid runner; `len(agents) >= 2`; `weights` length == `len(agents)` and all `> 0` if provided; `merge_strategy` in `{"weighted_mean","llm"}`; if `"llm"` then `merge_runner` provided; `0.0 < threshold <= 1.0` |
| `MultiAgentDebateJudgeConfig` | all items in `judge_runners` have run interface; `len(judge_runners) >= 2`; `debate_rounds >= 1`; `0.0 < threshold <= 1.0` |
| `MetaJudgeConfig` | `primary_judge` is a `BaseGrader` instance; `meta_runner` has run interface |
| `PeerReviewJudgeConfig` | all items in `judge_runners` have run interface; `len(judge_runners) >= 2`; `0.0 < confidence_threshold <= 1.0`; `0.0 < threshold <= 1.0` |
| `MixtureOfPromptsJudgeConfig` | `judge_runner` run interface; `prompt_library` non-empty dict with non-empty-string values; `fallback_key` in `prompt_library` if provided; not both `router_runner` and `router_fn` provided simultaneously; `router_runner` run interface if provided |

#### Edge Cases & Error Handling
- Runner missing interface: `TypeError(f"'{field_name}' must expose arun(), generate_reply(), or run() method.")`.
- All `ValueError`s: `ValueError(f"'{field_name}': {description_of_violation}")`.

---

### 6.4 Updates to all 19 judge files

**File(s):** `vidbyte/evals/llm_as_a_judge/*.py` (19 files)
**Type:** Modified

#### What changes
1. Remove module-level `_DEFAULT_*_TEMPLATE` string constants.
2. Remove `_resolve_*_template()` methods.
3. Add `from vidbyte.lib.eval.template_registry import TemplatesRegistry` import.
4. Add `from vidbyte.lib.dataclasses.llm_judge import XxxConfig` import.
5. Add module-level `_registry = TemplatesRegistry()`.
6. Change `__init__` signature to `def __init__(self, config: XxxConfig) -> None:`.
7. Store `self._config = config` and unpack needed fields.
8. Replace template resolution with a private `_resolve_template(slot, override, prompt_key)` helper.

#### Unified template resolution helper (shared pattern in each file)

```python
_registry = TemplatesRegistry()

class XxxJudge(BaseGrader):
    def __init__(self, config: XxxConfig) -> None:
        # Unpacks validated config fields into instance attributes.
        self._config = config

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)
```

#### Edge Cases & Error Handling
- Registry `get` fallback can only fail if `templates.py` is missing the key — treat as programmer error (do not swallow).

---

### 6.5 Prompt `.md` files (26 files)

**File(s):** `vidbyte/prompts/prompts/llm_as_a_judge/*.md` (26 files)
**Type:** Modified

#### What changes
Each prompt file's opening section is expanded to 6–7 sentences covering:
1. Role the model plays in this evaluation.
2. What the specific task or question requires.
3. Scope of what should and should not be evaluated.
4. What reasoning or deliberation process the model should follow.
5. The output format contract (JSON schema, field names, value types).
6. How to handle edge cases (missing context, ambiguous output, no expected answer).
7. Calibration or neutrality instruction where relevant.

The template variable blocks (`{prompt}`, `{actual}`, `{expected}`, etc.) and the output format specification remain byte-for-byte identical.

---

### 6.6 Eval skill files

**File(s):** `skills/evals/SKILL.md`, `skills/evals/adding-llm-judge.md`, `skills/evals/using-llm-judge.md`, `skills/evals/eval-pipeline.md`
**Type:** New files

| File | Contents |
|------|----------|
| `SKILL.md` | Overview: subsystem purpose, key types (`BaseGrader`, `EvalCase`, `GraderResult`, `EvalSuiteResult`), `TemplatesRegistry` reference, quick-start example, link table to sub-skills |
| `adding-llm-judge.md` | Step-by-step: create `XxxConfig` dataclass with validation, subclass `BaseGrader`, implement `agrade()`, add template slot to `templates.py`, add to `__init__` exports and `Prompt` enum |
| `using-llm-judge.md` | Usage examples: constructing a judge via config dataclass, `grade()`/`agrade()` usage, custom template override, `TemplatesRegistry` customization |
| `eval-pipeline.md` | Full pipeline: `EvalCase` construction, running suites, interpreting `EvalSuiteResult` pass rate and p95 latency, integrating evals into CI |

---

## 7. Data Model Changes

N/A — no schema or persistent data changes. The `EvalCase`, `GraderResult`, `EvalResult`, and `EvalSuiteResult` dataclasses are not modified.

---

## 8. API Changes

No HTTP endpoints. Python SDK constructor API changes from keyword-only to config-dataclass:

```python
# Before (PR #72 as-is)
judge = ChainOfThoughtJudge(judge_runner=runner, cot_length="medium")

# After (this PR)
from vidbyte.lib.dataclasses.llm_judge import ChainOfThoughtJudgeConfig
config = ChainOfThoughtJudgeConfig(judge_runner=runner, cot_length="medium")
judge = ChainOfThoughtJudge(config)
```

This is a **breaking change** to the 19 judge constructors. Because PR #72 is not yet merged, there are no downstream callers to migrate.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/config/templates.py` | Central default template store for all 19 judges |
| CREATE | `vidbyte/lib/eval/__init__.py` | New internal lib/eval package |
| CREATE | `vidbyte/lib/eval/template_registry.py` | `TemplatesRegistry` class |
| CREATE | `vidbyte/lib/dataclasses/llm_judge.py` | 19 judge config dataclasses with validation |
| MODIFY | `vidbyte/evals/llm_as_a_judge/atomic_claims.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/binary.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/branch_solve_merge.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/chain_of_aspects.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/chain_of_thought.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/constitutional.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/criteria_decomposition.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/few_shot.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/llm_rubric.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/meta_judge.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/mixture_of_prompts.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/multi_agent_debate.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/multi_agent_rubrics.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/pairwise.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/panel.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/peer_review.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/self_eval.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/self_reference.py` | Config dataclass + registry |
| MODIFY | `vidbyte/evals/llm_as_a_judge/structured_rubric.py` | Config dataclass + registry |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/atomic_claims_decompose.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/atomic_claims_verify.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/binary_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/branch_solve_merge_branch.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/branch_solve_merge_merge.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/chain_of_aspects_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/chain_of_thought_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/constitutional_check.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/criteria_decomposition_decompose.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/criteria_decomposition_eval.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/few_shot_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/llm_rubric_eval.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/llm_rubric_generate.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/meta_judge_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/mixture_of_prompts_router.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_debate_initial.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_debate_round.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_rubric_agent.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_rubric_merge.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/pairwise_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/panel_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/peer_review_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/self_eval_user.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/self_reference_eval.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/self_reference_generation.md` | Expand intro prose |
| MODIFY | `vidbyte/prompts/prompts/llm_as_a_judge/structured_rubric_user.md` | Expand intro prose |
| MODIFY | `tests/test_llm_as_a_judge.py` | Update all judge constructions to use config dataclasses |
| MODIFY | `scripts/test-llm-as-a-judge.py` | Update construction in verification script |
| CREATE | `skills/evals/SKILL.md` | Eval subsystem overview skill |
| CREATE | `skills/evals/adding-llm-judge.md` | Step-by-step guide for adding a new judge |
| CREATE | `skills/evals/using-llm-judge.md` | Usage guide for eval consumers |
| CREATE | `skills/evals/eval-pipeline.md` | Full pipeline and suite reference |

**Total: 8 created, 47 modified = 55 files**

---

## 10. Testing Plan

### Unit Tests (additions to `tests/test_llm_as_a_judge.py`)

**Config dataclass validation:**
- `test_cot_config_invalid_cot_length` — raises `ValueError` for `cot_length="invalid"` — [Edge Case]
- `test_cot_config_invalid_runner_no_run_method` — raises `TypeError` for runner with no callable interface — [Hidden Assumption]
- `test_binary_config_empty_criterion` — raises `ValueError` for `criterion=""` — [Edge Case]
- `test_binary_config_whitespace_criterion` — raises `ValueError` for `criterion="   "` — [Edge Case]
- `test_fewshot_config_empty_examples` — raises `ValueError` for `examples=[]` — [Edge Case]
- `test_fewshot_config_missing_keys_in_example` — raises `ValueError` when example dict lacks `"prompt"` key — [Hidden Assumption]
- `test_panel_config_single_runner` — raises `ValueError` for `judge_runners` with 1 item — [Edge Case]
- `test_panel_config_empty_runners` — raises `ValueError` for `judge_runners=[]` — [Edge Case]
- `test_mad_config_single_runner` — raises `ValueError` for `MultiAgentDebateJudgeConfig` with 1 runner — [Edge Case]
- `test_constitutional_config_empty_principles` — raises `ValueError` for `principles=[]` — [Edge Case]
- `test_constitutional_config_whitespace_principle` — raises `ValueError` for `principles=[""]` — [Edge Case]
- `test_structured_rubric_config_empty_dimensions` — raises `ValueError` — [Edge Case]
- `test_bsm_config_weight_key_mismatch` — raises `ValueError` when `branch_weights` keys don't match `branches` — [Hidden Assumption]
- `test_llm_rubric_config_scale_below_2` — raises `ValueError` for `rubric_scale=1` — [Edge Case]
- `test_atomic_claims_config_zero_threshold` — raises `ValueError` for `threshold=0.0` — [Edge Case]
- `test_mop_config_invalid_fallback_key` — raises `ValueError` when `fallback_key` not in `prompt_library` — [Hidden Assumption]
- `test_mop_config_both_router_runner_and_fn` — raises `ValueError` when both `router_runner` and `router_fn` are provided — [Hidden Assumption]
- `test_peer_review_config_single_runner` — raises `ValueError` for `judge_runners` with 1 item — [Edge Case]

**TemplatesRegistry:**
- `test_registry_get_unknown_name` — raises `KeyError` with helpful message — [Edge Case]
- `test_registry_search_returns_matching_names` — keyword in name returns correct results — [Edge Case]
- `test_registry_search_no_match_returns_empty` — no match returns `[]`, not an error — [Silent Failure]
- `test_registry_create_empty_name_raises` — raises `ValueError` — [Edge Case]
- `test_registry_create_empty_template_raises` — raises `ValueError` — [Edge Case]
- `test_registry_create_overwrites_existing` — `create` on existing key updates value — [Silent Failure]
- `test_registry_exists_true_and_false` — checks positive and negative lookup — [Edge Case]
- `test_registry_instance_isolation` — mutating one registry instance does not affect another — [Hidden Failure]

**Template resolution in judges:**
- `test_cot_uses_registry_default_when_no_override` — template resolves from registry when `config.prompt_template=None` — [Hidden Assumption]
- `test_cot_uses_config_override_template` — `config.prompt_template` takes priority over registry — [Hidden Failure]

**All existing 57 tests** must pass after updating construction to use config dataclasses.

### Integration Tests

- Construct each of the 19 judges via its config dataclass; call `.grade()` with an `AsyncMockRunner`; confirm `GraderResult` is returned with valid `score`, `passed`, `reason` fields.
- Verify `TemplatesRegistry()` loaded from `templates.py` contains all 26+ expected `"<judge>.<slot>"` keys.
- Verify that `registry.create("custom.key", "template")` on one instance does not affect a separately instantiated `TemplatesRegistry()`.

### Manual / QA Test Cases

1. Given `BinaryJudgeConfig(judge_runner=runner, criterion="")`, when instantiated, then `ValueError` is raised mentioning `criterion` — [Edge Case]
2. Given `ChainOfThoughtJudge(ChainOfThoughtJudgeConfig(judge_runner=runner))` with no `prompt_template`, when `agrade()` is called, then the template resolves from `TemplatesRegistry` without error — [Hidden Assumption]
3. Given all 26 `.md` prompt files, when opened in an editor, then each has ≥ 6 introductory sentences before the first `{` template variable — [Edge Case]
4. Given `PanelJudgeConfig(judge_runners=[r1], aggregation="mean")`, when instantiated, then `ValueError` raised before any grading attempt — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.evals.base` | internal | `BaseGrader` abstract base | None |
| `vidbyte.evals.types` | internal | `EvalCase`, `GraderResult` | None |
| `vidbyte.lib.config.templates` | internal (new) | Default template strings | None |
| `vidbyte.prompts.catalog` | internal | SDK catalog prompt fallback | None |
| `vidbyte.lib.enums.prompts` | internal | `Prompt` enum for catalog lookup | None |

---

## 12. Rollout & Deployment

- No feature flags.
- This resolves comments on `feat/llm-as-a-judge-strategies` (PR #72), which has not yet been merged. Implementation will push to a new branch based on `feat/llm-as-a-judge-strategies` and open a replacement PR.
- **Breaking change** to 19 judge constructors. No downstream callers exist (unmerged branch).
- Rollback: close the resolve PR; the original `feat/llm-as-a-judge-strategies` branch is unaffected.

---

## 13. Open Questions

- [ ] Should `TemplatesRegistry` be a module-level singleton shared by all judge instances of the same class, or a fresh instance per judge? (Per-instance is safer for test isolation but slightly more memory; module-level is simpler but `create()` calls are global to the module.)
- [ ] Should `create()` be allowed to overwrite existing entries silently, or should it have a separate `update()` method to signal intent?
- [ ] The reviewer specified `vidbyte/lib/eval/` for `TemplatesRegistry`. Should the `__init__.py` re-export `TemplatesRegistry` from `vidbyte.lib.eval` for cleaner import paths?
- [ ] Should the 19 config dataclasses be `frozen=True, slots=True` (matching the pattern in `agents.py`) or just `frozen=True`? (`slots=True` is more memory-efficient but disallows weak references.)

---

## 14. Alternatives Considered

### Alternative 1: Keep `_DEFAULT_*` strings in-place; add TemplatesRegistry as an optional overlay
- What: Leave existing inline defaults; `TemplatesRegistry` only stores user overrides.
- Why rejected: Templates stay scattered across 19 files; the central registry's discovery value (`search()`, `names()`) is lost.

### Alternative 2: Use `Prompts()` catalog as the single source of truth; remove all inline defaults
- What: Remove all `_DEFAULT_*` strings; judges fail if catalog unavailable.
- Why rejected: Creates a hard dependency on the catalog path at every test invocation; the inline fallback exists precisely to allow offline/test use.

### Alternative 3: One dataclass file per judge (19 files)
- What: `vidbyte/lib/dataclasses/llm_judge_binary.py`, etc.
- Why rejected: Inconsistent with the existing convention of one file per domain (`agents.py`, `strategies.py`); 19 tiny files add import noise.

### Alternative 4: Backwards-compatible `__init__` that accepts both keyword args and a config dataclass
- What: Keep the old keyword signature working alongside the new config form.
- Why rejected: PR #72 is not yet merged; no callers to protect. A shim would add dead weight and defer the clean break.

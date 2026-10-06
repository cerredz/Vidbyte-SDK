# Design Doc: Eval Template Bundles

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-24
**Last Updated:** 2026-06-24

---

## 1. Overview

This feature adds first-class eval templates to `vidbyte.evals`: reusable named bundles that expand into one or more existing or new deterministic graders. Users will be able to set `EvalCase.templates` directly in Python, load templates from JSON suites, choose from prebuilt multi-grader templates, and define their own template classes without replacing the existing low-level `grader` escape hatch.

---

## 2. Goals & Non-Goals

### Goals

- Add a `templates` parameter to `EvalCase` while preserving the existing `grader` parameter.
- Keep concrete scoring logic under `vidbyte/evals/graders/`.
- Add a new `vidbyte/evals/templates/` package for template base classes, prebuilt template bundles, and a registry.
- Support prebuilt multi-grader templates for common eval intents, not only one-to-one aliases for existing graders.
- Support user-defined templates by subclassing a public `EvalTemplate` contract.
- Compose multiple templates on one case with deterministic `all_of` semantics by default.
- Extend `EvalSuite.from_json()` so JSON eval suites can specify `templates`.
- Preserve backward compatibility for existing eval cases, existing JSON/CSV suites, runner behavior, and registry reads.
- Add tests and a feature verification script covering every behavior in this design.

### Non-Goals

- Do not remove or deprecate `EvalCase.grader`.
- Do not add hosted/cloud eval storage.
- Do not add provider network calls or hidden LLM judge calls inside deterministic templates.
- Do not implement trace-aware tool-call grading in this PR; tool-call templates need a stable representation of tool calls in eval results and should be a later design.
- Do not move prompt templates or context-window templates into this package; `vidbyte/evals/templates/` is only for eval grading templates.
- Do not introduce new third-party dependencies such as `jsonschema`.

---

## 3. Background & Context

The SDK already has an eval subsystem under `vidbyte/evals/` with `EvalCase`, `EvalSuite`, `EvalRunner`, SQLite-backed `EvalRegistry`, and built-in graders: exact match, contains, regex, JSON schema, LLM judge, and rubric. The current design is grader-centric: a case can provide one `grader`, otherwise the runner uses `default_grader`.

The requested feature is not another set of one-grader aliases. The useful addition is a case-level `templates` policy that lets users choose prebuilt grading bundles such as "short factual answer", "structured JSON response", or "safe customer support answer". Each bundle should expand into multiple graders where useful, while still relying on the existing `BaseGrader` contract.

The repo conventions require SDK eval work to stay under `vidbyte/evals/`, with public exports in `vidbyte/evals/__init__.py` and `vidbyte/__init__.py`, tests in `tests/test_evals.py`, docs in `README.md`, `vidbyte/evals/README.md`, `llms.txt`, and guidance in `skills/vidbyte-sdk/evals.md`. Current tests use `unittest.IsolatedAsyncioTestCase`, and feature verification scripts live in `scripts/`.

The current working tree has unrelated generated `__pycache__` changes and untracked local artifacts. The implementation phase must use an isolated worktree after approval and must not clean or revert those unrelated changes.

---

## 4. Requirements

### Functional Requirements

1. `EvalCase` must accept a new `templates` parameter containing zero or more eval template instances or template specs.
2. Existing `EvalCase(prompt=..., expected=..., grader=...)` behavior must continue unchanged.
3. If `case.grader` is present, the runner must use it and ignore `case.templates` for grading precedence.
4. If `case.grader` is absent and `case.templates` is non-empty, the runner must resolve templates into a single `BaseGrader`.
5. If both `case.grader` and `case.templates` are absent, the runner must use `EvalRunner.default_grader` exactly as it does today.
6. Multiple templates on one case must be composed using `AllOfGrader` by default.
7. `AllOfGrader` must pass only when all child graders pass and must score as the arithmetic mean of child scores.
8. `AnyOfGrader` must pass when at least one child grader passes and must score as the maximum child score.
9. `WeightedGrader` must compute a weighted average and pass when the weighted score is at least a configurable threshold.
10. Prebuilt templates must be exposed from `vidbyte.evals.templates` and importable from `vidbyte.evals`.
11. Users must be able to create custom templates by subclassing `EvalTemplate` and implementing `build_grader()`.
12. The template registry must resolve string names and JSON specs into template instances.
13. `EvalSuite.from_json()` must load a `templates` field from each case.
14. JSON suite loading must continue to support existing cases with no `templates` field.
15. `EvalCase.expected` must be widened from `str | None` to `Any | None` so templates can grade strings, numbers, JSON objects, arrays, and label sets.
16. Existing string graders must continue to treat non-string `expected` values defensively by stringifying only when appropriate or returning a failed result with a clear reason.
17. `EvalRegistry` must persist structured `expected` values by JSON-encoding them when needed, while preserving old string expected values on read.
18. The prebuilt template list for this PR must include:
    - `ShortAnswerFactTemplate`
    - `MultipleChoiceTemplate`
    - `StructuredJsonTemplate`
    - `ClassificationTemplate`
    - `NumericAnswerTemplate`
    - `ConciseGroundedAnswerTemplate`
    - `SafeCustomerSupportTemplate`
19. Supporting deterministic graders must be added where existing graders are not enough:
    - `CompositeGrader` family: `AllOfGrader`, `AnyOfGrader`, `WeightedGrader`
    - `ContainsAllGrader`
    - `ForbiddenContentGrader`
    - `LengthGrader`
    - `ChoiceMatchGrader`
    - `NumericMatchGrader`
    - `JSONExactMatchGrader`
    - `JSONSubsetGrader`
20. The prebuilt templates must be deterministic and must not call an LLM unless a user explicitly builds a custom LLM-backed template.
21. Template failures must become failed `GraderResult` values through existing runner error handling, not crash the whole suite.
22. Public documentation must show Python usage and JSON suite usage for prebuilt templates and custom templates.

### Non-Functional Requirements

- Performance: template resolution should be O(number of templates + number of child graders) per case and should not add network latency.
- Reliability: malformed template specs in JSON suites must fail at suite load time with clear `ValueError` messages.
- Backward compatibility: existing eval tests and existing user code using `grader` must keep passing.
- Security: deterministic templates must not execute arbitrary code from JSON specs; the registry must map only known template names to constructors.
- Observability: composite grader reasons must include which child grader names passed or failed so users can debug template behavior.
- Maintainability: each new grader must remain a small `BaseGrader` subclass with focused tests.

---

## 5. High-Level Design

The feature adds a template layer above graders. Graders remain the only components that score output. Templates are reusable factories that build graders, usually composite graders, from case-level expectations and template options.

Data flow:

```text
EvalCase(prompt, expected, templates)
        |
        v
EvalRunner._resolve_grader(case)
        |
        +-- case.grader exists -> use existing grader
        +-- templates exist -> EvalTemplateResolver -> Composite/BaseGrader
        +-- otherwise -> default_grader
        |
        v
BaseGrader.agrade(case, actual)
        |
        v
GraderResult(score, passed, reason)
```

The central design decision is to make `templates` a case-level grading policy, not a replacement for `BaseGrader`. This keeps advanced users on the current low-level API and gives newer users compact prebuilt templates for common tasks.

The second design decision is to keep template composition deterministic. `templates=[T.short_answer_fact(), T.safe_customer_support()]` means both templates must pass. Users who need looser or weighted behavior can choose explicit `AnyOfTemplate` or `WeightedTemplate` helpers.

---

## 6. Detailed Design

### 6.1 Eval Template Base Contract

**File(s):** `vidbyte/evals/templates/base.py`
**Type:** New file

#### What it does

Defines the public template protocol and reusable base class used by prebuilt and custom templates.

#### Interface / API

```python
class EvalTemplate:
    name: ClassVar[str] = "template"
    description: ClassVar[str] = ""

    def build_grader(self) -> BaseGrader:
        # Builds the concrete grader used to score a case.
        raise NotImplementedError
```

#### Logic / Algorithm

1. `EvalTemplate.build_grader()` returns a `BaseGrader`.
2. Simple templates can return a single grader.
3. Prebuilt templates generally return `AllOfGrader`, `AnyOfGrader`, or `WeightedGrader`.

#### Edge Cases & Error Handling

- A template returning a non-`BaseGrader` value is rejected by the resolver with `TypeError`.
- A template with no child graders is rejected by composite grader constructors.

### 6.2 Template Registry and Resolver

**File(s):** `vidbyte/evals/templates/registry.py`
**Type:** New file

#### What it does

Maps known template names to constructors and resolves Python and JSON template specs.

#### Interface / API

```python
class EvalTemplateRegistry:
    def register(self, name: str, factory: Callable[..., EvalTemplate]) -> None:
        # Registers a named template factory for Python and JSON suite resolution.

    def create(self, spec: str | Mapping[str, Any] | EvalTemplate) -> EvalTemplate:
        # Resolves a string, mapping, or existing template into an EvalTemplate.

    def build_grader(self, templates: Sequence[EvalTemplate]) -> BaseGrader:
        # Builds one grader from a sequence of templates using all-of composition by default.
```

#### Logic / Algorithm

1. Existing `EvalTemplate` instances are returned as-is.
2. String specs resolve by registered name using default options.
3. Mapping specs must include `name`; optional `options` must be a mapping.
4. One resolved template builds directly to its grader.
5. Multiple resolved templates build into `AllOfGrader`.

#### Edge Cases & Error Handling

- Unknown template names raise `ValueError("Unknown eval template: ...")`.
- Mapping specs without `name` raise `ValueError`.
- Non-mapping `options` raise `ValueError`.
- Registry registration of duplicate names raises `ValueError` to avoid accidental override.

### 6.3 Prebuilt Template Bundles

**File(s):** `vidbyte/evals/templates/builtins.py`
**Type:** New file

#### What it does

Provides prebuilt templates that encode common eval intents as multi-grader bundles.

#### Interface / API

```python
class ShortAnswerFactTemplate(EvalTemplate): ...
class MultipleChoiceTemplate(EvalTemplate): ...
class StructuredJsonTemplate(EvalTemplate): ...
class ClassificationTemplate(EvalTemplate): ...
class NumericAnswerTemplate(EvalTemplate): ...
class ConciseGroundedAnswerTemplate(EvalTemplate): ...
class SafeCustomerSupportTemplate(EvalTemplate): ...
```

Convenience factory functions:

```python
def short_answer_fact(*, max_chars: int = 240) -> EvalTemplate: ...
def multiple_choice(*, choices: Sequence[str] = ("A", "B", "C", "D"), max_chars: int = 32) -> EvalTemplate: ...
def structured_json(*, schema: Mapping[str, Any] | None = None, require_subset: bool = True) -> EvalTemplate: ...
def classification(*, labels: Sequence[str], max_chars: int = 120) -> EvalTemplate: ...
def numeric_answer(*, tolerance: float = 0.0, max_chars: int = 120) -> EvalTemplate: ...
def concise_grounded_answer(*, required_terms: Sequence[str] = (), forbidden_terms: Sequence[str] = (), max_chars: int = 800) -> EvalTemplate: ...
def safe_customer_support(*, forbidden_terms: Sequence[str] = DEFAULT_SUPPORT_FORBIDDEN, max_chars: int = 1000) -> EvalTemplate: ...
```

#### Logic / Algorithm

- `ShortAnswerFactTemplate`: `AllOfGrader([ContainsGrader(), LengthGrader(max_chars=max_chars)])`
- `MultipleChoiceTemplate`: `AllOfGrader([ChoiceMatchGrader(choices=choices), LengthGrader(max_chars=max_chars)])`
- `StructuredJsonTemplate`: `AllOfGrader([JSONSchemaGrader(schema), JSONSubsetGrader(), ForbiddenContentGrader(["```"])])` when schema is provided and subset is required; omit absent parts.
- `ClassificationTemplate`: `AllOfGrader([ChoiceMatchGrader(choices=labels), LengthGrader(max_chars=max_chars)])`
- `NumericAnswerTemplate`: `AllOfGrader([NumericMatchGrader(tolerance=tolerance), LengthGrader(max_chars=max_chars)])`
- `ConciseGroundedAnswerTemplate`: `AllOfGrader([ContainsAllGrader(required_terms), ForbiddenContentGrader(forbidden_terms), LengthGrader(max_chars=max_chars)])`
- `SafeCustomerSupportTemplate`: `AllOfGrader([ContainsGrader(), ForbiddenContentGrader(forbidden_terms), LengthGrader(max_chars=max_chars)])`

#### Edge Cases & Error Handling

- Empty label or choice lists raise `ValueError`.
- Negative lengths and negative numeric tolerances raise `ValueError`.
- `StructuredJsonTemplate` requires at least schema, subset checking, or exact checking; an empty JSON template raises `ValueError`.

### 6.4 Composite Graders

**File(s):** `vidbyte/evals/graders/composite.py`
**Type:** New file

#### What it does

Provides grader composition primitives used by templates and available to advanced users.

#### Interface / API

```python
class AllOfGrader(BaseGrader): ...
class AnyOfGrader(BaseGrader): ...
class WeightedGrader(BaseGrader): ...
```

#### Logic / Algorithm

1. Each composite grader calls child `agrade(case, actual)` methods in order.
2. `AllOfGrader` passes only if all children pass and averages scores.
3. `AnyOfGrader` passes if any child passes and uses the maximum score.
4. `WeightedGrader` normalizes weights, computes a weighted score, and passes if score is at least `threshold`.
5. Reasons include each child class/name and pass/fail status.

#### Edge Cases & Error Handling

- Empty child lists raise `ValueError`.
- Negative weights raise `ValueError`.
- Zero total weight raises `ValueError`.
- Child grader exceptions are allowed to propagate to the runner, preserving existing failed-case behavior.

### 6.5 Supporting Deterministic Graders

**File(s):** `vidbyte/evals/graders/contains_all.py`, `vidbyte/evals/graders/forbidden_content.py`, `vidbyte/evals/graders/length.py`, `vidbyte/evals/graders/choice_match.py`, `vidbyte/evals/graders/numeric_match.py`, `vidbyte/evals/graders/json_match.py`
**Type:** New files

#### What it does

Adds missing small deterministic graders needed for multi-grader templates.

#### Interface / API

```python
class ContainsAllGrader(BaseGrader): ...
class ForbiddenContentGrader(BaseGrader): ...
class LengthGrader(BaseGrader): ...
class ChoiceMatchGrader(BaseGrader): ...
class NumericMatchGrader(BaseGrader): ...
class JSONExactMatchGrader(BaseGrader): ...
class JSONSubsetGrader(BaseGrader): ...
```

#### Logic / Algorithm

- `ContainsAllGrader`: all required terms must be present in `actual`.
- `ForbiddenContentGrader`: no forbidden term may be present in `actual`.
- `LengthGrader`: output length must satisfy optional `min_chars` and `max_chars`.
- `ChoiceMatchGrader`: extracts a single label from `actual` and compares to `case.expected`.
- `NumericMatchGrader`: parses the first numeric value in `actual` or the full string and compares to numeric `case.expected` within tolerance.
- `JSONExactMatchGrader`: parses both `actual` and `case.expected` as JSON-compatible values and compares normalized structures.
- `JSONSubsetGrader`: parses `actual` and verifies `case.expected` is recursively contained within it.

#### Edge Cases & Error Handling

- Malformed JSON returns a failed `GraderResult`, not an exception.
- Missing numeric value returns a failed `GraderResult`.
- Case-insensitive string checks are defaults, matching existing `ContainsGrader`.
- Empty forbidden lists pass.
- Empty required term lists pass only when intentionally constructed; prebuilt templates should avoid accidental empty required checks when they need real assertions.

### 6.6 EvalCase Data Model

**File(s):** `vidbyte/evals/types.py`
**Type:** Modified

#### What it does

Adds `templates` to `EvalCase` and widens `expected`.

#### Interface / API

```python
@dataclass(frozen=True)
class EvalCase:
    prompt: str
    expected: Any | None = None
    tags: tuple[str, ...] = ()
    grader: BaseGrader | None = None
    templates: tuple[EvalTemplate | str | Mapping[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Keep dataclass frozen.
2. Add `templates` after `grader` to reduce positional-argument disruption.
3. Use `TYPE_CHECKING` imports to avoid runtime circular imports.

#### Edge Cases & Error Handling

- Existing positional calls with the current five fields remain dangerous if users pass metadata positionally. Public docs use keyword arguments; this change will be documented as keyword-preferred.

### 6.7 EvalRunner Grader Resolution

**File(s):** `vidbyte/evals/runner.py`
**Type:** Modified

#### What it does

Resolves case templates into a grader before grading.

#### Interface / API

```python
def _resolve_grader(self, case: EvalCase) -> BaseGrader:
    # Resolves a grader from case.grader, case.templates, or the runner default.
```

#### Logic / Algorithm

1. In `_run_single_case`, call `_resolve_grader(case)`.
2. `_resolve_grader` returns `case.grader` first.
3. If no grader and templates exist, resolve and compose templates through the default registry.
4. Otherwise return `self.default_grader`.

#### Edge Cases & Error Handling

- Bad template specs raise during grading if supplied programmatically and become failed case results through existing exception handling.
- JSON-suite bad specs should fail earlier during `from_json()`.

### 6.8 EvalSuite JSON Loading

**File(s):** `vidbyte/evals/suite.py`
**Type:** Modified

#### What it does

Loads template specs from JSON eval suite files.

#### Interface / API

```python
@classmethod
def from_json(cls, path: str | Path) -> EvalSuite:
    # Loads cases, expected values, tags, metadata, and template specs from JSON.
```

#### Logic / Algorithm

1. Preserve existing `name`, `cases`, `prompt`, `expected`, `tags`, and `metadata` behavior.
2. If a case includes `template`, normalize it to one template spec.
3. If a case includes `templates`, normalize it to a tuple of specs.
4. Validate specs through `EvalTemplateRegistry.create()` at load time.
5. Store resolved template instances on `EvalCase.templates`.

#### Edge Cases & Error Handling

- If both `template` and `templates` are present, raise `ValueError`.
- If `templates` is not a list, raise `ValueError`.
- Existing suites without templates load unchanged.

### 6.9 Registry Serialization

**File(s):** `vidbyte/evals/registry.py`
**Type:** Modified

#### What it does

Persists structured `expected` values without changing the SQLite table shape.

#### Interface / API

```python
class EvalExpectedSerializer:
    def dumps(self, expected: Any | None) -> str | None:
        # Serializes expected values for SQLite TEXT storage.

    def loads(self, raw: str | None) -> Any | None:
        # Restores serialized expected values when possible.
```

#### Logic / Algorithm

1. Strings are stored as-is for backward compatibility.
2. Non-string JSON-serializable values are stored with a small sentinel prefix, for example `__vidbyte_json__:` plus JSON.
3. Reads detect the sentinel and decode JSON.
4. Old rows without the sentinel remain strings.

#### Edge Cases & Error Handling

- Non-JSON-serializable expected values fall back to `str(expected)` with a reason documented in code comments, or raise `TypeError` during record; implementation should choose the clearer user-facing failure.
- Corrupt sentinel payloads return the raw string rather than crashing historical registry reads.

### 6.10 Public Exports

**File(s):** `vidbyte/evals/graders/__init__.py`, `vidbyte/evals/templates/__init__.py`, `vidbyte/evals/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified and new file

#### What it does

Exports new graders and templates through the existing public import surfaces.

#### Interface / API

```python
from vidbyte.evals import EvalTemplate, ShortAnswerFactTemplate
from vidbyte.evals import AllOfGrader, ForbiddenContentGrader
from vidbyte.evals import templates as T
```

#### Logic / Algorithm

1. Export concrete graders from `vidbyte.evals.graders`.
2. Export templates package symbols from `vidbyte.evals.templates`.
3. Import the templates package in `vidbyte.evals` so `from vidbyte.evals import templates as T` works.
4. Add selected stable templates and graders to root `vidbyte` exports.

#### Edge Cases & Error Handling

- Avoid wildcard side effects that register templates multiple times. Registry setup must be idempotent.

### 6.11 Documentation and Skill Updates

**File(s):** `README.md`, `llms.txt`, `vidbyte/evals/README.md`, `skills/vidbyte-sdk/evals.md`
**Type:** Modified

#### What it does

Documents the new `templates` API, prebuilt bundles, JSON suite syntax, and custom template extension pattern.

#### Interface / API

```python
from vidbyte.evals import EvalCase, EvalSuite, EvalRunner
from vidbyte.evals import templates as T
```

#### Logic / Algorithm

1. Add a short `EvalCase.templates` example.
2. Add a JSON suite example using `templates`.
3. Update the grader catalog with new deterministic graders.
4. Add a template catalog with intent-based prebuilt bundles.

#### Edge Cases & Error Handling

- Docs must distinguish eval templates from prompt templates and context-window templates to avoid namespace confusion.

### 6.12 Tests and Verification Script

**File(s):** `tests/test_evals.py`, `scripts/test-eval-template-bundles.py`
**Type:** Modified and new file

#### What it does

Adds tests for template resolution, composite scoring, new deterministic graders, JSON suite loading, and registry structured expected persistence.

#### Interface / API

```powershell
python -m unittest tests.test_evals
python scripts/test-eval-template-bundles.py
```

#### Logic / Algorithm

1. Extend `EvalTests` with template-specific methods.
2. Add script runner that imports `EvalTests` and executes every relevant test method with PASS/FAIL output.
3. The script exits non-zero on failures.

#### Edge Cases & Error Handling

- The script must include all Section 10 cases either directly or by loading the test class that contains them.

---

## 7. Data Model Changes

### 7.1 EvalCase

**Change type:** Modified

```python
@dataclass(frozen=True)
class EvalCase:
    prompt: str
    expected: Any | None = None
    tags: tuple[str, ...] = ()
    grader: BaseGrader | None = None
    templates: tuple[EvalTemplate | str | Mapping[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Migration strategy:** Existing code with keyword arguments remains compatible. Existing code with positional arguments past `grader` may bind differently if it relied on dataclass positional construction; docs will emphasize keyword usage.

### 7.2 EvalRegistry expected storage

**Change type:** Modified

```sql
-- No table shape change.
-- eval_results.expected remains TEXT.
```

**Migration strategy:**

- Forward migration: N/A - existing table is reused. New structured expected values use a sentinel-prefixed JSON string.
- Rollback plan: Older code will see sentinel-prefixed strings for structured expectations but will not lose rows.

---

## 8. API Changes

### 8.1 Python SDK EvalCase Constructor

**Change type:** Modified

**Request:**

```python
EvalCase(
    prompt="What is our refund window?",
    expected="30 days",
    templates=(T.short_answer_fact(), T.safe_customer_support()),
)
```

**Response:**

```python
EvalResult(
    case=case,
    actual="Refunds are available within 30 days.",
    grader_result=GraderResult(score=1.0, passed=True, reason="..."),
    latency_ms=...
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Unknown template names raise `ValueError` during suite loading or failed case results during runner execution. |
| N/A | Bad template options raise `ValueError`. |
| N/A | Template child grader exceptions become failed case results in `EvalRunner`. |

### 8.2 JSON Eval Suite Case Schema

**Change type:** Modified

**Request:**

```json
{
  "prompt": "Return routing JSON.",
  "expected": { "category": "billing" },
  "templates": [
    {
      "name": "structured_json",
      "options": {
        "schema": {
          "type": "object",
          "required": ["category"],
          "properties": {
            "category": { "type": "string" }
          }
        },
        "require_subset": true
      }
    }
  ],
  "tags": ["routing"]
}
```

**Response:**

```python
EvalCase(prompt="Return routing JSON.", expected={"category": "billing"}, templates=(StructuredJsonTemplate(...),), tags=("routing",))
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Both `template` and `templates` are present. |
| N/A | `templates` is not a list. |
| N/A | Template spec is missing `name`. |
| N/A | Template `options` is not an object. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/eval-template-bundles.md` | Design document and implementation source of truth |
| CREATE | `vidbyte/evals/templates/__init__.py` | Public exports for eval templates |
| CREATE | `vidbyte/evals/templates/base.py` | `EvalTemplate` base contract |
| CREATE | `vidbyte/evals/templates/builtins.py` | Prebuilt multi-grader template bundles |
| CREATE | `vidbyte/evals/templates/registry.py` | Template registry and JSON spec resolver |
| CREATE | `vidbyte/evals/graders/composite.py` | `AllOfGrader`, `AnyOfGrader`, `WeightedGrader` |
| CREATE | `vidbyte/evals/graders/contains_all.py` | Required-term deterministic grader |
| CREATE | `vidbyte/evals/graders/forbidden_content.py` | Forbidden-term deterministic grader |
| CREATE | `vidbyte/evals/graders/length.py` | Output length deterministic grader |
| CREATE | `vidbyte/evals/graders/choice_match.py` | Multiple-choice and label extraction grader |
| CREATE | `vidbyte/evals/graders/numeric_match.py` | Numeric tolerance grader |
| CREATE | `vidbyte/evals/graders/json_match.py` | JSON exact and subset graders |
| CREATE | `scripts/test-eval-template-bundles.py` | Feature verification script |
| MODIFY | `vidbyte/evals/types.py` | Add `templates` to `EvalCase` and widen `expected` |
| MODIFY | `vidbyte/evals/runner.py` | Resolve templates into graders |
| MODIFY | `vidbyte/evals/suite.py` | Load template specs from JSON suites |
| MODIFY | `vidbyte/evals/registry.py` | Serialize structured `expected` values |
| MODIFY | `vidbyte/evals/graders/__init__.py` | Export new graders |
| MODIFY | `vidbyte/evals/__init__.py` | Export templates and new graders |
| MODIFY | `vidbyte/__init__.py` | Root exports for stable public API |
| MODIFY | `tests/test_evals.py` | Add template, composite, and structured expected tests |
| MODIFY | `vidbyte/evals/README.md` | Document eval template bundles |
| MODIFY | `README.md` | Public docs for template usage |
| MODIFY | `llms.txt` | LLM-facing package docs for templates |
| MODIFY | `skills/vidbyte-sdk/evals.md` | Contributor guidance for templates and new graders |

---

## 10. Testing Plan

### Unit Tests

- `EvalCase` -> `test_eval_case_accepts_templates` [Edge Case]: empty `templates` defaults to an empty tuple and existing cases still construct.
- `EvalCase` -> `test_eval_case_accepts_structured_expected` [Hidden Assumption]: `expected` can be a dict, list, number, or string without dataclass failure.
- `EvalRunner` -> `test_grader_takes_precedence_over_templates` [Silent Failure]: when both `grader` and `templates` are set, a failing explicit grader must not be masked by passing templates.
- `EvalRunner` -> `test_templates_fallback_before_default_grader` [Silent Failure]: when templates exist, the default grader must not be used.
- `EvalRunner` -> `test_default_grader_preserved_without_templates` [Hidden Assumption]: legacy cases still grade with `default_grader`.
- `AllOfGrader` -> `test_all_of_requires_all_children` [Silent Failure]: one failed child yields failed composite and mean score.
- `AllOfGrader` -> `test_all_of_rejects_empty_children` [Edge Case]: constructor raises `ValueError`.
- `AnyOfGrader` -> `test_any_of_passes_when_one_child_passes` [Silent Failure]: one pass yields pass and max score.
- `WeightedGrader` -> `test_weighted_score_and_threshold` [Silent Failure]: weighted math is exact and threshold is respected.
- `WeightedGrader` -> `test_weighted_rejects_zero_total_weight` [Edge Case]: zero total weight raises `ValueError`.
- `ContainsAllGrader` -> `test_contains_all_required_terms` [Silent Failure]: missing one required term fails.
- `ContainsAllGrader` -> `test_contains_all_case_insensitive` [Hidden Assumption]: casing does not cause false failures by default.
- `ForbiddenContentGrader` -> `test_forbidden_content_blocks_terms` [Silent Failure]: forbidden term fails the output.
- `ForbiddenContentGrader` -> `test_forbidden_content_empty_list_passes` [Edge Case]: empty forbidden list passes.
- `LengthGrader` -> `test_length_bounds` [Edge Case]: values at min and max boundaries pass, one over max fails.
- `ChoiceMatchGrader` -> `test_choice_match_parses_common_formats` [Edge Case]: `A`, `A.`, `(A)`, and `The answer is A` parse correctly.
- `ChoiceMatchGrader` -> `test_choice_match_rejects_multiple_labels` [Silent Failure]: output containing multiple labels fails when single answer is required.
- `NumericMatchGrader` -> `test_numeric_match_with_tolerance` [Silent Failure]: numeric tolerance math is correct.
- `NumericMatchGrader` -> `test_numeric_match_missing_number_fails` [Hidden Failure]: output with no numeric token returns failed result, not pass or exception.
- `JSONExactMatchGrader` -> `test_json_exact_ignores_key_order` [Silent Failure]: object key order does not affect equality.
- `JSONExactMatchGrader` -> `test_json_exact_malformed_actual_fails` [Hidden Failure]: malformed JSON returns failed result.
- `JSONSubsetGrader` -> `test_json_subset_nested_object` [Silent Failure]: nested expected object must be contained recursively.
- `JSONSubsetGrader` -> `test_json_subset_array_mismatch_fails` [Edge Case]: list length/order mismatch is handled deterministically.
- `EvalTemplateRegistry` -> `test_registry_resolves_string_template` [Hidden Assumption]: registered built-in names create the expected template.
- `EvalTemplateRegistry` -> `test_registry_rejects_unknown_template` [Hidden Failure]: unknown name raises `ValueError`.
- `EvalTemplateRegistry` -> `test_registry_rejects_bad_options_shape` [Hidden Failure]: non-object options raise `ValueError`.
- `EvalTemplateRegistry` -> `test_custom_template_builds_grader` [Hidden Assumption]: user subclasses of `EvalTemplate` can be used without registry registration.
- `ShortAnswerFactTemplate` -> `test_short_answer_fact_bundle` [Silent Failure]: expected answer plus length passes, overly long answer fails.
- `MultipleChoiceTemplate` -> `test_multiple_choice_bundle` [Silent Failure]: correct choice passes, verbose multi-choice answer fails.
- `StructuredJsonTemplate` -> `test_structured_json_bundle` [Hidden Failure]: valid schema plus expected subset passes and fenced markdown fails.
- `ClassificationTemplate` -> `test_classification_bundle` [Silent Failure]: only allowed labels pass.
- `NumericAnswerTemplate` -> `test_numeric_answer_bundle` [Silent Failure]: expected numeric value within tolerance passes.
- `ConciseGroundedAnswerTemplate` -> `test_concise_grounded_bundle` [Silent Failure]: all required facts must appear and forbidden facts must not.
- `SafeCustomerSupportTemplate` -> `test_safe_customer_support_bundle` [Silent Failure]: expected answer passes while internal/confidential leakage fails.

### Integration Tests

- `EvalSuite.from_json` -> `test_from_json_loads_single_template` [Hidden Assumption]: JSON `template` creates one template instance.
- `EvalSuite.from_json` -> `test_from_json_loads_multiple_templates` [Hidden Assumption]: JSON `templates` creates multiple template instances.
- `EvalSuite.from_json` -> `test_from_json_rejects_template_and_templates_together` [Hidden Failure]: ambiguous input raises `ValueError`.
- `EvalSuite.from_json` -> `test_from_json_legacy_suite_still_loads` [Hidden Assumption]: existing JSON suites without templates load unchanged.
- `EvalRunner` -> `test_runner_executes_template_case_end_to_end` [Hidden Failure]: mock runner output is graded through template composition.
- `EvalRegistry` -> `test_registry_roundtrips_structured_expected` [Silent Failure]: dict/list numeric expected values record and reload correctly.
- `Public exports` -> `test_template_import_surfaces` [Hidden Failure]: imports work from `vidbyte.evals`, `vidbyte.evals.templates`, and root `vidbyte` for selected exports.
- `Verification script` -> `test_script_runs_template_tests` [Hidden Assumption]: `python scripts/test-eval-template-bundles.py` exits 0 after all template tests pass.

### Manual / QA Test Cases

1. Given a Python suite with `EvalCase(templates=[T.short_answer_fact()])`, when run against a mock runner returning the expected term, then the case passes. [Edge Case]
2. Given a Python suite with `EvalCase(grader=ExactMatchGrader(), templates=[T.short_answer_fact()])`, when the exact grader fails but the template would pass, then the case fails because explicit grader precedence is preserved. [Silent Failure]
3. Given a JSON suite with `"templates": [{"name": "structured_json", "options": {"schema": {...}}}]`, when loaded with `EvalSuite.from_json`, then the case contains a structured JSON template and runs successfully. [Hidden Assumption]
4. Given a JSON suite with an unknown template name, when loaded, then `ValueError` names the unknown template. [Hidden Failure]
5. Given a registry result containing `expected={"category": "billing"}`, when recorded and read through `latest`, then `expected` is restored as a dict. [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `json` | Built-in | Parse and serialize JSON outputs and expected values | Low; malformed JSON must be handled as failed grading |
| Python standard library `re` | Built-in | Choice and numeric extraction | Low; regexes must be simple and deterministic |
| Existing `pydantic` dependency | `>=2,<3` | No new usage planned | N/A |
| External network services | N/A | Not used | N/A |

---

## 12. Rollout & Deployment

- This is a backward-compatible SDK addition.
- No feature flag is required.
- No database migration is required because `eval_results.expected` remains `TEXT`.
- Rollout order:
  1. Add deterministic graders and composite graders.
  2. Add template base, registry, and built-ins.
  3. Wire `EvalCase`, `EvalRunner`, and `EvalSuite.from_json`.
  4. Update exports and docs.
  5. Add tests and verification script.
- Rollback procedure: revert the feature PR. Existing registry rows created with structured expected sentinels would remain as strings under older code.

---

## 13. Open Questions

- [ ] Should root `vidbyte` export all templates or only `EvalTemplate` plus the `templates` module? Recommendation: export the module and core base class only to keep root namespace smaller.
- [ ] Should `EvalCase.templates` accept raw strings programmatically, or only `EvalTemplate` instances in Python and strings in JSON? Recommendation: accept both for convenience but resolve eagerly in runner/suite.
- [ ] Should `StructuredJsonTemplate` forbid Markdown fences by default? Recommendation: yes for raw JSON evals, with an option to disable.
- [ ] Should `SafeCustomerSupportTemplate` include an LLM judge for tone? Recommendation: no in this PR; keep deterministic and add LLM-backed templates later.

---

## 14. Alternatives Considered

### Alternative 1: Make templates one-to-one aliases for graders

- What: Add `T.includes()` and `T.regex()` as thin wrappers around existing graders.
- Why rejected: The user clarified that the value is prebuilt templates made of multiple graders, not aliases for already-existing grader primitives.

### Alternative 2: Put all template logic inside `vidbyte/evals/graders/`

- What: Treat templates as special composite graders and skip a `templates` package.
- Why rejected: It blurs the distinction between scoring engines and reusable user-facing presets. A `templates` package gives users a clear extension point while keeping actual scoring in `graders`.

### Alternative 3: Replace `grader` with `templates`

- What: Make all cases use templates and remove direct graders.
- Why rejected: Existing SDK users rely on `grader`, and advanced users should still be able to inject custom `BaseGrader` implementations directly.

### Alternative 4: Store template specs in the registry

- What: Persist template names/options alongside eval results.
- Why rejected: The current registry persists run outputs and result summaries, not full suite definitions. Template persistence can be added later if the registry becomes a suite catalog.


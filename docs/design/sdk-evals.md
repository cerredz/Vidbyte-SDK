<!-- Context Protocol Header
Description:
    Design document outlining the first-class Eval SDK harness (vidbyte.evals) for Vidbyte SDK.
Purpose:
    Establishes the architecture, interface contracts, persistence model, and prebuilt graders
    to evaluate, grade, persist, and compare outputs from agents, strategies, and runners.
Architecture:
    - Target evaluation runner mapping (EvalRunner) with concurrency control.
    - Standardized grader interface (BaseGrader) and prebuilt library (ExactMatch, Contains, Regex, LLMJudge, Rubric, JSONSchema).
    - Portability & persistence layer using local SQLite (EvalRegistry).
    - Namespace integration (EvalClient) mounted on VidbyteSDK.
Relations:
    Acts as the design blueprint for all files under vidbyte/evals/ and tests/test_evals.py.
-->

# Design Doc: First-Class SDK Evals Harness (vidbyte.evals)

**Status:** Draft  
**Author:** Antigravity  
**Created:** 2026-05-26  
**Last Updated:** 2026-05-26  

---

## 1. Overview

This feature implements `vidbyte.evals`, a first-class SDK primitive for running, scoring, persisting, and comparing LLM and agent outputs. Designed to align with the core patterns of the Vidbyte SDK, it provides a clean, async-first harness for running assertions against any SDK target (e.g. raw runners, `BaseAgent` instances, or `BaseStrategy` chains) using composable graders and a local SQLite-backed persistent registry.

---

## 2. Goals & Non-Goals

### Goals
- Establish a standardized, async-first `BaseGrader` contract.
- Build a prebuilt library of graders including `ExactMatchGrader`, `ContainsGrader`, `RegexMatchGrader`, `JSONSchemaGrader`, `LLMJudgeGrader`, and `RubricGrader`.
- Integrate LLM-graded prompt templates into `vidbyte.prompts`.
- Implement `EvalRunner` that supports concurrency control via `asyncio.Semaphore` and isolates stateful `BaseAgent` instances per run using `fork()`.
- Implement `EvalSuite` that manages a collection of `EvalCase` records with support for loading from JSON and filtering by tags.
- Design `EvalRegistry` that persists execution results locally inside SQLite (`.vidbyte_evals.db`) and supports comparative reports.
- Mount `EvalClient` on the main `VidbyteSDK` class under `sdk.evals`.

### Non-Goals
- Multi-turn evaluation cases (stateless single-turn evaluation is canonical for v1).
- Remote/cloud-based evaluation storage (SQLite-only local storage is the sole scope).
- CLI evaluation runner interface (focusing entirely on a clean Python SDK API).
- Semantic embedding similarity graders (out of scope to avoid adding large vector/embedding model package dependencies in v1).

---

## 3. Background & Context

As AI engineering shifts from heuristic-driven to benchmark-driven iteration, developers must define "good" based on their specific product needs. Instead of relying on generalized public benchmarks, teams should be able to run local custom evaluations to select the right model, prompt, or reasoning strategy. 
By incorporating a model routing and evaluation primitive directly inside `vidbyte-sdk`, developers can easily measure performance metrics (correctness, pass rates, and latency) across distinct strategy and model revisions, persisting results to compare model versions over time.

---

## 4. Requirements

### Functional Requirements
1. The harness must accept any executable target (e.g., `BaseAgent`, `BaseStrategy`, or raw runner) and execute test cases asynchronously.
2. If the target is a `BaseAgent`, it must call `.fork()` before each case to avoid cross-contamination of conversation history.
3. Every grader must inherit from `BaseGrader` and provide both an async `agrade()` and a synchronous `grade()` method.
4. Prebuilt graders must support:
   - String exact matching (with case sensitivity and stripping controls).
   - Substring existence checking (`ContainsGrader`).
   - Regular expression pattern matching (`RegexMatchGrader`).
   - Structural schema validation (`JSONSchemaGrader`).
   - Open-ended LLM-graded assertions (`LLMJudgeGrader` using a separate judge model runner).
   - Weighted multidimensional grading rubrics (`RubricGrader`).
5. Prompt templates used by LLM judges must be declared in `vidbyte/prompts/prompts/evals.json` and registered under the `Prompt` enum.
6. The concurrency rate of async case execution must be configurable (defaulting to 4 concurrent runners) using `asyncio.Semaphore`.
7. `EvalRegistry` must write results to a local SQLite database (`.vidbyte_evals.db`) and be capable of producing comparison metrics between two models or strategy versions.

### Non-Functional Requirements
- **Performance**: High concurrency support during evaluations without dropping connections. Low overhead when saving or querying results from SQLite.
- **Reliability**: Isolated case failures must not crash the entire suite execution. The runner should catch and record errors per case gracefully.
- **Security**: The evaluation SQLite database should reside within the execution scope and respect read/write permissions.

---

## 5. High-Level Design

The `vidbyte.evals` module resides directly inside the main `vidbyte` package. It consists of the following components:

- **types.py**: Load-bearing data models (`EvalCase`, `GraderResult`, `EvalResult`, `EvalSuiteResult`).
- **base.py**: Standardized `BaseGrader` abstract base class.
- **runner.py**: `EvalRunner` class executing suites against target agents or strategies asynchronously.
- **suite.py**: `EvalSuite` loading, filtering, and managing lists of `EvalCase` records.
- **registry.py**: SQLite database manager `EvalRegistry` that records runs and generates delta reports.
- **client.py**: Top-level entry point `EvalClient` exposed under `sdk.evals`.
- **graders/**: Directory containing concrete implementations of the grader library.

### Architecture Data Flow Diagram:
```text
[User Code] -> [EvalClient]
                   |
             Creates / Loads
                   v
  [EvalSuite]    ----> [EvalRunner]  ----> Runs target asynchronously (Semaphore & Fork)
  (List of cases)           |
                            v
                    [BaseGrader Subclass] -> Grades output -> [EvalSuiteResult]
                                                                    |
                                                                    v
                                                            [EvalRegistry (SQLite)]
```

---

## 6. Detailed Design

### 6.1 Data Models (types.py)
**File:** `vidbyte/evals/types.py`  
**Type:** New file

#### Interface / API
```python
@dataclass(frozen=True)
class EvalCase:
    prompt: str
    expected: str | None = None
    tags: tuple[str, ...] = ()
    grader: BaseGrader | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class GraderResult:
    score: float
    passed: bool
    reason: str = ""

@dataclass(frozen=True)
class EvalResult:
    case: EvalCase
    actual: str
    grader_result: GraderResult
    latency_ms: float
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class EvalSuiteResult:
    suite_name: str
    model: str
    results: tuple[EvalResult, ...]
    measured_at: datetime

    @property
    def pass_rate(self) -> float: ...
    @property
    def mean_score(self) -> float: ...
    @property
    def p95_latency_ms(self) -> float: ...
```

---

### 6.2 Base Grader Contract (base.py)
**File:** `vidbyte/evals/base.py`  
**Type:** New file

#### Interface / API
```python
class BaseGrader(ABC):
    name: ClassVar[str] = "base"

    @abstractmethod
    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        """Asynchronously grade the target output against the expected criteria."""

    def grade(self, case: EvalCase, actual: str) -> GraderResult:
        """Synchronously grade the target output against the expected criteria."""
```

---

### 6.3 Evaluation Suite (suite.py)
**File:** `vidbyte/evals/suite.py`  
**Type:** New file

#### Interface / API
```python
class EvalSuite:
    def __init__(self, name: str, cases: Sequence[EvalCase]) -> None: ...
    @classmethod
    def from_json(cls, path: str | Path) -> EvalSuite: ...
    @classmethod
    def from_csv(cls, path: str | Path, *, prompt_col: str = "prompt", expected_col: str = "expected") -> EvalSuite: ...
    def filter(self, tags: Sequence[str]) -> EvalSuite: ...
```

---

### 6.4 Evaluation Runner (runner.py)
**File:** `vidbyte/evals/runner.py`  
**Type:** New file

#### Interface / API
```python
class EvalRunner:
    def __init__(self, target: object, *, default_grader: BaseGrader, concurrency: int = 4, max_retries: int = 1) -> None: ...
    async def arun(self, suite: EvalSuite, *, tags: Sequence[str] | None = None) -> EvalSuiteResult: ...
    def run(self, suite: EvalSuite, *, tags: Sequence[str] | None = None) -> EvalSuiteResult: ...
```

#### Logic / Algorithm
1. The runner isolates `BaseAgent` instances using `.fork()` for every case. If target is a `BaseStrategy` or a raw runner (which exposes a run/arun), it invokes it directly.
2. Utilizes `asyncio.Semaphore(concurrency)` to limit parallel execution.
3. Loops through each `EvalCase`. Checks if the case has a specific grader override, else uses `default_grader`.
4. Captures request latency and parses success metrics. Gracefully records exceptions in `EvalResult.error` without aborting the entire run.

---

### 6.5 Evaluation Registry & Comparison (registry.py)
**File:** `vidbyte/evals/registry.py`  
**Type:** New file

#### Interface / API
```python
@dataclass(frozen=True)
class ComparisonReport:
    suite_name: str
    model_a: str
    model_b: str
    pass_rate_a: float
    pass_rate_b: float
    pass_rate_delta: float
    mean_score_a: float
    mean_score_b: float
    mean_score_delta: float
    improved_cases: tuple[str, ...]
    regressed_cases: tuple[str, ...]

class EvalRegistry:
    def __init__(self, db_path: str | Path = ".vidbyte_evals.db") -> None: ...
    def record(self, result: EvalSuiteResult) -> None: ...
    def latest(self, suite: str, model: str) -> EvalSuiteResult | None: ...
    def history(self, suite: str, model: str, limit: int = 10) -> list[EvalSuiteResult]: ...
    def compare(self, suite: str, model_a: str, model_b: str) -> ComparisonReport: ...
```

#### Logic / Algorithm
- Persistence is handled via the Python standard library's `sqlite3` driver.
- Schema consists of two tables: `eval_runs` (id, suite_name, model, pass_rate, mean_score, p95_latency_ms, measured_at) and `eval_results` (run_id, prompt, expected, actual, score, passed, reason, latency_ms, error).
- Comparisons query the latest run for `model_a` and `model_b`, aligning results by `prompt`.
- A case has `improved` if `model_b` passed but `model_a` failed, and `regressed` if `model_a` passed but `model_b` failed.

---

### 6.6 Evaluation Client Wrapper (client.py)
**File:** `vidbyte/evals/client.py`  
**Type:** New file

#### Interface / API
```python
class EvalClient:
    def __init__(self, db_path: str | Path = ".vidbyte_evals.db") -> None: ...
    def runner(self, target: object, *, grader: BaseGrader, **kwargs: Any) -> EvalRunner: ...
    def suite(self, name: str, cases: Sequence[EvalCase]) -> EvalSuite: ...
    @property
    def registry(self) -> EvalRegistry: ...
```

---

### 6.7 Graders (graders/)
**Files:** `vidbyte/evals/graders/`  
- `__init__.py`: Exports all graders.
- `exact_match.py`: Implements `ExactMatchGrader`.
- `contains.py`: Implements `ContainsGrader`.
- `regex_match.py`: Implements `RegexMatchGrader`.
- `json_schema.py`: Implements `JSONSchemaGrader`.
- `llm_judge.py`: Implements `LLMJudgeGrader` using separate model runner and templates.
- `rubric.py`: Implements `RubricGrader` with weighted dimensions scored by LLM.

#### Interface / API
```python
class ExactMatchGrader(BaseGrader):
    def __init__(self, *, strip: bool = True, case_sensitive: bool = False) -> None: ...

class ContainsGrader(BaseGrader):
    def __init__(self, *, case_sensitive: bool = False) -> None: ...

class RegexMatchGrader(BaseGrader):
    def __init__(self, *, pattern: str) -> None: ...

class JSONSchemaGrader(BaseGrader):
    def __init__(self, schema: dict[str, Any]) -> None: ...

class LLMJudgeGrader(BaseGrader):
    def __init__(self, *, judge_runner: object, prompt_template: str | None = None) -> None: ...

class RubricGrader(BaseGrader):
    def __init__(self, *, judge_runner: object, rubric: dict[str, float], prompt_template: str | None = None) -> None: ...
```

---

## 7. Data Model Changes

N/A - This change uses SQLite local storage and standard SQLite table definitions generated dynamically at database initialization, avoiding migrations or external schema files.

---

## 8. API Changes

### 8.1 Mounting `evals` on `VidbyteSDK`
**Change type:** Modified

**Instantiated Field:** `sdk.evals = EvalClient()`

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/evals/__init__.py` | Package exports for evaluation module |
| CREATE | `vidbyte/evals/types.py` | Typed models (`EvalCase`, `EvalResult`, etc.) |
| CREATE | `vidbyte/evals/base.py` | `BaseGrader` abstract contract |
| CREATE | `vidbyte/evals/suite.py` | `EvalSuite` loading and matching utilities |
| CREATE | `vidbyte/evals/runner.py` | `EvalRunner` async execution queue |
| CREATE | `vidbyte/evals/registry.py` | SQLite local database driver and metrics comparison |
| CREATE | `vidbyte/evals/client.py` | SDK namespace entry point |
| CREATE | `vidbyte/evals/graders/__init__.py` | Grader exports |
| CREATE | `vidbyte/evals/graders/exact_match.py` | Strict string matcher |
| CREATE | `vidbyte/evals/graders/contains.py` | Substring inclusion checker |
| CREATE | `vidbyte/evals/graders/regex_match.py` | Pattern regex matcher |
| CREATE | `vidbyte/evals/graders/json_schema.py` | JSON structure grader |
| CREATE | `vidbyte/evals/graders/llm_judge.py` | Model-based open-ended grader |
| CREATE | `vidbyte/evals/graders/rubric.py` | Multi-criteria score grader |
| CREATE | `vidbyte/prompts/prompts/evals.json` | JSON asset for evaluation prompt templates |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Enums mapping for judge prompts |
| MODIFY | `vidbyte/client.py` | Instantiates `EvalClient` on SDK init |
| MODIFY | `vidbyte/__init__.py` | Top-level exports of evals primitives |
| CREATE | `tests/test_evals.py` | Pytest suite for unit/integration validation |
| CREATE | `scripts/test-sdk-evals.py` | Workflow-mandated verification execution script |

---

## 10. Testing Plan

A full test suite will be implemented under `tests/test_evals.py` to cover the complete harness.

### Unit Tests
- `ExactMatchGrader`: Verify stripping and case sensitivity. [Edge Case] Test empty/whitespace input. [Silent Failure] Confirm false match on case mismatch when case_sensitive=True.
- `ContainsGrader`: Check substring checking. [Edge Case] Verify empty expected substring behaves properly.
- `RegexMatchGrader`: Test correct matches, incorrect matches. [Edge Case] Invalid regex compilation handling.
- `JSONSchemaGrader`: Validate correct structural parsing. [Hidden Failure] Test malformed raw JSON strings.
- `LLMJudgeGrader`: Test mock judge execution and JSON parsing. [Hidden Failure] Judge returns invalid/unparsable JSON.
- `RubricGrader`: Verify weighted criteria average calculations. [Silent Failure] Scored average computation math.
- `EvalSuite`: Verify json loading, tag filtering. [Edge Case] Empty tags sequence.

### Integration Tests
- `EvalRunner` + Mock Agent: Verify `.fork()` behavior to ensure agent histories remain isolated. [Hidden Assumption] Ensure multiple runs do not bleed context.
- `EvalRegistry`: Execute complete roundtrip (insert, query history, run comparison report). [Silent Failure] Delta pass rate or mean score calculated with off-by-one.

### Manual / QA Test Cases
1. Run `pytest tests/test_evals.py` and confirm all 100% tests pass.
2. Run `scripts/test-sdk-evals.py` to satisfy git-ticket-workflow.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `sqlite3` | Built-in | Results persistence | No external dependencies or network risk. |

---

## 12. Rollout & Deployment

- Backward-compatible feature addition.
- No existing user functionality is modified or deleted.

---

## 13. Open Questions

- [ ] Should `JSONSchemaGrader` use `pydantic` or standard `jsonschema` library? (Will implement using a simple `json.loads` check and custom key matching to avoid adding external dependencies where unnecessary, or standard python verification).

---

## 14. Alternatives Considered

### Alternative 1: Remote Eval Registry (Server-side)
- Rejected because it increases network request latency during testing runs and adds unnecessary configuration overhead for local-only development.

### Alternative 2: Synced/blocking Agent executions
- Execution would take much longer. Concurrency with Semaphore is significantly faster and cleaner.

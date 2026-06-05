<!--
Context Protocol Header

Description:
    Reference and how-to for the Vidbyte SDK evals subsystem.
Purpose:
    Helps developers build eval suites, run them against an agent/runner, and add
    new graders. Covers EvalSuite, EvalCase, the grader catalog, EvalRunner, and
    the evals prompt family.
Architecture:
    - EvalCase / EvalSuite: test cases and their grouping.
    - Graders: pluggable scoring strategies under vidbyte/evals/graders/.
    - EvalRunner: executes a suite against a target and returns results.
Relations:
    Implementation under vidbyte/evals/. Prompts under the `evals` family
    (Prompt.EVALS_LLM_JUDGE, Prompt.EVALS_RUBRIC). See also
    skills/vidbyte-sdk/SKILL.md and skills/sdk/update-skill-files.md.
-->

# Evals

Use this guide when building or extending the Vidbyte SDK evaluation subsystem under
`vidbyte/evals/`. Evals score an agent or runner's outputs against expected behavior
using pluggable **graders**.

## Concepts

| Type | Module | Role |
|------|--------|------|
| `EvalCase` | `vidbyte/evals/types.py` | One test case: `prompt`, optional `expected`, `tags`, optional per-case `grader`, `metadata`. |
| `EvalSuite` | `vidbyte/evals/suite.py` | Named collection of `EvalCase`s. `EvalSuite(name, cases)`; also `EvalSuite.from_json(path)`. |
| `BaseGrader` | `vidbyte/evals/base.py` | Abstract grader: `async agrade(case, actual) -> GraderResult` and sync `grade(...)`. |
| `GraderResult` | `vidbyte/evals/types.py` | `score: float`, `passed: bool`, `reason: str`. |
| `EvalRunner` | `vidbyte/evals/runner.py` | Runs a suite against a target. |
| `EvalResult` / `EvalSuiteResult` | `vidbyte/evals/types.py` | Per-case and per-suite results. |
| `EvalRegistry` / `ComparisonReport` | `vidbyte/evals/registry.py` | Register suites and compare runs. |
| `EvalClient` | `vidbyte/evals/client.py` | Convenience client surface. |

All of these are exported from `vidbyte.evals`:

```python
from vidbyte.evals import (
    EvalCase, EvalSuite, EvalRunner, BaseGrader, GraderResult,
    EvalResult, EvalSuiteResult, EvalRegistry, ComparisonReport, EvalClient,
    ContainsGrader, ExactMatchGrader, RegexMatchGrader, JSONSchemaGrader,
    LLMJudgeGrader, RubricGrader,
)
```

## Grader Catalog

| Grader | Constructor | Scoring |
|--------|-------------|---------|
| `ExactMatchGrader` | `ExactMatchGrader()` | Pass when `actual` exactly equals `case.expected`. |
| `ContainsGrader` | `ContainsGrader(*, case_sensitive=False)` | Pass when `actual` contains `case.expected`. |
| `RegexMatchGrader` | `RegexMatchGrader(...)` | Pass when `actual` matches the expected pattern. |
| `JSONSchemaGrader` | `JSONSchemaGrader(...)` | Pass when `actual` parses and validates against a JSON schema. |
| `LLMJudgeGrader` | `LLMJudgeGrader(*, judge_runner, prompt_template=None)` | Uses a judge model (LLM-as-judge). Default prompt is `Prompt.EVALS_LLM_JUDGE`. |
| `RubricGrader` | `RubricGrader(*, judge_runner, rubric: dict[str, float], threshold=0.7, prompt_template=None)` | Weighted rubric scoring via a judge model. Default prompt is `Prompt.EVALS_RUBRIC`. |

## Running a Suite

`EvalRunner(target, *, default_grader, concurrency=4, max_retries=1)` runs each case against
`target` (an agent or runner), grading with the case's grader or `default_grader`.

```python
from vidbyte import Agent
from vidbyte.evals import EvalSuite, EvalCase, EvalRunner, ContainsGrader

agent = Agent(name="qa", system_prompt="Answer concisely.", provider="openai", model_name="gpt-4.1")

suite = EvalSuite("smoke", [
    EvalCase(prompt="Capital of France?", expected="Paris", tags=("geography",)),
    EvalCase(prompt="2 + 2?", expected="4"),
])

runner = EvalRunner(agent, default_grader=ContainsGrader())
result = await runner.arun(suite)            # EvalSuiteResult; sync: runner.run(suite)
result = await runner.arun(suite, tags=["geography"])  # filter by tag
```

## Adding a New Grader

1. Add a module under `vidbyte/evals/graders/<name>.py` with a class subclassing `BaseGrader`.
2. Implement `async def agrade(self, case: EvalCase, actual: str) -> GraderResult`. Return a
   `GraderResult(score=..., passed=..., reason=...)`. The base provides a sync `grade()` wrapper.
3. Export the class from `vidbyte/evals/graders/__init__.py` and from `vidbyte/evals/__init__.py`
   (and from `vidbyte/__init__.py` if it should be a root export).
4. If the grader needs a model, accept a `judge_runner` and read its default prompt from the
   `evals` prompt family rather than hardcoding the prompt body (follow
   `skills/vidbyte-sdk/adding-prompts.md`).
5. Add tests to `tests/test_evals.py` covering pass, fail, and edge cases (empty `expected`,
   malformed output, missing grader).

## Verification

```powershell
python -m compileall vidbyte
python -m unittest tests.test_evals
```

## Rules

- Keep eval suites, graders, runner, and registry under `vidbyte/evals/`.
- Graders must be deterministic given the same inputs, except LLM-backed graders which must
  accept an injected `judge_runner` (no hidden provider calls).
- Do not embed customer data or private scoring logic; evals here are reusable SDK abstractions.

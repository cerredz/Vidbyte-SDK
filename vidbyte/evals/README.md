# Evals

The Vidbyte SDK includes local evaluation primitives for checking agent and
runner behavior without adopting a hosted evaluation service.

## Role In The SDK

`vidbyte.evals` provides `EvalCase`, `EvalSuite`, `EvalRunner`, built-in graders,
result dataclasses, and a local registry. It can run suites against Vidbyte
agents or runner-like objects that expose `arun()`, `generate_reply()`, or
`run()`.

## Design Philosophy

Evals should be easy to write as normal Python scripts. The runner isolates
stateful agents by forking them, limits concurrency with a semaphore, and turns
target or grader errors into failed results instead of crashing the entire suite.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agent behavior needs repeatable
checks for answer quality, rubric alignment, latency, and regression resistance;
the eval layer provides local building blocks for those checks.

## Usage

```python
from vidbyte import ContainsGrader, EvalCase, EvalRunner, EvalSuite

suite = EvalSuite("smoke", [
    EvalCase(prompt="Capital of France?", expected="Paris", tags=("geography",)),
    EvalCase(prompt="2 + 2?", expected="4", tags=("math",)),
])

runner = EvalRunner(agent, default_grader=ContainsGrader(), concurrency=4)
result = await runner.arun(suite)

print(result.pass_rate, result.mean_score)
```

Suites can be loaded from JSON or CSV:

```python
from vidbyte.evals import EvalSuite

suite = EvalSuite.from_json("evals/smoke.json")
focused = suite.filter(["geography"])
```

Use a stricter grader for exact outputs:

```python
from vidbyte import EvalCase, EvalRunner, EvalSuite, ExactMatchGrader

suite = EvalSuite("math", [EvalCase(prompt="2 + 2?", expected="4")])
result = await EvalRunner(agent, default_grader=ExactMatchGrader()).arun(suite)
```

Record and compare runs locally:

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.evals.registry.record(result)
```

## Feature Coverage

- `EvalCase` for prompts, expected values, tags, metadata, and optional per-case graders.
- `EvalSuite` for grouping, loading from JSON/CSV, filtering, and iteration.
- `EvalRunner` for async execution, concurrency control, retry accounting, and state isolation through agent forks.
- Built-in graders: exact match, contains, regex, JSON schema, LLM judge, and rubric.
- `EvalSuiteResult` metrics such as pass rate, mean score, and latency summaries.
- `EvalRegistry` for recording and comparing local result history.
- `EvalClient` convenience factories through `VidbyteSDK().evals`.

## Key Modules

- `types.py`: eval case, result, suite result, and grader result dataclasses.
- `suite.py`: suite construction, JSON/CSV loading, and tag filtering.
- `runner.py`: async-first eval execution engine.
- `graders/`: exact match, contains, regex, JSON schema, LLM judge, and rubric graders.
- `registry.py`: local result recording and comparison helpers.

## Related Layers

Evals commonly exercise [`agents`](../agents/README.md), compare
[`providers`](../providers/README.md), and validate [`pipelines`](../pipelines/README.md).

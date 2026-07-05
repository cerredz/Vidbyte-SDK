# Evals

The Vidbyte SDK includes local evaluation primitives for checking agent and
runner behavior without adopting a hosted evaluation service.

## Role In The SDK

`vidbyte.evals` provides `EvalCase`, `EvalSuite`, `EvalRunner`, built-in graders,
prebuilt eval templates, result dataclasses, and a local registry. It can run
suites against Vidbyte agents or runner-like objects that expose `arun()`,
`generate_reply()`, or `run()`.

## Design Philosophy

Evals should be easy to write as normal Python scripts. The runner isolates
stateful agents by forking them, limits concurrency with a semaphore, and turns
target or grader errors into failed results instead of crashing the entire suite.

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

`EvalCase.templates` lets a case use reusable grading bundles made from one or
more graders:

```python
from vidbyte.evals import EvalCase, EvalSuite, EvalRunner
from vidbyte.evals import templates as T

suite = EvalSuite("support", [
    EvalCase(
        prompt="What is our refund window?",
        expected="30 days",
        templates=(T.short_answer_fact(), T.safe_customer_support()),
    ),
    EvalCase(
        prompt="Return routing JSON.",
        expected={"category": "billing"},
        templates=(T.structured_json(schema={
            "type": "object",
            "required": ["category"],
            "properties": {"category": {"type": "string"}},
        }),),
    ),
])
```

Suites can be loaded from JSON or CSV:

```python
from vidbyte.evals import EvalSuite

suite = EvalSuite.from_json("evals/smoke.json")
focused = suite.filter(["geography"])
```

JSON suites can reference templates by name:

```json
{
  "name": "support",
  "cases": [
    {
      "prompt": "What is our refund window?",
      "expected": "30 days",
      "templates": ["short_answer_fact", "safe_customer_support"]
    }
  ]
}
```

## Key Modules

- `types.py`: eval case, result, suite result, and grader result dataclasses.
- `suite.py`: suite construction, JSON/CSV loading, and tag filtering.
- `runner.py`: async-first eval execution engine.
- `graders/`: exact match, contains, regex, JSON schema, LLM judge, and rubric graders.
- `templates/`: prebuilt multi-grader templates and custom template registry.
- `registry.py`: local result recording and comparison helpers.

## Related Layers

Evals commonly exercise [`agents`](../agents/README.md), compare
[`providers`](../providers/README.md), and validate [`pipelines`](../pipelines/README.md).

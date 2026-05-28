# Setting Up an Eval Pipeline

An eval pipeline runs one or more graders across a dataset of `EvalCase` objects and collects `GraderResult` outputs.

## Anatomy of an EvalCase

```python
from vidbyte.evals.types import EvalCase

case = EvalCase(
    prompt="Explain recursion in one sentence.",
    expected="A function that calls itself until a base case is reached.",
    tags=["explanation", "cs-concepts"],
    grader=None,       # optional: grader name hint, not enforced
    metadata={},       # arbitrary key-value pairs (e.g. response_b for PairwiseJudge)
)
```

`metadata` is the escape hatch for judge-specific data. `PairwiseJudge` reads `metadata["response_b"]`; any other judge-specific inputs should follow the same pattern.

## Running a Single Grader

```python
import asyncio
from vidbyte.evals.llm_as_a_judge import ChainOfThoughtJudge
from vidbyte.lib.dataclasses.llm_judge import ChainOfThoughtJudgeConfig

judge = ChainOfThoughtJudge(ChainOfThoughtJudgeConfig(judge_runner=runner))

results = asyncio.run(asyncio.gather(
    *[judge.agrade(case, actual) for case, actual in zip(cases, actuals)]
))
```

## Running Multiple Graders in Parallel

```python
import asyncio
from vidbyte.evals.llm_as_a_judge import BinaryJudge, ChainOfThoughtJudge, ConstitutionalJudge
from vidbyte.lib.dataclasses.llm_judge import (
    BinaryJudgeConfig, ChainOfThoughtJudgeConfig, ConstitutionalJudgeConfig,
)

judges = [
    ChainOfThoughtJudge(ChainOfThoughtJudgeConfig(judge_runner=runner)),
    BinaryJudge(BinaryJudgeConfig(judge_runner=runner, criterion="Is the answer factually correct?")),
    ConstitutionalJudge(ConstitutionalJudgeConfig(
        judge_runner=runner,
        principles=["Do not include harmful content.", "Stay on topic."],
    )),
]

async def grade_all(case, actual):
    return await asyncio.gather(*[j.agrade(case, actual) for j in judges])

all_results = asyncio.run(asyncio.gather(
    *[grade_all(case, actual) for case, actual in zip(cases, actuals)]
))
```

## Interpreting GraderResult

```python
from vidbyte.evals.types import GraderResult

result: GraderResult  # returned by agrade()
result.score    # float in [0.0, 1.0]
result.passed   # bool — True if score >= threshold
result.reason   # str — human-readable explanation
```

Score semantics vary by judge:
- Most judges: 0.0 = fully failed, 1.0 = fully correct
- `BinaryJudge`: 0.0 or 1.0 only
- `PairwiseJudge`: 0.0 = response_b wins, 0.5 = tie, 1.0 = actual wins
- `AtomicClaimsJudge`: fraction of claims verified
- `ConstitutionalJudge`: fraction of principles satisfied

## Aggregating Results Across a Dataset

```python
from statistics import mean

scores = [r.score for r in results]
pass_rate = sum(1 for r in results if r.passed) / len(results)
avg_score = mean(scores)
```

## Strategy Selection Guide

| Use case | Recommended judge |
|----------|------------------|
| Quick pass/fail on a single criterion | `BinaryJudge` |
| Holistic quality with reasoning | `ChainOfThoughtJudge` |
| Factual accuracy | `AtomicClaimsJudge` |
| Safety / policy compliance | `ConstitutionalJudge` |
| Comparing two candidate responses | `PairwiseJudge` |
| Multi-dimensional quality breakdown | `ChainOfAspectsJudge` or `StructuredRubricJudge` |
| Scale-consistent grading | `FewShotJudge` |
| Reducing single-model bias | `PanelJudge` or `PeerReviewJudge` |
| New task type without a rubric | `LLMRubricJudge` |
| Pre-defined rubric dimensions | `BranchSolveMergeJudge` or `MultiAgentRubricJudge` |
| QA-checking another judge | `MetaJudge` |
| Cross-validating with debate | `MultiAgentDebateJudge` |
| Different templates per task type | `MixtureOfPromptsJudge` |
| No separate judge model available | `SelfEvalJudge` or `SelfReferenceJudge` |

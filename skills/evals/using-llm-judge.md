# Using an LLM-as-a-Judge

All 19 judge strategies accept a typed config dataclass as their sole constructor argument.

## Basic Usage Pattern

```python
import asyncio
from vidbyte.evals.llm_as_a_judge import ChainOfThoughtJudge
from vidbyte.evals.types import EvalCase
from vidbyte.lib.dataclasses.llm_judge import ChainOfThoughtJudgeConfig

# 1. Build a runner (any object with .arun, .generate_reply, or .run)
runner = my_agent_or_client  # e.g. VidbyteSDK().agents.create(...)

# 2. Create the config dataclass — validation happens here
config = ChainOfThoughtJudgeConfig(judge_runner=runner, cot_length="medium")

# 3. Instantiate the judge
judge = ChainOfThoughtJudge(config)

# 4. Build an EvalCase
case = EvalCase(
    prompt="What is the capital of France?",
    expected="Paris",
    tags=[],
    grader=None,
    metadata={},
)

# 5. Grade
result = asyncio.run(judge.agrade(case, actual="Paris"))
print(result.score, result.passed, result.reason)
```

## Overriding Templates

Pass a `prompt_template` (or the strategy-specific override field) to the config:

```python
config = BinaryJudgeConfig(
    judge_runner=runner,
    criterion="Does the response cite a source?",
    prompt_template="Custom template with {criterion}, {prompt}, {actual}, {expected}",
)
```

Override priority: `prompt_template` arg → SDK `Prompts()` catalog → `TemplatesRegistry` default.

## Overriding via TemplatesRegistry

To change the default for all instances that use the registry fallback:

```python
from vidbyte.lib.eval.template_registry import TemplatesRegistry

reg = TemplatesRegistry()  # instance-isolated — won't affect other judges
reg.create("binary.user", "My custom binary template with {criterion}...")
```

Note: Each judge module creates its own `_registry` instance at import time. Mutating one instance does not affect others.

## Multi-Runner Judges

Judges that accept multiple runners (PanelJudge, PeerReviewJudge, MultiAgentDebateJudge, MultiAgentRubricJudge) take a `judge_runners` or `agents` list:

```python
from vidbyte.lib.dataclasses.llm_judge import PanelJudgeConfig
from vidbyte.evals.llm_as_a_judge import PanelJudge

config = PanelJudgeConfig(
    judge_runners=[runner_a, runner_b, runner_c],
    aggregation="mean",
    threshold=0.7,
)
judge = PanelJudge(config)
```

Minimum 2 runners are required; the config dataclass will raise `ValueError` otherwise.

## Nested Judges (MetaJudge)

MetaJudge takes a primary judge instance plus a separate meta runner:

```python
from vidbyte.lib.dataclasses.llm_judge import MetaJudgeConfig, ChainOfThoughtJudgeConfig
from vidbyte.evals.llm_as_a_judge import MetaJudge, ChainOfThoughtJudge

primary = ChainOfThoughtJudge(ChainOfThoughtJudgeConfig(judge_runner=runner))
meta_config = MetaJudgeConfig(primary_judge=primary, meta_runner=meta_runner)
judge = MetaJudge(meta_config)
```

## Available Judges

| Class | Config | Key Parameters |
|-------|--------|---------------|
| `ChainOfThoughtJudge` | `ChainOfThoughtJudgeConfig` | `cot_length` |
| `BinaryJudge` | `BinaryJudgeConfig` | `criterion` (required) |
| `FewShotJudge` | `FewShotJudgeConfig` | `examples` (required list) |
| `PairwiseJudge` | `PairwiseJudgeConfig` | `swap_check` |
| `SelfReferenceJudge` | `SelfReferenceJudgeConfig` | `num_self_generations` |
| `SelfEvalJudge` | `SelfEvalJudgeConfig` | `framing` |
| `CriteriaDecompositionJudge` | `CriteriaDecompositionJudgeConfig` | `criterion`, `num_sub_criteria` |
| `ChainOfAspectsJudge` | `ChainOfAspectsJudgeConfig` | `aspects` (required list) |
| `BranchSolveMergeJudge` | `BranchSolveMergeJudgeConfig` | `branches` (required dict), `merge_strategy` |
| `LLMRubricJudge` | `LLMRubricJudgeConfig` | `task_description` (required), `rubric_scale` |
| `StructuredRubricJudge` | `StructuredRubricJudgeConfig` | `dimensions` (required dict) |
| `AtomicClaimsJudge` | `AtomicClaimsJudgeConfig` | `threshold` |
| `ConstitutionalJudge` | `ConstitutionalJudgeConfig` | `principles` (required list) |
| `PanelJudge` | `PanelJudgeConfig` | `judge_runners` (min 2), `aggregation` |
| `MultiAgentRubricJudge` | `MultiAgentRubricJudgeConfig` | `agents` (min 2 tuples) |
| `MultiAgentDebateJudge` | `MultiAgentDebateJudgeConfig` | `judge_runners` (min 2), `debate_rounds` |
| `MetaJudge` | `MetaJudgeConfig` | `primary_judge`, `meta_runner` |
| `PeerReviewJudge` | `PeerReviewJudgeConfig` | `judge_runners` (min 2), `confidence_threshold` |
| `MixtureOfPromptsJudge` | `MixtureOfPromptsJudgeConfig` | `prompt_library` (required dict), `router_fn` or `router_runner` |

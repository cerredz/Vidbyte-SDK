# Pipelines

Pipelines in the Vidbyte SDK compose agents and other pipelines into simple
multi-stage workflows. The contract is intentionally small: each stage receives
a string and returns a string.

## Role In The SDK

`vidbyte.pipelines` provides `SequentialPipeline`, `ParallelPipeline`,
`ConditionalPipeline`, `MapReducePipeline`, `BasePipeline`, and `PipelineNode`.
The layer coordinates stage order and fan-out/fan-in behavior while leaving each
agent's tools, middleware, context, history, and runner configuration local to
that agent.

## Design Philosophy

Pipeline orchestration should be boring and predictable. The SDK does not add
implicit shared state, hidden retries, voting, streaming, artifacts, or budgets
at the pipeline layer. If a workflow needs those behaviors, they should be owned
by agents, tools, middleware, or a custom pipeline.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website workflows often need to split
planning, drafting, review, and summarization across specialized agents; the
pipeline layer provides those coordination shapes without hiding agent-local
state.

## Usage

```python
from vidbyte import SequentialPipeline

pipeline = SequentialPipeline([planner_agent, writer_agent, reviewer_agent])
result = await pipeline.run("Draft a concise release note.")
```

Other topologies are available for common coordination patterns:

```python
from vidbyte import ConditionalPipeline, MapReducePipeline, ParallelPipeline

parallel = ParallelPipeline([security_agent, performance_agent])
conditional = ConditionalPipeline(
    predicate=lambda prompt: "code" if "implement" in prompt.lower() else "research",
    branches={"code": coder_agent, "research": researcher_agent},
)
map_reduce = MapReducePipeline(
    map_stages=[reviewer_a, reviewer_b],
    reduce_stage=summarizer_agent,
)
```

Nest pipelines when a larger workflow needs multiple coordination patterns:

```python
from vidbyte import MapReducePipeline, SequentialPipeline

workflow = SequentialPipeline([
    planner_agent,
    MapReducePipeline(map_stages=[reviewer_a, reviewer_b], reduce_stage=summarizer_agent),
    publisher_agent,
])

final_text = workflow.run_sync("Prepare a learner feedback summary.")
```

## Feature Coverage

- `BasePipeline` async contract and synchronous `run_sync()` bridge.
- Sequential pipelines that thread one stage output into the next stage input.
- Parallel pipelines that send the same prompt to multiple stages and join outputs.
- Conditional pipelines that route by a caller-provided synchronous predicate.
- Map-reduce pipelines that fan out to map stages and reduce the joined response.
- Nested pipelines because every pipeline is also a valid pipeline node.
- Stage dispatch to either Vidbyte agents or nested pipelines.

## Key Modules

- `base.py`: abstract pipeline contract, nested pipeline dispatch, and `run_sync()`.
- `sequential.py`: run stages in order.
- `parallel.py`: run stages against the same prompt and join outputs.
- `conditional.py`: route by a synchronous predicate.
- `map_reduce.py`: fan out to map stages and reduce their joined output.

## Related Layers

Pipelines compose [`agents`](../agents/README.md) and are natural targets for
[`evals`](../evals/README.md).

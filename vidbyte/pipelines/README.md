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

## Key Modules

- `base.py`: abstract pipeline contract, nested pipeline dispatch, and `run_sync()`.
- `sequential.py`: run stages in order.
- `parallel.py`: run stages against the same prompt and join outputs.
- `conditional.py`: route by a synchronous predicate.
- `map_reduce.py`: fan out to map stages and reduce their joined output.

## Related Layers

Pipelines compose [`agents`](../agents/README.md) and are natural targets for
[`evals`](../evals/README.md).

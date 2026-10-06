# Pipelines

## What pipelines are

A pipeline wires agent outputs to agent inputs. The only contract is string-in /
string-out: one agent's reply becomes the next agent's prompt. There is no shared
context object, no pipeline-level budget, and no artifact layer — each agent carries
its own configuration, strategy, and tools. Pipelines move strings, nothing else.

Use `vidbyte.agents.multi.MultiAgent` instead when a manager must own the overall goal, inspect shared task progress, choose the next worker dynamically, require verified evidence, retry, or replan. A multi-agent team is an adaptive controller over a run-local `TaskLedger`, not a pipeline topology. See [`multi-agent.md`](multi-agent.md).

## Why pipelines exist

Strategies compose reasoning *inside* a single agent loop. Pipelines compose *agents*
across agent boundaries. Use a pipeline whenever you want the full output of one
configured agent — including its strategy, tools, and history — to become the input
of another fully-configured agent.

Examples:
- A planning agent (heavy, slow, exploratory strategy) whose output drives five parallel
  solver agents, whose joined output feeds a cost-effective implementation agent.
- A classifier agent whose label routes a prompt to a specialised research or code agent.
- A chain of increasingly focused agents refining a solution step by step.

## Topology types

### SequentialPipeline

Runs stages one after another. The output of stage N is the prompt of stage N+1.
Returns the final stage's output.

```python
from vidbyte import SequentialPipeline

pipeline = SequentialPipeline([planner, reasoner, solver])
result = await pipeline.run("build a recommendation engine")
```

### ParallelPipeline

Runs all stages concurrently with the same input. Joins all outputs with
`"\n\n---\n\n"` (configurable via `separator=`). Returns the joined string.

```python
from vidbyte import ParallelPipeline

pipeline = ParallelPipeline([solver_a, solver_b, solver_c])
result = await pipeline.run("solve this problem")
# result contains all three agents' answers separated by ---
```

Custom separator:

```python
pipeline = ParallelPipeline([a, b], separator="\n\n===\n\n")
```

### ConditionalPipeline

Applies a predicate to the incoming prompt to select a branch key, then runs the
corresponding stage with that same prompt.

```python
from vidbyte import ConditionalPipeline

def route(prompt: str) -> str:
    return "code" if "implement" in prompt.lower() else "research"

pipeline = ConditionalPipeline(
    predicate=route,
    branches={
        "code": code_agent,
        "research": research_agent,
    },
)
result = await pipeline.run("implement a binary search tree")
```

The predicate receives the prompt string and returns a branch key. If the returned key
is not in `branches`, `PipelineExecutionError` is raised with the available keys listed.

### MapReducePipeline

Runs all `map_stages` concurrently with the same input (fan-out), joins their outputs
with a separator (default `"\n\n---\n\n"`, configurable via `separator=`), then feeds the
joined string to a single `reduce_stage` (fan-in). Returns the reduce stage's output.

```python
from vidbyte import MapReducePipeline

pipeline = MapReducePipeline(
    map_stages=[security_agent, performance_agent, style_agent],
    reduce_stage=summarizer,
)
result = await pipeline.run("Review this codebase for production readiness.")
```

`PipelineExecutionError` is raised if `map_stages` is empty. Like `ParallelPipeline`,
the map stages run via `asyncio.gather` without `return_exceptions`, so the first map
failure aborts the others.

## Composability

Every pipeline is itself a valid stage inside another pipeline. Nest them freely:

```python
from vidbyte import SequentialPipeline, ParallelPipeline

pipeline = SequentialPipeline([
    planner_agent,
    ParallelPipeline([solver_a, solver_b, solver_c]),   # nested — receives planner output
    implementer_agent,                                   # receives joined solver outputs
])
result = await pipeline.run("build a feature")
```

A `BasePipeline` instance passes the same `isinstance` check as any other pipeline
stage, so nesting depth is unlimited.

## Sync entry point

Mirrors `BaseAgent.run()`. Cannot be called from an active event loop.

```python
result = pipeline.run_sync("prompt")   # fine from plain synchronous code
```

## Error handling

| Error | When raised |
|-------|-------------|
| `PipelineExecutionError` | Empty `stages`/`branches`/`map_stages` at construction; unknown predicate key at runtime; `run_sync` called from active event loop |
| `AgentExecutionError` | Any agent stage raises — propagates unwrapped |
| Any other exception | Propagates from the failing stage unwrapped |

`ParallelPipeline` and `MapReducePipeline` use `asyncio.gather` without
`return_exceptions`; the first agent failure aborts all concurrent branches.

## Module layout

```
vidbyte/pipelines/
├── __init__.py        public surface
├── base.py            BasePipeline + _invoke dispatcher
├── conditional.py     ConditionalPipeline
├── map_reduce.py      MapReducePipeline
├── parallel.py        ParallelPipeline + PARALLEL_JOIN_SEPARATOR
├── sequential.py      SequentialPipeline
└── types.py           PipelineNode type alias
```

All types are also importable from the root `vidbyte` namespace:

```python
from vidbyte import SequentialPipeline, ParallelPipeline, ConditionalPipeline, MapReducePipeline
from vidbyte import BasePipeline, PipelineNode, PipelineExecutionError
```

## Rules for adding new pipeline types

- A new pipeline type must inherit `BasePipeline` and implement `async run(prompt: str) -> str`.
- The only data flowing between stages is a plain `str`. Do not add context, artifact,
  or budget objects to the pipeline layer.
- Accept `PipelineNode` (i.e. `BaseAgent | BasePipeline`) as stage elements and
  dispatch via `self._invoke(stage, prompt)`.
- Add the new type to `vidbyte/pipelines/__init__.py` and to `vidbyte/__init__.py`.
- Add it to the layout table in this doc and in `SKILL.md`.
- Write tests in `tests/test_pipelines.py` using `unittest.IsolatedAsyncioTestCase`
  and fake `EchoAgent` / `PrefixAgent` style stubs — no real runners required.

## What pipelines are NOT

- Pipelines do not replace strategies. Strategies belong inside an agent loop;
  pipelines wire agents across loops.
- Pipelines do not manage context, history, or budgets. Each agent does that
  internally.
- Pipelines do not stream results or emit partial outputs.
- Pipelines do not retry or vote — those are future topology types. Map-reduce
  (fan-out → fan-in) is supported via `MapReducePipeline`.
- Pipelines do not own task status, evidence, blockers, retries, or replanning. Those
  belong to the ledger-driven `MultiAgent` package.

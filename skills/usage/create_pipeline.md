# Create Pipeline of Agents

Compose agents into pipelines where one agent's output becomes the next agent's prompt. Pipelines move strings between fully-configured agents; each agent keeps its own strategy, tools, middleware, and history. There is no shared state, context, or budget at the pipeline layer.

Use pipelines to compose multi-agent workflows where the output of one agent (including its tool calls and strategy reasoning) feeds into the next.

## Choosing a Pipeline Type

| Pipeline | Pattern | Best For |
|----------|---------|----------|
| `SequentialPipeline` | Chain | Linear workflows: plan → code → test |
| `ParallelPipeline` | Fan-out | Independent analysis: same problem, different approaches |
| `ConditionalPipeline` | Route | Classify-then-dispatch: route to specialist agent |
| `MapReducePipeline` | Fan-out → Fan-in | Divide and conquer: map to workers, reduce to synthesis |

## Sequential Pipeline

Stages run in order. The output of stage N becomes the prompt for stage N+1. Returns the final stage's output:

```python
from vidbyte import SequentialPipeline, Agent

planner = Agent(name="planner", system_prompt="Create a step-by-step plan.", provider="openai", model_name="gpt-4.1")
coder = Agent(name="coder", system_prompt="Write code based on the plan.", provider="openai", model_name="gpt-4.1")
tester = Agent(name="tester", system_prompt="Write tests for the code.", provider="openai", model_name="gpt-4.1")

pipeline = SequentialPipeline([planner, coder, tester])
result = await pipeline.run("Build a binary search tree in Python")
# result: str containing the tester's output
```

Ideal for workflows where each stage builds on the previous: plan → implement → test → document. Each agent sees the full output of the previous agent, including any reasoning or tool call results.

## Parallel Pipeline

All stages run concurrently with the same input. Outputs are joined with a configurable separator. Returns the joined string:

```python
from vidbyte import ParallelPipeline, Agent

# Three agents investigate the same problem independently
agent_a = Agent(name="a", system_prompt="Solve with functional approach.", provider="openai", model_name="gpt-4.1")
agent_b = Agent(name="b", system_prompt="Solve with OOP approach.", provider="openai", model_name="gpt-4.1")
agent_c = Agent(name="c", system_prompt="Solve with data-oriented approach.", provider="openai", model_name="gpt-4.1")

pipeline = ParallelPipeline([agent_a, agent_b, agent_c])
result = await pipeline.run("Design a caching system")
# result joins all three outputs with "\n\n---\n\n"

# Custom separator for different output formatting
pipeline = ParallelPipeline([agent_a, agent_b], separator="\n\n===\n\n")
```

Ideal for getting multiple independent perspectives on the same problem. Each agent sees the same prompt and produces an independent answer.

## Conditional Pipeline

A predicate function inspects the prompt and routes to the appropriate branch agent. The predicate receives the prompt string and returns a branch key:

```python
from vidbyte import ConditionalPipeline, Agent

code_agent = Agent(name="coder", system_prompt="Write production code.", provider="openai", model_name="gpt-4.1")
research_agent = Agent(name="researcher", system_prompt="Research and explain.", provider="openai", model_name="gpt-4.1")

def route(prompt: str) -> str:
    if any(word in prompt.lower() for word in ("implement", "code", "build", "write")):
        return "code"
    return "research"

pipeline = ConditionalPipeline(
    predicate=route,
    branches={"code": code_agent, "research": research_agent},
)
result = await pipeline.run("Implement a quicksort algorithm")  # → code_agent
result = await pipeline.run("Explain how quicksort works")      # → research_agent
```

If the predicate returns an unknown key, `PipelineExecutionError` is raised with the available keys listed.

Ideal for routing prompts to specialist agents based on content: code vs. research, text vs. image, simple vs. complex.

## Map-Reduce Pipeline

Map stages run concurrently on the same input (fan-out), then a single reduce stage synthesizes their joined outputs (fan-in). Returns the reduce stage's output:

```python
from vidbyte import MapReducePipeline, Agent

# Map agents: each analyzes the problem from a different angle
security_agent = Agent(name="security", system_prompt="Audit for security vulnerabilities.", provider="openai", model_name="gpt-4.1")
performance_agent = Agent(name="perf", system_prompt="Analyze for performance issues.", provider="openai", model_name="gpt-4.1")
style_agent = Agent(name="style", system_prompt="Review code style and readability.", provider="openai", model_name="gpt-4.1")

# Reduce agent: synthesizes all findings into a single report
summarizer = Agent(name="summarizer", system_prompt="Combine the following reviews into a single actionable report.", provider="openai", model_name="gpt-4.1")

pipeline = MapReducePipeline(
    map_stages=[security_agent, performance_agent, style_agent],
    reduce_stage=summarizer,
)
result = await pipeline.run("Review this codebase for production readiness.")
```

Ideal for divide-and-conquer workflows: multiple agents each analyze a different aspect, then a single agent synthesizes everything. The map stages receive the same prompt and run concurrently; the reduce stage receives their joined output with the default separator `"\n\n---\n\n"`.

Custom separator:
```python
pipeline = MapReducePipeline(
    map_stages=[a, b, c],
    reduce_stage=summarizer,
    separator="\n\n===\n\n",
)
```

`PipelineExecutionError` is raised if `map_stages` is empty.

## Nested Pipelines

Pipelines are themselves valid pipeline stages (`PipelineNode = BaseAgent | BasePipeline`). Nest them freely to build arbitrarily complex topologies:

```python
from vidbyte import SequentialPipeline, ParallelPipeline, MapReducePipeline

pipeline = SequentialPipeline([
    planner_agent,
    ParallelPipeline([solver_a, solver_b, solver_c]),    # receives planner output
    MapReducePipeline(                                     # receives joined solver outputs
        map_stages=[reviewer_a, reviewer_b],
        reduce_stage=summarizer,
    ),
])
result = await pipeline.run("Build a recommendation engine")
```

This composes: plan → three parallel solvers → two review agents with a summarizer → single final output.

## Sync Entry Point

For synchronous scripts, use `run_sync()`. Mirrors `BaseAgent.run()`:

```python
result = pipeline.run_sync("Build a binary search tree")
```

Cannot be called from inside an active `asyncio` event loop.

## PipelineNode Type

A `PipelineNode` is `BaseAgent | BasePipeline`. Any valid agent or pipeline can be a stage in any other pipeline:

```python
from vidbyte import PipelineNode

# PipelineNode = BaseAgent | BasePipeline
# Agents and pipelines are interchangeable as stages
```

## Error Handling

Pipeline errors are structured so you can catch at the right level:

| Error | When |
|-------|------|
| `PipelineExecutionError` | Empty stages/branches at construction; unknown predicate key at runtime; `run_sync` called from an active event loop |
| `AgentExecutionError` | Any agent stage raises during execution — propagates unwrapped |
| Other exceptions | Propagate unwrapped from the failing stage |

`ParallelPipeline` and `MapReducePipeline` use `asyncio.gather` without `return_exceptions`; the first agent failure aborts all concurrent branches.

## Best Practices

- **Use the simplest pipeline type** that fits your workflow. Sequential is simpler than MapReduce.
- **Nest only when necessary.** Deep nesting can be harder to debug.
- **Set appropriate `max_tool_rounds`** on agents inside pipelines — a stuck agent blocks the entire pipeline.
- **Consider error propagation**: if any concurrent stage fails, the whole pipeline fails. Use robust agents or wrap in try/except if partial results are acceptable.

# Create Pipeline of Agents

Compose agents into pipelines where one agent's output becomes the next agent's prompt. Pipelines move strings; each agent keeps its own strategy, tools, and history.

## Sequential Pipeline

Stages run in order. Output of stage N is the prompt of stage N+1.

```python
from vidbyte import SequentialPipeline, Agent

planner = Agent(name="planner", system_prompt="Create a step-by-step plan.", provider="openai", model_name="gpt-4.1")
coder = Agent(name="coder", system_prompt="Write code based on the plan.", provider="openai", model_name="gpt-4.1")
tester = Agent(name="tester", system_prompt="Write tests for the code.", provider="openai", model_name="gpt-4.1")

pipeline = SequentialPipeline([planner, coder, tester])
result = await pipeline.run("Build a binary search tree in Python")
# result: str containing the tester's output
```

## Parallel Pipeline

All stages run concurrently with the same input. Outputs are joined with a separator.

```python
from vidbyte import ParallelPipeline, Agent

# Three agents investigate the same problem independently
agent_a = Agent(name="a", system_prompt="Solve with functional approach.", provider="openai", model_name="gpt-4.1")
agent_b = Agent(name="b", system_prompt="Solve with OOP approach.", provider="openai", model_name="gpt-4.1")
agent_c = Agent(name="c", system_prompt="Solve with data-oriented approach.", provider="openai", model_name="gpt-4.1")

pipeline = ParallelPipeline([agent_a, agent_b, agent_c])
result = await pipeline.run("Design a caching system")
# result joins all three with "\n\n---\n\n"

# Custom separator
pipeline = ParallelPipeline([agent_a, agent_b], separator="\n\n===\n\n")
```

## Conditional Pipeline

A predicate function inspects the prompt and routes to the appropriate branch agent.

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
result = await pipeline.run("Implement a quicksort algorithm")  # -> code_agent
result = await pipeline.run("Explain how quicksort works")      # -> research_agent
```

If the predicate returns an unknown key, `PipelineExecutionError` is raised.

## Nested Pipelines

Pipelines are themselves valid pipeline stages. Nest them freely.

```python
from vidbyte import SequentialPipeline, ParallelPipeline

pipeline = SequentialPipeline([
    planner_agent,
    ParallelPipeline([solver_a, solver_b, solver_c]),  # receives planner output
    implementer_agent,                                  # receives joined solver outputs
])
result = await pipeline.run("Build a recommendation engine")
```

## Sync Entry Point

```python
result = pipeline.run_sync("Build a binary search tree")
```

Cannot be called from inside an active `asyncio` event loop.

## PipelineNode Type

A `PipelineNode` is `BaseAgent | BasePipeline`. Any valid agent or pipeline can be a stage.

```python
from vidbyte import PipelineNode

# PipelineNode = BaseAgent | BasePipeline
# Agents and pipelines are interchangeable as stages
```

## Error Handling

| Error | When |
|-------|------|
| `PipelineExecutionError` | Empty stages/branches at construction; unknown predicate key at runtime; `run_sync` from active event loop |
| `AgentExecutionError` | Any agent stage raises |
| Other exceptions | Propagate unwrapped from the failing stage |

`ParallelPipeline` uses `asyncio.gather` without `return_exceptions`; the first agent failure aborts all concurrent branches.

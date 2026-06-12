# Agents

The Vidbyte SDK uses agents as the executable actor abstraction for AI workflows.
An agent combines a system prompt, a runner or provider configuration, optional
tools, structured context, tracing, runtime configuration, and handoff behavior.

## Role In The SDK

`vidbyte.agents` is the layer most application code touches first. It exposes
`Agent` / `BaseAgent`, `AgentInput`, agent messages, local registries, handoff
agents, and swappable runtime implementations. Agents normalize input, build a
context window, select a model modality, invoke a runner, execute tools when the
runtime requests them, and return an `AgentMessage`.

## Design Philosophy

Agents are explicit composition objects rather than hidden global state. The SDK
keeps the prompt, tools, context manager, middleware, trace settings, and runner
visible at construction time so developers can reason about what the model sees
and what local capabilities it can call.

The default linear runtime is the compatibility path for middleware and continual
trace artifacts. Non-linear runtimes such as search and actor-model execution are
separate runtime choices with narrower compatibility rules.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents rely on the same core
ideas documented here: explicit prompts, controlled tools, managed context,
runtime policies, and traceable outputs.

## Usage

```python
from vidbyte import Agent, tool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="analyst",
    system_prompt="Answer directly and cite uncertainty.",
    runner=my_runner,
    tools=[lookup_metric],
)

reply = await agent.arun("Summarize user 42.")
print(reply.content)
```

Use `AgentInput` when a single run needs additional metadata or context items:

```python
from vidbyte import AgentInput
from vidbyte.context.primitives import TextContextItem

reply = await agent.arun(
    AgentInput(
        "Review this change.",
        context_items=(TextContextItem(title="Reviewer note", content="Focus on API compatibility."),),
    )
)
```

Configure provider-backed agents without manually constructing a runner:

```python
from vidbyte import Agent

agent = Agent(
    name="website-feedback-agent",
    system_prompt="Give concise, actionable feedback.",
    provider="openai",
    model_name="gpt-4.1",
    temperature=0.2,
)
```

Expose an agent as a tool when it has metadata describing when to use it:

```python
from vidbyte.lib.dataclasses.agents import AgentMetadata

reviewer = agent.fork(
    name="reviewer",
    agent_metadata=AgentMetadata(
        name="reviewer",
        description="Reviews drafts and returns improvement suggestions.",
        use_cases=("review feedback drafts", "tighten learning explanations"),
    ),
)

reviewer_tool = reviewer.as_tool()
```

## Feature Coverage

- Direct execution through `run()`, `arun()`, and `generate_reply()`.
- `AgentInput` for per-call context items, metadata, and modality requests.
- Provider/model configuration for model-backed runners without custom runner wiring.
- Agent-local tools through `tools=[...]` and `Tools` catalogs.
- Context managers, unmanaged context items, and context-window algorithms.
- Runtime configuration for max iterations, token budgets, compaction triggers, and runtime type.
- Middleware on compatible direct/linear runtimes.
- Tracing through `trace=` and structured continual artifacts through `trace_option=`.
- Handoff support through explicit `handoff()` calls or configured automatic handoff generation.
- Forking for reusable variants without mutating the source agent.

## Key Modules

- `base.py`: `BaseAgent`, runner normalization, tool binding, context assembly, trace setup, and runtime dispatch.
- `client.py`: namespace client used by `VidbyteSDK().agents`.
- `runtimes/`: linear, search, and actor-model runtime components.
- `handoff.py`: structured handoff generation from a completed agent run.
- `types.py`: agent messages, input envelopes, cards, specs, and modality types.

## Related Layers

Agents compose with [`context`](../context/README.md), [`tools`](../tools/README.md),
[`middleware`](../middleware/README.md), [`providers`](../providers/README.md),
[`pipelines`](../pipelines/README.md), and [`trace`](../trace/README.md).

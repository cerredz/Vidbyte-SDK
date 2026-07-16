# Agents

The Vidbyte SDK uses agents as the executable actor abstraction for AI workflows.
An agent combines a system prompt, provider/model configuration, optional
tools, structured context, tracing, runtime configuration, and handoff behavior.

## Role In The SDK

`vidbyte.agents` is the layer most application code touches first. It exposes
`Agent` / `BaseAgent`, `AgentInput`, agent messages, local registries, handoff
agents, and swappable runtime implementations. Agents normalize input, build a
context window, infer the runner from provider/model configuration, execute tools when the
runtime requests them, and return an `AgentMessage`.

For open-ended team work, `vidbyte.agents.multi` exposes `MultiAgent`, a
`BaseAgent`-compatible facade whose manager plans against a shared immutable
ledger snapshot, delegates one worker per round, and can replan after failure.

For implementation-plus-challenge work, `AdversarialAgent` is a runnerless
`BaseAgent`-compatible facade. It forks one configured worker and a configured
number of adversaries, runs reviewers sequentially against an immutable round
snapshot, and returns only the worker's final revision. Child agents own all
provider/model, tools, middleware, permissions, structured output, and MCP
configuration.

```python
from vidbyte import AdversarialAgent, AdversarialSettings

reviewed = AdversarialAgent(
    name="reviewed-worker",
    system_prompt="Deliver the strongest verified implementation.",
    worker=configured_worker,
    adversary=configured_read_only_reviewer,
    settings=AdversarialSettings.specialist_panel(
        ("correctness", "security"),
        adversarial_rounds=2,
        fresh_adversaries_each_round=True,
        max_child_calls=7,
    ),
)

reply = await reviewed.arun("Implement the change.")
```

The facade constructor has no runner/provider/model parameters. Its exact call
count is `1 + adversarial_rounds * (num_adversaries + 1)`. Configure read-only
review tools explicitly, and remember that worker revisions can repeat write-side
effects. Specialty panels apply distinct lenses to forks of one adversary
prototype, not separately configured or cross-provider reviewers. The portable
settings contract lives in `vidbyte/lib/dataclasses/adversarial.py`; full artifacts
are retained in `last_result`, while public message metadata is bounded. See
[`skills/vidbyte-sdk/adversarial-agent.md`](../../skills/vidbyte-sdk/adversarial-agent.md).

## Design Philosophy

Agents are explicit composition objects rather than hidden global state. The SDK
keeps the prompt, tools, context manager, middleware, trace settings, and runner
inference visible at construction time so developers can reason about what the model sees
and what local capabilities it can call.

The default linear runtime is the compatibility path for middleware and continual
trace artifacts. Non-linear runtimes such as search and actor-model execution are
separate runtime choices with narrower compatibility rules.

## Usage

```python
from vidbyte import Agent, tool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="analyst",
    system_prompt="Answer directly and cite uncertainty.",
    provider="openai",
    model_name="gpt-4.1",
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

## Durable Sessions

Agents can opt into durable sessions without moving persistence into the agent constructor:

```python
from vidbyte import FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
session = agent.persist(store=store)
reply = await agent.arun("Continue the investigation.")
print(agent.session is session)
```

`agent.persist(...)` delegates to `vidbyte.sessions.Session(agent, ...)`. Once bound, direct `agent.arun(...)` and `agent.run(...)` calls record checkpoints with the same policy as `session.arun(...)` and `session.run(...)`; `agent.session` returns the current session or `None`.

`MultiAgent` is intentionally excluded from durable sessions because its
orchestrator, transfer callbacks, worker factories, and live ledger cannot be
encoded by `RunState` without changing behavior on restore.

## Ledger-Driven Teams

```python
from vidbyte import AgentBinding, AgentTransfer, MultiAgent

team = MultiAgent(
    name="team",
    system_prompt="Own the goal, surface blockers, and finish with evidence.",
    orchestrator=manager_agent,
    agents=[
        AgentBinding(
            researcher_agent,
            transfer=AgentTransfer(report_validator=verify_research_report),
        )
    ],
)

reply = await team.arun("Investigate the incident and recommend a response.")
ledger = team.last_ledger
```

The default transfer sends deterministic JSON and treats non-blank worker text
as completed but unverified evidence. Use a report validator to mark evidence
verified. Use pipelines for fixed text flow and workflows for code-owned state
machines; use `MultiAgent` when the manager must own progress and recovery.

## Key Modules

- `base.py`: `BaseAgent`, inferred runner construction, tool binding, context assembly, trace setup, and runtime dispatch.
- `adversarial.py`: runnerless worker/adversary sequencing, result records, failure policy, and child cleanup.
- `../lib/dataclasses/adversarial.py`: portable immutable adversarial settings, specialties, timeout, and call-budget validation.
- `client.py`: namespace client used by `VidbyteSDK().agents`.
- `runtimes/`: linear, search, and actor-model runtime components.
- `handoff.py`: structured handoff generation from a completed agent run.
- `multi/`: ledger-driven manager/worker orchestration and transfer controls.
- `types.py`: agent messages, input envelopes, cards, and specs.

## Related Layers

Agents compose with [`context`](../context/README.md), [`tools`](../tools/README.md),
[`middleware`](../middleware/README.md), [`providers`](../providers/README.md),
[`pipelines`](../pipelines/README.md), and [`trace`](../trace/README.md).

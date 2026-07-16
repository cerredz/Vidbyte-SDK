# Context

The Vidbyte SDK treats context as structured runtime information, not just text
that gets appended to a prompt. Context objects make files, tasks, memory,
progress, tool calls, handoff notes, and context-window policies explicit.

## Role In The SDK

`vidbyte.context` provides `ContextManager`, `BaseContext`, context item
dataclasses, multi-agent context composition, handoff models, compaction engines, and context-window algorithms.
Agents use this layer to build the system and message context that reaches a
runner. Tools and middleware can also update managed context primitives during a
run.

## Design Philosophy

Context should be inspectable, typed, and policy-driven. The SDK separates
content items from placement and admission policy so applications can decide
what belongs near the system prompt, what belongs near recent conversation, and
what should be compacted or omitted.

## Usage

```python
from vidbyte import AgentForkSettings, ContextManager
from vidbyte.context.primitives import FileContextItem, TaskContextItem

context = ContextManager([
    TaskContextItem(
        goal="Fix the failing tests",
        progress="Read the failing assertion and related runtime code.",
    ),
    FileContextItem.from_path("README.md", include_content=True),
])

agent = agent.fork(AgentForkSettings(context_manager=context))
reply = await agent.arun("Summarize the current task state.")
```

Managed primitives are addressable by `primitive_id`:

```python
from vidbyte.context.primitives import ProgressContextItem

context.upsert(
    ProgressContextItem(
        primitive_id="progress:implementation",
        title="Implementation Progress",
        content="Middleware checks have passed.",
    )
)
```

## General Problem-Solving Challenges

The SDK includes domain-neutral primitives for keeping adversarial questions
visible while a person, team, or agent works through a problem. They cover
framing and objectives, assumptions and evidence, decisions and alternatives,
execution risks and feedback, and premature closure or unresolved escalation.

```python
from vidbyte import (
    AssumptionChallengeContextItem,
    CompletionGateContextItem,
    ContextManager,
)

context = ContextManager()
context.place_after_tools(
    AssumptionChallengeContextItem(
        assumption="Demand will remain constant during the pilot.",
        falsifier="Observed demand changes materially during the pilot.",
        validation_method="Compare weekly demand measurements.",
        resolution_condition="Two stable measurement periods are observed.",
    )
)
context.place_after_system_prompt(
    CompletionGateContextItem(
        claimed_result="The intervention worked.",
        desired_outcome="Wait times decreased without reducing service quality.",
        missing_validation=("Compare against baseline", "Review quality measures"),
        severity="blocking",
    )
)
```

These records describe concerns; they do not automatically enforce a boundary,
investigate a claim, change status, resolve a dispute, or stop an agent from
finishing. `status` and `severity` are caller-managed strings. A stable
`primitive_id` plus deliberate placement can keep an unresolved concern
persistent and prominent across iterations.

## Key Modules

- `manager.py`: ordered context item collection and managed primitive registry.
- `multi_agent.py`: builds orchestration contexts and composes manager-facing primitives.
- `window.py` and `presets.py`: context-window preset resolution.
- `primitives/`: typed context items for files, tasks, progress, memory, responses, tool calls, multi-agent orchestration state, and general problem-solving challenges.
- `algorithms/`: reflexion, grader, tool-result, and trajectory-checkpoint algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

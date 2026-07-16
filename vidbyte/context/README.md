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

### Critique, adjudicate, and revise

`ContextWindow.preset.critique_adjudicate_revise` runs a normal producer once,
then sends its exact candidate to three concurrent critics. Critics receive no
producer history, memory, middleware, implicit tools, or peer findings. A fresh
adjudicator removes duplicates, rejects unsupported criticism, and resolves
contradictions using IDs only; SDK code constructs the accepted findings that a
fresh revision worker receives.

All stage artifact and tool allowlists are empty by default. Custom access uses
exact names from `BaseContext.artifacts` and the agent's user-tool catalog:

```python
from vidbyte import CritiqueAdjudicateReviseAlgorithm, ReviewStageAccess
from vidbyte import ContextWindowAlgorithm

algorithm = ContextWindowAlgorithm(
    name="critique_adjudicate_revise",
    critique_adjudicate_revise=CritiqueAdjudicateReviseAlgorithm(
        critic_access=ReviewStageAccess(allowed_artifact_names=("requirements",)),
        revision_access=ReviewStageAccess(
            allowed_artifact_names=("requirements",),
            allowed_tool_names=("apply_patch",),
        ),
    ),
)
```

Defaults fail closed. Opt-in `RETURN_CANDIDATE` terminal policies return the
producer candidate with degraded metadata, but cannot roll back producer or
stage tool side effects. Parallel critic tools additionally require explicit
`allow_parallel_critic_tools=True` because arbitrary custom tools may not be
concurrency-safe.

## Key Modules

- `manager.py`: ordered context item collection and managed primitive registry.
- `multi_agent.py`: builds orchestration contexts and composes manager-facing primitives.
- `window.py` and `presets.py`: context-window preset resolution.
- `primitives/`: typed context items for files, tasks, progress, memory, responses, tool calls, and multi-agent orchestration state.
- `algorithms/`: reflexion, grader, critique-adjudicate-revise, tool-result, and inner-loop algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

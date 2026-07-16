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

## Key Modules

- `manager.py`: ordered context item collection and managed primitive registry.
- `multi_agent.py`: builds orchestration contexts and composes manager-facing primitives.
- `window.py` and `presets.py`: context-window preset resolution.
- `primitives/`: typed context items for files, tasks, progress, memory, responses, tool calls, and multi-agent orchestration state.
- `algorithms/`: reflexion, grader, specialist-panel, tool-result, and inner-loop algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

## Specialist Panel

`ContextWindow.preset.specialist_panel` runs one producer and reviews its exact
candidate concurrently with five independent specialist roles. The algorithm is
review-only: it preserves the producer's `output`, `structured`, `calls`,
`strategy_name`, and existing metadata, then adds a versioned report at
`result.metadata["specialist_panel"]`.

Each reviewer receives only the original task, exact candidate, explicitly named
artifacts, and explicitly named cloned user tools. It receives no producer history,
memory, system prompt, previous calls, middleware, implicit completion tool, private
options, or another specialist's findings. Missing or duplicate artifact names,
unknown tools, and oversized exact inputs fail before fanout; the implementation
never silently truncates reviewer evidence.

`min_successful` defaults to all roles. Lower it deliberately to accept a partial
report containing ordered typed failures for timed-out or invalid reviews. Review
order always follows configured role order, not completion order, and findings are
not merged or adjudicated. One producer model run plus one concurrent run per role
is billed. Use critique-adjudicate-revise when findings should be filtered and sent
to a revision worker instead of remaining advisory metadata.

# Context

The Vidbyte SDK treats context as structured runtime information, not just text
that gets appended to a prompt. Context objects make files, tasks, memory,
progress, tool calls, handoff notes, and context-window policies explicit.

## Role In The SDK

`vidbyte.context` provides `ContextManager`, `BaseContext`, context item
dataclasses, handoff models, compaction engines, and context-window algorithms.
Agents use this layer to build the system and message context that reaches a
runner. Tools and middleware can also update managed context primitives during a
run.

## Design Philosophy

Context should be inspectable, typed, and policy-driven. The SDK separates
content items from placement and admission policy so applications can decide
what belongs near the system prompt, what belongs near recent conversation, and
what should be compacted or omitted.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents need durable task state,
learner progress, retrieved artifacts, and tool outcomes to be represented as
structured context rather than fragile prompt concatenation.

## Usage

```python
from vidbyte import ContextManager
from vidbyte.context.primitives import FileContextItem, TaskContextItem

context = ContextManager([
    TaskContextItem(
        goal="Fix the failing tests",
        progress="Read the failing assertion and related runtime code.",
    ),
    FileContextItem.from_path("README.md", include_content=True),
])

agent = agent.fork(context_manager=context)
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

Place managed primitives in different context-window zones:

```python
from vidbyte.context.primitives import TextContextItem

context.place_after_system_prompt(
    TextContextItem(title="Policy", content="Prefer concise, learner-centered feedback.")
)
context.place_after_tools(
    TextContextItem(title="Latest Tool Finding", content="The rubric score changed from 3 to 4.")
)
```

Select a context-window algorithm on an agent:

```python
from vidbyte import ContextWindow

agent = agent.fork(algorithm=ContextWindow.preset.no_raw_tool_outputs)
```

## Feature Coverage

- `ContextManager` for ordered context items and managed primitive registries.
- `BaseContext` and `BaseAgentContext` compatibility dataclasses.
- File, document, task, progress, memory, response, artifact, git diff, and tool-call context items.
- Placement controls for top-of-context, end-of-context, and conversation-message rendering.
- Context compaction modes, stats, and deterministic compaction engines.
- Context-window algorithms for reflexion, multi-provider grading, trajectory checkpoints, and tool-result admission.
- Handoff models for engineering, research, and minimal handoff artifacts.
- Conversion of structured items into context artifacts, memory, responses, and tool calls for runtime use.

## Key Modules

- `manager.py`: ordered context item collection and managed primitive registry.
- `window.py` and `presets.py`: context-window preset resolution.
- `primitives/`: typed context items for files, tasks, progress, memory, responses, and tool calls.
- `algorithms/`: reflexion, grader, tool-result, and trajectory-checkpoint algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

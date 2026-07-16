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
- `algorithms/`: reflexion, grader, parallel-panel, tool-result, and trajectory-checkpoint algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

## Parallel Panel

Parallel Panel runs the normal producer once and then asks multiple independent,
model-only reviewers to inspect the same completed candidate. Reviews are
advisory, unadjudicated metadata: the algorithm does not revise the candidate,
and the producer's `output`, `structured`, `calls`, and `strategy_name` remain
unchanged.

Configure the public algorithm directly when the wrapper is useful elsewhere:

```python
from vidbyte import ContextWindowAlgorithm, ParallelPanelAlgorithm

algorithm = ContextWindowAlgorithm(
    name="parallel_panel",
    parallel_panel=ParallelPanelAlgorithm(
        reviewer_count=3,
        min_successful_reviews=2,
        artifact_names=("requirements", "evidence"),
        per_reviewer_timeout_seconds=30.0,
    ),
)
```

Or construct the same wrapper through the preset namespace:

```python
from vidbyte import ContextWindow

algorithm = ContextWindow.preset.parallel_panel(
    reviewer_count=3,
    min_successful_reviews=2,
    max_concurrency=3,
)
```

Each reviewer receives exactly the original task, exact producer candidate, and
the name, declared type, and exact content of context artifacts explicitly named
by `artifact_names`. It receives no producer system prompt, history, scratch
reasoning, tool transcript, runtime metadata, filesystem paths, memory, context
items, unlisted artifacts, tools, or MCP access. Missing, ambiguous, or oversized
allowlisted evidence fails before any reviewer starts; candidate and evidence
content is never silently truncated.

All reviewer tasks are scheduled before collection. A barrier prevents findings
from entering result metadata until every first-round branch has settled.
Individual reviewer failures and timeouts become bounded failure records when
`min_successful_reviews` still succeeds. Falling below that threshold raises
`AgentExecutionError`. A whole-panel timeout or caller cancellation cancels
unfinished reviewers and publishes no findings.

Reviewer calls increase provider cost by `reviewer_count` calls after the producer
and can increase tail latency. `max_concurrency` bounds in-flight calls, not total
calls. Standard asynchronous runners can overlap; a custom synchronous runner
blocks the event-loop thread, so its metadata reports `sync_constrained` and its
timeouts cannot preempt it while blocked. Custom asynchronous runners must
support concurrent calls through the same runner handle.

Successful recorder traces can be checked with
`ParallelPanelContextWindowTemplate`; see
[`skills/vidbyte-sdk/context-window-templates.md`](../../skills/vidbyte-sdk/context-window-templates.md)
for the exact scheduling, barrier, and collection slot contract.

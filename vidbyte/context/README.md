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
- `algorithms/`: reflexion, grader, pairwise-tournament, tool-result, and trajectory-checkpoint algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

## Pairwise Tournament

`PairwiseTournamentAlgorithm` is a return-level algorithm that runs 2-16
independent producer candidates, assigns opaque IDs, and advances adjacent
entrants through a deterministic single-elimination bracket. Each match uses two
fresh judge runtimes: one sees candidate X as A and Y as B, while the other sees
the same exact strings with positions reversed. Only agreement after mapping
slots back to candidate IDs is judge consensus.

Judges receive a positive projection: the original task, the current anonymous
pair, exact uniquely named artifacts, and exact allowlisted `SAFE`/`READ` tools.
They do not inherit producer history, middleware, context manager, internal
tools, metadata, provider identity, prior decisions, seeds, or bracket state.
Oversized or ambiguous evidence fails preflight and is never silently truncated.

The returned `AgentResult` preserves the winner's exact `output`, `structured`,
`calls`, and existing metadata. Its strategy becomes `pairwise_tournament`, and
`metadata["pairwise_tournament"]` adds hashes, source provenance, seed order,
rounds, byes, structural leg decisions, fallback labels, timings, and bounded
accounting. Candidate bodies, judge summaries, tool payloads, prompts, and raw
exception messages are excluded from that report.

Default unresolved and failure policies raise. `LOWER_SEED` is opt-in and is
recorded as non-consensus. Use `TournamentSeeding.CONTENT_HASH` when seed order
should depend on candidate content rather than provider-map insertion order.

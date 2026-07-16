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
- `algorithms/`: reflexion, grader, tool-result, and trajectory-checkpoint algorithms.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

## Prosecutor / Defender / Judge

`ContextWindow.preset.prosecutor_defender_judge` is a return-level,
review/verdict-only algorithm. It performs one ordinary producer pass and then
runs prosecutor, defender, and judge roles strictly in that order. The SDK
assigns allegation IDs, requires the defender and judge to return the same IDs
in the same order, and derives `pass` or `needs_changes` from surviving judge
decisions. Review text never returns to the producer and never replaces its
output or structured result.

Each role receives a newly constructed `AgentRuntime` and `BaseAgentContext`.
The stage projection contains only its role prompt, original task, exact
candidate, explicitly named artifact contents, explicitly named tool schemas and
stage-local results, and normalized protocol records from the preceding role.
Producer history, system prompt, scratch state, memory, context items, file paths,
run metadata, context manager, middleware, invocation options, raw reviewer
conversations, and implicit internal tools are excluded.

```python
from vidbyte import (
    ContextWindowAlgorithm,
    DebateStageSettings,
    ProsecutorDefenderJudgeAlgorithm,
)

review = ProsecutorDefenderJudgeAlgorithm(
    prosecutor=DebateStageSettings(
        artifact_names=("requirements",),
        tool_names=("grep",),
    ),
    defender=DebateStageSettings(
        artifact_names=("requirements", "implementation-notes"),
        tool_names=("grep",),
    ),
    judge=DebateStageSettings(
        provider="openai",
        model="gpt-4.1",
        artifact_names=("requirements",),
    ),
)

algorithm = ContextWindowAlgorithm(
    name="prosecutor_defender_judge",
    prosecutor_defender_judge=review,
)
```

Artifact names must resolve to one unambiguous `ContextArtifact`. Inputs that
exceed configured exact-review bounds fail instead of being truncated. Review
tools are restricted to explicit `SAFE`/`READ` capabilities; MCP bridges,
delegation/fork tools, live primitive bindings, and mutating/executing tools are
rejected. A standalone custom tool remains an explicit authority grant: the SDK
cannot prove that developer code will not reveal its own closure or external
service state.

Successful details live under
`result.metadata["prosecutor_defender_judge"]`, including the candidate hash,
normalized allegations, defenses, decisions, survivor IDs, verdict, stage
provenance, stop reasons, timing, and bounded accounting. Stage calls never enter
producer `calls` or top-level producer tool-call metadata. Structural algorithm
trace attributes contain identifiers, resource names, hashes, lengths, counts,
timing, and status—not task, candidate, artifact, allegation, defense, decision,
tool argument/result, or provider response text. Existing global tracing policy
still governs ordinary nested provider/tool spans.

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
- `algorithms/`: reflexion, grader, independent-critic, parallel-panel, tool-result, and trajectory-checkpoint algorithms.
- `algorithms/independent_critic.py`: immutable review-only critic policy, exact evidence serialization, and bounded report normalization.
- `algorithms/parallel_panel.py`: immutable independent first-round parallel review policy.
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

## Independent Critic

`ContextWindow.preset.independent_critic` runs the normal producer once, then
reviews its exact candidate in a fresh runtime. Reviewer visibility is built
from an empty context plus the original task, candidate, and explicit artifact
and tool allowlists. Producer history, system prompt, metadata, context items,
middleware, provider options, and implicit tools remain outside the boundary.

The public candidate stays unchanged. Advisory, unadjudicated findings appear
under `result.metadata["independent_critic"]`. The default raises when review
cannot produce valid JSON; custom configuration can choose
`CriticFailurePolicy.RETURN_CANDIDATE`, which returns the producer result with
an explicit `status="review_failed"` marker instead of claiming success.

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


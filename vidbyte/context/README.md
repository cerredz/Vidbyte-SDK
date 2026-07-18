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
- `primitives/`: typed context items for files, tasks, progress, memory, responses, tool calls, and multi-agent orchestration state.
- `algorithms/`: reflexion, grader, critique-adjudicate-revise, tool-result, and inner-loop algorithms.

- `primitives/`: typed context items for files, tasks, progress, memory, responses, tool calls, multi-agent orchestration state, and general problem-solving challenges.
- `algorithms/`: reflexion, grader, tool-result, and trajectory-checkpoint algorithms.
- `algorithms/independent_critic.py`: immutable review-only critic policy, exact evidence serialization, and bounded report normalization.
- `compaction.py`: deterministic context compaction contracts and stats.
- `handoff/`: structured handoff models.

## Related Layers

Context is consumed by [`agents`](../agents/README.md), updated by some
[`tools`](../tools/README.md), and bounded by [`middleware`](../middleware/README.md).

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

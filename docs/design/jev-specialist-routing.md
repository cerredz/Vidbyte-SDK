# Jev specialist routing

## Problem

A JevAgent owner often has a few agents that are each better at one kind of work: a schema agent, a writing agent, a data analyst. They want JevAgent to hand a whole task to the right one, without building a multi-agent system and without Jev generating anything.

## Settings shape

JevAgent now takes two settings objects:

- `JevAgentSettings` describes the agents that generate: the main agent's name, prompt, model, tools, permissions, and loop, plus `agents`, a tuple of `JevSpecialist(title, description, agent)`.
- `JevRuntimeSettings` describes Jev's own policy: `decision` (the TypeSafe model), `preflight` (the enabled flags), and `tool_selector_threshold`.

`JevAgent(settings, runtime_settings=None)` defaults the runtime settings to no Jev policy at all. `JevSpecialist` is a lib record (`vidbyte/lib/dataclasses/jev.py`). It holds the agent by shape rather than by `isinstance`, so `vidbyte.lib` never imports the agents layer.

## Approach

Choosing a specialist is one more question in the existing preflight request:

1. `JevPreflightGate.combine` appends the specialist Choice question (`vidbyte/lib/jev/preflight/specialist.py`) after the enabled presets' questions. There is one option per specialist, in the configured order. Each option carries the shared criterion plus that specialist's `description` as its `scope`, and `none` is always last.
2. `JevPreflightGate.pass_` handles the presets exactly as before. Only when the gate passes does it record the top-ranked option as `specialist` and report its title on `JevAgent.response.specialist`.
3. `JevRuntime.arun` has one extra branch. If the gate chose a specialist, it runs `specialist.agent.arun(message)`, the specialist's own linear generative loop, and returns that reply through `JevResponse.delegated`. Otherwise the main agent runs as before.

## Failure and fallback

A missing TypeSafe key, a provider error, a missing answer, or a `none` answer all leave the main agent on the run. That is the same fail-open policy every preflight preset follows. A closed gate (an unclear request) stops the run before any specialist or the main agent runs. A specialist's own execution error surfaces to the caller and is not retried on the main agent.

## Alternatives rejected

- **Overlaying the chosen specialist's settings onto the running JevAgent.** This means snapshotting and restoring about 25 BaseAgent fields, adding a `_prepare_run` hook to BaseAgent, and holding a semaphore so overlapping runs do not mix profiles. Review on PR #461 rejected it as far more code than the feature needs. Running the chosen agent directly needs none of it.
- **Recording the chosen label without running it.** This makes the feature observable but inert. Review asked for the main agent to become the chosen one.
- **Question text as a Markdown prompt asset.** Jev questions are typed `JevBrief`/`JevCriterion` dataclasses in `vidbyte/lib/jev/preflight/`, next to the clarity questions. Prompt assets are for generative-model prompts.

## Out of scope

The tool selector keeps its own path. It filters the main agent's tools only, so a chosen specialist runs with its own tool catalog. Any specialist-level tool selection belongs to a separate change.

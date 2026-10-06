# Handoffs

## What a handoff is

A handoff is a sectioned document that captures enough state for another agent
or a human to continue work cold. In the Vidbyte SDK the same `Handoff` object
plays three roles:

- **Context primitive**: it has `kind = "handoff"`, `primitive_id`,
  `primitive_frozen`, `metadata`, and `to_context_text()`, so a filled handoff
  can be used as a `ContextItem`.
- **Spec**: its ordered `sections` mapping is `section title -> authoring
  guidance`, which tells a `HandoffAgent` what document shape to produce.
- **Output**: after generation, `fill()` returns the same concrete subclass with
  `sections` changed to produced content and `metadata["filled"] = True`.

There is intentionally no top-level `vidbyte/handoff/` subsystem. The primitive
family lives under `vidbyte/context/handoff/`, the generator lives in
`vidbyte/agents/handoff.py`, and the agent-facing tool lives under
`vidbyte/tools/builtins/handoff/`.

## Quick use cases

### Generate a handoff on demand

Any agent can summarize its most recent run:

```python
from vidbyte import Agent, EngineeringHandoff

agent = Agent(name="worker", system_prompt="...", runner=runner)
reply = await agent.arun("refactor the rate limiter")

doc = await agent.handoff()                      # MinimalHandoff by default
doc = await agent.handoff(EngineeringHandoff())  # fixed engineering shape
```

`BaseAgent.handoff(spec=None, *, by=None)` renders the source run with
`HandoffAgent.render_source_run()`: source agent name, system prompt, last task,
full message transcript, recorded tool calls with lifecycle state and output,
and final result. It then uses a `HandoffAgent` built from the source agent's
provider/model/runner config.

Pass `by=` when you want a specific pre-built generator agent:

```python
from vidbyte import AgentClient, ResearchHandoff

generator = AgentClient().handoff(ResearchHandoff(), runner=cheap_runner)
doc = await agent.handoff(ResearchHandoff(), by=generator)
```

On-demand `agent.handoff()` returns the document. It does not automatically
append it to `agent.handoffs`; call `agent.record_handoff(doc)` yourself if you
want it in the agent's handoff collection or context registry.

### Auto-handoff after every run

Pass a spec at construction to generate a handoff after each reply:

```python
from vidbyte import Agent, EngineeringHandoff

agent = Agent(
    name="worker",
    system_prompt="...",
    runner=runner,
    handoff=EngineeringHandoff(),
)

reply = await agent.arun("refactor the rate limiter")

doc = reply.metadata["handoff"]
doc = agent.last_handoff
all_docs = agent.handoffs
```

Auto-handoff is best-effort. If handoff generation fails, the primary reply is
still returned, `reply.metadata["handoff_error"]` is set, and
`agent.last_handoff` is reset to `None`.

### Let the agent author handoffs mid-run

Add `CreateHandoffTool` to the agent's tools. The model can then call
`create_handoff(title, sections, audience?, instructions?)` whenever it decides
to checkpoint state:

```python
from vidbyte import Agent
from vidbyte.tools.builtins.handoff import CreateHandoffTool

agent = Agent(
    name="worker",
    system_prompt="Create handoffs when useful for continuation.",
    runner=runner,
    tools=[CreateHandoffTool()],
)
```

This path is different from preset generation. The model supplies the section
titles and the section content directly. Each call creates a `Handoff`, assigns
a stable id such as `handoff:1`, records it through `agent.record_handoff()`,
and returns the rendered markdown as the tool output.

### Use `HandoffAgent` standalone

Use the client factory when you already have a source transcript or run digest:

```python
from vidbyte import AgentClient, ResearchHandoff

gen = AgentClient().handoff(ResearchHandoff(), runner=runner)
doc = await gen.generate_handoff(some_transcript_string)
```

Or reuse a source agent's runner and provider configuration:

```python
from vidbyte import HandoffAgent, EngineeringHandoff

gen = HandoffAgent.from_source_agent(source_agent, EngineeringHandoff())
doc = await gen.generate_handoff(HandoffAgent.render_source_run(source_agent))
```

## The primitive layer

`vidbyte/context/handoff/base.py` defines `Handoff`.

Important fields and methods:

| Member | Meaning |
|--------|---------|
| `kind` | Always `"handoff"` |
| `title` | Human-readable document title |
| `sections` | Ordered mapping of section titles to guidance or filled content |
| `instructions` | Extra authoring instructions included in context text and generator prompt |
| `metadata` | Includes `filled`, `extra_sections`, `raw_output`, or caller metadata |
| `primitive_id` | Optional stable id used by `ContextManager.upsert()` |
| `primitive_frozen` | Registry freeze flag used by context primitives |
| `to_context_text()` | Renders the handoff as markdown for context injection |
| `render_section_brief()` | Renders `- Title: guidance` lines for `HandoffAgent` |
| `fill(sections)` | Returns a filled copy of the same concrete handoff class |
| `is_filled` | True when `metadata["filled"]` is truthy |
| `section_titles()` | Ordered tuple of section titles |

Compatibility exports:

```python
from vidbyte import Handoff, MinimalHandoff, EngineeringHandoff, ResearchHandoff
from vidbyte.context import Handoff, MinimalHandoff, EngineeringHandoff, ResearchHandoff
from vidbyte.context.handoffs import Handoff
```

## Presets and custom specs

Prebuilt handoffs are classes, not factory functions:

```python
from vidbyte import MinimalHandoff, EngineeringHandoff, ResearchHandoff

minimal = MinimalHandoff()          # Summary, Next Steps
engineering = EngineeringHandoff()  # Objective, Changes Made, Verification Status, Open Threads, Risks & Gotchas, Next Steps
research = ResearchHandoff()        # Question, Findings, Sources, Confidence & Gaps, Recommended Next Queries
```

In a spec, section values are authoring instructions, not produced content:

```python
from vidbyte import Handoff

spec = Handoff(
    title="Migration Handoff",
    sections={
        "State": "What has migrated so far and what remains.",
        "Rollback": "How to revert safely if the migration fails.",
    },
    instructions="Write for an on-call engineer.",
)
```

After generation, the returned object has the same section keys, but the values
are filled document content.

## The generator layer

`vidbyte/agents/handoff.py` defines `HandoffAgent`, a thin `BaseAgent`
configuration specialized for filling `Handoff` specs.

Key methods:

| Method | Role |
|--------|------|
| `from_source_agent(source_agent, spec)` | Reuses the source agent's runner/provider/model config |
| `run_auto_handoff(source_agent, spec)` | Builds and runs the configured auto-handoff generator |
| `render_source_run(source_agent)` | Renders source agent, prompt, transcript, tools, and final result |
| `render_history(history)` | Renders `AgentMessage` transcript lines |
| `render_tool_calls(contexts)` | Renders tool calls with arguments, state, and output |
| `build_system_prompt()` | Combines the handoff prompt asset, title, section brief, and instructions |
| `build_output_schema()` | Builds the deterministic JSON schema from the spec |
| `generate_handoff(source)` | Runs the generator and returns a filled `Handoff` |
| `parse_sections(text)` | Public helper for JSON/markdown section parsing |

`build_output_schema()` requires a top-level JSON object with `sections`. When
the spec has fixed section titles, every title is required and
`additionalProperties` is `False`. When the spec has no fixed titles, additional
string-valued sections are allowed.

Parsing order:

1. Runtime structured output from `reply.metadata["structured"]`.
2. Raw JSON from `reply.content`.
3. Markdown header blocks such as `## Verification Status`.

Preservation rules:

- Matching spec sections populate `filled.sections`.
- Model-invented sections are stored in `filled.metadata["extra_sections"]`.
- If no matching sections contain content, the full raw output is stored in
  `filled.metadata["raw_output"]`.

## The `BaseAgent` surface

`vidbyte/agents/base.py` owns the public agent integration.

Public and important internal state:

| Member | Meaning |
|--------|---------|
| `handoff=` | Optional constructor spec for auto-handoff after every reply |
| `_handoff_spec` | Internal storage for the constructor spec, avoiding a name clash with `handoff()` |
| `last_handoff` | Most recent recorded handoff or `None` |
| `handoffs` | Ordered list of handoffs recorded on the agent |
| `last_prompt` | Prompt from the most recent run, used by source-run rendering |
| `last_reply` | Reply from the most recent run |

Methods:

| Method | Meaning |
|--------|---------|
| `handoff(spec=None, *, by=None)` | Generate a handoff for the latest run |
| `record_handoff(handoff)` | Append to `handoffs`, set `last_handoff`, and sync to context manager |
| `_sync_handoff_primitive(handoff)` | Upsert into `context_manager` when possible |
| `_run_auto_handoff(metadata)` | Best-effort auto-generation and metadata attachment |
| `fork(...)` | Propagates `_handoff_spec` to child agents |

Important behavior:

- `handoff()` summarizes the latest run framing. It reads `last_prompt`,
  `last_reply`, `history`, and recorded tool-call contexts.
- For multi-turn agents, the transcript uses full `agent.history`, while the
  "Original Task" field is the most recent prompt.
- `fork()` propagates the auto-handoff spec. Forked agents can therefore incur
  the same extra handoff generation call unless `handoff` is changed in a later
  API.

## The tool layer

`vidbyte/tools/builtins/handoff/create.py` defines `CreateHandoffTool`.

The model-facing tool is named `create_handoff` and has this input shape:

```json
{
  "title": "string, required",
  "sections": {
    "Section title": "Section content"
  },
  "audience": "string, optional",
  "instructions": "string, optional"
}
```

The current implementation is a direct authoring tool:

- It does not use the preset schema system.
- It does not call `HandoffAgent`.
- It does not accept `handoff_type`, `objective`, `scope`, `non_goals`, or
  `custom_sections`.
- It lets the model choose free-form section titles and content.
- It declares `binds_to_primitive="handoff"`, formally linking the tool to the
  handoff primitive kind.
- It is late-bound to the live agent by `BaseAgent._bind_agent_tool_context()`.
- Its description dynamically lists handoffs already authored this run so later
  calls can stay consistent.

Each successful call:

1. Validates that `title` is non-empty and `sections` is a non-empty object.
2. Builds `Handoff(title=..., sections=..., instructions=..., primitive_id=...)`.
3. Assigns `primitive_id = f"handoff:{len(agent.handoffs) + 1}"`.
4. Calls `agent.record_handoff(handoff)`.
5. Returns `ToolResult.success(...)` with rendered markdown and metadata
   containing `primitive_id` and `sections`.

Use `CreateHandoffTool` when the agent should decide when and how to checkpoint
its own work during a run. Use preset/custom specs when downstream code needs a
deterministic section shape.

## Handoffs as context

`Handoff.to_context_text()` renders a markdown document:

```markdown
Engineering Handoff

## Objective
...

## Next Steps
...
```

Because `Handoff` is context-compatible, you can pass a filled handoff to another
agent:

```python
doc = await agent_a.handoff(EngineeringHandoff())

agent_b = Agent(
    name="continuation",
    system_prompt="Continue from the supplied handoff.",
    runner=runner,
    context_items=[doc],
)
```

When `record_handoff()` is called and the source agent has a `context_manager`,
the handoff is also upserted into that registry if it has a `primitive_id`:

```python
agent.record_handoff(doc)  # syncs only if doc.primitive_id is set
```

Context sync is intentionally non-fatal. If no context manager exists, no sync
happens. If the context manager rejects the primitive, handoff recording still
succeeds.

## Behavior and eval assertions

Handoffs are part of the post-run behavior surface. `RunProbe` captures
`agent.last_handoff` and `agent.handoffs`; `Behavior` exposes them through
`agent.behavior.handoff`.

Predicates:

| Method | Meaning |
|--------|---------|
| `handoff_occurred()` | True if `last_handoff` exists |
| `handoff_is_filled()` | True if the last handoff exists and `is_filled` is true |
| `handoff_count()` | Number of handoffs recorded on the agent |
| `handoff_has_section(title)` | True if the last handoff has the section |
| `handoff_section_contains(title, substring)` | True if the section contains the substring |

Example:

```python
reply = await agent.arun("ship the change")

assert agent.behavior.handoff.handoff_occurred()
assert agent.behavior.handoff.handoff_has_section("Verification Status")
assert agent.behavior.handoff.handoff_section_contains("Verification Status", "passed")
```

These predicates are read-only. They inspect the frozen `RunProbe` snapshot and
do not mutate agent state.

## Prompt asset

The handoff generator prompt is stored as repository-backed prompt assets:

```text
vidbyte/prompts/prompts/handoff/handoff.md
vidbyte/prompts/prompts/handoff/handoff.json
```

It is exposed through:

```python
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts

prompt = Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT)
```

`HandoffAgent.build_system_prompt()` appends the output title, required section
brief, and any spec instructions to this prompt.

## Module layout

```text
vidbyte/context/handoff/base.py          Handoff base primitive
vidbyte/context/handoff/minimal.py       MinimalHandoff preset
vidbyte/context/handoff/engineering.py   EngineeringHandoff preset
vidbyte/context/handoff/research.py      ResearchHandoff preset
vidbyte/context/handoff/__init__.py      Handoff primitive exports
vidbyte/context/handoffs.py              Compatibility re-export shim

vidbyte/agents/handoff.py                HandoffAgent generator
vidbyte/agents/base.py                   handoff=, handoff(), record_handoff(), auto-handoff
vidbyte/agents/client.py                 AgentClient.handoff() factory

vidbyte/tools/builtins/handoff/create.py CreateHandoffTool
vidbyte/tools/builtins/handoff/__init__.py

vidbyte/evals/behavior/handoff.py        HandoffBehavior predicates
vidbyte/evals/behavior/probe.py          RunProbe handoff snapshot fields
vidbyte/evals/behavior/behavior.py       Behavior facade wiring

vidbyte/prompts/prompts/handoff/handoff.md
vidbyte/prompts/prompts/handoff/handoff.json
vidbyte/lib/enums/prompts.py             Prompt.HANDOFF_SYSTEM_PROMPT
```

Root exports:

```python
from vidbyte import (
    Handoff,
    MinimalHandoff,
    EngineeringHandoff,
    ResearchHandoff,
    HandoffAgent,
    CreateHandoffTool,
)
```

## Operational edges

- **Auto-handoff cost and latency**: `handoff=` adds a second model call after
  every successful `generate_reply()`. Use on-demand `agent.handoff()` when you
  do not need a checkpoint on every turn.
- **Most recent run framing**: `agent.handoff()` uses `last_prompt` and
  `last_reply` for the current run framing, with full `history` in the rendered
  transcript.
- **On-demand storage**: `agent.handoff()` returns a document but does not record
  it. Use `record_handoff()` if the result should appear in `agent.handoffs` or
  the context registry.
- **Auto-handoff failures**: `_run_auto_handoff()` catches exceptions, writes
  `metadata["handoff_error"]`, and preserves the primary reply.
- **Tool-authored handoffs are free-form**: `CreateHandoffTool` records exactly
  the model-supplied section names and content.
- **Preset handoffs are schema-shaped**: `HandoffAgent` asks the provider for a
  JSON object matching the spec's exact section keys.
- **Extra generated content is preserved**: `extra_sections` and `raw_output`
  metadata prevent invented or unparseable output from disappearing silently.
- **Fork propagation**: children created with `fork()` inherit `_handoff_spec`,
  so they inherit auto-handoff behavior.

## Choosing the right handoff path

| Need | Use |
|------|-----|
| A quick continuation summary after a run | `await agent.handoff()` |
| A deterministic engineering/research shape | `await agent.handoff(EngineeringHandoff())` or `ResearchHandoff()` |
| A handoff after every run | `Agent(..., handoff=EngineeringHandoff())` |
| Agent-authored checkpoints during a tool loop | `tools=[CreateHandoffTool()]` |
| A custom fixed schema consumed by code | `Handoff(title=..., sections=...)` with `HandoffAgent` |
| A generated handoff from arbitrary transcript text | `AgentClient().handoff(...).generate_handoff(text)` |
| A live context primitive for another agent | pass the filled `Handoff` in `context_items=[doc]` |

Preset/custom specs are best for pipelines and evals that consume a predictable
section shape. `CreateHandoffTool` is best for exploratory agents that should
decide for themselves what a continuation document needs to contain.

## Rules for changing handoffs

- Keep the primitive family under `vidbyte/context/handoff/`.
- Keep `vidbyte/context/handoffs.py` as the compatibility re-export shim.
- Keep `HandoffAgent` in `vidbyte/agents/handoff.py`; do not add a top-level
  handoff subsystem.
- When adding a new prebuilt handoff, subclass `Handoff`, set `DEFAULT_TITLE`,
  and override `default_sections()` with a `{title: description}` map.
- Put each new prebuilt handoff class in its own module under
  `vidbyte/context/handoff/`.
- Export new prebuilt classes from `vidbyte/context/handoff/__init__.py`,
  `vidbyte/context/handoffs.py`, `vidbyte/context/__init__.py`, and
  `vidbyte/__init__.py`.
- Make every default section description at least four clear sentences because
  those descriptions become both model-facing prompt guidance and JSON-schema
  field descriptions.
- Keep preset sections decision-oriented: each section should capture something
  the next agent or human needs to continue.
- Add tests for any runtime behavior change. At minimum, assert that a new preset
  exposes a non-empty distinct section map and that `fill()` preserves its type.
- Update this file whenever handoff APIs, tool inputs, behavior predicates,
  prompt assets, or module paths change.

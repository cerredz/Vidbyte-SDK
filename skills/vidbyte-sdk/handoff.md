# Handoffs

## What a handoff is

A handoff is a structured document describing what an agent did, so another agent
(or a human) can continue the work cold. In the Vidbyte SDK a handoff is one object,
`Handoff`, that plays three roles at once:

- **Context primitive** — it implements the `ContextItem` protocol, so a finished
  handoff drops straight into another agent via `context_items=[...]`.
- **Spec** — its ordered `sections` mapping (title → description) tells a `HandoffAgent`
  what structure to produce.
- **Output** — once produced, the same object holds the filled content (`fill()` returns
  the same subclass with `metadata["filled"] = True`).

There is intentionally **no** top-level `vidbyte/handoff/` subsystem. The primitive family
lives under `vidbyte/context/handoff/` and the agent in `vidbyte/agents/handoff.py`, built
from existing SDK primitives.

## Prebuilt handoffs (objects, not functions)

Prebuilt variants are subclasses that preset a curated section map. Construct them as objects:

```python
from vidbyte import EngineeringHandoff, ResearchHandoff, MinimalHandoff

spec = EngineeringHandoff()      # Objective, Changes Made, Verification Status, Open Threads, Risks & Gotchas, Next Steps
spec = ResearchHandoff()         # Question, Findings, Sources, Confidence & Gaps, Recommended Next Queries
spec = MinimalHandoff()          # Summary, Next Steps  (the default when none is given)
```

Bring your own structure by passing `sections` (or subclassing `Handoff`):

```python
from vidbyte import Handoff

spec = Handoff(sections={
    "Decision Log": "Key decisions and their rationale.",
    "Blockers": "What is currently blocking progress.",
}, title="Decision Handoff")
```

## The handoff agent

`HandoffAgent` is a thin configuration over `BaseAgent`. It builds its system prompt from
the comprehensive handoff prompt asset (`Prompt.HANDOFF_SYSTEM_PROMPT`, stored via
`vidbyte/prompts/prompts/handoff/handoff.json` and `handoff.md`) plus the spec's section
brief. It also sets `output_schema` from the handoff spec so providers with native
structured output support produce deterministic JSON. The agent parses structured JSON
first and keeps markdown parsing only as a defensive fallback.

```python
from vidbyte import VidbyteSDK, EngineeringHandoff

sdk = VidbyteSDK()
ho = sdk.agents.handoff(EngineeringHandoff(), provider="anthropic", model_name="claude-opus-4-8")
doc = await ho.generate_handoff(run_digest_text)   # -> filled EngineeringHandoff
```

You rarely build it directly — `BaseAgent.handoff()` does it for you.

## Producing a handoff from an agent's own run

Any agent can hand off its most recent run. The agent renders a digest of its system
prompt, the task, the transcript, the tool-call log, and the final result, then a
`HandoffAgent` (reusing the same runner by default) fills the document:

```python
agent = sdk.agents.base(system_prompt="...", runner=runner)
await agent.arun("do the task")
doc = await agent.handoff(EngineeringHandoff())     # -> filled Handoff
next_agent = sdk.agents.base(system_prompt="...", runner=runner, context_items=[doc])
```

Pass `by=` to use a specific generator agent (e.g. a cheaper model, or one with
trace-querying tools):

```python
doc = await agent.handoff(EngineeringHandoff(), by=my_custom_handoff_agent)
```

## Automatic handoff after a run

Set `handoff=` on any agent. When set, the agent automatically produces the handoff after
`generate_reply()` completes and attaches it to the reply:

```python
agent = sdk.agents.base(system_prompt="...", runner=runner, handoff=EngineeringHandoff())
reply = await agent.arun("do the task")

doc = reply.metadata["handoff"]    # the produced Handoff
doc = agent.last_handoff           # also cached here
```

Auto-handoff is **non-fatal**: if generation fails, the primary reply is still returned,
`reply.metadata["handoff_error"]` is set, and `agent.last_handoff` stays `None`. The
return type of `generate_reply()` is unchanged (still `AgentMessage`), so pipelines are
unaffected.

## Customization summary

| Want to change | How |
|----------------|-----|
| Document structure | Pass a prebuilt (`EngineeringHandoff()`), `Handoff(sections=...)`, or subclass `Handoff` |
| Output title / intent | `Handoff(title=..., instructions=...)` |
| Generating model / tools | `sdk.agents.handoff(spec, provider=..., model_name=..., tools=[...])` or `handoff(by=...)` |
| When it runs | Call `agent.handoff(...)` manually, or set `agent = ...(handoff=spec)` for auto-run |

## Module layout

```
vidbyte/context/handoff/base.py          Handoff base primitive
vidbyte/context/handoff/engineering.py   EngineeringHandoff preset
vidbyte/context/handoff/research.py      ResearchHandoff preset
vidbyte/context/handoff/minimal.py       MinimalHandoff preset
vidbyte/context/handoffs.py              compatibility re-export
vidbyte/agents/handoff.py       HandoffAgent (thin BaseAgent subclass)
vidbyte/agents/base.py          handoff= param, handoff() method, auto-run hook
vidbyte/prompts/prompts/handoff/handoff.json   prompt catalog descriptor
vidbyte/prompts/prompts/handoff/handoff.md     comprehensive handoff system prompt
```

Public imports:

```python
from vidbyte import HandoffAgent, Handoff, EngineeringHandoff, ResearchHandoff, MinimalHandoff
# also from vidbyte.context import Handoff, EngineeringHandoff, ResearchHandoff, MinimalHandoff
# also from vidbyte.agents import HandoffAgent
```

## Rules for adding a new prebuilt handoff

- Subclass `Handoff`, set `DEFAULT_TITLE`, and override `default_sections()` with a
  `{title: description}` map. Put each new prebuilt handoff class in its own module under
  `vidbyte/context/handoff/`.
- Export it from `vidbyte/context/handoff/__init__.py`, `vidbyte/context/handoffs.py`,
  `vidbyte/context/__init__.py`, and `vidbyte/__init__.py`.
- Make every default section description at least four clear sentences because those
  descriptions become both model-facing prompt guidance and JSON-schema field descriptions.
- Keep sections decision-oriented: each section title should map to something the next
  agent must know to continue.
- Add a unit test asserting the new variant exposes a non-empty, distinct section map and
  that `fill()` preserves its type.

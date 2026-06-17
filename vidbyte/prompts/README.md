# Prompts

The Vidbyte SDK ships repository-backed prompt assets for common agent,
handoff, eval, template, goal, and trajectory workflows. Prompt text is loaded
through a small catalog rather than scattered string constants.

## Role In The SDK

`vidbyte.prompts` exposes the `Prompts` catalog, `PromptRecord`, the `Prompt`
enum, and direct prompt imports generated from catalog keys. Agents and MCP
servers can use these assets as stable prompt building blocks.

## Design Philosophy

Prompt assets should be discoverable and validated at import time. The catalog
requires prompt JSON records to map to enum values, validates referenced Markdown
assets, and exposes metadata methods so developers can inspect available prompt
families instead of memorizing filenames.

## Usage

```python
from vidbyte.prompts import Prompts
from vidbyte.lib.enums.prompts import Prompt

prompts = Prompts()
system_prompt = prompts.get(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT)
descriptions = prompts.descriptions()
```

Direct imports are generated from prompt enum values:

```python
from vidbyte.prompts import handoff_system_prompt, templates_persona

handoff_prompt = handoff_system_prompt
persona_template = templates_persona
```

## Available Prompts

This catalog is the canonical, human- and machine-readable index of every prompt
family shipped by the SDK. It is the source of truth for the personal
`/vidbyte-prompts` skill: when you ask that skill to "download the vidbyte
&lt;name&gt; prompt", it reads this catalog, resolves the name to a prompt, and
saves that prompt's **direct `.md` file link** into your collection.

Every link below points at the individual prompt asset on GitHub. Markdown-backed
prompts link to their `.md` file directly. A few families store their text inline
inside a JSON record and therefore have **no `.md` file** — those link to the
`.json` record instead and are marked _(inline)_.

### Quick reference

| Prompt | Key | Prompt file(s) — direct links |
| --- | --- | --- |
| Actor Runtime | `actor_runtime` | [actor_runtime/](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime) — 15 role `.md` files (see Descriptions) |
| Agentic Loop | `agentic_loop` | [agentic_loop.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_loop.json) _(inline)_ |
| Context Engineering | `context_engineering` | [context_engineering.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/context_engineering.json) _(inline)_ |
| Continual Trace | `continual_trace` | [system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/continual_trace/system_prompt.md) |
| Evals | `evals` | [evals.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/evals.json) _(inline)_ |
| Expert Prompting | `expert_prompting` | [expert_prompting.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/expert_prompting.json) _(inline)_ |
| Goal Behavior | `goals` | [goal_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/goals/goal_prompt.md) |
| Handoff | `handoff` | [handoff.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/handoff/handoff.md) |
| Mimic Behavior | `mimic_behavior` | [mimic_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/mimic_behavior/mimic_prompt.md) |
| Multi-Provider Agentic Grader | `multi_provider_agentic_grader` | [agent_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_agentic_grader/agent_system_prompt.md), [grader_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_agentic_grader/grader_system_prompt.md), [grader_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_agentic_grader/grader_prompt.md) |
| Multi-Provider Aggregator | `multi_provider_aggregator` | [synthesis_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_system_prompt.md), [synthesis_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_prompt.md) |
| Prompt Engineering | `prompt_engineering` | [prompt_engineering.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/prompt_engineering.json) _(inline)_ |
| Reflexion | `reflexion` | [agent_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/reflexion/agent_system_prompt.md), [reflect_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/reflexion/reflect_system_prompt.md), [reflect_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/reflexion/reflect_prompt.md) |
| Prompt Templates | `templates` | [intent_based.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/intent_based.md), [persona.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/persona.md), [specification.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/specification.md) |
| Trajectory Checkpoints | `trajectory_checkpoints` | [trajectory_checkpoints_agentic_summarizer.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/trajectory_checkpoints_agentic_summarizer.md) |

### Descriptions

Each family lists its individual prompts with a direct link to the prompt file.
These per-prompt `.md` links are what the `/vidbyte-prompts` skill installs.

#### Actor Runtime — `actor_runtime`

System prompts for prebuilt actor roles in the Asynchronous Actor Model Runtime.

- `planner` — [planner.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/planner.md)
- `coder` — [coder.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/coder.md)
- `reviewer` — [reviewer.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/reviewer.md)
- `generator` — [generator.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/generator.md)
- `critic` — [critic.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/critic.md)
- `reasoner` — [reasoner.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/reasoner.md)
- `summarization` — [summarization.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/summarization.md)
- `decomposer` — [decomposer.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/decomposer.md)
- `explorer` — [explorer.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/explorer.md)
- `tradeoff` — [tradeoff.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/tradeoff.md)
- `hypothesis_generator` — [hypothesis_generator.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/hypothesis_generator.md)
- `refiner` — [refiner.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/refiner.md)
- `formatter` — [formatter.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/formatter.md)
- `safety` — [safety.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/safety.md)
- `final_answer` — [final_answer.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/final_answer.md)

#### Agentic Loop — `agentic_loop`

Short runtime context injected after system prompts so agents understand they are
executing inside a loop.

- `context_prompt` — [agentic_loop.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_loop.json) _(inline; text lives in the JSON record)_

#### Context Engineering — `context_engineering`

Context Engineering is a meta-prompt that provides reusable guidance for
constructing effective operational prompts for capable models. It is not a
reasoning strategy itself but a design methodology that SDK users can apply when
authoring their own custom prompts. The guidance instructs prompt authors to
structure their text as dense operational context, covering seven essential
dimensions: role, objective, constraints, available inputs, work procedure,
output contract, and quality bar. It emphasizes concrete policy statements over
vague encouragement — telling the model exactly what to do and what to avoid,
rather than asking it to try hard or be thorough. The prompt also advises authors
to declare any assumptions the model must preserve and to explain what to avoid
when it affects correctness or safety. This methodology ensures that custom
prompts integrated into the SDK maintain the same rigorous inspectable quality as
the built-in strategies.

- `guideline_prompt` — [context_engineering.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/context_engineering.json) _(inline; text lives in the JSON record)_

#### Continual Trace — `continual_trace`

System prompt for the continual trace agent that incrementally fills a typed
trace schema from a read-only snapshot of a running agent, calling updateTrace to
record new goal, action, mistake, and status information.

- `system_prompt` — [system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/continual_trace/system_prompt.md)

#### Evals — `evals`

Prompts used for evaluating and grading model outputs.

- `llm_judge` — [evals.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/evals.json) _(inline; text lives in the JSON record)_
- `rubric` — [evals.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/evals.json) _(inline; text lives in the JSON record)_

#### Expert Prompting — `expert_prompting`

Expert Prompting is a persona-based strategy that frames the model as a domain
expert in a specified domain to elicit higher-quality practitioner-level
responses. It is designed for tasks where domain depth matters — medical
analysis, legal interpretation, engineering design, financial modeling, and any
field with specialized vocabulary and edge cases that a generalist would miss.
The prompt instructs the model to use expert-level concepts, constraints, and
edge cases rather than generic explanations that could apply to any field. It
requires the model to state assumptions explicitly when domain details are
missing, making the reasoning auditable. Unlike generic role-prompting, Expert
Prompting sets a practitioner-level quality bar where the answer should be useful
to someone already working in the field, not a beginner's introduction. This
strategy is lightweight — requiring only a single model call — and pairs well
with any other reasoning strategy to add domain depth to the reasoning process.

- `expert_prompt` — [expert_prompting.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/expert_prompting.json) _(inline; text lives in the JSON record)_

#### Goal Behavior — `goals`

A system prompt for emulating Codex-style goal behavior in models that do not
have the native Codex /goal tool. It teaches persistent objective tracking,
evidence-based completion, iteration policy, blockers, and budget-aware stopping
without claiming that the model is running inside Codex.

- `goal_prompt` — [goal_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/goals/goal_prompt.md)

#### Handoff — `handoff`

System prompt for the handoff agent that turns a completed agent run into a
structured, reusable handoff document another agent or human can use to continue
the work cold.

- `system_prompt` — [handoff.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/handoff/handoff.md)

#### Mimic Behavior — `mimic_behavior`

A system prompt that turns uploaded source material such as a blog post, paper,
transcript, tweet thread, specification, or example output into an immensely
detailed behavior-mimicking prompt optimized to reproduce the source's observable
patterns without copying private or unnecessary source text.

- `mimic_prompt` — [mimic_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/mimic_behavior/mimic_prompt.md)

#### Multi-Provider Agentic Grader — `multi_provider_agentic_grader`

Prompt assets for the Multi-Provider Agentic Grader context-window algorithm.
This algorithm runs the same task concurrently across multiple model providers,
executes a full agentic loop for each, and then invokes a meta-grader agent to
evaluate all candidate outputs and select the single best response. These prompts
separate the agent execution context from the grading stage so SDK users can
inspect, override, or extend either stage independently when constructing
MultiProviderAgenticGraderAlgorithm.

- `agent_system_prompt` — [agent_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_agentic_grader/agent_system_prompt.md)
- `grader_system_prompt` — [grader_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_agentic_grader/grader_system_prompt.md)
- `grader_prompt` — [grader_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_agentic_grader/grader_prompt.md)

#### Multi-Provider Aggregator — `multi_provider_aggregator`

Prompt assets for the Multi-Provider Aggregator (Mixture-of-Agents). This pattern
runs the same request concurrently across multiple proposer models and then
routes every candidate answer to a single aggregator model that synthesizes a
new, superior response grounded in all of them. Unlike the Multi-Provider Agentic
Grader, the aggregator composes its own answer instead of selecting one candidate
verbatim. These prompts let SDK users inspect, override, or extend the
aggregator's system instruction and the synthesis message template independently
when constructing AggregateConfig.

- `synthesis_system_prompt` — [synthesis_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_system_prompt.md)
- `synthesis_prompt` — [synthesis_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_prompt.md)

#### Prompt Engineering — `prompt_engineering`

Prompt Engineering is a comprehensive master reference that defines the universal
principles of designing effective system prompts. It synthesizes patterns
observed across production AI harnesses (Claude Code, Grok Build, opencode,
Hermes, Cursor, Windsurf, Cline, Manus, Devin, and others), validated research
findings, and practitioner experience into a single canonical guide. The prompt
opens with a philosophy preamble establishing the foundational paradigms of the
discipline and then presents eighteen XML-tagged sections, each covering one
dimension of prompt design with a definition of what the section is, what it
accomplishes, why and when to use it, concrete use cases and intent, and a
description of the output it should produce. The guidance emphasizes that prompt
engineering is fundamentally about constructing a generative context that shifts
probability distributions — not about writing instructions to a person — and that
structure, section clarity, state externalization, attention-aware placement, and
explicit behavioral loops are the mechanisms that make long prompts work, not raw
token count. This prompt is a reference asset for SDK users designing their own
system prompts and for downstream agents that need to construct high-quality
prompts programmatically.

- `master_prompt` — [prompt_engineering.json](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/prompt_engineering.json) _(inline; text lives in the JSON record)_

#### Reflexion — `reflexion`

Prompt assets for the Reflexion context-window algorithm. Reflexion is a verbal
reinforcement loop where failed trials are diagnosed, converted into compact
reflection memory, and injected into later attempts. These prompts separate the
main agent retry context from the reflection stage so SDK users can inspect or
override either stage when constructing ReflexionAlgorithm.

- `agent_system_prompt` — [agent_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/reflexion/agent_system_prompt.md)
- `reflect_system_prompt` — [reflect_system_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/reflexion/reflect_system_prompt.md)
- `reflect_prompt` — [reflect_prompt.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/reflexion/reflect_prompt.md)

#### Prompt Templates — `templates`

Master prompts designed to generate highly optimized structural prompts for
specific engineering paradigms.

- `intent_based` — [intent_based.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/intent_based.md)
- `persona` — [persona.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/persona.md)
- `specification` — [specification.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/specification.md)

#### Trajectory Checkpoints — `trajectory_checkpoints`

Prompts used to generate agentic trajectory checkpoints.

- `agentic_summarizer` — [trajectory_checkpoints_agentic_summarizer.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/trajectory_checkpoints_agentic_summarizer.md)

## Key Modules

- `catalog.py`: prompt record loading, validation, family lookup, and direct import names.
- `prompts/`: JSON and Markdown prompt assets packaged with the SDK.
- `__init__.py`: dynamic direct prompt exports.

## Related Layers

Prompts are consumed by [`agents`](../agents/README.md),
[`mcp_server`](../mcp_server/README.md), [`evals`](../evals/README.md), and
[`trace`](../trace/README.md).

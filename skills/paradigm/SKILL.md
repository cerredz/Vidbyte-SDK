---
name: paradigm
description: >-
  Guides the design and placement of Vidbyte SDK paradigm harnesses: thin,
  runnable high-level harness patterns that compose agents, tools, context,
  middleware, prompts, trace, pipelines, and evals into opinionated agentic
  engineering workflows. Use when proposing, designing, scaffolding, or reviewing
  a new paradigm harness or adapter.
---

# Paradigm Harnesses

<identity>
You are a Vidbyte paradigm architect. Your job is to help turn repeatable
agentic and harness-engineering strategies into thin runnable SDK harnesses
without confusing those harnesses with the lower-level primitives they compose.
A paradigm is not a prompt trick, not a single tool, not a middleware flag, and
not a vague best practice. A paradigm is a named execution strategy with its own
control flow, user-facing configuration, trace shape, stopping criteria, and
measurement story. The SDK should make these strategies easy to run while keeping
their building blocks reusable outside the paradigm itself.
</identity>

<intent>
Paradigms exist because agentic engineering has no single best harness shape.
Some tasks benefit from minimal context windows. Some benefit from fresh-window
decomposition. Some benefit from worker-critic-repair loops. Some benefit from
large system-prompt influence templates. Some benefit from subagent launch and
merge strategies. The Vidbyte SDK should support this diversity by making
paradigms concrete, inspectable, and runnable rather than leaving them as loose
prompting advice.

The intent of a paradigm harness is to let a user configure a high-level
workflow and call `run()` or `arun()` without manually wiring every agent, critic,
trace artifact, context policy, prompt template, and stopping rule. The harness
should own the orchestration. The user should provide meaningful edges: tools,
system prompts, model/provider choices, limits, policies, and task input. A good
paradigm harness lets beginners run a sophisticated strategy out of the box and
lets advanced users swap the underlying pieces when they know what they are
doing.
</intent>

<structure>
The current paradigm scaffolding lives under these paths.

- `vidbyte/paradigms/` - Public SDK namespace for Vidbyte-owned thin paradigm
  harnesses. This package contains scaffold contracts now and will contain
  concrete paradigm harness subpackages later.
- `vidbyte/paradigms/base.py` - Defines `ParadigmHarness`, the abstract runnable
  contract for future paradigm implementations.
- `vidbyte/paradigms/client.py` - Defines `ParadigmClient`, the namespace client
  exposed through `VidbyteSDK().paradigms`.
- `vidbyte/paradigms/README.md` - Explains the role and non-goals of the
  paradigm package.
- `skills/paradigm/SKILL.md` - This guide. It explains what paradigms are in
  relation to the codebase and how future contributors should design them.

Paradigms compose these SDK layers.

- `vidbyte.agents` - Owns executable agent actors. A paradigm harness may create
  or accept worker, critic, planner, decomposer, reviewer, or merger agents.
- `vidbyte.context` - Owns structured context, context primitives, context-window
  algorithms, handoff models, and compaction contracts. A paradigm harness may
  use these to decide what each model call sees.
- `vidbyte.middleware` - Owns deterministic runtime policy around agent loops.
  A paradigm harness may attach middleware for budgets, retries, rate limits,
  trace replacement, or message-history compaction.
- `vidbyte.tools` - Owns model-callable capabilities. A paradigm harness may
  accept caller-provided tools or attach specific built-ins, but it should not
  hide tool permission policy.
- `vidbyte.prompts` - Owns static prompt assets. A paradigm harness may use
  prompt templates for worker, critic, planner, decomposition, merge, and audit
  stages.
- `vidbyte.trace` - Owns trace artifacts and observability helpers. A paradigm
  harness should define what trace state it carries across stages and what it
  returns to the caller.
- `vidbyte.evals` - Owns measurement. A mature paradigm must have eval cases or
  graders that test whether the strategy actually improves the target outcome.
- `vidbyte.pipelines` - Owns string-in/string-out stage composition. A paradigm
  may use pipelines internally, but pipelines do not own shared context, budgets,
  artifacts, or the full harness lifecycle.
- `vidbyte.harnesses` - Owns external harness integration adapters. Do not put
  Vidbyte-owned paradigm implementations here; use `vidbyte.paradigms` instead.
</structure>

<criteria>
Not every idea qualifies as a paradigm harness. Apply these criteria before
designing one.

- The idea must own a repeatable execution loop. If the idea is only "use this
  prompt" or "add this middleware," it is probably a prompt template or runtime
  policy, not a paradigm.
- The idea must have meaningful user-facing configuration. A user should be able
  to supply tools, system prompts, model choices, limits, context policy, or
  stage-specific instructions without rewriting the harness.
- The idea must compose multiple SDK primitives. A paradigm harness should
  typically involve more than one layer: agents plus prompts, context plus trace,
  tools plus middleware, evals plus result schemas, or similar combinations.
- The idea must have measurable outcomes. Examples include pass rate, bug-find
  rate, token cost, latency, number of repair rounds, context size reduction,
  critique precision, or task completion quality.
- The idea must have a stable conceptual name. If the name describes only an
  implementation detail, such as "call this helper twice," the concept is too
  small.
- The idea must justify an owned result shape or trace shape. A paradigm should
  return more than an opaque string when its internal stages matter to the user.
- The idea must be reusable across tasks. If it only solves one customer-specific
  workflow with private service logic, it belongs in an application or hosted API
  layer, not the reusable SDK.

Examples that qualify:
- Critique-repair loop: run a worker, run a critic against the original prompt
  and produced state, return fixes, repair, and repeat until no defects remain.
- Minimal-context debugging: implement, preserve only original instructions and
  current artifact, audit in a fresh window, repair, and repeat.
- Fresh-window decomposition: split a task into isolated subtasks, run each in a
  clean context, merge outputs, and audit the merged result.
- PRD-to-subagent implementation: convert a request into a detailed spec, launch
  a specialized implementation agent, and review against the spec.

Examples that do not qualify by themselves:
- A single context primitive.
- A single prompt template.
- A single model-callable tool.
- A middleware factory method.
- A pipeline topology with no paradigm-specific trace, stopping rules, or result
  contract.
- A hosted API route that hides proprietary service behavior and has no reusable
  SDK contract.
</criteria>

<placement>
Use these placement rules when deciding where code belongs.

- Put the runnable high-level strategy in `vidbyte/paradigms/<name>/` when the
  SDK owns the harness pattern and users should be able to run it locally.
- Put reusable context items, context-window algorithms, handoff models, and
  context policies in `vidbyte/context/`.
- Put deterministic lifecycle policy in `vidbyte/middleware/`.
- Put model-callable capabilities in `vidbyte/tools/`.
- Put static prompt assets in `vidbyte/prompts/prompts/<family>/`.
- Put local measurement, graders, templates, and comparison utilities in
  `vidbyte/evals/`.
- Put string-in/string-out topology composition in `vidbyte/pipelines/`.
- Put external host integration helpers in `vidbyte/harnesses/`.
- Put hosted API routes, persistence, dashboards, proprietary scoring, and
  private orchestration in the service/API repository, not in `vidbyte-sdk`.
- Put zero-setup operational guidance for Codex, Claude Code, Cursor, or other
  existing harnesses in skills. A skill is an adapter and instruction layer, not
  the canonical SDK implementation of the paradigm.

The canonical implementation order is: design the paradigm, identify primitive
gaps, add stable primitives, then add the thin harness that composes them. Do not
start by embedding all behavior directly in a paradigm package. If a piece of
behavior could help other paradigms, it probably belongs in a lower-level SDK
layer first.
</placement>

<procedure>
To add a future paradigm harness, execute these steps in order.

1. Write a design doc under `docs/design/<paradigm-name>.md`. The doc must define
   the paradigm's intent, workflow, non-goals, result shape, trace shape, stopping
   criteria, configuration surface, primitive dependencies, adapter surfaces, and
   eval strategy.

2. Name the paradigm with a stable snake_case key. Use the same key for the
   package, metadata, prompt family, docs, API route draft, and skill adapter
   when those surfaces exist. Examples: `critique_repair`,
   `context_minimal_debugging`, `fresh_window_decomposition`.

3. Identify primitive gaps before writing the harness. If the paradigm needs a
   new context primitive, middleware transform, trace schema, prompt template, or
   tool, design that primitive in its owning layer. The primitive must be useful
   outside the paradigm or it should remain private to the harness.

4. Define the harness package under `vidbyte/paradigms/<name>/`. The package
   should normally contain `harness.py`, `config.py`, `types.py`, `README.md`,
   and optional prompt or adapter helpers. Keep the package thin; orchestration
   belongs here, reusable mechanics belong in lower layers.

5. Expose one obvious constructor through `ParadigmClient` only after the harness
   is implemented. Do not add client methods that return placeholders for
   unimplemented paradigms.

6. Give the harness an agent-like execution surface. Concrete harnesses should
   subclass `ParadigmHarness` and implement `arun(prompt, **options)`. The sync
   `run()` bridge comes from the base class unless a concrete harness has a
   reviewed reason to override it.

7. Define the configuration surface conservatively. Accept user-provided agents,
   tools, system prompts, model/provider names, maximum rounds, context policy,
   and stopping criteria. Do not require users to manually construct internal
   prompt strings, trace merge logic, or repair-loop wiring.

8. Define the result type before implementing the loop. A paradigm result should
   expose final output plus useful stage metadata such as iterations, critiques,
   repairs, token usage, trace artifact, or stop reason. Avoid returning only a
   raw string when the paradigm's internal process is the point.

9. Add evals or an eval plan. A paradigm without measurement is just an
   attractive harness shape. Measure the property the paradigm claims to improve:
   correctness, bug discovery, token cost, latency, context window size, or
   reliability.

10. Add adapters only after the core harness is clear. Skills, hosted API routes,
    CLI wrappers, MCP tools, and external harness integrations should all wrap
    the same conceptual contract rather than inventing parallel behavior.
</procedure>

<conventions>
- Use `ParadigmHarness` for the abstract base and `<Name>Harness` for concrete
  classes, such as `CritiqueRepairHarness`.
- Use snake_case package names and metadata keys.
- Use explicit dataclasses or Pydantic models for non-trivial config and result
  types.
- Keep concrete harness methods small and named by orchestration step, such as
  `run_worker`, `run_critic`, `build_repair_prompt`, `should_stop`, and
  `build_result`.
- Keep prompt bodies in the prompt catalog when they are large, reusable, or
  user-facing.
- Keep hosted API vocabulary aligned with SDK vocabulary. If the SDK class is
  `CritiqueRepairHarness`, the hosted route should read like
  `/paradigms/critique-repair/run`, not an unrelated product name.
- Document which lower-level primitives a paradigm composes. A future maintainer
  should be able to see why each dependency exists.
- Keep the first implementation of a paradigm narrow. It is better to ship one
  clear harness with two well-defined knobs than a broad meta-harness with
  unclear behavior.
</conventions>

<rules>
- Never implement a concrete paradigm without an approved design doc.
- Never put private Vidbyte service logic, database access, hosted scoring, or
  proprietary orchestration into `vidbyte-sdk`.
- Never duplicate lower-level primitive behavior inside a paradigm harness when
  the behavior belongs in `context`, `middleware`, `tools`, `prompts`, `trace`,
  `evals`, or `pipelines`.
- Never treat a skill as the canonical implementation of a paradigm. Skills are
  adapters and operating instructions for external harnesses.
- Never add a `ParadigmClient` factory for a harness that does not exist.
- Never make users manually wire the internal loop of a paradigm harness. If the
  user must create the worker, critic, prompts, trace merge, and stop condition
  by hand, the paradigm abstraction has failed.
- Never call every idea a paradigm. A weak paradigm dilutes the namespace and
  makes the SDK harder to navigate.
- Always state what a paradigm does not own. Clear non-goals prevent future
  agents from stuffing unrelated helper behavior into the harness package.
- Always preserve raw auditability when a paradigm compacts, prunes, summarizes,
  or hides model-visible context. The user should be able to inspect what
  happened even when the next model call sees a reduced window.
</rules>

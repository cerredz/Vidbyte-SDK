---
name: paradigm
description: >-
  Explains what a paradigm is in the Vidbyte SDK: a thin, runnable high-level
  harness pattern that composes agents, tools, context, middleware, prompts,
  trace, pipelines, and evals into an opinionated agentic-engineering execution
  loop, and how paradigms differ from the primitives, pipelines, harnesses, and
  skills around them. Use when proposing, designing, scaffolding, or reviewing
  anything under vidbyte/paradigms/.
---

<!-- Context Protocol Header
Description:
    Explains what a paradigm is in the Vidbyte SDK: a thin, runnable high-level
    harness pattern that composes SDK primitives into an opinionated execution
    loop, and how paradigms differ from the primitives, pipelines, harnesses,
    and skills that surround them.
Purpose:
    Gives contributors and agents the context to recognize a paradigm, locate
    the paradigm scaffolding, read the ParadigmHarness / ParadigmClient contract,
    and decide whether a new idea qualifies as a paradigm harness before writing
    code.
Architecture:
    SDK Skill Guide (explanatory reference).
Relations:
    Located in skills/paradigm/SKILL.md. Describes vidbyte/paradigms/ and the
    layers it composes. Complements skills/sdk/SKILL.md (framework boundaries)
    and skills/context-minimal-fanout/SKILL.md (a concrete paradigm operating
    guide).
-->

# Paradigms

Use this guide to understand what a **paradigm** is in the Vidbyte SDK, where the
paradigm scaffolding lives, and how paradigms relate to the primitives,
pipelines, harnesses, and skills already in this repo. Read it before proposing,
designing, scaffolding, or reviewing anything under `vidbyte/paradigms/`.

---

## 1. What A Paradigm Is In This Repo

A **paradigm** is a named agentic-engineering *strategy* - a repeatable way to
shape an agent run so it produces better results than a single naive model call.
A **paradigm harness** is the runnable SDK implementation of that strategy: a
thin object that owns the strategy's control flow and composes lower-level SDK
primitives (agents, tools, context, middleware, prompts, trace, evals, and
pipelines) into one opinionated execution loop.

The point is separation of concerns. Agentic engineering has no single best
harness shape. Some tasks want a worker/critic/repair loop. Some want a task
split into fresh, isolated context windows. Some want a PRD expanded into a spec
before a specialist agent implements it. Each of those is a *strategy*; each
deserves a runnable *harness* the caller can configure and `run()` like an agent,
without hand-wiring the worker, the critic, the prompts, the trace handoff, the
stopping rule, and the retry loop every time.

A paradigm in this repo is therefore **not**:

- a single prompt or prompt trick,
- a single tool,
- a single middleware policy or flag,
- a single context primitive,
- a pipeline topology with no strategy-specific control flow, or
- a vague best practice.

It **is** a named execution strategy with its own control flow, user-facing
configuration, trace shape, stopping criteria, and measurement story - packaged
as a thin harness over stable primitives.

The canonical short definition, from `vidbyte/paradigms/README.md`:

> `vidbyte.paradigms` is the namespace for thin runnable paradigm harnesses:
> high-level agentic engineering patterns that compose SDK primitives into an
> opinionated execution loop.

---

## 2. Where Paradigms Live

The paradigm scaffolding is a first-class SDK layer under `vidbyte/paradigms/`.
As of this scaffolding, the package provides the contract and the namespace only
- **no concrete paradigm harnesses ship from it yet**.

```text
vidbyte/paradigms/
|-- __init__.py    Public exports: ParadigmHarness, ParadigmClient
|-- base.py        ParadigmHarness - abstract runnable contract
|-- client.py      ParadigmClient - namespace client (currently a marker)
`-- README.md      Package role, design philosophy, non-goals
```

It is reachable two ways:

```python
from vidbyte.paradigms import ParadigmClient, ParadigmHarness
from vidbyte import ParadigmClient, ParadigmHarness   # root re-export
```

and it is exposed as a namespace on the root SDK client, alongside `agents`,
`tools`, `providers`, and `harnesses`:

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.paradigms          # ParadigmClient()
```

Future concrete paradigms live in subpackages of this namespace, one per
strategy, e.g. `vidbyte/paradigms/critique_repair/`,
`vidbyte/paradigms/context_minimal/`, `vidbyte/paradigms/fresh_window/`.

---

## 3. The Contract: `ParadigmHarness`

`vidbyte/paradigms/base.py` defines the abstract runnable contract every concrete
paradigm harness implements. It is deliberately minimal so future paradigms are
not forced into a premature result schema.

```python
class ParadigmHarness(ABC):
    """Abstract base for thin runnable paradigm harnesses."""

    @abstractmethod
    async def arun(self, prompt: str, **options: Any) -> Any:
        # Concrete paradigms implement their orchestration loop here.
        raise NotImplementedError

    def run(self, prompt: str, **options: Any) -> Any:
        # Sync bridge: asyncio.run(arun) when no loop is running,
        # else raise PipelineExecutionError telling the caller to await arun().
        ...
```

Two things to know:

- **`arun` is the strategy.** A concrete harness subclasses `ParadigmHarness` and
  implements `arun`, giving the paradigm an agent-like execution surface. The
  return type is `Any` today because no concrete paradigm output schema has been
  designed; a real paradigm should return final output *plus* useful stage
  metadata (iterations, critiques, repairs, token usage, trace artifact, stop
  reason), not an opaque string.
- **`run` is a sync bridge, not new behavior.** It mirrors the existing pattern
  in `vidbyte/pipelines/base.py`: if called with no running event loop it uses
  `asyncio.run`; if called from inside an active loop it fails fast with
  `PipelineExecutionError` (reused rather than inventing a new error type)
  instructing the caller to `await arun()`. Concrete harnesses inherit this and
  should not override it without a reviewed reason.

`vidbyte/paradigms/client.py` defines `ParadigmClient`, currently an empty
namespace marker. It reserves the public surface for future paradigm factory
methods but intentionally exposes none, so its presence never implies a paradigm
exists. Factories get added to it only *after* the harness they construct is
implemented.

---

## 4. How Paradigms Relate To The Other Layers

A paradigm harness is a *composer*. It owns orchestration and delegates the
mechanics to the layer that already owns them. This table maps each layer to the
role it plays inside a paradigm.

| Layer | What it owns | Role inside a paradigm harness |
|-------|--------------|--------------------------------|
| `vidbyte.agents` | Executable agent actors | Worker, critic, planner, decomposer, reviewer, or merger agents the harness creates or accepts |
| `vidbyte.context` | Structured context, context-window algorithms, handoff models, compaction | Decides what each model call in the strategy sees |
| `vidbyte.middleware` | Deterministic runtime policy around the agent loop | Budgets, retries, rate limits, loop detection, compaction attached to the harness's agents |
| `vidbyte.tools` | Model-callable capabilities | Caller-provided tools or specific built-ins the harness attaches (without hiding permission policy) |
| `vidbyte.prompts` | Static prompt assets | Worker / critic / planner / decompose / merge / audit prompt templates |
| `vidbyte.trace` | Trace artifacts and observability | The trace state the strategy carries across stages and returns to the caller |
| `vidbyte.evals` | Measurement (graders, suites, runner) | The eval cases that prove the strategy actually improves the target outcome |
| `vidbyte.pipelines` | String-in/string-out stage composition | Used *internally* when a stage is a simple wiring step; pipelines do not own shared context, budgets, artifacts, or the harness lifecycle |
| `vidbyte.harnesses` | External harness integration adapters | A *sibling* boundary, not a home for paradigms - see below |

Two boundaries are easy to blur, so state them plainly:

- **Paradigms vs. pipelines.** Pipelines move strings between fully-configured
  agents; they hold no shared context, budget, artifacts, or stopping logic. A
  paradigm *may use* a pipeline for a stage, but the paradigm is the thing that
  owns the loop, the shared state, and the stop condition.
- **Paradigms vs. harnesses.** `vidbyte.harnesses` is the boundary for *adapting*
  SDK abstractions into external execution harnesses (Codex, Claude Code, Cursor,
  and similar). `vidbyte.paradigms` is for *Vidbyte-owned* runnable strategy
  patterns. Do not put paradigm implementations under `vidbyte.harnesses`, and do
  not put external-host adapters under `vidbyte.paradigms`.

Skills (like this file) are yet another layer: a **skill is an adapter and
operating-instruction layer**, not the canonical implementation of a paradigm.
`skills/context-minimal-fanout/SKILL.md` is a good example - it is operating
guidance for running the context-minimal fanout strategy inside an external
harness *today*, while the runnable SDK version of such strategies is what
`vidbyte/paradigms/` will eventually hold.

---

## 5. What Qualifies As A Paradigm

Use these tests before calling something a paradigm. An idea qualifies when it
meets essentially all of them:

- **Owns a repeatable execution loop.** If the idea is only "use this prompt" or
  "add this middleware," it is a prompt template or a runtime policy - not a
  paradigm.
- **Has meaningful user-facing configuration.** A caller should be able to supply
  tools, system prompts, model/provider choices, limits, context policy, or
  stage-specific instructions without rewriting the harness.
- **Composes multiple primitives.** It typically spans more than one layer:
  agents plus prompts, context plus trace, tools plus middleware, evals plus
  result schema.
- **Has measurable outcomes.** Pass rate, bug-find rate, token cost, latency,
  repair rounds, context-size reduction, critique precision, task quality.
- **Has a stable conceptual name.** If the best name describes an implementation
  detail ("call this helper twice"), the concept is too small.
- **Justifies an owned result or trace shape.** It should return more than an
  opaque string when its internal stages matter to the caller.
- **Is reusable across tasks.** If it only solves one customer-specific workflow
  with private service logic, it belongs in an application or hosted API layer,
  not the reusable SDK.

**Qualifying examples:**

- **Critique-repair loop** - run a worker, run a critic against the original
  prompt and produced state, return fixes, repair, repeat until no defects
  remain.
- **Minimal-context debugging** - implement, preserve only original instructions
  and the current artifact, audit in a fresh window, repair, repeat.
- **Fresh-window decomposition** - split a task into isolated subtasks, run each
  in a clean context, merge outputs, audit the merged result.
- **PRD-to-subagent implementation** - convert a request into a detailed spec,
  launch a specialized implementation agent, review against the spec.

**Not paradigms by themselves:** a single context primitive; a single prompt
template; a single model-callable tool; a middleware factory method; a pipeline
topology with no paradigm-specific trace, stopping rule, or result contract; a
hosted API route that hides proprietary service behavior and exposes no reusable
SDK contract.

---

## 6. Placement Rules

When you have an idea, decide where it belongs *before* writing it. Most ideas
are primitives, not paradigms.

| Put this... | ...here |
|-------------|---------|
| The runnable high-level strategy the SDK owns | `vidbyte/paradigms/<name>/` |
| Reusable context items, context-window algorithms, handoff models, policies | `vidbyte/context/` |
| Deterministic lifecycle policy | `vidbyte/middleware/` |
| Model-callable capabilities | `vidbyte/tools/` |
| Static prompt assets | `vidbyte/prompts/prompts/<family>/` |
| Local measurement, graders, templates, comparison utilities | `vidbyte/evals/` |
| String-in/string-out topology composition | `vidbyte/pipelines/` |
| External host integration helpers | `vidbyte/harnesses/` |
| Zero-setup operating guidance for Codex, Claude Code, Cursor, etc. | a skill under `skills/` |
| Hosted API routes, persistence, dashboards, proprietary scoring, private orchestration | the service/API repository, **not** `vidbyte-sdk` |

The canonical build order is: **design the paradigm, identify primitive gaps, add
the stable primitives in their owning layer, then add the thin harness that
composes them.** Do not start by embedding all behavior inside a paradigm
package. If a piece of behavior could help other paradigms, it belongs in a
lower-level layer first.

---

## 7. Adding A Future Paradigm

Concrete paradigms are added in future, design-reviewed PRs - not casually. The
sequence:

1. **Write a design doc** under `docs/design/<paradigm-name>.md` covering intent,
   workflow, non-goals, result shape, trace shape, stopping criteria,
   configuration surface, primitive dependencies, adapter surfaces, and eval
   strategy.
2. **Pick a stable snake_case key** and reuse it everywhere the paradigm surfaces
   (package, metadata, prompt family, docs, API route draft, skill adapter),
   e.g. `critique_repair`, `context_minimal_debugging`,
   `fresh_window_decomposition`.
3. **Close primitive gaps first.** If the paradigm needs a new context primitive,
   middleware transform, trace schema, prompt template, or tool, add it to its
   owning layer. Keep it private to the harness only if it is genuinely
   single-use.
4. **Define the harness package** at `vidbyte/paradigms/<name>/`, normally
   `harness.py`, `config.py`, `types.py`, `README.md`, plus optional prompt or
   adapter helpers. Keep it thin - orchestration here, reusable mechanics in
   lower layers.
5. **Give it an agent-like surface.** Subclass `ParadigmHarness` and implement
   `arun(prompt, **options)`; inherit the sync `run()` bridge.
6. **Define config conservatively.** Accept caller-provided agents, tools, system
   prompts, model/provider names, max rounds, context policy, and stopping
   criteria. Do not make callers hand-build internal prompt strings, trace merge
   logic, or repair-loop wiring.
7. **Define the result type before the loop.** Expose final output plus stage
   metadata (iterations, critiques, repairs, token usage, trace artifact, stop
   reason).
8. **Add evals or an eval plan.** Measure the property the paradigm claims to
   improve. A paradigm without measurement is just an attractive harness shape.
9. **Expose a `ParadigmClient` factory only after the harness exists.** Never add
   a client method that returns a placeholder for an unimplemented paradigm.
10. **Add adapters last.** Skills, hosted API routes, CLI wrappers, MCP tools, and
    external-harness integrations should all wrap the *same* conceptual contract
    rather than inventing parallel behavior.

---

## 8. Conventions

- Name the abstract base `ParadigmHarness` and concrete classes `<Name>Harness`
  (e.g. `CritiqueRepairHarness`).
- Use snake_case package names and metadata keys.
- Use explicit dataclasses or Pydantic models for non-trivial config and result
  types.
- Keep concrete harness methods small and named by orchestration step, e.g.
  `run_worker`, `run_critic`, `build_repair_prompt`, `should_stop`,
  `build_result`.
- Keep large, reusable, or user-facing prompt bodies in the prompt catalog, not
  inline in the harness.
- Keep hosted-API vocabulary aligned with SDK vocabulary. If the SDK class is
  `CritiqueRepairHarness`, the route reads like `/paradigms/critique-repair/run`,
  not an unrelated product name.
- Document which lower-level primitives a paradigm composes and why each
  dependency exists.
- Ship the first version of a paradigm narrow. One clear harness with two
  well-defined knobs beats a broad meta-harness with unclear behavior.

---

## 9. Rules

- Never implement a concrete paradigm without an approved design doc.
- Never put private Vidbyte service logic, database access, hosted scoring, or
  proprietary orchestration into `vidbyte-sdk`.
- Never duplicate lower-level primitive behavior inside a paradigm harness when
  it belongs in `context`, `middleware`, `tools`, `prompts`, `trace`, `evals`,
  or `pipelines`.
- Never treat a skill as the canonical implementation of a paradigm. Skills are
  adapters and operating instructions for external harnesses.
- Never add a `ParadigmClient` factory for a harness that does not exist.
- Never make callers hand-wire the internal loop of a paradigm harness. If the
  user must assemble the worker, critic, prompts, trace merge, and stop condition
  themselves, the abstraction has failed.
- Never call every idea a paradigm. A weak paradigm dilutes the namespace and
  makes the SDK harder to navigate.
- Always state what a paradigm does *not* own. Clear non-goals stop future agents
  from stuffing unrelated helpers into the harness package.
- Always preserve raw auditability when a paradigm compacts, prunes, summarizes,
  or hides model-visible context. A caller must be able to inspect what happened
  even when the next model call sees a reduced window.

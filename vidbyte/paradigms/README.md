# Paradigms

`vidbyte.paradigms` is the namespace for thin runnable paradigm harnesses:
high-level agentic engineering patterns that compose SDK primitives into an
opinionated execution loop.

## Role In The SDK

Paradigm harnesses sit above agents, tools, context, middleware, prompts, trace,
pipelines, and evals. They are not raw primitives. A paradigm harness owns a
repeatable control flow such as "worker, critic, repair, repeat" or "decompose
into fresh context windows, run isolated subtasks, merge, and audit."

This package provides `ParadigmHarness`, `ParadigmClient`, and concrete
paradigm harness families such as `context_minimal_fanout`.

## Design Philosophy

Paradigms should be thin harnesses over stable SDK primitives. The harness owns
the orchestration shape, stopping criteria, trace handoff, and user-facing
configuration. Lower-level behavior should still live in the appropriate SDK
layer: context policies in `vidbyte.context`, runtime hooks in
`vidbyte.middleware`, model-callable capabilities in `vidbyte.tools`, prompt text
in `vidbyte.prompts`, and measurement in `vidbyte.evals`.

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
paradigms = sdk.paradigms
harness = paradigms.context_minimal_fanout.multiple_prompts()
print(type(harness).__name__)
```

Concrete paradigm harnesses expose an agent-like `run()` / `arun()` surface
while accepting caller-provided tools, system prompts, models, limits, and
policies.

## Key Modules

- `base.py`: `ParadigmHarness`, the abstract runnable contract for future thin
  harnesses.
- `client.py`: `ParadigmClient`, currently a namespace marker for future
  paradigm factories.
- `context_minimal_fanout/`: the first concrete paradigm family, used to split a
  large request into multiple non-overlapping implementation prompts and run
  them in fresh contexts.
- `__init__.py`: public exports for the paradigm namespace.

## Related Layers

Paradigm harnesses will usually compose [`agents`](../agents/README.md),
[`context`](../context/README.md), [`middleware`](../middleware/README.md),
[`tools`](../tools/README.md), [`prompts`](../prompts/README.md),
[`trace`](../trace/README.md), [`pipelines`](../pipelines/README.md), and
[`evals`](../evals/README.md).

## Non-Goals

- Do not put primitive-only behavior here. If a feature is just a context item,
  middleware hook, tool, prompt, grader, or pipeline topology, it belongs in that
  lower-level package.
- Do not use this package for external harness integration adapters. Those
  belong in `vidbyte.harnesses`.
- Do not add hosted Vidbyte API routes, persistence, dashboards, proprietary
  scoring, or private service logic to this package.
- Do not implement a concrete paradigm without an approved design doc that
  identifies primitive gaps, result shape, stopping criteria, trace behavior,
  eval strategy, and adapter surfaces.

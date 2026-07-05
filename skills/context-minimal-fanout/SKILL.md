---
name: context-minimal-fanout
description: >-
  Explains the context-minimal fanout paradigm in the Vidbyte SDK: a four-stage
  harness (context extraction, split planning, adversarial de-overlap, parallel
  implementation) that turns one large request into non-overlapping, context-rich
  prompts run in fresh, smaller agent contexts. Use when deciding whether and how
  to apply ContextMinimalFanoutParadigm.
---

# Context Minimal Fanout

## 1. What This Paradigm Is

Context minimal fanout is a concrete Vidbyte paradigm implemented as
`vidbyte.paradigms.ContextMinimalFanoutParadigm`. It exists to keep each
implementation agent's context window small. Instead of one agent that reads the
whole repository and holds the whole task, the paradigm decomposes the work so
that exploration is done once and compressed, and each unit of implementation
runs in its own fresh, minimal context.

It is not a prompt trick and not a single tool. It is a named execution strategy
with its own control flow, configuration surface, and structured result. The
public entry point is a direct class instantiation:

```python
from vidbyte import ContextMinimalFanoutParadigm

harness = ContextMinimalFanoutParadigm(default_tool_root=".", implementation_tools=[patch_tool])
result = harness.run("Implement the requested repo change.")
```

## 2. When To Reach For It

Use it when a request is broad enough that a single agent would fill too much of
its context window with unrelated files, history, and reasoning, and when the
work can be divided into areas with distinct ownership (separate files, contracts,
tests, docs, configs, or verification surfaces). It is a poor fit for small,
tightly-coupled changes where a single agent is simpler, or for work that cannot
be divided into independent ownership areas.

## 3. The Four Stages

1. **Context agent.** Explores the environment with the read-only minimal
   filesystem toolset, then returns a compressed `EnvironmentContext` (a summary,
   the relevant files, and notes) using the runtime output-schema tools. Its own
   window fills with tool calls and reasoning, but only the appended structured
   entries are returned — the transcript is discarded.
2. **Splitter agent.** Consumes the original request plus the `EnvironmentContext`
   and emits a `PromptSplitPlan`: a goal, global instructions, non-overlap
   requirements, and a list of rich, self-contained `SplitPrompt` objects.
3. **Adversarial agent (looped).** Consumes the original request, the current
   prompts, and the environment context, and rewrites the prompts to remove
   ownership overlap. It runs for up to `max_adversarial_rounds`, fed the detected
   conflicts each round, and always runs *before* the deterministic gate.
4. **Implementation agents (parallel).** Each receives its rich `SplitPrompt`, the
   shared environment context, and its own tools, and runs concurrently under
   `max_concurrency` in a fresh context.

After the adversarial loop, `PromptSplitPlan.validate` runs as a hard,
fail-closed gate: if declared ownership still overlaps, the run raises rather than
launching conflicting implementation agents.

## 4. What Each Stage Consumes And Produces

- Context agent: `prompt` → `EnvironmentContext`.
- Splitter agent: `prompt + EnvironmentContext` → `PromptSplitPlan`.
- Adversarial agent: `prompt + PromptSplitPlan + EnvironmentContext + detected overlaps`
  → updated `PromptSplitPlan`.
- Implementation agents: `SplitPrompt + EnvironmentContext + global goal/instructions`
  → `ImplementationOutput` per branch.
- Harness: everything above → `ContextMinimalFanoutResult`
  (`plan`, `plan_markdown`, `environment`, `outputs`, `metadata`).

## 5. Non-Overlap Model

Non-overlap is enforced on **declared ownership**, not on semantics. Each
`SplitPrompt` declares `owned_paths` (its mutation/contract boundary) and
`read_only_paths` (shared context it must not change). The adversarial agent
reduces overlap using judgment; the deterministic check then guarantees no two
prompts own the same normalized path and no ids repeat. Perfect semantic
non-overlap is not guaranteed — the guarantee is on the declared metadata.

## 6. Configuration Shape

`ContextMinimalFanoutSettings` exposes independent per-role configuration
(`context_*`, `splitter_*`, `adversarial_*`, `implementation_*`) for model,
provider, temperature, tools, middleware, and token budgets, so a strong model
can plan while cheaper models implement in parallel. Shared controls cover the
minimal toolset (`include_minimal_toolset`, `default_tool_root`,
`implementation_include_write`), fanout shape (`max_prompt_count`,
`max_concurrency`, `max_adversarial_rounds`), optional cost budgeting, and
`plan_output_path` for writing the Markdown plan.

## 7. Boundaries

The harness owns orchestration, not repository mutation policy. Implementation
agents can only edit the repository if the caller supplies write tools (or leaves
`implementation_include_write` enabled, which adds the minimal write tool rooted
at `default_tool_root`). The harness never commits, opens PRs, or mutates state on
its own.

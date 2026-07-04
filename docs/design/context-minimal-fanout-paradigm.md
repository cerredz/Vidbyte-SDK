# Design Doc: Context Minimal Fanout Paradigm (v2 — Four-Stage Pipeline)

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-04
**Last Updated:** 2026-07-04

---

## 1. Overview

This change ships the first real Vidbyte paradigm harness, `context_minimal_fanout`,
as a single top-level class `ContextMinimalFanoutParadigm`. The paradigm turns one
large implementation request into several non-overlapping, context-rich implementation
prompts and runs those prompts in parallel in fresh agent contexts. It is a full
redesign of the abandoned PR #199 shape: instead of a single splitter agent that both
reads the repo and splits, the paradigm decomposes the work into a **four-stage agent
pipeline** — a context-extraction agent, a splitter agent, an adversarial de-overlap
agent, and parallel implementation agents. To support the "read a lot, return only a
compressed structured result" behavior, this PR also adds a new reusable SDK tool
primitive (runtime output-schema declaration + append) and a reusable filesystem
toolset (`ParadigmMinimalToolset`) shared by all thin harnesses.

---

## 2. Goals & Non-Goals

### Goals

- Ship `context_minimal_fanout` as a top-level, directly-instantiable paradigm class:
  `harness = ContextMinimalFanoutParadigm(...)` then `harness.run()` / `await harness.arun()`.
- Replace the single-splitter algorithm with a four-stage pipeline:
  1. **Context agent** — explores the environment and emits a compressed structured
     context artifact.
  2. **Splitter agent** — consumes the original prompt + context artifact and emits a
     structured list of implementation prompts.
  3. **Adversarial splitter agent (looped)** — consumes the original request, the
     splitter prompts, and the context artifact, and rewrites the prompts until they
     do not overlap. Runs *before* the deterministic overlap gate.
  4. **Implementation agents (parallel)** — each receives its context-rich structured
     prompt, the environment context, and its own tools.
- Add a new reusable SDK tool primitive that lets an agent **declare an output schema at
  runtime and append entries to it during the run**, backed by a harness-owned
  accumulator. This realizes context compression: the agent fills its own window with
  tool calls and reasoning, but only the appended structured entries are returned.
- Add a reusable `ParadigmMinimalToolset` under `vidbyte/tools/toolsets/` — a
  "minimal universal toolset" for filesystem-resident harnesses — and consume it from
  the paradigm instead of hand-building tool tuples. Preserve the existing behavior
  where caller-provided tools are appended on top.
- Keep the deterministic non-overlap validation (`PromptSplitPlan.validate`) as a hard
  fail-closed gate that runs after the adversarial agent.
- Rewrite `skills/context-minimal-fanout/SKILL.md` as an explanatory paradigm document
  (mirroring `skills/paradigm/SKILL.md`), not an operational instruction sheet.
- Update `README.md` to show the correct `ContextMinimalFanoutParadigm(...).run()` usage.

### Non-Goals

- No hosted API routes, dashboards, persistence, or remote execution.
- No MCP server exposure of paradigms in this PR.
- No tests or verification scripts (per the no-tests workflow).
- No changes to existing agent runtime, pipeline, or middleware behavior beyond
  additive exports.
- No automatic git commits, PR creation, or repository mutation policy inside the
  harness. Mutation capability is governed entirely by the tools the caller supplies.
- No guarantee of perfect semantic non-overlap. The adversarial agent reduces overlap;
  the deterministic gate enforces declared-ownership non-overlap.

---

## 3. Background & Context

PR #195 (`feat: Paradigm Harness Scaffolding`) is now merged into `main`. It provides
`vidbyte.paradigms`, the abstract `ParadigmHarness` (async `arun` + sync `run` bridge),
`ParadigmClient`, and a maintainer skill describing what a paradigm is. `main` does not
yet contain any concrete paradigm.

PR #199 attempted the first concrete paradigm but was left unmerged and received review
feedback that reshapes it substantially:

- The run interface should be a direct top-level class, not the
  `sdk.paradigms.context_minimal_fanout.multiple_prompts(...)` client chain.
- The skill file was the wrong type (operational instructions rather than an
  explanatory paradigm document).
- The default tool tuple should be extracted into a reusable `ParadigmMinimalToolset`
  under a new `vidbyte/tools/toolsets/` folder, built for harnesses that live on a
  filesystem, with more tools considered.
- The algorithm should be decomposed into a four-stage pipeline (context → split →
  adversarial de-overlap → implement), with each implementation prompt being a rich
  structured object, and with a runtime output-schema tool used for context compression.

Reviewer answers that pin down open questions:

- **(a)** The desired mechanism is a tool to declare an output schema at runtime plus a
  tool to append to it during the run. This tool does not currently exist in the SDK
  (confirmed by audit); it must be built.
- **(b)** The adversarial agent is a looped agent that runs *before* the deterministic
  overlap check (the deterministic check remains as a final gate).
- **(c)** Implement the run-interface exactly as the PR comment stated
  (`ContextMinimalFanoutParadigm(params)` → `harness.run()`), and implement the
  remaining comments as judged appropriate.

Relevant existing primitives confirmed during audit:

- `BaseAgent` accepts `name`, `system_prompt`, `tools`, `middleware`, `provider`,
  `model_name`, `temperature`, `api_key`, `output_schema`, `metadata`, and more.
- `vidbyte.tools.Tools` is a `Sequence[BaseTool]` catalog exposing `.all()`; the
  paradigm settings' tuple-normalizer already accepts any object with `.all()`.
- Context-window primitive tools (`ContextUpsertTool`, `ContextListTool`,
  `ContextRemoveTool`) show the established pattern: a builtin tool holds a reference to
  a live manager object and mutates it during the run. The new output-schema tools
  follow this pattern with a harness-owned accumulator.
- Filesystem/search tools: `GlobTool`, `GrepTool`, `ReadTextTool`, `ReadLinesTool`,
  `ListDirTool`, plus `CodeExecutionTool` and `PatchTool` (write).

---

## 4. Requirements

### Functional Requirements

1. `ContextMinimalFanoutParadigm` MUST be importable from the top level:
   `from vidbyte import ContextMinimalFanoutParadigm`.
2. It MUST accept configuration via constructor kwargs or a settings object, and expose
   `run(prompt, **options)` (sync) and `arun(prompt, **options)` (async) inherited from
   `ParadigmHarness`.
3. `arun` MUST execute the four stages in order: context agent → splitter agent →
   adversarial loop → implementation fanout, returning a structured result.
4. The **context agent** MUST run with the minimal filesystem toolset plus the runtime
   output-schema tools, and MUST return a compressed structured `EnvironmentContext`
   (files, notes, and free-form entries it appended), not its full transcript.
5. The **splitter agent** MUST receive the original prompt and the `EnvironmentContext`
   and MUST produce a structured `PromptSplitPlan` (goal, global instructions,
   non-overlap requirements, and a list of rich `SplitPrompt` objects) via the runtime
   output-schema tools.
6. The **adversarial agent** MUST receive the original request, the splitter's prompts,
   and the `EnvironmentContext`, and MUST return an updated `PromptSplitPlan`. It MUST
   run in a loop of up to `max_adversarial_rounds`, re-running with detected overlap
   feedback until the deterministic overlap check passes or rounds are exhausted.
7. After the adversarial loop, `PromptSplitPlan.validate(max_prompt_count=...)` MUST run
   as a hard gate; if it still fails, `arun` MUST raise `ConfigurationError`.
8. Each **implementation agent** MUST receive its rich structured `SplitPrompt`, the
   `EnvironmentContext`, and its own tools (caller `implementation_tools` plus, if
   enabled, the minimal toolset with write access). Implementation agents MUST run
   concurrently under `max_concurrency`.
9. A branch failure MUST be captured into an `ImplementationOutput` with an `error`
   field when `return_exceptions` is true (default), and MUST propagate otherwise.
10. The paradigm MUST optionally render the plan as Markdown and write it to
    `plan_output_path` when provided.
11. The new output-schema tool primitive MUST provide two model-facing tools —
    `declare_output_schema` and `append_output` — backed by an `OutputSchemaBuilder`
    accumulator whose snapshot the harness reads after each agent run.
12. `ParadigmMinimalToolset` MUST expose a `Tools` catalog rooted at a filesystem path,
    with a read-only variant (context/splitter/adversarial agents) and a
    write-enabled variant (implementation agents).
13. All new builtin tools MUST be re-exported from `vidbyte.tools.builtins`, and
    `ContextMinimalFanoutParadigm` MUST be re-exported from `vidbyte.paradigms` and the
    top-level `vidbyte` package.

### Non-Functional Requirements

- **Concurrency:** implementation agents run under an `asyncio.Semaphore`. Each agent
  run owns its own `OutputSchemaBuilder` instance — no shared mutable accumulator across
  concurrent branches.
- **Immutability:** all result/plan/settings dataclasses are `frozen=True, slots=True`,
  normalizing input in `__post_init__` via `object.__setattr__` (matching the house
  style established in PR #199's `types.py`).
- **Reuse:** the paradigm composes existing primitives; the only genuinely new SDK
  surface is the output-schema tool primitive and the toolset package.
- **Observability:** each agent is named per role/branch and tagged with `metadata`
  (`role`, `split_prompt_id`) so traces are attributable.
- **Fail-closed:** deterministic overlap validation is authoritative; the LLM
  adversarial pass never bypasses it.

---

## 5. High-Level Design

```
                          ┌───────────────────────────────────────────────┐
 user prompt ───────────▶ │ ContextMinimalFanoutParadigm.arun(prompt)      │
                          └───────────────────────────────────────────────┘
                                            │
             ┌──────────────────────────────┼───────────────────────────────┐
             ▼                                                                │
  ┌─────────────────────┐   fills its window with reads/greps/reasoning,     │
  │ 1. Context Agent     │   appends only relevant items to output schema     │
  │ (minimal RO toolset  │──────────────▶ EnvironmentContext (compressed)     │
  │  + output-schema     │                (files, notes, entries)             │
  │  tools)              │                                                     │
  └─────────────────────┘                                                     │
             │  original prompt + EnvironmentContext                          │
             ▼                                                                │
  ┌─────────────────────┐                                                     │
  │ 2. Splitter Agent    │──────────────▶ PromptSplitPlan (rich SplitPrompts) │
  │ (output-schema tools)│                                                     │
  └─────────────────────┘                                                     │
             │  original request + prompts + EnvironmentContext               │
             ▼                                                                │
  ┌─────────────────────┐   loop ≤ max_adversarial_rounds until overlap-free  │
  │ 3. Adversarial Agent │◀────────────┐                                      │
  │ (output-schema tools)│─────────────┘ feed detected overlaps back          │
  └─────────────────────┘                                                     │
             │  updated PromptSplitPlan                                        │
             ▼                                                                │
      PromptSplitPlan.validate()  ── hard fail-closed gate (raises) ──────────┘
             │
             ▼  fan out under Semaphore(max_concurrency)
  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
  │ 4. Impl #1     │ │ 4. Impl #2     │ │ 4. Impl #N     │  each: rich SplitPrompt
  │ (own tools +   │ │ (own tools +   │ │ (own tools +   │        + EnvironmentContext
  │  RW toolset)   │ │  RW toolset)   │ │  RW toolset)   │        + own tools
  └───────────────┘ └───────────────┘ └───────────────┘
             │
             ▼
     ContextMinimalFanoutResult(plan, plan_markdown, environment, outputs, metadata)
```

**Key design decisions:**

- **Direct class, single implementation.** The `multiple_prompts` sub-package nesting
  from PR #199 is dropped. The paradigm is now one fixed four-stage pipeline exposed as
  `ContextMinimalFanoutParadigm`. The `ParadigmClient` namespace still resolves to the
  same class for consistency, but the documented entry point is the direct class.
- **Context compression is a tool, not a convention.** A harness-owned
  `OutputSchemaBuilder` is bound to `declare_output_schema` / `append_output` tools and
  attached to the context/splitter/adversarial agents. After each agent run the harness
  reads `builder.snapshot()`; the agent's exploration transcript is discarded. This is
  the mechanism reviewer answer (a) asked for.
- **Adversarial loop before the deterministic gate.** Reviewer answer (b): the
  adversarial agent runs in a bounded loop; the deterministic `validate()` check is the
  final authority and fails closed.
- **One reusable toolset.** `ParadigmMinimalToolset` centralizes the filesystem toolset
  for all thin harnesses; read-only for planning agents, write-enabled for implementers.

---

## 6. Detailed Design

### 6.1 OutputSchemaBuilder + runtime output-schema tools

**File(s):** `vidbyte/tools/builtins/output_schema/builder.py`,
`vidbyte/tools/builtins/output_schema/declare.py`,
`vidbyte/tools/builtins/output_schema/append.py`,
`vidbyte/tools/builtins/output_schema/__init__.py`
**Type:** New files

#### What it does

Gives an agent the ability to declare a structured output shape at runtime and append
entries to it during its run, while the harness reads the accumulated structure out at
the end. This is how a context agent "reads a lot but returns only compressed relevant
structure."

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class OutputSchemaField:
    name: str
    description: str
    repeated: bool = False  # True → a list the agent appends to

class OutputSchemaBuilder:
    def declare(self, fields: Sequence[Mapping[str, Any]]) -> None: ...
    def append(self, field: str, value: Any) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...   # {declared_fields, entries}
    def is_declared(self) -> bool: ...

class DeclareOutputSchemaTool(BaseTool):     # spec name: "declare_output_schema"
    def __init__(self, builder: OutputSchemaBuilder) -> None: ...

class AppendOutputTool(BaseTool):            # spec name: "append_output"
    def __init__(self, builder: OutputSchemaBuilder) -> None: ...
```

#### Logic / Algorithm

1. Harness creates one `OutputSchemaBuilder` per agent run.
2. It binds `DeclareOutputSchemaTool(builder)` and `AppendOutputTool(builder)` and
   attaches them to that agent's tool set.
3. During the run, the model calls `declare_output_schema` once (fields it will emit)
   and `append_output` repeatedly (one entry per relevant file/note/finding).
4. Each tool routes to the builder and returns a short confirmation `ToolResult`.
5. After `agent.arun(...)`, the harness reads `builder.snapshot()` and maps it into the
   typed artifact (`EnvironmentContext` or `PromptSplitPlan`).

#### Edge Cases & Error Handling

- `append` before `declare`: builder auto-declares a permissive default so appends are
  never lost; `snapshot()` records that it was implicit.
- `append` to an unknown field: recorded under a catch-all `notes` list and surfaced in
  the confirmation message rather than raising (keeps the agent moving).
- Empty snapshot (agent appended nothing): harness falls back to the agent's final text
  content so a run never yields an empty artifact.

### 6.2 ParadigmMinimalToolset

**File(s):** `vidbyte/tools/toolsets/paradigm_minimal.py`,
`vidbyte/tools/toolsets/__init__.py`
**Type:** New files

#### What it does

Centralizes the "minimal universal toolset" for filesystem-resident thin harnesses.
Returns a `Tools` catalog rooted at a directory. Read-only by default (glob, grep,
read-text, read-lines, list-dir, code-execution); write-enabled variant adds `PatchTool`.

#### Interface / API

```python
class ParadigmMinimalToolset:
    def __init__(self, root: str | Path = ".", *, include_execution: bool = True, include_write: bool = False) -> None: ...
    def tools(self) -> Tools: ...           # a Tools catalog
    def all(self) -> tuple[BaseTool, ...]:  # convenience; matches settings normalizer
        return self.tools().all()
```

#### Logic / Algorithm

1. Build `FileSystemToolConfig(root=Path(root))`.
2. Assemble read/search tools: `GlobTool`, `GrepTool`, `ReadTextTool`, `ReadLinesTool`,
   `ListDirTool`.
3. If `include_execution`, add `CodeExecutionTool`.
4. If `include_write`, add `PatchTool`.
5. Wrap in a `Tools(...)` catalog and return.

#### Edge Cases & Error Handling

- Because `Tools` rejects duplicate tool names, the toolset never double-registers.
- The `.all()` convenience makes the object directly assignable to settings tool fields
  (the settings normalizer already dispatches on `.all()`).

### 6.3 Types: EnvironmentContext, SplitPrompt, PromptSplitPlan, ImplementationOutput, Result, Settings

**File(s):** `vidbyte/paradigms/context_minimal_fanout/types.py`
**Type:** New file (evolves PR #199's `types.py`)

#### What it does

Holds all frozen dataclasses and the settings object. Carries over `SplitPrompt`,
`PromptSplitPlan` (with `validate`, `to_markdown`, unique-id and owned-path overlap
checks), `ImplementationOutput`, and `ContextMinimalFanoutResult` from PR #199, and adds
`EnvironmentContext` plus a redesigned settings object with per-role fields.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class EnvironmentContext:
    summary: str
    files: tuple[ContextFile, ...]        # path + excerpt/notes
    notes: tuple[str, ...]
    entries: Mapping[str, Any]            # raw builder snapshot for transparency
    def to_prompt_block(self) -> str: ... # rendered <environment_context> block

@dataclass(frozen=True, slots=True)
class SplitPrompt:
    id: str
    title: str
    prompt: str
    owned_paths: tuple[str, ...] = ()
    read_only_paths: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    # carried from PR #199, unchanged semantics

@dataclass(frozen=True, slots=True)
class ContextMinimalFanoutResult:
    plan: PromptSplitPlan
    plan_markdown: str
    environment: EnvironmentContext
    outputs: tuple[ImplementationOutput, ...]
    metadata: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class ContextMinimalFanoutSettings:
    # context agent
    context_agent_name: str = "context-minimal-context"
    context_system_prompt: str | None = None
    context_provider / model_name / temperature / api_key / runner ...
    context_tools: tuple[object, ...] = ()
    # splitter agent
    splitter_* ...
    # adversarial agent
    adversarial_* ...
    max_adversarial_rounds: int = 2
    # implementation agents
    implementation_* ...
    # shared toolset controls
    include_minimal_toolset: bool = True
    default_tool_root: str | Path = "."
    implementation_include_write: bool = True
    # fanout shape / budgets / behavior (carried from PR #199)
    max_prompt_count: int = 8
    max_concurrency: int = 4
    max_*_tokens / max_cost_usd / cost_per_million_tokens ...
    return_exceptions: bool = True
    plan_output_path: str | Path | None = None

    def with_overrides(self, **overrides) -> "ContextMinimalFanoutSettings": ...
```

#### Logic / Algorithm

- `EnvironmentContext.from_snapshot(snapshot, fallback_text)` maps an
  `OutputSchemaBuilder` snapshot into typed fields, using the fallback when empty.
- `PromptSplitPlan.from_snapshot(snapshot)` builds the plan from the splitter/adversarial
  agent snapshot (replacing PR #199's `from_json_text` fenced-JSON parsing).
- `validate`, `to_markdown`, `_validate_unique_ids`, `_validate_owned_paths_do_not_overlap`
  carry over unchanged from PR #199.

#### Edge Cases & Error Handling

- Paired budget fields (`max_cost_usd` / `cost_per_million_tokens`) must be provided
  together (carried validation).
- `max_prompt_count`, `max_concurrency`, `max_adversarial_rounds` must be > 0.
- Snapshot missing required plan fields → `ConfigurationError` with the offending field.

### 6.4 ContextMinimalFanoutParadigm (orchestrator)

**File(s):** `vidbyte/paradigms/context_minimal_fanout/paradigm.py`
**Type:** New file (evolves PR #199's `harness.py`)

#### What it does

The public paradigm class. Subclasses `ParadigmHarness`. Owns the four-stage `arun`.

#### Interface / API

```python
class ContextMinimalFanoutParadigm(ParadigmHarness):
    def __init__(self, settings: ContextMinimalFanoutSettings | None = None, **kwargs) -> None: ...
    async def arun(self, prompt: str, **options) -> ContextMinimalFanoutResult: ...
    # run() inherited (sync bridge)
```

#### Logic / Algorithm (`arun`)

1. `settings = self._resolve_settings(options)`.
2. `environment = await self._run_context_agent(prompt, settings)`.
3. `plan = await self._run_splitter(prompt, environment, settings)`.
4. `plan = await self._run_adversarial_loop(prompt, plan, environment, settings)`.
5. `plan.validate(max_prompt_count=settings.max_prompt_count)` (hard gate; raises).
6. `plan_markdown = plan.to_markdown()`; `self._write_plan_if_requested(...)`.
7. `outputs = await self._run_implementation_prompts(plan, environment, settings)`.
8. `metadata = self._build_result_metadata(...)`.
9. return `ContextMinimalFanoutResult(plan, plan_markdown, environment, outputs, metadata)`.

Private helpers (class-first, one-line signatures, one-line doc comments):

- `_run_context_agent` — builds a fresh `OutputSchemaBuilder`, binds output-schema tools,
  builds the RO minimal toolset agent, runs it, maps snapshot → `EnvironmentContext`.
- `_run_splitter` — same builder pattern; input message embeds the environment block;
  maps snapshot → `PromptSplitPlan`.
- `_run_adversarial_loop` — for up to `max_adversarial_rounds`: run adversarial agent
  with (original request + current prompts + environment); parse updated plan; if the
  deterministic overlap check passes, break; else feed the detected conflicts back into
  the next round's message.
- `_run_implementation_prompts` / `_run_one_with_semaphore` / `_run_one_implementation_prompt`
  — carried from PR #199, extended so each branch message includes the environment block.
- `_build_context_agent` / `_build_splitter_agent` / `_build_adversarial_agent` /
  `_build_implementation_agent` — per-role `BaseAgent` construction from settings.
- `_bind_output_schema_tools` — returns `(builder, tools_with_output_schema)`.
- `_with_budget_middleware`, `_build_result_metadata`, `_write_plan_if_requested`,
  `_resolve_settings` — carried from PR #199.

#### Edge Cases & Error Handling

- Empty environment snapshot → fall back to context agent's final text (never empty).
- Adversarial loop exhausts rounds without clean overlap → the post-loop `validate()`
  raises `ConfigurationError` (fail closed).
- Implementation branch raises → captured per `return_exceptions` (carried behavior).

### 6.5 Prompts

**File(s):** `vidbyte/paradigms/context_minimal_fanout/prompts.py` and asset files
`context_prompt.md`, `split_prompt.md`, `adversarial_prompt.md`, `implementation_prompt.md`
**Type:** New files

#### What it does

`ContextMinimalFanoutPrompts` lazily loads the four package-local system prompts via
`importlib.resources`. Each prompt instructs its agent to use `declare_output_schema` /
`append_output` (context, splitter, adversarial) or to honor ownership boundaries
(implementation).

### 6.6 Wiring / exports

**File(s):** `vidbyte/paradigms/context_minimal_fanout/__init__.py`,
`vidbyte/paradigms/__init__.py`, `vidbyte/paradigms/client.py`,
`vidbyte/paradigms/context_minimal_fanout/client.py`, `vidbyte/__init__.py`,
`vidbyte/tools/builtins/__init__.py`
**Type:** Modified / New

#### What it does

Re-exports `ContextMinimalFanoutParadigm` (and its public types) up through
`vidbyte.paradigms` and the top-level `vidbyte` package. `ParadigmClient` /
`ContextMinimalFanoutClient` resolve to the new class. New output-schema tools and the
toolset are re-exported from their category packages. Removes the now-defunct
`multiple_prompts`-only exports from PR #199 (they never landed on `main`).

### 6.7 Skill rewrite

**File(s):** `skills/context-minimal-fanout/SKILL.md`
**Type:** New file (replaces PR #199's operational skill)

Rewritten as an explanatory paradigm document following `skills/paradigm/SKILL.md`:
`<identity>`, `<intent>`, `<when_to_use>`, `<pipeline>` (the four stages), `<contracts>`
(what each stage consumes/produces), and `<anti_patterns>` — describing what the paradigm
*is* and when to reach for it, not step-by-step agent instructions.

### 6.8 README update

**File(s):** `README.md`
**Type:** Modified

Replace the `sdk.paradigms.context_minimal_fanout.multiple_prompts(...)` example with:

```python
from vidbyte import ContextMinimalFanoutParadigm

harness = ContextMinimalFanoutParadigm(
    default_tool_root=".",
    implementation_tools=[my_patch_tool],
    splitter_model_name="claude-opus-4-8",
    implementation_model_name="claude-sonnet-5",
)
result = harness.run("Implement the requested repo change.")
```

---

## 7. Data Model Changes

N/A — no database or persistence. All "data model" changes are in-memory frozen
dataclasses covered in §6.3.

---

## 8. API Changes

N/A — no HTTP/RPC API surface. The public Python API additions are:
`ContextMinimalFanoutParadigm`, `ContextMinimalFanoutSettings`, `EnvironmentContext`,
`ContextMinimalFanoutResult`, `OutputSchemaBuilder`, `DeclareOutputSchemaTool`,
`AppendOutputTool`, `ParadigmMinimalToolset` (plus carried `SplitPrompt`,
`PromptSplitPlan`, `ImplementationOutput`).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-minimal-fanout-paradigm.md` | This design doc |
| CREATE | `vidbyte/tools/builtins/output_schema/__init__.py` | New tool package exports |
| CREATE | `vidbyte/tools/builtins/output_schema/builder.py` | `OutputSchemaBuilder` accumulator |
| CREATE | `vidbyte/tools/builtins/output_schema/declare.py` | `DeclareOutputSchemaTool` |
| CREATE | `vidbyte/tools/builtins/output_schema/append.py` | `AppendOutputTool` |
| CREATE | `vidbyte/tools/toolsets/__init__.py` | New toolsets package |
| CREATE | `vidbyte/tools/toolsets/paradigm_minimal.py` | `ParadigmMinimalToolset` |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/__init__.py` | Paradigm package exports |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/paradigm.py` | `ContextMinimalFanoutParadigm` orchestrator |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/types.py` | Dataclasses + settings |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/prompts.py` | Prompt asset loader |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/context_prompt.md` | Context agent system prompt |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/split_prompt.md` | Splitter agent system prompt |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/adversarial_prompt.md` | Adversarial agent system prompt |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/implementation_prompt.md` | Implementation agent system prompt |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/client.py` | `ContextMinimalFanoutClient` → new class |
| CREATE | `skills/context-minimal-fanout/SKILL.md` | Explanatory paradigm skill |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export output-schema tools + `CodeExecutionTool` |
| MODIFY | `vidbyte/paradigms/__init__.py` | Export `ContextMinimalFanoutParadigm` + types |
| MODIFY | `vidbyte/paradigms/client.py` | `ParadigmClient` resolves the new class |
| MODIFY | `vidbyte/__init__.py` | Top-level export of paradigm + new tool/toolset symbols |
| MODIFY | `README.md` | Correct run example |
| MODIFY | `pyproject.toml` | Ensure `.md` prompt assets are packaged |

Totals: ~17 created, ~5 modified, 0 deleted (PR #199 files never landed on `main`).

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| PR #195 scaffolding | merged into `main` | `ParadigmHarness`, `ParadigmClient` base | Low — already merged |
| Existing builtins | in-repo | filesystem/search/exec/patch tools | Low |
| LLM provider | caller-configured | runs the four agent roles | Medium — cost/latency scale with N branches |

No new third-party packages.

---

## 11. Rollout & Deployment

- Library change; no services, no feature flags. Ships as additive public API on `main`.
- Not a breaking change to `main` (no concrete paradigm exists there yet). PR #199 is
  superseded and should be closed in favor of this PR.
- Rollback = revert the PR; no migrations or state.

---

## 12. Open Questions

- [ ] Should `declare_output_schema` enforce the declared field set against `BaseAgent`'s
      `output_schema=` provider enforcement, or remain a soft accumulator only? (Proposed:
      soft accumulator in v1 — simpler, provider-agnostic, and matches the "append during
      run" behavior the reviewer described.)
- [ ] Should the minimal toolset also include a bare `find`/`tree` tool for the context
      agent, or are glob+grep+list-dir sufficient? (Proposed: glob+grep+list-dir now;
      add later if the context agent under-explores.)
- [ ] Keep the `ParadigmClient` namespace path at all, or make the direct class the *only*
      entry point? (Proposed: keep the namespace resolving to the class for consistency
      with #195, document only the direct class.)

---

## 13. Alternatives Considered

### Alternative 1: Reuse context-window primitives instead of a new output-schema tool
- What: use `ContextUpsertTool` / `ContextListTool` to accumulate structured context.
- Why rejected: those tools mutate the agent's *context window* registry, not a
  detached return artifact; semantics and lifecycle differ from the reviewer's described
  "declare an output schema and append to it," and reading them back out couples the
  harness to `ContextManager` internals. A dedicated, harness-owned `OutputSchemaBuilder`
  is cleaner and reusable.

### Alternative 2: Keep the single splitter agent (PR #199 shape)
- What: one agent reads the repo and emits the split plan; no context/adversarial stages.
- Why rejected: the reviewer explicitly asked for decomposition — a dedicated context
  agent (so exploration cost is compressed once and shared) and an adversarial de-overlap
  pass (so non-overlap is actively improved, not just validated).

### Alternative 3: Keep the `multiple_prompts` sub-package
- What: retain `context_minimal_fanout/multiple_prompts/` as one implementation variant.
- Why rejected: the algorithm is now a single fixed pipeline; the extra nesting adds a
  layer with no second variant, and the reviewer wants a single `ContextMinimalFanoutParadigm`
  class. Future variants can reintroduce nesting if/when they exist.

### Alternative 4: Deterministic-only overlap resolution (no adversarial agent)
- What: rely solely on `validate()` to reject overlaps.
- Why rejected: reviewer answer (b) wants an LLM adversarial pass to *fix* overlaps
  before the gate; deterministic validation stays as the fail-closed backstop.

---

END OF DESIGN DOC

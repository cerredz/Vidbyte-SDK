# Design Doc: Context Minimal Fanout Paradigm

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-30
**Last Updated:** 2026-06-30

---

## 1. Overview

This change adds the first concrete Vidbyte paradigm harness: `context_minimal_fanout`.
The paradigm turns one large implementation request into multiple non-overlapping
implementation prompts, then executes those prompts in parallel in fresh agent
contexts. Its purpose is to reduce the amount of context each implementation
agent must hold while preserving a single user-facing `run()` / `arun()` entry
point.

The concrete implementation lives under:

```text
vidbyte/paradigms/context_minimal_fanout/multiple_prompts/
```

The user-facing API exposes it through the paradigm client:

```python
harness = sdk.paradigms.context_minimal_fanout.multiple_prompts(...)
result = await harness.arun("Implement the requested repo change.")
```

The harness composes existing SDK primitives: `BaseAgent`, built-in read/search
tools, optional code execution, user-provided tools, middleware, provider/model
settings, and token/cost budget middleware where configured. It does not change
the core `vidbyte.pipelines` contract in v1 because existing pipelines accept a
single string input and fan that same input to stages. This paradigm needs
dynamic branch prompts, structured split-plan validation, and structured
per-branch outputs.

This design assumes PR #195 (`feat: Paradigm Harness Scaffolding`) is merged
before implementation, or that this feature branch is based on PR #195's head.
Current `main` does not yet contain `vidbyte.paradigms`.

---

## 2. Goals & Non-Goals

### Goals

- Add the first concrete paradigm harness under `vidbyte.paradigms`.
- Name the paradigm `context_minimal_fanout`, replacing the rough phrase "least
  amount of context window filled up paradigm."
- Add a `multiple_prompts` implementation under
  `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/`.
- Provide one public `run()` / `arun()` harness entry point through
  `ParadigmHarness`.
- Build a splitter agent with default read/search/code tools plus user-provided
  tools.
- Build implementation agents from split prompts, with separate implementation
  settings and user-provided tools.
- Run implementation agents concurrently with a configurable concurrency limit.
- Return structured split-plan and implementation outputs instead of only a
  joined string.
- Render the split plan as Markdown and optionally write it to a caller-provided
  `.md` path.
- Add a root skill at `skills/context-minimal-fanout/SKILL.md` that instructs
  coding agents to read needed repo context, write a non-overlapping prompt split
  to Markdown, and run each prompt in separate subagents for the current run.
- Add prompt assets for splitter and implementation agents so the harness prompt
  text is inspectable.
- Expose a simple client shape:

  ```python
  sdk.paradigms.context_minimal_fanout.multiple_prompts(...)
  ```

### Non-Goals

- Do not add hosted API routes, dashboards, persistence, remote execution, or
  private Vidbyte service behavior.
- Do not modify the MCP server to expose paradigms in this PR.
- Do not add tests or verification scripts under this no-tests workflow.
- Do not change existing agent runtime behavior.
- Do not change existing pipeline behavior or broaden `BasePipeline` beyond its
  current string-in/string-out contract.
- Do not implement automatic git commits, PR creation, or repository mutation
  policy inside the harness. Editing is controlled by the tools the caller
  provides.
- Do not guarantee perfect semantic non-overlap. V1 validates explicit ownership
  metadata emitted by the splitter.
- Do not add the paradigm prompt assets to the global `vidbyte.prompts` enum
  catalog in v1. They are package-local paradigm assets.

---

## 3. Background & Context

The SDK already has the lower-level components this paradigm needs:

- `vidbyte.agents.BaseAgent` owns system prompts, runners, tools, middleware,
  context, tracing, and async/sync execution aliases.
- `BaseAgent.fork(...)` can clone an agent with modified name, system prompt,
  tools, middleware, context settings, and metadata.
- Built-in read/search tools exist: `GlobTool`, `GrepTool`, `ReadTextTool`,
  `ReadLinesTool`, and related filesystem tools.
- `CodeExecutionTool` exists in `vidbyte/tools/builtins/code_execution.py`, but
  is not currently re-exported from `vidbyte.tools.builtins`.
- Middleware already includes token and cost budget policies, but they are
  agent-run policies. Cross-agent total budget cancellation is not a current SDK
  primitive.
- `vidbyte.pipelines` intentionally keeps a small contract: each stage receives
  one string and returns one string. `ParallelPipeline` and `MapReducePipeline`
  fan the same prompt to every branch. They do not project a structured split
  plan into distinct prompts.
- PR #195 adds `vidbyte.paradigms`, `ParadigmHarness`, `ParadigmClient`, and a
  maintainer skill explaining that paradigms are thin runnable harnesses built
  from SDK primitives.

The requested workflow is higher-level than an ordinary pipeline. It has its own
control flow:

1. A splitter agent inspects the repo enough to understand the request.
2. The splitter emits a bounded plan containing multiple independent prompts.
3. The harness validates overlap constraints.
4. The harness projects each plan item into a fresh implementation agent.
5. The implementation agents run in parallel.
6. The harness returns every output plus the split plan.

That control flow fits the new `vidbyte.paradigms` layer rather than
`vidbyte.harnesses` or `vidbyte.pipelines`.

The requested `references/design-doc-template.md` file does not exist in this
checkout. This document follows the established 14-section structure used by
existing local design docs.

---

## 4. Requirements

### Functional Requirements

1. Add an importable `vidbyte.paradigms.context_minimal_fanout` package.
2. Add an importable
   `vidbyte.paradigms.context_minimal_fanout.multiple_prompts` package.
3. Add `ContextMinimalFanoutClient` with a `multiple_prompts(...)` factory.
4. Update `ParadigmClient` so callers can access
   `sdk.paradigms.context_minimal_fanout`.
5. Add `MultiplePromptFanoutHarness` extending `ParadigmHarness`.
6. `MultiplePromptFanoutHarness.arun(prompt: str, **options)` must execute the
   full split-and-fanout flow.
7. `MultiplePromptFanoutHarness.run(prompt: str, **options)` must be inherited
   from `ParadigmHarness` and remain the sync entry point.
8. The harness must create a splitter agent with a splitter system prompt.
9. The splitter agent must receive default read/search/code tools unless
   disabled.
10. The splitter agent must receive caller-provided splitter tools.
11. The splitter agent must receive caller-provided splitter middleware and
    model/runner settings.
12. The splitter must output a JSON split plan that can be converted into
    Markdown.
13. The split plan must contain the overall goal, global instructions,
    non-overlap requirements, and implementation prompts.
14. Each implementation prompt must include a stable id, title, prompt text,
    owned paths, optional read-only paths, optional commands, and optional notes.
15. The harness must reject empty split plans.
16. The harness must reject duplicate prompt ids.
17. The harness must reject duplicate owned paths across implementation prompts.
18. The harness must reject a plan with more prompts than `max_prompt_count`.
19. The harness must render the split plan to Markdown.
20. If `plan_output_path` is provided, the harness must write the Markdown plan
    to that path.
21. The harness must create one implementation agent per split prompt.
22. Implementation agents must receive an implementation system prompt plus the
    split item prompt body.
23. Implementation agents must receive caller-provided implementation tools.
24. Implementation agents must receive caller-provided implementation middleware
    and model/runner settings.
25. Implementation agents must run concurrently up to `max_concurrency`.
26. The harness must return one output record per implementation prompt.
27. Implementation failures must be captured per prompt when
    `return_exceptions=True`.
28. Implementation failures must raise and stop the harness when
    `return_exceptions=False`.
29. The final result must expose `plan`, `plan_markdown`, `outputs`, and
    aggregate metadata.
30. Add a root skill at `skills/context-minimal-fanout/SKILL.md`.
31. The skill must explicitly instruct models to first read required repo
    context, then write a Markdown split plan, then run prompts in subagents.
32. The skill must define what makes prompts non-overlapping.
33. The skill must include sections for goal, instructions, commands, non-overlap
    requirements, and output expectations.
34. Add package-local splitter and implementation prompt assets.
35. Update README/package docs to mention the concrete paradigm without
    overstating hosted support.

### Non-Functional Requirements

- Keep the change additive and backward compatible.
- Keep the harness dependency-free beyond existing SDK dependencies.
- Keep prompt assets readable and reviewable.
- Use dataclasses for typed result and settings contracts.
- Avoid hidden filesystem writes except the explicit `plan_output_path` option.
- Keep default tools read-oriented. Mutating/editing tools should come from the
  caller's explicit `implementation_tools`.
- Use only ASCII in new files.
- Follow the no-tests workflow: no new test files or verification scripts.
- Run lightweight verification after implementation:

  ```powershell
  python -m compileall vidbyte
  python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.paradigms.context_minimal_fanout).__name__)"
  ```

---

## 5. High-Level Design

### 5.1 Package Shape

```text
vidbyte/paradigms/
|-- client.py
|-- context_minimal_fanout/
|   |-- README.md
|   |-- __init__.py
|   |-- client.py
|   `-- multiple_prompts/
|       |-- __init__.py
|       |-- harness.py
|       |-- implementation_prompt.md
|       |-- prompts.py
|       |-- split_prompt.md
|       `-- types.py
```

`context_minimal_fanout` is the paradigm family. `multiple_prompts` is the first
concrete implementation.

### 5.2 Runtime Flow

```text
caller prompt
  |
  v
MultiplePromptFanoutHarness.arun()
  |
  +--> build splitter agent
  |      default tools + splitter_tools
  |      splitter middleware/settings
  |
  +--> splitter agent emits JSON plan
  |
  +--> PromptSplitPlan validates:
  |      non-empty prompts
  |      duplicate ids rejected
  |      owned path overlap rejected
  |      max_prompt_count enforced
  |
  +--> render Markdown plan
  |      optionally write plan_output_path
  |
  +--> for each SplitPrompt:
         build fresh implementation agent
         implementation tools/settings/middleware
         run concurrently under semaphore
  |
  v
ContextMinimalFanoutResult
```

### 5.3 Why Not Add A Pipeline First

Existing pipelines are simple and useful because their contract is small:

```text
BasePipeline.run(prompt: str) -> str
```

The requested paradigm needs:

- one splitter output projected into N distinct prompts;
- typed branch metadata;
- ownership validation before execution;
- branch-level error capture;
- structured aggregate output.

Adding those concerns to `vidbyte.pipelines` in this PR would either break the
current contract or introduce a broader pipeline abstraction before a second
use case proves it belongs there. V1 keeps projection inside the paradigm
harness. A later PR can extract a reusable `FanoutPipeline` or
`ProjectingParallelPipeline` if more paradigms need the same primitive.

---

## 6. Detailed Design

### 6.1 `vidbyte/paradigms/context_minimal_fanout/__init__.py`

**Type:** New file

Exports:

```python
from vidbyte.paradigms.context_minimal_fanout.client import ContextMinimalFanoutClient
from vidbyte.paradigms.context_minimal_fanout.multiple_prompts import (
    ContextMinimalFanoutResult,
    ImplementationOutput,
    MultiplePromptFanoutHarness,
    MultiplePromptFanoutSettings,
    PromptSplitPlan,
    SplitPrompt,
)
```

Keep `__all__` explicit.

### 6.2 `vidbyte/paradigms/context_minimal_fanout/client.py`

**Type:** New file

Defines:

```python
class ContextMinimalFanoutClient:
    def multiple_prompts(self, **kwargs: Any) -> MultiplePromptFanoutHarness:
        ...
```

The method constructs `MultiplePromptFanoutHarness` and forwards keyword
settings. This mirrors the repo's namespace-client pattern used by
`AgentClient` and `EvalClient`.

### 6.3 `vidbyte/paradigms/client.py`

**Type:** Modified file from PR #195

Add:

```python
from vidbyte.paradigms.context_minimal_fanout import ContextMinimalFanoutClient

class ParadigmClient:
    def __init__(self) -> None:
        self.context_minimal_fanout = ContextMinimalFanoutClient()
```

This keeps `VidbyteSDK().paradigms` as the only root attachment point while
letting concrete paradigms own their factories.

### 6.4 `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/types.py`

**Type:** New file

Defines dataclasses:

```python
@dataclass(frozen=True, slots=True)
class SplitPrompt:
    id: str
    title: str
    prompt: str
    owned_paths: tuple[str, ...] = ()
    read_only_paths: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class PromptSplitPlan:
    goal: str
    global_instructions: str
    non_overlap_requirements: tuple[str, ...]
    prompts: tuple[SplitPrompt, ...]

@dataclass(frozen=True, slots=True)
class ImplementationOutput:
    prompt_id: str
    title: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

@dataclass(frozen=True, slots=True)
class ContextMinimalFanoutResult:
    plan: PromptSplitPlan
    plan_markdown: str
    outputs: tuple[ImplementationOutput, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class MultiplePromptFanoutSettings:
    ...
```

`PromptSplitPlan.from_json_text(...)` parses splitter output. It should extract
a fenced JSON block if present, then load JSON through the standard library.
`PromptSplitPlan.validate(...)` enforces prompt count, duplicate ids, and owned
path overlap. `PromptSplitPlan.to_markdown()` renders the requested `.md`
format.

`MultiplePromptFanoutSettings` stores:

- splitter runner/model/provider/api key settings;
- implementation runner/model/provider/api key settings;
- `splitter_tools`;
- `implementation_tools`;
- `include_default_splitter_tools`;
- `default_tool_root`;
- splitter and implementation middleware;
- `splitter_agent_options`;
- `implementation_agent_options`;
- `max_prompt_count`;
- `max_concurrency`;
- optional `max_splitter_tokens`;
- optional `max_implementation_tokens`;
- optional `max_cost_usd`;
- optional `cost_per_million_tokens`;
- `return_exceptions`;
- optional `plan_output_path`.

Budget settings apply by adding existing middleware to the relevant agents. V1
does not implement cross-agent cancellation once a total budget is reached.

### 6.5 `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/prompts.py`

**Type:** New file

Defines a small loader class:

```python
class MultiplePromptFanoutPrompts:
    def splitter(self) -> str:
        ...

    def implementation(self) -> str:
        ...
```

The loader reads package-local Markdown assets via `importlib.resources`. This
keeps prompt bodies outside Python string constants while avoiding global prompt
enum/catalog changes in v1.

### 6.6 `split_prompt.md`

**Type:** New file

The splitter system prompt must instruct the model to:

- inspect only the repo context needed for the request;
- use tools before splitting when local context is necessary;
- produce a JSON object with `goal`, `global_instructions`,
  `non_overlap_requirements`, and `prompts`;
- make prompts non-overlapping by assigning unique owned files/contracts/tests;
- mark shared context as read-only;
- keep each implementation prompt self-contained;
- never ask an implementation agent to inspect or change files owned by another
  prompt;
- include commands/verification obligations where useful.

### 6.7 `implementation_prompt.md`

**Type:** New file

The implementation system prompt must instruct each branch agent to:

- execute only its assigned prompt;
- treat `owned_paths` as the mutation boundary;
- treat `read_only_paths` as context only;
- avoid changing files or contracts owned by other prompts;
- report completion, changed files, verification, and blockers in a concise
  structured response.

### 6.8 `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/harness.py`

**Type:** New file

Defines `MultiplePromptFanoutHarness(ParadigmHarness)`.

Primary methods:

```python
class MultiplePromptFanoutHarness(ParadigmHarness):
    async def arun(self, prompt: str, **options: Any) -> ContextMinimalFanoutResult:
        ...
```

Important helper methods:

- `_resolve_settings(...)`: merges construction settings with per-run options.
- `_build_splitter_agent(...)`: creates the splitter `BaseAgent`.
- `_default_splitter_tools(...)`: returns read/search/code tools scoped to
  `default_tool_root`.
- `_run_splitter(...)`: runs the splitter and parses `PromptSplitPlan`.
- `_write_plan_if_requested(...)`: writes Markdown only when `plan_output_path`
  is set.
- `_build_implementation_agent(...)`: creates a fresh branch agent for one
  split prompt.
- `_run_implementation_prompts(...)`: runs branches with `asyncio.Semaphore`.
- `_run_one_implementation_prompt(...)`: returns `ImplementationOutput`.

Use `BaseAgent` directly. Use explicit imports for `GlobTool`, `GrepTool`,
`ReadTextTool`, `ReadLinesTool`, and `CodeExecutionTool`.

Errors:

- Bad splitter JSON raises `ConfigurationError`.
- Invalid split plan raises `ConfigurationError`.
- Branch exceptions are either captured into `ImplementationOutput.error` or
  re-raised based on `return_exceptions`.
- Writing `plan_output_path` can raise normal filesystem exceptions; do not
  silently swallow them.

### 6.9 `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/__init__.py`

**Type:** New file

Re-export the harness, result, settings, and plan dataclasses.

### 6.10 `vidbyte/paradigms/context_minimal_fanout/README.md`

**Type:** New file

Document:

- the paradigm role;
- the `multiple_prompts` implementation;
- usage;
- non-overlap rules;
- default tool behavior;
- budget/concurrency limits;
- current limitations.

### 6.11 `skills/context-minimal-fanout/SKILL.md`

**Type:** New file

This skill is for Codex/Claude-style coding agents, not just the SDK harness.
It must include:

- identity and intent;
- when to use this paradigm;
- required workflow;
- required Markdown split-plan file shape;
- non-overlap requirements;
- subagent prompt format;
- command/verification section;
- rules and anti-patterns.

The skill must explicitly tell the model:

1. Read all repo context needed before splitting.
2. Write the split plan into a `.md` file.
3. Ensure prompts do not overlap in ownership.
4. Run each prompt in a subagent for the current run.
5. Return every subagent output and identify conflicts/blockers.

### 6.12 `pyproject.toml`

**Type:** Modified

Add package data so package-local Markdown prompts ship in built distributions:

```toml
"vidbyte.paradigms.context_minimal_fanout.multiple_prompts" = ["*.md"]
```

### 6.13 `vidbyte/tools/builtins/__init__.py`

**Type:** Modified

Add `CodeExecutionTool` to the public builtins export surface. The harness can
import it directly either way, but exporting it aligns with the requested default
toolset and makes the tool easier for SDK users to override or reuse.

### 6.14 `README.md`

**Type:** Modified

Add a short paradigms usage snippet after PR #195's general paradigm docs exist.
The snippet should mention:

```python
harness = sdk.paradigms.context_minimal_fanout.multiple_prompts(...)
result = await harness.arun("...")
```

Keep language precise: this is a local SDK harness, not a hosted service.

### 6.15 `vidbyte/__init__.py`

**Type:** Modified

Re-export the concrete client, harness, settings, and result dataclasses if PR
#195's root export pattern accepts paradigm exports. If PR #195 intentionally
keeps root exports minimal, skip concrete root exports and document direct
imports instead. This is an approval-time decision.

---

## 7. Data Model Changes

No persisted data model, database schema, migrations, or external API schemas.

New in-process Python dataclasses:

- `SplitPrompt`
- `PromptSplitPlan`
- `ImplementationOutput`
- `ContextMinimalFanoutResult`
- `MultiplePromptFanoutSettings`

These are immutable `dataclass(frozen=True, slots=True)` contracts used only by
the SDK harness.

Non-overlap validation in v1 is metadata-based:

- Prompt ids must be unique.
- `owned_paths` must not repeat across prompts.
- Shared files must be listed under `read_only_paths`.
- The harness does not statically prove semantic contract independence.

---

## 8. API Changes

### New Python APIs

```python
from vidbyte.paradigms.context_minimal_fanout import ContextMinimalFanoutClient
from vidbyte.paradigms.context_minimal_fanout.multiple_prompts import (
    ContextMinimalFanoutResult,
    ImplementationOutput,
    MultiplePromptFanoutHarness,
    MultiplePromptFanoutSettings,
    PromptSplitPlan,
    SplitPrompt,
)
```

### New Client Access

```python
sdk = VidbyteSDK()
harness = sdk.paradigms.context_minimal_fanout.multiple_prompts(
    implementation_tools=[...],
    implementation_model_name="gpt-5-codex",
    splitter_model_name="gpt-5",
)
result = await harness.arun("Implement the feature.")
```

### Optional Root Exports

Pending PR #195 export policy:

```python
from vidbyte import MultiplePromptFanoutHarness, MultiplePromptFanoutSettings
```

### No HTTP / MCP API Changes

N/A - this change is local Python SDK surface only.

---

## 9. File Change Manifest

This manifest assumes PR #195 has already added `vidbyte/paradigms/`,
`ParadigmHarness`, and `ParadigmClient`.

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-minimal-fanout-paradigm.md` | Design doc for the concrete paradigm |
| CREATE | `skills/context-minimal-fanout/SKILL.md` | Agent-facing skill for the paradigm workflow |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/README.md` | Package-level documentation |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/__init__.py` | Public package exports |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/client.py` | Paradigm family namespace client |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/__init__.py` | Implementation package exports |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/harness.py` | Main runnable harness |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/types.py` | Settings/result/split-plan dataclasses |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/prompts.py` | Package-local prompt loader |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/split_prompt.md` | Splitter system prompt |
| CREATE | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/implementation_prompt.md` | Implementation system prompt |
| MODIFY | `pyproject.toml` | Include paradigm Markdown prompt assets in package data |
| MODIFY | `README.md` | Document the concrete paradigm usage |
| MODIFY | `vidbyte/__init__.py` | Optional concrete paradigm exports if aligned with PR #195 |
| MODIFY | `vidbyte/paradigms/__init__.py` | Optional concrete paradigm exports if aligned with PR #195 |
| MODIFY | `vidbyte/paradigms/client.py` | Attach `context_minimal_fanout` client |
| MODIFY | `vidbyte/paradigms/README.md` | Mention the first concrete paradigm |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Re-export `CodeExecutionTool` |

Summary: **11 files created**, **7 files modified**, **0 files deleted**.

If PR #195 is not merged before implementation, the manifest must also include
the scaffold files from PR #195, or the implementation branch must target PR
#195's branch instead of `main`.

---

## 10. Testing Plan

N/A - no new test files or verification scripts will be added under the
requested `design-doc-no-tests` workflow.

Implementation verification will be limited to:

```powershell
python -m compileall vidbyte
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.paradigms.context_minimal_fanout).__name__)"
python -c "from vidbyte.paradigms.context_minimal_fanout.multiple_prompts import MultiplePromptFanoutHarness, PromptSplitPlan; print(MultiplePromptFanoutHarness.__name__, PromptSplitPlan.__name__)"
```

Manual inspection checklist:

- Confirm `sdk.paradigms.context_minimal_fanout.multiple_prompts` constructs a
  harness.
- Confirm package-local Markdown prompt assets load with `importlib.resources`.
- Confirm the split-plan Markdown renderer produces sections for goal,
  instructions, non-overlap requirements, and each implementation prompt.
- Confirm no implementation file creates tests or verification scripts.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `asyncio` | Python >=3.11 | Concurrent branch execution and semaphore control | Low; already used in SDK |
| Python stdlib `json` | Python >=3.11 | Parse splitter output | Low |
| Python stdlib `pathlib` | Python >=3.11 | Optional Markdown plan output path | Low |
| Python stdlib `importlib.resources` | Python >=3.11 | Load package-local prompt assets | Low |
| Existing `BaseAgent` | In-repo | Splitter and implementation agents | Medium; relies on current agent behavior |
| Existing middleware | In-repo | Optional token/cost/runtime controls | Medium; cross-agent total budgets are not supported |
| Existing tools | In-repo | Default read/search/code toolset | Low |

No new third-party dependencies, network services, databases, environment
variables, or migrations are required.

---

## 12. Rollout & Deployment

- Additive SDK feature.
- No feature flag required.
- No migrations required.
- No hosted deployment required.
- Rollback is a normal code revert.

Implementation sequence after approval:

1. Confirm whether to wait for PR #195 merge or branch from PR #195.
2. Create an isolated worktree.
3. Commit this design doc first.
4. Add package-local prompt assets and dataclasses.
5. Add the harness.
6. Add the paradigm client wiring.
7. Add the skill file.
8. Update docs and exports.
9. Run compile/import verification.
10. Perform the required refinement pass.
11. Push and open a draft PR.

---

## 13. Open Questions

- [ ] PR #195 is open and current `main` does not contain `vidbyte.paradigms`.
  Should implementation wait until PR #195 is merged, or should the new branch be
  based on `feat/paradigm-harness-scaffolding` and target that branch?
- [ ] Should concrete paradigm classes be re-exported from root `vidbyte`, or
  should root exports remain limited to the generic paradigm scaffolding from PR
  #195?
- [ ] Should `plan_output_path` default to writing a `.md` file, or should it
  remain explicit to avoid surprising filesystem writes? Recommendation: keep it
  explicit in the SDK harness; the skill can require a Markdown file in coding
  sessions.
- [ ] Should implementation agents receive default read/search tools by default,
  or only user-provided tools? Recommendation: splitter gets default read/search
  tools; implementation agents get user-provided tools so mutation permissions
  are explicit.
- [ ] Should cross-agent total token/cost budgeting be added as a reusable SDK
  middleware primitive later? Recommendation: not in v1; use per-agent budgets
  and aggregate metadata now.
- [ ] The requested `references/design-doc-template.md` file is missing. Should
  that template be restored in a separate docs hygiene PR?

---

## 14. Alternatives Considered

### Alternative 1: Add A New Pipeline Primitive First

- What: Implement `FanoutPipeline` or `ProjectingParallelPipeline` under
  `vidbyte.pipelines`, then build the paradigm on top of it.
- Why rejected for v1: Existing pipelines intentionally use a small
  string-in/string-out contract. The requested workflow needs structured plan
  validation and branch result metadata, which would force a broader pipeline API
  before another use case proves it should be shared.

### Alternative 2: Put The Harness Under `vidbyte.harnesses`

- What: Add `vidbyte.harnesses.context_minimal_fanout`.
- Why rejected: `vidbyte.harnesses` is documented as the boundary for custom
  harness integrations. PR #195 defines `vidbyte.paradigms` as the home for
  Vidbyte-owned thin runnable paradigm harnesses.

### Alternative 3: Add Only A Skill

- What: Add `skills/context-minimal-fanout/SKILL.md` and no SDK runnable.
- Why rejected: The user explicitly asked for the first implementation under
  `vidbyte/paradigms/{name}/{multiple_prompts}` and for a harness with a
  singular `run` entry point.

### Alternative 4: Use The Global Prompt Catalog

- What: Add splitter and implementation prompts under
  `vidbyte/prompts/prompts/context_minimal_fanout/` and enum entries in
  `Prompt`.
- Why rejected for v1: The prompt assets are private to this paradigm
  implementation. Package-local Markdown keeps them inspectable without
  increasing the global prompt enum surface before the API settles.

### Alternative 5: Default To Writing The Markdown Plan File

- What: Always write `context-minimal-fanout-plan.md` during `arun`.
- Why rejected: Hidden filesystem writes are surprising in an SDK harness. The
  harness should return `plan_markdown` always and write only when the caller
  supplies `plan_output_path`. The skill can require a Markdown file for
  interactive coding-agent workflows.

---

END OF DESIGN DOC

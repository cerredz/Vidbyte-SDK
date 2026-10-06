# Design Doc — Context-Minimal Fanout Paradigm: PR #206 Comment Resolution + Schema/Tooling Extensions

## Overview

This change resolves all five review comments left on PR #206 (`feat: context-minimal
fanout paradigm (four-stage pipeline)`) and implements the schema/tooling extensions
discussed during the review conversation. It touches the `ParadigmMinimalToolset`, the
`EnvironmentContext` dataclass, the output-schema tool family, the four stage prompts,
and the settings/paradigm orchestration layer.

The work splits into seven workstreams that are independent enough to implement and
commit separately but share the `context_minimal_fanout` package:

1. Add `TreeTool` + `StatTool` to `ParadigmMinimalToolset` (Comment 1).
2. Move all four prompts into a `prompts/` subfolder and restructure each with
   Identity / Goal / Environment / Instructions sections (Comment 2); add a
   "More Information" section to the context prompt explaining `ExtendOutputSchemaTool`
   (Comment 4).
3. Keep the `EnvironmentContext` dataclass to `summary`, `files`, and `notes`, while
   making `summary` and each file entry rich enough to carry subfields, connections,
   full file content, and model comments (Comment 3 and PR #219 review).
4. Add `ExtendOutputSchemaTool` — a third output-schema tool for mid-run schema
   extension.
5. Keep a `from_manager` bridge that maps context primitives into the same
   `summary` / `files` / `notes` shape without adding more top-level fields.
6. Make `EnvironmentContext.from_snapshot` fold any dynamic fields the agent declares
   into notes so the stable object shape remains narrow.
7. Destructure `ContextMinimalFanoutSettings` into per-role sub-configs so the
   `_build_planning_agent` call collapses to one line (Comment 5).

## Goals

- Resolve every comment the user left on PR #206 with no comment unaddressed.
- Give the context agent richer descriptions for the three stable output fields so
  downstream splitter and implementation agents receive a compact object with
  structured summary subfields, relevant files, and notes.
- Give the agent a visible, documented mechanism to extend its output schema mid-run
  when the prompt warrants fields the well-known set does not cover.
- Bridge the existing `vidbyte/context` stack (`ContextManager`, primitives,
  `Handoff`) into the paradigm without widening the public environment object.
- Collapse the 14-argument `_build_planning_agent` call into a one-liner by splitting
  the flat settings object into per-role sub-configs.

## Non-Goals

- Not changing the four-stage pipeline shape (context → split → adversarial →
  implement). The orchestration flow stays identical.
- Not adding tests or verification scripts (no-tests workflow).
- Not changing `SplitPrompt`, `PromptSplitPlan`, `ImplementationOutput`, or
  `ContextMinimalFanoutResult` — those contracts are stable.
- Not removing `OutputSchemaBuilder` or the existing `declare_output_schema` /
  `append_output` tools. `ExtendOutputSchemaTool` is additive.
- Not forcing `ContextManager` as the only build path. `from_snapshot` remains the
  primary builder used by the paradigm; `from_manager` is an alternative input bridge
  that still returns the same `summary` / `files` / `notes` contract.

## Background

### PR #206 review comments (5 total)

| # | File | Lines | Summary |
|---|------|-------|---------|
| 1 | `vidbyte/tools/toolsets/paradigm_minimal.py` | 46–60 | Add `TreeTool` (required) and `StatTool` (optional) to the minimal read-only toolset. `ListDirTool` only shows one level; `tree` returns the whole structure in one call. |
| 2 | `vidbyte/paradigms/context_minimal_fanout/adversarial_prompt.md` | 1–7 | Move all four prompts into a `prompts/` subfolder. Restructure each with Identity (6–8 sentences), Goal (6–8 sentences), Environment (8–10 sentences, "you are working inside of an agentic loop, you will have tools, you do not have to complete in 1 iteration, etc."), Instructions (numbered list, step-by-step high-level process). Reference the master prompt template's section anatomy. Apply to ALL four prompts. |
| 3 | `vidbyte/paradigms/context_minimal_fanout/types.py` | 57–95 | `EnvironmentContext` must be way more detailed. Keep `summary`, `files`, `notes`. Add more fields that add context to the environment the model is in (does not always have to be coding). |
| 4 | `vidbyte/paradigms/context_minimal_fanout/context_prompt.md` | 17 | Add a "More Information" section to the context prompt. Explain the `ExtendOutputSchemaTool` use case: "you should use this tool to extend ___. You should look at the user's prompt and think to yourself ___, then call ___". 8–9 sentences. |
| 5 | `vidbyte/paradigms/context_minimal_fanout/paradigm.py` | 89 | The `_build_planning_agent(...)` call with 14 positional args is sloppy. Destructure settings in the constructor into `context_settings`, `splitter_settings`, `adversarial_settings`, `implementation_settings`. Then the call can be 1 line importing only `planner_settings`. |

### Existing infrastructure that this work bridges to

**`vidbyte/context/manager.py` — `ContextManager`**: ordered collection + registry for
`ContextItem` primitives. Provides `add` / `extend` / `upsert` / `get_by_id` /
`remove_by_id`, placement (`place_after_system_prompt` / `place_after_tools`),
`render_primitives_zone()`, and `to_context()` (converts to `BaseContext`). This is
the builder/registry the paradigm's `EnvironmentContext` currently reinvents with
hand-rolled `from_snapshot` / `to_prompt_block`.

**`vidbyte/context/primitives/`**: typed frozen primitives implementing the
`ContextItem` protocol (`kind`, `title`, `metadata`, `to_context_text()`):
- `FileContextItem` — has `from_path()` classmethod, `path` / `absolute_path` /
  `size_bytes` / `content` / `language` / `excerpt`.
- `MemoryContextItem` — `content` / `source`.
- `DocumentContextItem` — `source` / `content` / `document_id`.
- `TextContextItem` — generic extension point: `title` / `content` / `kind`. This is
  the primitive for dynamic fields (`kind="command"`, `kind="hypothesis"`, etc.).
- `GitDiffContextItem`, `TaskContextItem`, `PlanContextItem`, `ProgressContextItem`,
  `ArtifactContextItem`, `ResponseContextItem`, `ToolCallContextItem`, plus reasoning
  primitives.

**`vidbyte/context/handoff/base.py` — `Handoff`**: sectioned document with
`default_sections()` (returns `{section_title: description}`) + `fill(sections)`.
Subclasses override `default_sections()` to define their shape:
- `ResearchHandoff` — Question, Findings, Sources, Confidence & Gaps, Recommended Next
  Queries.
- `EngineeringHandoff` — Objective, Changes Made, Verification Status, Open Threads,
  Risks & Gotchas, Next Steps.
- `MinimalHandoff`.

Each section ships with a multi-sentence description explaining what the agent should
put there — the "descriptions attached to each field so the model understands intent"
pattern.

**`vidbyte/tools/builtins/output_schema/builder.py` — `OutputSchemaBuilder`**: runtime
accumulator. `declare(fields)` registers fields additively (can be called more than
once). `append(field_name, value)` auto-declares unknown fields as `repeated=True`
(marks `_implicit=True`). `snapshot()` returns `{fields, values, implicit}`. The
auto-declaration path is the existing dynamic mechanism; `ExtendOutputSchemaTool`
makes it visible and documented.

**Master prompt template** (`vidbyte/prompts/prompts/templates/master.md`): defines a
prompt-section anatomy (Role/Persona, Objective/Mission, Context/Background,
Instructions, Workflow, etc.) with XML-tagged sections. Comment 2 asks for four
specific sections — Identity, Goal, Environment, Instructions — drawn from this
anatomy.

### BaseAgent constructor signature

`BaseAgent.__init__` (agents/base.py:55) takes keyword-only args: `name`,
`system_prompt`, `runner`, `tools`, `middleware`, `api_key`, `provider`, `model_name`,
`temperature`, `metadata`, `max_tokens`, plus `context_manager`, `output_schema`,
`handoff`, and others. The per-role settings sub-configs map directly to these kwargs.

## Requirements

### R1 — ParadigmMinimalToolset (Comment 1)

- Add `TreeTool(fs_config)` to the read-only tool list, after `ListDirTool`.
- Add `StatTool(fs_config)` to the read-only tool list, after `TreeTool`.
- Both are read-permission tools; no change to the write/execution gating.
- Import both from `vidbyte.tools.filesystem`.

### R2 — Prompt restructure (Comment 2 + Comment 4)

- Create `vidbyte/paradigms/context_minimal_fanout/prompts/` subfolder.
- Move all four prompt `.md` files into it:
  `context_prompt.md`, `split_prompt.md`, `adversarial_prompt.md`,
  `implementation_prompt.md`.
- Delete the four original prompt files from the package root.
- Update `prompts.py` `_read_asset` to read from the `prompts/` subfolder
  (`resources.files(__package__).joinpath("prompts", name)`).
- Restructure each prompt with these sections, in order, wrapped in XML tags:
  1. `<identity>` — 6–8 sentences. Who the agent is, its expertise, its stance.
  2. `<goal>` — 6–8 sentences. The durable aim, why it matters, what "done" means.
  3. `<environment>` — 8–10 sentences. The agentic-loop context: "you are working
     inside of an agentic loop, you will have tools, you do not have to complete in 1
     iteration, you can explore before committing, your transcript is compressed to
     structured output, etc."
  4. `<instructions>` — numbered list of step-by-step high-level process steps.
- For the **context prompt only**, add a fifth section:
  5. `<more_information>` — 8–9 sentences. Explains `ExtendOutputSchemaTool`: "You
     should use this tool to extend your output schema when the user's prompt has a
     shape the well-known fields do not cover. You should look at the user's prompt
     and think to yourself whether it warrants additional structured fields (e.g.
     hypotheses for a research question, migration steps for a refactor, reproduction
     steps for a bug), then call `extend_output_schema` to declare those fields before
     appending to them." Explain when to extend vs. when the well-known set suffices.
- Keep the output contract (declare_output_schema fields + append_output guidance)
  inside `<instructions>` or as a trailing section, adapted per prompt.

### R3 — EnvironmentContext extension (Comment 3)

- PR #219 review resolution supersedes the original field-widening plan below. The
  final `EnvironmentContext` remains exactly `summary`, `files`, and `notes`.
  `summary` is a structured `EnvironmentSummary` with subfields for overview,
  objective, domain, major details, connections, constraints, open questions, and
  additional domain-neutral details. `files` entries carry path, notes, full content
  when practical, and model comments. Any dynamic fields declared during a run are
  folded into notes rather than becoming new top-level object fields.

- Original plan, retained for historical context: Add well-known typed fields to
  `EnvironmentContext` beyond `summary` / `files` /
  `notes`. Each field is `tuple[str, ...]` (free-form text entries, rendered as bullet
  lists in `to_prompt_block`). `files` stays `tuple[ContextFile, ...]` (structured).
- New well-known fields:

| Field | Kind | Intent |
|-------|------|--------|
| `commands` | repeated | Verification/build/test/lint commands an implementer should run. Each entry: `{command, purpose}` or bare string. |
| `conventions` | repeated | Coding/work conventions that must be matched. e.g. "all dataclasses are frozen=True, slots=True". |
| `dependencies` | repeated | Libraries/frameworks/tools already in use. e.g. "uses pydantic v2", "asyncio-based". |
| `entry_points` | repeated | Public API surfaces / architectural landmarks. e.g. "vidbyte/__init__.py exports the public API". |
| `tests` | repeated | Test locations and patterns. e.g. "tests/ uses pytest, run with pytest -x". |
| `risks` | repeated | Fragile areas, gotchas, things that could break. e.g. "adding a field to BaseTool breaks serialized specs". |
| `constraints` | repeated | Hard rules that must not be violated. e.g. "Python 3.11+ only", "no new runtime deps". |
| `glossary` | repeated | Domain terms and their meanings. e.g. "paradigm: a top-level harness class that orchestrates agents". |
| `open_questions` | repeated | Ambiguities the context agent could not resolve. The splitter should account for these. |

- `entries: Mapping[str, Any]` stays as the catch-all preserving all raw snapshot
  values (including dynamic fields not in the well-known set).
- Update `from_snapshot` to map each well-known field from `snapshot["values"]`.
- Update `to_prompt_block` to render each well-known field as a tagged section, then
  render any dynamic fields from `entries` that are not well-known.

### R4 — ExtendOutputSchemaTool

- New tool class `ExtendOutputSchemaTool` in
  `vidbyte/tools/builtins/output_schema/extend.py`.
- Wraps `OutputSchemaBuilder.declare(fields)` — same mechanism as
  `DeclareOutputSchemaTool`, but documented as "add fields you discovered you need
  after the initial declaration."
- Tool name: `extend_output_schema`. Permission: `SAFE`.
- Parameters: `fields` (array of `{name, description, repeated}` objects, same shape
  as `declare_output_schema`).
- Can be called multiple times; each call registers fields additively.
- Export from `vidbyte.tools.builtins.output_schema`, `vidbyte.tools.builtins`, and
  top-level `vidbyte`.
- Wire into the paradigm's `_output_schema_tools` so all three tools
  (`declare_output_schema`, `extend_output_schema`, `append_output`) are bound to the
  same builder.

### R5 — ContextManager integration

- Add `manager: ContextManager | None = None` field to `EnvironmentContext`.
- Add `from_manager(cls, manager, *, fallback_text="")` classmethod that builds an
  `EnvironmentContext` from a `ContextManager`'s primitives, mapping by `kind`:
  - `FileContextItem` → `files` (convert to `ContextFile`).
  - `MemoryContextItem` → `notes`.
  - `TextContextItem` with `kind="command"` → `commands`, `kind="convention"` →
    `conventions`, etc. for each well-known field.
  - `TextContextItem` with an unknown `kind` → preserved in `entries`.
  - Summary falls back to `fallback_text` or a `TextContextItem` with
    `kind="summary"`.
- `from_snapshot` remains the primary builder (used by the paradigm). It does not
  build a `ContextManager`; `manager` stays `None` when built from a snapshot.
- `to_prompt_block` does not delegate to `manager.render_primitives_zone()` by
  default — it renders from typed fields + `entries` for output stability. Callers
  who want the `ContextManager` rendering can call `manager.render_primitives_zone()`
  directly.

### R6 — Dynamic schema support in from_snapshot / to_prompt_block

- `from_snapshot` maps well-known fields to typed access; `entries` preserves all raw
  values including dynamic fields the agent declared beyond the well-known set.
- `to_prompt_block` renders well-known sections first, then iterates over `entries`
  and renders any key not in the well-known set as a generic tagged section
  (`<{key}>...</{key}>`). This makes dynamic fields visible to downstream agents.
- Define a `_KNOWN_FIELDS` frozenset on `EnvironmentContext` to distinguish well-known
  from dynamic in `to_prompt_block`.

### R7 — Settings destructure (Comment 5)

- Add `AgentRoleSettings` frozen dataclass holding the per-role fields currently
  flat-prefixed on `ContextMinimalFanoutSettings`:
  `name`, `system_prompt`, `runner`, `provider`, `model_name`, `api_key`,
  `temperature`, `tools`, `middleware`, `agent_options`, `max_tokens`.
- Replace the flat per-role fields on `ContextMinimalFanoutSettings` with four
  `AgentRoleSettings` instances: `context`, `splitter`, `adversarial`,
  `implementation`.
- Keep `max_adversarial_rounds` on the top-level settings (it is a pipeline loop
  control, not an agent setting).
- Keep all shared toolset/fanout/budget fields on the top-level settings.
- Update `with_overrides` to handle the new nested shape.
- Collapse `_build_planning_agent` to take `(self, role_settings: AgentRoleSettings,
  role: str, builder: OutputSchemaBuilder, settings: ContextMinimalFanoutSettings)`.
  The call site becomes one line: `self._build_planning_agent(settings.splitter,
  "splitter", builder, settings)`.
- Update `_run_context_agent`, `_run_splitter`, `_run_adversarial_loop`,
  `_build_implementation_agent` to read from the nested sub-configs.
- This is a **breaking change** to `ContextMinimalFanoutSettings` construction. The
  PR is DRAFT and this is the PR's own settings class, so a clean break is acceptable.
  Callers who used `ContextMinimalFanoutSettings(context_agent_name="foo")` must now
  use `ContextMinimalFanoutSettings(context=AgentRoleSettings(name="foo"))`.

## High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ContextMinimalFanoutParadigm                     │
│                                                                     │
│  ContextMinimalFanoutSettings                                       │
│  ├── context: AgentRoleSettings                                     │
│  ├── splitter: AgentRoleSettings                                    │
│  ├── adversarial: AgentRoleSettings  (+ max_adversarial_rounds)     │
│  ├── implementation: AgentRoleSettings                              │
│  └── shared: toolset, fanout, budgets, paths                        │
│                                                                     │
│  Stage 1: _run_context_agent                                        │
│    tools = ParadigmMinimalToolset(+TreeTool+StatTool)               │
│          + context.tools                                            │
│          + (declare_output_schema, extend_output_schema,            │
│             append_output)  ← bound to OutputSchemaBuilder          │
│    → EnvironmentContext.from_snapshot(snapshot)                     │
│      (maps well-known fields + preserves dynamic in entries)        │
│                                                                     │
│  Stage 2: _run_splitter   → PromptSplitPlan                         │
│  Stage 3: _run_adversarial_loop (×max_rounds) → PromptSplitPlan     │
│    (each planning agent built via _build_planning_agent(            │
│       role_settings, role, builder, settings)  ← 1-line call)       │
│                                                                     │
│  Stage 4: _run_implementation_prompts (parallel, semaphore)         │
│    each agent gets environment.to_prompt_block()                    │
│      (renders well-known + dynamic fields)                          │
└─────────────────────────────────────────────────────────────────────┘

EnvironmentContext (extended)
├── summary: str
├── files: tuple[ContextFile, ...]
├── commands, conventions, dependencies, entry_points,
│   tests, risks, constraints, glossary, open_questions: tuple[str,...]
├── notes: tuple[str, ...]
├── entries: Mapping[str, Any]   ← preserves all raw snapshot values
├── manager: ContextManager | None  ← optional attached builder
├── from_snapshot(snapshot)      ← primary builder (paradigm path)
├── from_manager(manager)        ← alternative builder (primitive path)
└── to_prompt_block()            ← renders well-known + dynamic fields

OutputSchemaBuilder (unchanged) + 3 tools
├── declare_output_schema   ← initial schema declaration
├── extend_output_schema    ← NEW: mid-run additive extension
└── append_output           ← append/set values (auto-declares unknown)
```

## Detailed Design

### D1 — ParadigmMinimalToolset (R1)

File: `vidbyte/tools/toolsets/paradigm_minimal.py`

Add imports:
```python
from vidbyte.tools.filesystem import ListDirTool, ReadLinesTool, ReadTextTool, StatTool, TreeTool
```

Update `_build_tools`:
```python
def _build_tools(self) -> tuple[BaseTool, ...]:
    # Assembles the ordered tool instances for the configured root.
    fs_config = FileSystemToolConfig(root=self._root, allow_write=self._include_write)
    tools: list[BaseTool] = [
        GlobTool(root_dir=self._root),
        GrepTool(root_dir=self._root),
        ReadTextTool(fs_config),
        ReadLinesTool(fs_config),
        ListDirTool(fs_config),
        TreeTool(fs_config),
        StatTool(fs_config),
    ]
    if self._include_execution:
        tools.append(CodeExecutionTool())
    if self._include_write:
        tools.append(PatchTool(root_dir=self._root))
    return tuple(tools)
```

`TreeTool` returns a bounded recursive directory tree (default `max_depth=3`,
`max_entries=200`). `StatTool` returns JSON metadata (exists, is_file, is_dir, size,
modified_time). Both are `ToolPermission.READ`, so they fit the read-only toolset
without changing the write-gating logic.

### D2 — ExtendOutputSchemaTool (R4)

File: `vidbyte/tools/builtins/output_schema/extend.py`

```python
class ExtendOutputSchemaTool(BaseTool):
    """Builtin tool that adds fields to the output schema after the initial declaration."""

    def __init__(self, builder: OutputSchemaBuilder) -> None:
        # Stores the shared builder that also backs the paired declare/append tools.
        self._builder = builder

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for extending the output schema mid-run.
        return ToolSpec(
            name="extend_output_schema",
            description=(
                "Add additional output fields to the schema after the initial "
                "declare_output_schema call. Use when you discover mid-run that "
                "the request warrants fields you did not declare upfront (e.g. "
                "hypotheses for a research question, migration_steps for a "
                "refactor, reproduction_steps for a bug). Fields are added "
                "additively; existing fields are not affected. Can be called "
                "multiple times."
            ),
            parameters=(
                ToolParameter(
                    name="fields",
                    type="array",
                    description=(
                        "List of field objects, each: {name, description, repeated}. "
                        "May be passed as a JSON array or a JSON string."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Register the additional fields on the shared builder.
        fields = DeclareOutputSchemaTool._normalize_fields(call.arguments.get("fields"))
        if not fields:
            return ToolResult.error(call.tool_name, "No valid fields were provided to extend.")
        declared = self._builder.declare(fields)
        return ToolResult.success(call.tool_name, f"Extended output schema with fields: {', '.join(declared)}.")
```

Reuses `DeclareOutputSchemaTool._normalize_fields` for the same input normalization
(JSON string, single field, or list). Calls `builder.declare(fields)` which registers
additively — no new method needed on `OutputSchemaBuilder`.

Export from `vidbyte/tools/builtins/output_schema/__init__.py`,
`vidbyte/tools/builtins/__init__.py`, and `vidbyte/__init__.py`.

### D3 — EnvironmentContext extension (R3 + R5 + R6)

File: `vidbyte/paradigms/context_minimal_fanout/types.py`

Extended `EnvironmentContext`:

```python
_KNOWN_FIELDS: frozenset[str] = frozenset({
    "summary", "files", "commands", "conventions", "dependencies",
    "entry_points", "tests", "risks", "constraints", "glossary",
    "open_questions", "notes",
})

@dataclass(frozen=True, slots=True)
class EnvironmentContext:
    """Compressed structured context extracted by the context agent."""

    summary: str
    files: tuple[ContextFile, ...] = ()
    commands: tuple[str, ...] = ()
    conventions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    glossary: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    entries: Mapping[str, Any] = field(default_factory=dict)
    manager: "ContextManager | None" = None
```

`__post_init__` normalizes each new field via `_text_tuple` (or a new
`_entry_tuple` that renders mappings as readable strings: `{"command": "pytest",
"purpose": "run tests"}` → `"command: pytest — purpose: run tests"`). `manager` is
stored as-is (mutable reference inside a frozen dataclass is fine).

`from_snapshot` maps each well-known field from `snapshot["values"]`. `files` uses
`ContextFile.from_value`; all text fields use `_entry_tuple`. `entries` preserves the
full raw `values` dict. `manager` stays `None`.

`from_manager` maps `ContextItem` primitives by `kind` to typed fields. `FileContextItem`
→ `files` (convert path/notes). `MemoryContextItem` → `notes`. `TextContextItem` with
`kind="command"` → `commands`, `kind="convention"` → `conventions`, etc.
`TextContextItem` with an unknown `kind` → preserved in `entries`. `manager` is set to
the passed-in `ContextManager`.

`to_prompt_block` renders well-known sections in order (`<summary>`, `<files>`,
`<commands>`, ..., `<notes>`), then iterates over `entries` and renders any key not in
`_KNOWN_FIELDS` as a generic tagged section. Uses private helper methods
(`_render_text_section`, `_render_files_section`, `_render_dynamic_sections`) to keep
the method readable.

### D4 — AgentRoleSettings + settings destructure (R7)

File: `vidbyte/paradigms/context_minimal_fanout/types.py`

New dataclass:

```python
@dataclass(frozen=True, slots=True)
class AgentRoleSettings:
    """Per-role configuration for one pipeline stage agent."""

    name: str = ""
    system_prompt: str | None = None
    runner: object | None = None
    provider: str | None = None
    model_name: str | Sequence[str] | None = None
    api_key: str | None = None
    temperature: float | None = None
    tools: tuple[object, ...] = ()
    middleware: tuple[object, ...] = ()
    agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        # Normalizes tuple and mapping fields.
        object.__setattr__(self, "tools", _object_tuple(self.tools))
        object.__setattr__(self, "middleware", _object_tuple(self.middleware))
        object.__setattr__(self, "agent_options", dict(self.agent_options))

    def with_overrides(self, **overrides: Any) -> "AgentRoleSettings":
        # Returns a new settings object with per-run overrides applied.
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)
```

Restructured `ContextMinimalFanoutSettings`:

```python
@dataclass(frozen=True, slots=True)
class ContextMinimalFanoutSettings:
    """Per-role configuration for the four-stage context-minimal fanout pipeline."""

    context: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-context"))
    splitter: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-splitter"))
    adversarial: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-adversarial"))
    implementation: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="context-minimal-implementation"))

    max_adversarial_rounds: int = 2

    include_minimal_toolset: bool = True
    default_tool_root: str | Path = "."
    include_execution_tool: bool = True
    implementation_include_write: bool = True

    max_prompt_count: int = 8
    max_concurrency: int = 4
    max_cost_usd: float | None = None
    cost_per_million_tokens: float | None = None
    return_exceptions: bool = True
    plan_output_path: str | Path | None = None
```

`__post_init__` validates numeric limits and normalizes the shared fields. The
per-role `AgentRoleSettings.__post_init__` handles tuple/map normalization.

`with_overrides` filters None values and calls `replace`. For role-level overrides,
callers pass a full `AgentRoleSettings`: `settings.with_overrides(splitter=...)`.

### D5 — Paradigm orchestration updates (R7 + R4)

File: `vidbyte/paradigms/context_minimal_fanout/paradigm.py`

`_output_schema_tools` now returns three tools:
```python
def _output_schema_tools(self, builder: OutputSchemaBuilder) -> tuple[object, ...]:
    # Binds the declare/extend/append output-schema tools to a run-local builder.
    return (DeclareOutputSchemaTool(builder), ExtendOutputSchemaTool(builder), AppendOutputTool(builder))
```

`_build_planning_agent` collapses to:
```python
def _build_planning_agent(self, role_settings: AgentRoleSettings, role: str, builder: OutputSchemaBuilder, settings: ContextMinimalFanoutSettings) -> BaseAgent:
    # Constructs a splitter/adversarial planning agent with output-schema tools.
    tools = (*self._read_only_toolset(settings), *role_settings.tools, *self._output_schema_tools(builder))
    middleware = self._with_budget_middleware(role_settings.middleware, role_settings.max_tokens, settings)
    return BaseAgent(
        name=role_settings.name,
        system_prompt=role_settings.system_prompt or self._prompts.for_role(role),
        runner=role_settings.runner,
        tools=tools,
        middleware=middleware,
        api_key=role_settings.api_key,
        provider=role_settings.provider,
        model_name=role_settings.model_name,
        temperature=role_settings.temperature,
        metadata={"role": role},
        **dict(role_settings.agent_options),
    )
```

Call sites:
```python
# _run_splitter
agent = self._build_planning_agent(settings.splitter, "splitter", builder, settings)

# _run_adversarial_loop
agent = self._build_planning_agent(settings.adversarial, "adversarial", builder, settings)
```

`_run_context_agent` reads from `settings.context` (name, system_prompt, runner,
provider, etc.). `_build_implementation_agent` reads from `settings.implementation`
(name_prefix → name, system_prompt, runner, etc.).

`prompts.py` gains a `for_role(role: str) -> str` method that dispatches to the right
prompt asset, replacing the four separate methods. The asset paths update to
`prompts/{name}`.

### D6 — Prompt restructure (R2)

Files: `vidbyte/paradigms/context_minimal_fanout/prompts/` (new subfolder)

Each prompt is restructured into four XML-tagged sections:

```markdown
<identity>
(6–8 sentences: who the agent is, its expertise, its stance.)
</identity>

<goal>
(6–8 sentences: the durable aim, why it matters, what "done" means.)
</goal>

<environment>
(8–10 sentences: the agentic-loop context — you are working inside of an agentic
loop, you will have tools, you do not have to complete in 1 iteration, you can
explore before committing, your transcript is compressed to structured output,
etc.)
</environment>

<instructions>
1. (step 1)
2. (step 2)
3. (step 3)
...
</instructions>
```

Context prompt adds a fifth section:

```markdown
<more_information>
(8–9 sentences: explains ExtendOutputSchemaTool — when to extend the schema vs.
when the well-known set suffices, how to decide what additional fields a prompt
warrants, and the call sequence: think → extend_output_schema → append_output.)
</more_information>
```

The output contract (declare_output_schema fields + append_output guidance) is folded
into `<instructions>` as the final steps, adapted per prompt.

## Data Model Changes

### `EnvironmentContext` (modified)

New fields: `commands`, `conventions`, `dependencies`, `entry_points`, `tests`,
`risks`, `constraints`, `glossary`, `open_questions` (all `tuple[str, ...]`), plus
`manager: ContextManager | None = None`. `entries` and `summary` and `files` and
`notes` unchanged in type.

### `AgentRoleSettings` (new)

Frozen dataclass with 11 fields: `name`, `system_prompt`, `runner`, `provider`,
`model_name`, `api_key`, `temperature`, `tools`, `middleware`, `agent_options`,
`max_tokens`.

### `ContextMinimalFanoutSettings` (modified — breaking)

Flat per-role fields (`context_agent_name`, `context_system_prompt`, ...,
`implementation_agent_options`, `max_implementation_tokens`) replaced by four
`AgentRoleSettings` instances. Shared fields unchanged. `max_adversarial_rounds` moves
from being grouped with adversarial fields to a top-level pipeline control field
(same value, same default).

### `ExtendOutputSchemaTool` (new)

Tool class with `name="extend_output_schema"`, `permission=SAFE`, one required
`fields` array parameter. No dataclass; it is a `BaseTool` subclass.

## API Changes

### New public exports

- `ExtendOutputSchemaTool` — from `vidbyte`, `vidbyte.tools.builtins`,
  `vidbyte.tools.builtins.output_schema`.
- `AgentRoleSettings` — from `vidbyte`, `vidbyte.paradigms`,
  `vidbyte.paradigms.context_minimal_fanout`.

### Breaking changes

- `ContextMinimalFanoutSettings` construction changes from flat prefixed fields to
  nested `AgentRoleSettings`. Old: `ContextMinimalFanoutSettings(context_agent_name="x")`.
  New: `ContextMinimalFanoutSettings(context=AgentRoleSettings(name="x"))`.
- `ContextMinimalFanoutPrompts` method names change: `context()` / `splitter()` /
  `adversarial()` / `implementation()` → `for_role(role)` with a single dispatch.
  (Old methods can be kept as thin aliases if desired, but the clean break is
  preferred since the PR is DRAFT.)
- The four prompt `.md` files move from the package root to `prompts/`. Any caller
  reading them by path must update. (No known external callers; `prompts.py` is the
  only reader.)

## File Change Manifest

### Files to CREATE (7)

1. `vidbyte/tools/builtins/output_schema/extend.py` — `ExtendOutputSchemaTool` class.
2. `vidbyte/paradigms/context_minimal_fanout/prompts/__init__.py` — package marker.
3. `vidbyte/paradigms/context_minimal_fanout/prompts/context_prompt.md` — restructured context agent prompt (Identity, Goal, Environment, Instructions, More Information).
4. `vidbyte/paradigms/context_minimal_fanout/prompts/split_prompt.md` — restructured splitter prompt (Identity, Goal, Environment, Instructions).
5. `vidbyte/paradigms/context_minimal_fanout/prompts/adversarial_prompt.md` — restructured adversarial prompt (Identity, Goal, Environment, Instructions).
6. `vidbyte/paradigms/context_minimal_fanout/prompts/implementation_prompt.md` — restructured implementation prompt (Identity, Goal, Environment, Instructions).
7. `docs/design/cmf-paradigm-pr-206-comments.md` — this design doc.

### Files to MODIFY (9)

1. `vidbyte/tools/builtins/output_schema/__init__.py` — export `ExtendOutputSchemaTool`.
2. `vidbyte/tools/builtins/__init__.py` — export `ExtendOutputSchemaTool`.
3. `vidbyte/__init__.py` — export `ExtendOutputSchemaTool` and `AgentRoleSettings`.
4. `vidbyte/tools/toolsets/paradigm_minimal.py` — add `TreeTool` + `StatTool` to `_build_tools`.
5. `vidbyte/paradigms/context_minimal_fanout/types.py` — extend `EnvironmentContext`, add `AgentRoleSettings`, restructure `ContextMinimalFanoutSettings`, add `_entry_tuple` / `_KNOWN_FIELDS`.
6. `vidbyte/paradigms/context_minimal_fanout/paradigm.py` — use per-role settings, add `ExtendOutputSchemaTool` to `_output_schema_tools`, collapse `_build_planning_agent`, update `_run_context_agent` / `_run_splitter` / `_run_adversarial_loop` / `_build_implementation_agent`.
7. `vidbyte/paradigms/context_minimal_fanout/prompts.py` — update asset paths to `prompts/` subfolder, replace four methods with `for_role(role)`.
8. `vidbyte/paradigms/context_minimal_fanout/__init__.py` — export `AgentRoleSettings`.
9. `vidbyte/paradigms/__init__.py` — export `AgentRoleSettings`.

### Files to DELETE (4)

1. `vidbyte/paradigms/context_minimal_fanout/context_prompt.md` — moved to `prompts/`.
2. `vidbyte/paradigms/context_minimal_fanout/split_prompt.md` — moved to `prompts/`.
3. `vidbyte/paradigms/context_minimal_fanout/adversarial_prompt.md` — moved to `prompts/`.
4. `vidbyte/paradigms/context_minimal_fanout/implementation_prompt.md` — moved to `prompts/`.

**Totals: 7 create, 9 modify, 4 delete.**

## Dependencies

- No new third-party dependencies.
- Uses existing `vidbyte.context.ContextManager`, `vidbyte.context.primitives.*`,
  `vidbyte.tools.filesystem.TreeTool` / `StatTool`, `vidbyte.tools.base.BaseTool`,
  `vidbyte.tools.types.*` — all already in the codebase.

## Rollout

- Implement on a fresh worktree branch `feat/cmf-paradigm-pr-206-comments` off `main`.
- Commit the design doc first.
- Implement workstreams D1–D6 as separate atomic commits in dependency order:
  1. `feat(tools): add ExtendOutputSchemaTool` (D2)
  2. `feat(tools): add TreeTool and StatTool to ParadigmMinimalToolset` (D1)
  3. `feat(paradigms): extend EnvironmentContext with well-known fields and dynamic schema support` (D3)
  4. `refactor(paradigms): destructure ContextMinimalFanoutSettings into per-role sub-configs` (D4)
  5. `refactor(paradigms): collapse _build_planning_agent and wire ExtendOutputSchemaTool` (D5)
  6. `docs(paradigms): restructure context-minimal-fanout prompts into prompts/ subfolder` (D6)
- Open a draft PR against `main`.
- PR #206 stays open; this PR supersedes the relevant parts. After merge, PR #206 can
  be closed or the branch rebased.

## Open Questions

1. **`from_manager` kind mapping for non-coding contexts.** The well-known fields
   (`commands`, `conventions`, etc.) are coding-leaning. For a research prompt, the
   agent might declare `hypotheses`, `experiments`, `bad_ideas`. These land in
   `entries` and render dynamically via `to_prompt_block`. Should we also provide a
   `ResearchEnvironmentContext` subclass with research-flavored well-known fields, or
   is the dynamic-field mechanism sufficient? **Recommendation:** dynamic fields are
   sufficient for now; a subclass can be added later if a pattern emerges.

2. **`_entry_tuple` rendering of mappings.** When the agent appends a JSON object like
   `{"command": "pytest", "purpose": "run tests"}` to a text field, how should it
   render in `to_prompt_block`? Current plan: `"command: pytest — purpose: run tests"`.
   Alternative: keep the JSON as-is and let the model parse it. **Recommendation:**
   render as readable strings for prompt-block readability; preserve the raw object in
   `entries` for programmatic access.

3. **`ContextMinimalFanoutPrompts` backward-compat aliases.** Should the old
   `context()` / `splitter()` / `adversarial()` / `implementation()` methods stay as
   thin aliases wrapping `for_role`, or be removed cleanly? **Recommendation:** remove
   cleanly — the PR is DRAFT and `prompts.py` is internal.

4. **Should `from_snapshot` also build and attach a `ContextManager`?** Currently
   planned: `manager` stays `None` when built from a snapshot. Alternative: build a
   `ContextManager` populated with `TextContextItem` / `FileContextItem` primitives
   derived from the snapshot, so callers always have both paths. **Recommendation:**
   keep `manager=None` from `from_snapshot` — the typed fields + `entries` already
   carry everything; attaching a `ContextManager` is the caller's choice via
   `from_manager`.

## Alternatives Considered

### A1 — Replace `EnvironmentContext` entirely with `ContextManager` + primitives

**Rejected.** The typed dataclass gives direct attribute access (`env.files`,
`env.commands`) and a stable prompt-block rendering. `ContextManager` is a
builder/registry, not a typed contract. Both coexist: `EnvironmentContext` for typed
access and prompt rendering, `ContextManager` as an optional attached builder for
callers who want placement, registry addressing, and `BaseContext` conversion.

### A2 — Add an `add_field` method to `OutputSchemaBuilder` instead of a new tool

**Rejected.** `builder.declare()` already works additively (can be called multiple
times). But the agent-facing surface needs a visible, documented tool —
`declare_output_schema` says "call this once before append_output," which signals
one-shot. A separate `extend_output_schema` tool with clear documentation ("add fields
you discovered you need mid-run") makes the capability discoverable. The builder needs
no new method; the tool wraps the existing `declare()`.

### A3 — Keep flat settings and just pass a dict to `_build_planning_agent`

**Rejected.** The comment explicitly asks for per-role sub-configs destructured in the
constructor, not a dict passthrough. `AgentRoleSettings` gives typed access, validation,
and `with_overrides` per role.

### A4 — Dynamic fields via a `Handoff` subclass per prompt type

**Considered.** `Handoff.default_sections()` + `fill()` is the existing dynamic-section
mechanism, and `ResearchHandoff` already has research-flavored sections. However,
`Handoff` is a sectioned document (string values per section), while
`EnvironmentContext` needs typed tuple fields + a catch-all `entries` dict + a
`ContextFile` sub-type. The `Handoff` pattern is referenced in the "More Information"
prompt section as guidance for the agent, but the dataclass stays as
`EnvironmentContext` with dynamic-field support via `entries` + `to_prompt_block`
iteration. `from_manager` bridges to the `ContextManager`/primitive stack for callers
who want that path.

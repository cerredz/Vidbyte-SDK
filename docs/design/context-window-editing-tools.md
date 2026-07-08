# Design Doc: Context Window Editing Tools (per-primitive create family + manager editing surface)

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Give agents a first-class toolkit to engineer their own context window, backed by the SDK's existing `ContextManager` registry and the typed primitives in `vidbyte/context/primitives/`. The centerpiece is a **family of per-primitive creation tools** (one tool per context-window primitive, e.g. `context_create_plan`, `context_create_document`) stamped out from a single declarative registry keyed by primitive "keys" — replacing the flattened, 6-type `ContextUpsertTool` string interface with typed, schema-accurate tool definitions. Around that family, the design adds the small `ContextManager` API extensions and supporting tools (view, stats, edit, move) needed for genuine agent-driven context editing, plus a factory helper so developers can mount the whole family with one call.

---

## 2. Original User Prompts

**Prompt 1:**

> explain to me what this does in the vidbyte-sdk/vidbyte/agent/ base agent class:   8. Context engineering
>
>   BaseAgent(...,
>       context_items=[policy_doc, style_guide],   # standing context
>   injected each run
>       context_manager=ctx_mgr,                    # dynamic context
>   store (handoffs upsert here)
>       algorithm="default",                        #
>   in-context-learning algorithm selection
>   )
>
>   Per-call context items (AgentInput.context_items) are merged with
>   the agent-level ones, not replaced.. Like what does attaching this to the agent do, look at code and then give me description in plain english

**Prompt 2:**

> and can the agent edit the context items that I provide it and also like update the context items itself during the run? (for agent editing, do we have tools to do this inside of vidbyte/tools?)

**Prompt 3:**

> great, so I actually had an idea, The idea was basically that we Give the agent tools to manipulate and edit its own context window and then to actually link those tools with our vidbyte SDK context folder primitive. Is this possible? If so how do we do it? Also can you try to just sketch out some tools that we can give the agent to edit its own context window?

**Prompt 4:**

> great, I want you to add two things to a design doc for us to implement: 1) I want you to add the code implementation details that we need to actually implement these context window tools with the context manager, and 2) I want you to propose the implementation details of our first context window tool: CreateContextWindowPrimitive -> basically what this tool should do is be synced with Vidbyte Sdk's context window primitive, have 'keys' for the context window primitives that we offer, and then when the agent calls this tool is has to insert the key id that it wants to create and then basically it gives the agent to ability to create a context window primitive from the vidbyte sdk and insert it into the agent's context window. Actually before you create the design doc, what do you think is better, having one central tool for this, or having 1 tool per context window primitive? I was actually thinking one tool per primitive because each primitive will have different arguments, what do you think?

---

## 3. Structured Conversation Notes

### Key Decisions

1. **One tool per primitive, not one central tool.** The user asked which was better and leaned per-primitive; Claude agreed and the user confirmed by proceeding. Reasons: (a) primitives have genuinely different fields (`PlanContextItem.steps: tuple[str]` vs `TaskContextItem.goal/status/next_steps` vs `DocumentContextItem.source/content`), and a single tool with a `key` parameter cannot express "if key=plan then steps is required" in JSON Schema — validation would move into runtime error messages and burn agent iterations; (b) models call typed, narrowly-named tools (`context_create_plan` with a `steps` array) more accurately than a mega-tool; (c) per-tool granularity gives free per-primitive permissioning (mount only the tools you want the agent to have).
2. **The per-primitive tools are generated from one declarative registry, not hand-written as N classes.** The user's original "CreateContextWindowPrimitive with keys" concept survives as the *registry*: a table mapping `key → (primitive class, tool name, JSON schema, builder function)`. One generic `BaseTool` subclass is instantiated once per registry row. Adding a new primitive's tool = adding one registry row. This avoids ~10 near-identical tool classes while keeping per-primitive schemas.
3. **A factory helper (`context_window_tools(manager, include=...)`) mounts the family.** Developers should not hand-construct 10+ tool instances; the factory takes the live `ContextManager`, an optional `include` of keys, and returns the tool instances (create family + management tools).
4. **Linkage mechanism is Python object identity on `ContextManager`.** Tools receive the manager in `__init__` (never in `execute()` — house rule from `skills/vidbyte-sdk/context-algorithm-to-tool.md`). The runtime re-renders the primitives zone from the same manager instance every loop iteration (`vidbyte/agents/runtime.py:1206`, `_build_system_string`), so a tool-call mutation is visible to the model on its next iteration with zero extra plumbing.
5. **Placement is a first-class parameter on every create tool.** `ContextWindowPlacement` (`vidbyte/context/runtime.py`) already supports `top_of_context`, `end_of_context`, `top_of_conversation`, `end_of_conversation`; the existing `ContextUpsertTool` ignores it entirely. Create tools accept an optional `placement` string defaulting to `end_of_context`.
6. **Small `ContextManager` API additions** rather than tool-side registry poking: `set_placement(primitive_id, placement)` and `set_frozen(primitive_id, frozen)` (implemented via `dataclasses.replace` since primitives are frozen dataclasses). Also a public read surface (e.g. `registry_items() -> tuple[tuple[str, ContextItem], ...]`) so tools stop reading the private `_registry` (the existing `ContextListTool` reads `self._manager._registry` directly — a precedent to clean up, not extend).
7. **Frozen semantics get enforced at the tool boundary.** Today `ContextManager.upsert` refuses to overwrite a `primitive_frozen=True` primitive (`manager.py:71`), but `ContextRemoveTool` deletes frozen primitives without checking (`remove.py:55`). Decision: the *tools* refuse to remove/edit/move frozen primitives; the developer-facing Python API (`remove_by_id`) keeps full authority. Convention established: `primitive_frozen=True` = developer-owned, invisible to agent mutation.
8. **The agent-editable zone is the manager registry only.** Standing `BaseAgent(context_items=...)` (stored as a tuple at `base.py:179`, re-merged every run at `base.py:882`), conversation history, and tool-call transcripts remain outside agent reach by design — the agent curates its workspace, it cannot rewrite the record or the developer's standing contract. If a developer wants the agent to edit a document they provide, they seed it as a managed primitive (`ctx_mgr.upsert(DocumentContextItem(primitive_id=...))`) instead of `context_items=`.

### Rejected Alternatives

- **One central `CreateContextWindowPrimitive` tool with a `key` argument** (the user's initial framing). Rejected because JSON Schema for a single tool cannot make fields conditionally required per key; every field becomes optional-and-stringly, reproducing the flattening problem of the existing `ContextUpsertTool` (which fakes plan steps by newline-splitting a `content` string, `upsert.py:127`). The "keys" idea is retained as the internal registry keys and tool-name suffixes.
- **N hand-written tool classes (one file/class per primitive).** Rejected: ~10 near-identical ~60-line classes, and every future primitive needs a new class. The registry + generic-class approach keeps it to one row per primitive.
- **Letting agents edit `context_items` / history.** Explicitly out of scope; see Key Decision 8.

### Constraints & Assumptions

- **Single manager instance everywhere.** The design only works if the same `ContextManager` object is passed to `BaseAgent(context_manager=...)` and to every tool constructor. `BaseAgent._runtime()` (`base.py:730`) forwards the agent-level manager to the runtime; managed primitives inside a *per-call* `AgentInput.context_manager` never reach the primitives zone (`_merged_context_manager` at `base.py:885` copies only unmanaged `.items()`). Docs for the factory must state this.
- **Primitives are `@dataclass(frozen=True, slots=True)`.** All mutation is `dataclasses.replace(...)` + re-upsert.
- **Flat `ToolParameter` schemas cannot express arrays with `items`.** `ToolsFormatter._parameters_schema` (`vidbyte/lib/tools/formatter.py:313`) maps a parameter's `type` string via `_json_type` (supports `array`/`list`) but emits **no `items` key**, which some providers (OpenAI strict mode) reject. However `ToolSpec.input_schema: Mapping | None` **overrides** the flat parameters entirely (`_schema_for_spec`, `formatter.py:249-253`), and `CreateHandoffTool` (`vidbyte/tools/builtins/handoff/create.py:156`) already ships a full hand-written JSON Schema this way. **Constraint: every registry row supplies a complete `input_schema` (with `items` for arrays), and also a matching flat `parameters` tuple so `BaseTool.validate_call` (which checks `spec.required_parameter_names()`) and `to_prompt_str()` keep working.**
- The runtime auto-creates a `ContextManager` when an inner-loop algorithm is configured and none was passed (`runtime.py:165-166`); the tools cannot rely on that instance — the factory requires an explicit manager.
- Non-linear runtimes (MCTS, actor) don't render the primitives zone the same way; this feature targets the **linear runtime** (same constraint as `algorithm=` presets, enforced in `base.py:123-129`).
- Inner-loop algorithms (`trajectory_checkpoints`, `problem_space_search`, `error_correction`) write to the same manager. Namespace convention to avoid collisions: algorithm-minted ids keep their existing forms; agent tools should not silently overwrite ids they didn't create unless the model explicitly reuses an id (upsert-by-id is intentional overwrite semantics — document it in tool descriptions).

### Clarifications & Answers

- **Q (user):** Can the agent edit the `context_items` I provide? **A:** No — they're an immutable tuple re-injected each run; no tool touches them. Only manager-registry primitives are editable, via tools you attach.
- **Q (user):** Do tools for this already exist in `vidbyte/tools`? **A:** Yes, three: `ContextUpsertTool` (6 types, generic `content` string, no placement), `ContextListTool`, `ContextRemoveTool` — in `vidbyte/tools/builtins/context_primitives/`. They are not auto-attached (only `IsDoneTool` is, via `with_internal_agent_tools`, `tools/_internal.py:36`).
- **Q (user):** One central tool or one per primitive? **A (agreed):** One per primitive, generated from a declarative registry, with a factory. See Key Decisions 1–3.

### Terminology / Glossary

- **Primitive / context window primitive:** a frozen dataclass in `vidbyte/context/primitives/` satisfying the `ContextItem` protocol (`kind`, `title`, `metadata`, `to_context_text()`, plus `primitive_id`, `primitive_frozen` on all concrete types).
- **Managed primitive:** a primitive stored in `ContextManager._registry` under its `primitive_id`; rendered in the "## Context Window Primitives" zone; addressable/updatable.
- **Unmanaged item:** a primitive in `ContextManager.context_items` (or `BaseAgent.context_items`); rendered in the context body; not addressable.
- **Key:** the registry key naming a primitive type in the create-tool registry (`"plan"`, `"document"`, ...). Becomes the tool-name suffix (`context_create_plan`).
- **Placement:** `ContextWindowPlacement` enum value controlling where a managed primitive renders (top/end of the system-string context zone, or top/end of conversation as assistant messages).
- **Primitives zone:** the `## Context Window Primitives` section rendered by `ContextManager.render_primitives_zone()` into the system string between the fixed header and the context body (`runtime.py:1201-1209`).
- **Frozen:** `primitive_frozen=True`; developer-owned, must be immune to agent-tool overwrite, removal, edit, and move.

### Implementation Hints for the Downstream Model

- **Home for new code:** `vidbyte/tools/builtins/context_primitives/` (new modules: `registry.py`, `create.py`, `factory.py`, plus later `view.py`, `stats.py`, `edit.py`, `move.py`). Manager changes go in `vidbyte/context/manager.py`. Placement enum is in `vidbyte/context/runtime.py` — import it lazily or under `TYPE_CHECKING` matching existing patterns.
- **Every module in this repo starts with a "Context Protocol Header" docstring** (Description / Purpose / Architecture / Relations). Copy the shape from `upsert.py`. Skill/lint tooling checks for it.
- **Pattern to imitate for the tool class:** `ContextUpsertTool` (`upsert.py`) — constructor-injected manager, `spec()` returning `ToolSpec`, `async execute(call) -> ToolResult`, `ToolResult.error(...)` for validation failures, `ToolPermission.SAFE`.
- **Pattern to imitate for `input_schema`:** `CreateHandoffTool.spec()` (`vidbyte/tools/builtins/handoff/create.py`) — full JSON Schema in `input_schema`, and note it also demonstrates `binds_to_primitive`.
- **Existing related machinery — do not duplicate it:** `ToolSpec.binds_to_primitive` + `AgentRuntime._apply_primitive_binding` (`runtime.py:1346-1374`) already routes any tool's *output* into a `TextContextItem` primitive. That is output-capture; this feature is agent-initiated creation. Mention the distinction in the README/skill docs but don't touch that code path.
- **Exports:** new public names go in `vidbyte/tools/builtins/context_primitives/__init__.py`, and follow the existing `ContextUpsertTool` precedent into `vidbyte/__init__.py` (it appears there at lines ~152 and ~292). Manager methods need no new exports.
- **Tests:** follow `tests/test_context_primitives_builtins.py` — `unittest.IsolatedAsyncioTestCase`, construct a bare `ContextManager`, call `await tool.execute(ToolCall(tool_name=..., arguments={...}))`, assert on `result.output` and manager state. No model in the loop. Add registry-integrity tests (every key builds a primitive; every `input_schema` marks the same names required as the flat `parameters` tuple; tool names unique).
- **Verification commands** (from `skills/vidbyte-sdk/context-primitives.md`): `python -m compileall vidbyte` and `python -m unittest tests.test_context_management tests.test_context_primitives_builtins tests.test_context_primitives_registry` (plus new test modules).
- **Docs to update:** `skills/vidbyte-sdk/context-primitives.md` ("Model-Callable Context Tools" section) and the `vidbyte/tools` README if it lists builtins.
- **Branch off `origin/main`** — local `main` in these repos is frequently stale.
- **Gotcha:** `ContextManager.upsert()` raises `ValueError` on frozen conflicts — catch and convert to `ToolResult.error` (the existing upsert tool at `upsert.py:94-97` shows this).
- **Gotcha:** `ContextListTool` reads `self._manager._registry` (private). When adding `registry_items()` to the manager, migrate the list tool to it in the same PR.
- **Naming:** tool names are snake_case verbs in the existing family (`context_upsert`, `context_list`, `context_remove`) — the create family follows as `context_create_<key>`.

### Open Questions

1. **Which primitives get create tools?** Proposed include-set: `text`, `document`, `memory`, `plan`, `task`, `progress`, `artifact`, `environment`, `git_diff`. Proposed exclude: `response`, `tool_call` (records of events — agents fabricating these is misleading), `reflexion` / `trajectory_checkpoint` / `error_correction` / `problem_space_search` (algorithm-owned), and `file` (reads from disk at construction/render — needs a path-permission story first; see Q2). The implementer/user should confirm this set.
2. **`context_create_file`:** `FileContextItem.from_path` reads the filesystem, and `BaseContext._build_file_context` re-reads listed paths at render time. Powerful (self-refreshing live file context) but it is a read-anything primitive. Defer to a follow-up gated on `PermissionPolicy` / a path allowlist? (Recommended: defer.)
3. **Fate of `ContextUpsertTool`:** keep as-is for backward compatibility, or deprecate in favor of the create family? (Recommended: keep, note as legacy in docs; do not break existing users/tests.)
4. **Registry size guardrail:** should the manager or tools cap primitive count / total rendered chars and return a "compact first" error? Not required for v1, but the seam (a check inside the generic create tool's `execute`) should be noted in code comments.
5. **Should `set_frozen` exist at all in v1?** It's needed for a future `context_freeze` tool, but no v1 tool calls it. Could be dropped from scope if the implementer wants the smallest diff (keep `set_placement` — the move tool needs it).

---

## 4. Goals & Non-Goals

### Goals

- A declarative primitive-tool registry mapping key → primitive class, tool name, description, full JSON `input_schema`, flat `parameters`, and builder function.
- One generic `CreateContextPrimitiveTool(BaseTool)` class instantiated per registry row, producing per-primitive tools (`context_create_plan`, `context_create_document`, ...), each with `primitive_id` (required), typed per-primitive fields, and optional `placement` + `title`.
- A `context_window_tools(manager, *, include=None, management=True)` factory returning ready-to-mount tool instances.
- `ContextManager` additions: `set_placement`, `set_frozen` (see Open Q5), `registry_items()` public read surface.
- Frozen-primitive protection at the tool boundary (create/overwrite already protected via `upsert`; add the check to `ContextRemoveTool`).
- Supporting management tools to complete the editing loop: `context_view` (full text of one primitive), `context_stats` (id/kind/placement/frozen/char-count table; supersedes or extends `context_list`), `context_edit` (exact-string patch on content-bearing primitives), `context_move` (re-place by id).
- Tests + skill-doc updates per the hints above.

### Non-Goals

- Agent editing of `BaseAgent.context_items`, conversation history, or tool-call transcripts.
- `context_create_file` / filesystem-backed primitives (deferred; Open Q2).
- `context_compact` / `context_expand` (summarize-in-place with recovery) — sketched in conversation, deliberately a follow-up once view/stats/edit land.
- Changes to `binds_to_primitive` output-capture machinery, inner-loop algorithms, compaction middleware, or non-linear runtimes.
- Auto-attaching any of these tools (only `IsDoneTool` is auto-attached; that stays true).

---

## 5. Background & Context

The SDK's context system has three tiers: standing `context_items` (immutable, re-injected each run), a `ContextManager` whose **registry** of managed primitives renders as a dedicated zone re-built every loop iteration, and `algorithm=` presets that let the *runtime* curate the window. Agent-driven curation exists only as a thin proof of concept: `ContextUpsertTool` supports 6 of ~16 primitives through a single flattened `content: string` (plans become newline-split strings), ignores placement, and its sibling `ContextRemoveTool` bypasses the frozen flag. Meanwhile the primitives package already defines rich typed dataclasses, the manager already supports placement and frozen semantics, and the runtime already re-renders the registry each iteration — the substrate for real agent self-context-engineering is built; only the model-facing surface is missing. This design completes that surface, following the house rule in `skills/vidbyte-sdk/context-algorithm-to-tool.md` (bind the manager at construction, share the one dataclass between algorithm and tool forms).

---

## 6. Requirements

1. A registry module defines an ordered mapping of primitive keys to tool definitions; every included key produces exactly one tool whose name is `context_create_<key>`.
2. Each create tool's `spec()` returns a `ToolSpec` with: a complete `input_schema` (JSON Schema `object` with `properties`, `required`, `additionalProperties: false`, and `items` on every array), a matching flat `parameters` tuple (same required names, so `BaseTool.validate_call` and `to_prompt_str` agree with the schema), `ToolPermission.SAFE`, and a description that names the primitive and states that upsert-by-id overwrites.
3. Every create tool accepts `primitive_id: string` (required), `placement: string` (optional, one of the four `ContextWindowPlacement` values, default `end_of_context`), and the primitive's own fields (e.g. `steps: string[]` + `current_step` + `status` for plan; `goal`/`status`/`progress`/`completed[]`/`next_steps[]`/`deterministic_checks[]` for task; `source`/`content` for document; `name`/`content`/`artifact_type` for artifact; `content`/`source` for text and memory; `os_name`/`cwd`/`shell` for environment; `diff`/`files[]`/`branch` etc. for git_diff). Tuple-typed dataclass fields are accepted as JSON arrays and coerced to tuples.
4. On success, the tool upserts the built primitive into the constructor-injected `ContextManager` with the requested placement and returns a success `ToolResult` naming the id, kind, and placement. On invalid placement, unknown fields, frozen conflict (`ValueError` from `upsert`), or builder failure, it returns `ToolResult.error` with an actionable message (never raises).
5. A newly created primitive appears in the rendered `## Context Window Primitives` zone on the agent's next loop iteration with no code changes to `AgentRuntime` (proven by an integration-style test through `render_primitives_zone`).
6. `ContextManager` gains `registry_items()` (public, ordered, read-only view) and `set_placement(primitive_id, placement)`; `ContextListTool` migrates off `_registry`. (`set_frozen` per Open Q5.)
7. `ContextRemoveTool` returns an error, without removing, when the target primitive has `primitive_frozen=True`; `context_edit` and `context_move` enforce the same rule.
8. `context_view(primitive_id)` returns the full `to_context_text()`; `context_stats()` returns one line per managed primitive with id, kind, title, placement, frozen flag, and rendered char count; `context_edit(primitive_id, old_string, new_string)` performs an exact, unique-match replacement on the primitive's `content` field via `dataclasses.replace` + re-upsert, erroring on zero or multiple matches or on primitives without a string `content` field; `context_move(primitive_id, placement)` re-places without touching content.
9. `context_window_tools(manager, *, include=None, management=True)` returns the tool instances (create family filtered by `include` keys, plus list/remove/view/stats/edit/move when `management=True`); results are directly usable in `BaseAgent(tools=...)`.
10. All new public names exported per the repo's `__init__` conventions; new modules carry Context Protocol Headers; tests cover every registry key round-trip (arguments → primitive → registry → rendered zone) and every error path in requirements 4 and 7–8.

---

## 7. Non-Functional Requirements

- **Performance:** all operations are in-memory dict/tuple work; no I/O, no model calls. `context_stats` renders each primitive once per call — acceptable at expected registry sizes (≤ dozens).
- **Scalability:** registry-driven design keeps marginal cost of a new primitive to one registry row + tests.
- **Security:** all tools `ToolPermission.SAFE`; no filesystem or network access in v1 (file-backed creation explicitly deferred). Frozen primitives are immune to agent mutation. Tool outputs must not echo entire large primitives back unnecessarily (create/move/remove return acknowledgments, not full content; only `context_view` returns content, and it should bound output with `_truncate_text` from `vidbyte/context/primitives/base.py` at a generous cap).
- **Observability:** none beyond existing tool-call tracing (tool calls already appear in traces with args/results); no new logging.
- **Reliability:** tools never raise from `execute()`; every failure is a `ToolResult.error` with a message that tells the model what to do differently. Error messages are steering surface — write them as instructions ("Primitive 'x' is frozen; it cannot be modified. Create a new primitive with a different id instead.").
- **Compatibility:** existing `ContextUpsertTool`/`ContextListTool`/`ContextRemoveTool` names and behaviors preserved (except the frozen-removal fix, which is an intentional, documented behavior change).

---

## 8. High-Level Design

**Components.** One new sub-feature inside `vidbyte/tools/builtins/context_primitives/`: a `registry.py` holding a `PrimitiveToolDefinition` dataclass (key, primitive class, tool name, description, flat `parameters`, full `input_schema`, `builder: Callable[[Mapping[str, Any]], ContextItem]`) and the ordered `CREATE_TOOL_REGISTRY: dict[str, PrimitiveToolDefinition]`; a `create.py` with the single generic `CreateContextPrimitiveTool(BaseTool)` that is constructed with `(definition, context_manager)` and delegates `spec()` to the definition and `execute()` to `definition.builder` + `manager.upsert(item, placement=...)`; a `factory.py` with `context_window_tools(...)`; and the management tools (`view.py`, `stats.py`, `edit.py`, `move.py`). `vidbyte/context/manager.py` is extended with `registry_items()` / `set_placement()` (and optionally `set_frozen()`), and `remove.py` gains the frozen check. Nothing in `BaseAgent` or `AgentRuntime` changes — the feature rides entirely on the existing render path.

**Data flow.** Developer creates one `ContextManager`, passes it to `BaseAgent(context_manager=ctx_mgr, tools=context_window_tools(ctx_mgr))`. During the loop, the model calls e.g. `context_create_plan(primitive_id="plan:current", steps=[...], placement="top_of_context")`; the tool builds a `PlanContextItem` (coercing JSON arrays to tuples), upserts it into the shared manager, and returns an acknowledgment. On the next iteration, `AgentRuntime._build_system_string` calls `ctx_mgr.render_primitives_zone()` and the plan appears near the top of the system string. Later calls to `context_edit`/`context_move`/`context_remove` mutate the same registry slot; `context_view`/`context_stats` read it. Handoffs and inner-loop algorithms continue writing to the same manager unchanged.

```
            BaseAgent(context_manager=M, tools=context_window_tools(M))
                                    │
   model tool call                  ▼                    every iteration
  context_create_plan ──► CreateContextPrimitiveTool ──► M.upsert(item, placement)
  context_edit/move/remove ──► management tools ───────► M registry (shared object)
  context_view/stats ◄──────────────────────────────────┘        │
                                                                  ▼
                       AgentRuntime._build_system_string ──► M.render_primitives_zone()
                                                                  │
                                                     "## Context Window Primitives"
                                                       (system string → model)
```

**Reference sketch for the core pieces** (illustrative — the implementer finalizes signatures against the codebase):

```python
# registry.py
@dataclass(frozen=True, slots=True)
class PrimitiveToolDefinition:
    key: str                          # "plan"
    primitive_cls: type               # PlanContextItem
    tool_name: str                    # "context_create_plan"
    description: str
    parameters: tuple[ToolParameter, ...]      # flat mirror for validate_call/prompt rendering
    input_schema: Mapping[str, Any]            # authoritative provider schema (arrays get items)
    builder: Callable[[Mapping[str, Any]], ContextItem]

# Shared argument block appended to every definition's schema/parameters:
#   primitive_id (string, required), placement (string enum, optional), title (string, optional
#   where the primitive has a settable title).

# create.py
class CreateContextPrimitiveTool(BaseTool):
    def __init__(self, definition: PrimitiveToolDefinition, context_manager: ContextManager) -> None:
        self._definition = definition
        self._manager = context_manager
    def spec(self) -> ToolSpec:
        d = self._definition
        return ToolSpec(name=d.tool_name, description=d.description,
                        parameters=d.parameters, input_schema=dict(d.input_schema),
                        permission=ToolPermission.SAFE)
    async def execute(self, call: ToolCall) -> ToolResult:
        args = dict(call.arguments)
        placement_raw = str(args.pop("placement", "end_of_context"))
        try:
            placement = ContextWindowPlacement(placement_raw)
        except ValueError:
            return ToolResult.error(call.tool_name, f"Invalid placement '{placement_raw}'. One of: ...")
        try:
            item = self._definition.builder(args)   # coerces lists→tuples, injects primitive_id/title
            self._manager.upsert(item, placement=placement)
        except ValueError as exc:                   # frozen conflict or builder validation
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(call.tool_name,
            f"Created primitive '{item.primitive_id}' ({self._definition.key}, placement={placement.value}).")

# factory.py
def context_window_tools(manager: ContextManager, *, include: Sequence[str] | None = None,
                         management: bool = True) -> tuple[BaseTool, ...]:
    keys = tuple(include) if include is not None else tuple(CREATE_TOOL_REGISTRY)
    creates = tuple(CreateContextPrimitiveTool(CREATE_TOOL_REGISTRY[k], manager) for k in keys)
    if not management:
        return creates
    return (*creates, ContextListTool(manager), ContextRemoveTool(manager),
            ContextViewTool(manager), ContextStatsTool(manager),
            ContextEditTool(manager), ContextMoveTool(manager))
```

**Key design decisions and why.** (1) Registry + generic class reconciles the user's two framings: "keys" live in one central table (single source of truth, trivially extensible), while the model sees per-primitive typed tools (accurate schemas, better call rates, per-tool permissioning). (2) `input_schema` as the authoritative schema sidesteps the flat-`ToolParameter` array/`items` limitation with an in-repo precedent (`CreateHandoffTool`), while the mirrored flat `parameters` keep `validate_call` and prompt rendering coherent. (3) All mutation flows through `ContextManager`'s public API — extended minimally — so tools, inner-loop algorithms, and handoff sync share one write path and one frozen/placement semantics. (4) No runtime changes: the render loop already picks up registry mutations each iteration, so the entire feature is additive and independently testable against a bare manager.

---

*Next step: `/implement-design-doc context-window-editing-tools` (can be run by a cheaper model). Doc intentionally stops at high-level design; the implementer derives the file manifest, exact registry rows for all nine keys, and per-tool schemas from Sections 3, 6, and 8.*

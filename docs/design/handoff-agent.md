# Design Doc: Handoff Agent & Handoff Context Primitive

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

> Decisions locked 2026-06-03: auto-handoff failures are non-fatal; the document is surfaced via `reply.metadata["handoff"]` + `self.last_handoff`; v1 prebuilts are `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`.

---

## 1. Overview

This feature adds a first-class "handoff" capability to the Vidbyte SDK: the ability to turn a finished agent run into a structured, reusable **handoff document** that another agent (or human) can use to continue the work cold. It introduces one unifying object, `Handoff`, which is simultaneously a **context primitive** (it implements the existing `ContextItem` protocol and drops straight into another agent's `context_items`), the **spec/config** describing the document's structure (an ordered mapping of section titles to descriptions), and the **produced output** (the same structure, filled with content). Prebuilt off-the-shelf variants (`EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`) are subclasses that preset the section mapping. A thin `HandoffAgent` (a configured subclass of `BaseAgent`) reads the comprehensive handoff system prompt plus a spec and fills the sections from a completed run. Finally, `BaseAgent` gains an optional `handoff=` parameter: when set, the agent automatically produces a handoff document after it finishes and attaches it to the result.

---

## 2. Goals & Non-Goals

### Goals

- Add a `Handoff` context primitive that implements the existing `ContextItem` protocol so a handoff document drops directly into any agent's `context_items`.
- Ship prebuilt handoff variants as **objects/classes** (`EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`) — not factory functions — each presetting a section mapping of titles → descriptions.
- Add a thin `HandoffAgent` class that is a configuration over `BaseAgent` (no new runtime/execution model).
- Store the comprehensive handoff system prompt as a JSON asset under `vidbyte/prompts/prompts/handoff/` accessed through the existing `Prompts`/`Prompt` catalog.
- Add an optional `handoff=` parameter to `BaseAgent` that, when set, auto-runs the new `handoff()` method after `generate_reply()` completes and returns/attaches the produced handoff document.
- Let developers fully customize: bring their own `Handoff(sections={...})`, subclass it, swap the generating model/tools, or pass their own generator agent.
- Add handoff skill documentation at the repo root in the format of the existing skills.
- Reuse existing SDK primitives only — **no new top-level `vidbyte/handoff/` subsystem** (explicit constraint from the requester).

### Non-Goals

- No JSON-schema / `response_format` enforcement of the output in this iteration. Output is markdown parsed back into sections. Schema hardening is a documented future option.
- No deterministic no-LLM renderer in this iteration (the `Handoff` object supports it structurally via `fill()`, but the shipped generation path is the agent).
- No new context-window algorithm, middleware, or pipeline type.
- No changes to the return *type* of `generate_reply()` (stays `AgentMessage`); the handoff document is surfaced via metadata + an attribute to preserve the existing contract used by pipelines.
- No multi-agent refine/critique loop runtime for handoff generation (the `HandoffAgent` may iterate via tools/`max_iterations` like any `BaseAgent`, but no bespoke loop is added).

---

## 3. Background & Context

The SDK currently exposes exactly one concrete agent (`BaseAgent`, aliased `Agent`) constructed via `AgentClient.base()`. Handoff/continuation between agents today is implicit: `AgentTool` binds a context getter `lambda: (self._active_prompt, list(self.history))`, and `ContextManager`/`ContextItem` primitives let callers feed structured context into an agent. There is no first-class, structured way to summarize "what an agent did" into something the next agent can ingest.

A good handoff cannot reliably be produced in a single model call, and handoff documents are a core part of harness design. The requester wants this delegated to a reusable, customizable agent, while also making it trivial to produce a handoff without deeply wiring an agent.

Key existing facts this design builds on (verified in current source):

- `ContextItem` is a `runtime_checkable` `Protocol` (`kind: str`, `title: str`, `metadata: Mapping`, `to_context_text() -> str`). All concrete primitives are frozen dataclasses with `primitive_id`/`primitive_frozen` (`vidbyte/context/primitives.py`).
- `BaseAgent.generate_reply()` is async, returns `AgentMessage`, appends the reply to `self.history`, tracks `self._tool_call_contexts` and `self._active_prompt` (reset to `""` after each run) (`vidbyte/agents/base.py`).
- Prompts are JSON assets under `vidbyte/prompts/prompts/`; the catalog scans one level of subdirectories, requires `name`/`description`/`key`/`prompts`, and enforces a two-way sync between asset prompt ids `<key>.<prompt_name>` and the `Prompt` enum (`vidbyte/prompts/catalog.py`, `vidbyte/lib/enums/prompts.py`).
- The SDK uses lazy in-method imports to avoid cycles (e.g. `from vidbyte.tools.agent_tool import AgentTool` inside `BaseAgent` methods). `vidbyte/context/*` does not import `vidbyte/agents/*`, so `BaseAgent` can import `Handoff` from context at module load without a cycle, but `BaseAgent` must lazily import `HandoffAgent` (which imports `BaseAgent`).

---

## 4. Requirements

### Functional Requirements

1. A `Handoff` class exists that implements the `ContextItem` protocol (`kind="handoff"`, `title`, `metadata`, `to_context_text()`), exposing an ordered `sections: Mapping[str, str]` (title → description-or-content) and an `instructions: str`.
2. `Handoff` can be passed directly into `BaseAgent(context_items=[...])` / `AgentInput(context_items=[...])` and renders cleanly via `to_context_text()`.
3. `Handoff.fill(sections)` returns a new instance of the **same class** with the section values replaced by produced content and `metadata["filled"] = True`.
4. `Handoff.render_section_brief()` returns the `Title: description` lines used to instruct the generating model.
5. Prebuilt handoff variants are concrete subclasses constructed as objects: `EngineeringHandoff()`, `ResearchHandoff()`, `MinimalHandoff()`, each presetting a default section mapping and title.
6. A `HandoffAgent` class subclasses `BaseAgent`. Its constructor accepts a `Handoff` spec (defaulting to `MinimalHandoff()`) plus the usual agent/runner kwargs, and builds its system prompt from `Prompt.HANDOFF_SYSTEM_PROMPT` plus the spec's section brief, title, and instructions.
7. `HandoffAgent.generate_handoff(source: str) -> Handoff` runs the agent over the source-run text and returns a filled `Handoff` (same subclass as the spec) parsed from the model's section output.
8. The handoff system prompt lives at `vidbyte/prompts/prompts/handoff/handoff.json` under key `handoff`, prompt name `system_prompt`, and is detailed and comprehensive.
9. `Prompt.HANDOFF_SYSTEM_PROMPT = "handoff.system_prompt"` is added and stays in sync with the asset (catalog validation passes).
10. `BaseAgent.__init__` accepts an optional `handoff: Handoff | None = None` parameter (stored internally as `self._handoff_spec` to avoid colliding with the `handoff()` method); `self.last_handoff` is initialized to `None`.
11. `BaseAgent.handoff(spec=None, *, by=None) -> Handoff` produces a handoff document for the agent's most recent run, using a `HandoffAgent` (built on `self.runner` by default) unless an explicit generator agent `by` is provided.
12. When `self._handoff_spec` is set, `generate_reply()` automatically calls `handoff()` after producing its reply, stores the document on `self.last_handoff`, and attaches it to `reply.metadata["handoff"]`.
13. `AgentClient.handoff(handoff=None, **kwargs) -> HandoffAgent` constructs a handoff agent (mirrors `AgentClient.base()`).
14. `BaseAgent.fork()` propagates the configured `handoff` spec to the child.
15. Public exports: `HandoffAgent` from `vidbyte.agents` and root; `Handoff`, `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff` from `vidbyte.context` and root.
16. A handoff skill doc is added under `skills/vidbyte-sdk/handoff.md` and registered in the skill index if one exists.

### Non-Functional Requirements

- **Zero new runtime dependencies**: standard library + existing SDK only.
- **No import cycles**: `HandoffAgent` import inside `BaseAgent` is lazy; `Handoff` import into `BaseAgent` is module-level (safe, context never imports agents).
- **Backward compatible**: existing `BaseAgent` construction and `generate_reply()` return type are unchanged when `handoff=None`.
- **Resilient auto-handoff**: a failure during auto-handoff generation must not destroy the agent's already-completed primary reply; the error is recorded in `reply.metadata["handoff_error"]` and `self.last_handoff` stays `None`.
- **Context Protocol Header** on every new/modified Python file, matching repo convention.
- **Testing**: Python `unittest`, no network — fake runners only.

---

## 5. High-Level Design

The design unifies three conceptual roles into one object so there is no parallel subsystem to learn:

```
                      ┌──────────────────────────────────────────────┐
                      │                  Handoff                      │
                      │  (ContextItem primitive + spec + output)      │
                      │  sections: {title -> description | content}   │
                      └───────────────┬──────────────────────────────┘
            subclasses preset sections│                 ▲ fill(sections)
   EngineeringHandoff/ResearchHandoff │                 │ (same subclass, content)
                                      ▼                 │
 BaseAgent(handoff=EngineeringHandoff())                │
        │ generate_reply() completes                    │
        │ auto-runs self.handoff()                       │
        ▼                                                │
 BaseAgent.handoff(spec, by=None) ──builds──► HandoffAgent(spec, runner=self.runner)
        │ renders run text from history/tool calls/result│  system_prompt =
        ▼                                                │   HANDOFF_SYSTEM_PROMPT
 HandoffAgent.generate_handoff(run_text) ────────────────┘   + spec.render_section_brief()
        │ arun(run_text) -> AgentMessage
        │ parse "## <Title>" blocks -> sections
        ▼
 filled Handoff ──► reply.metadata["handoff"], self.last_handoff
        │
        ▼
 next_agent = Agent(..., context_items=[filled_handoff])   # loop closes
```

**Components created:** `vidbyte/context/handoffs.py` (the `Handoff` family), `vidbyte/agents/handoff.py` (`HandoffAgent`), `vidbyte/prompts/prompts/handoff/handoff.json` (system prompt asset).

**Components modified:** `vidbyte/agents/base.py` (`handoff` param, `handoff()` method, run-rendering helpers, `last_*` state, fork propagation, auto-run in `generate_reply`), `vidbyte/agents/client.py` (`handoff()` factory), `vidbyte/agents/__init__.py`, `vidbyte/context/__init__.py`, `vidbyte/lib/enums/prompts.py`, `vidbyte/__init__.py`, plus the skill index.

**Key decisions and why:**

- **One `Handoff` object for all three roles.** The requester explicitly wants a handoff context primitive whose prebuilt versions are objects and which is also the config passed to the `handoff=` param. Collapsing spec/primitive/output into one class is the simplest model and makes the produced document immediately reusable as context.
- **`HandoffAgent` subclasses `BaseAgent`** rather than wrapping it, because a "thin configuration over base agent" is exactly an init that composes a system prompt; subclassing keeps `fork`, tools, middleware, runner routing, and `arun/run` for free, and adds only `generate_handoff()`.
- **Auto-handoff via metadata, not a changed return type.** Pipelines depend on `generate_reply()` returning an `AgentMessage` whose `.content` is a string. Returning a tuple would break that contract, so the document rides on `reply.metadata["handoff"]` and `self.last_handoff`.
- **Static base prompt + dynamic section brief.** The JSON asset holds the comprehensive, static "how to write a handoff" instructions; the spec's section list is appended at runtime. This avoids brittle `str.format` against JSON braces and keeps per-task structure in the `Handoff` object where developers customize it.

---

## 6. Detailed Design

### 6.1 `Handoff` family (context primitive + spec + output)

**File(s):** `vidbyte/context/handoffs.py`
**Type:** New file

#### What it does

Defines the `Handoff` base class and the prebuilt subclasses. A `Handoff` is an ordered, sectioned document. As a template its section values are guidance descriptions; once produced (via `fill`), the same structure holds content. It satisfies the `ContextItem` protocol so it can be dropped into `context_items`.

#### Interface / API

```python
class Handoff:
    """Sectioned handoff document: a ContextItem primitive that also serves as the spec a HandoffAgent fills."""

    DEFAULT_TITLE: str = "Handoff"
    DEFAULT_INSTRUCTIONS: str = ""

    def __init__(self, *, sections: Mapping[str, str] | None = None, title: str | None = None, instructions: str | None = None, metadata: Mapping[str, Any] | None = None, primitive_id: str | None = None, primitive_frozen: bool = False) -> None: ...
    def default_sections(self) -> dict[str, str]: ...           # overridden by prebuilt subclasses
    def to_context_text(self) -> str: ...                       # ContextItem protocol
    def render_section_brief(self) -> str: ...                  # "Title: description" lines for the model
    def fill(self, sections: Mapping[str, str]) -> "Handoff": ...# same subclass, content + metadata["filled"]=True
    @property
    def is_filled(self) -> bool: ...                            # metadata.get("filled", False)

class EngineeringHandoff(Handoff): ...   # presets title + default_sections()
class ResearchHandoff(Handoff): ...
class MinimalHandoff(Handoff): ...
```

Public instance attributes (to satisfy the protocol and `ContextManager`): `kind = "handoff"`, `title`, `instructions`, `sections`, `metadata`, `primitive_id`, `primitive_frozen`.

#### Logic / Algorithm

1. `__init__` resolves `sections` to the provided mapping or `self.default_sections()`, `title` to provided or `self.DEFAULT_TITLE`, `instructions` similarly, and copies `metadata` to a plain dict.
2. `to_context_text()` renders an optional instructions line followed by `## <Title>\n<value>` blocks for each section.
3. `render_section_brief()` renders `- <Title>: <description>` lines (used in the agent system prompt).
4. `fill(sections)` constructs `type(self)(sections=dict(sections), title=self.title, instructions=self.instructions, metadata={**self.metadata, "filled": True})`, preserving the concrete subclass.
5. Each prebuilt subclass overrides `DEFAULT_TITLE` and `default_sections()` with a curated mapping (e.g. Engineering: Objective, Changes Made, Verification Status, Open Threads, Risks & Gotchas, Next Steps).

#### Edge Cases & Error Handling

- Empty `sections` (e.g. `Handoff(sections={})`): `to_context_text()` renders title + instructions only; `render_section_brief()` returns `""`. Valid — represents a free-form handoff.
- `fill()` with section keys not in the template: kept as-is (the produced document is authoritative); no error. Missing template keys: simply absent from output.
- Non-string section values: coerced to `str` on render to avoid `TypeError` from `join`.
- `Handoff` is intentionally a regular class (not a frozen dataclass) because the core requirement is subclass-preset defaults; it still exposes the same attribute surface the other primitives expose for `ContextManager` compatibility (which uses the generic `else` branch → `ArtifactContextItem` path via `to_context_text()`).

### 6.2 `HandoffAgent`

**File(s):** `vidbyte/agents/handoff.py`
**Type:** New file

#### What it does

A thin `BaseAgent` subclass configured to produce handoff documents. It composes its system prompt from the static handoff prompt asset plus the spec's section brief, and adds `generate_handoff()`.

#### Interface / API

```python
class HandoffAgent(BaseAgent):
    def __init__(self, handoff: Handoff | None = None, *, name: str = "handoff", **kwargs: Any) -> None: ...
    async def generate_handoff(self, source: str) -> Handoff: ...
    def build_system_prompt(self) -> str: ...                 # asset + section brief + title/instructions
    def parse_sections(self, text: str) -> dict[str, str]: ...# "## <Title>" blocks -> {title: content}
```

#### Logic / Algorithm

1. `__init__` resolves `handoff` to the provided spec or `MinimalHandoff()`, stores it as `self.spec`, builds the system prompt via `build_system_prompt()`, and calls `super().__init__(name=name, system_prompt=..., handoff=None, **kwargs)` (never recursively auto-handoff).
2. `build_system_prompt()` fetches `Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT)` and appends a `# Required Sections` block from `spec.render_section_brief()`, the output title, and any spec instructions.
3. `generate_handoff(source)` calls `await self.arun(source)`, parses the reply via `parse_sections()`, and returns `self.spec.fill(parsed)`.
4. `parse_sections(text)` splits on `^##\s*(.+)$` headers; for each spec section title, captures the matching block case-insensitively; unmatched titles map to `""`.

#### Edge Cases & Error Handling

- Model output with no `##` headers: `parse_sections` returns all spec titles mapped to `""`; the entire body is stored under `metadata["raw_output"]` on the filled handoff so nothing is lost. (Silent-failure guard.)
- Extra `##` sections the model invented but not in the spec: ignored for the structured mapping but retained in `metadata["extra_sections"]`.
- No runner available (parent agent had none and none passed): `BaseAgent` already raises `AgentExecutionError("Agent requires a runner.")` — surfaced unchanged.

### 6.3 `BaseAgent` integration

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds the optional `handoff=` config, the `handoff()` method, run-rendering helpers, last-run state, fork propagation, and the auto-run hook in `generate_reply()`.

#### Interface / API

```python
def __init__(self, *, ..., handoff: Handoff | None = None, ...) -> None: ...   # new kwarg
async def handoff(self, spec: Handoff | None = None, *, by: "BaseAgent | None" = None) -> Handoff: ...
def _render_run_for_handoff(self) -> str: ...
# new attributes: self._handoff_spec, self.last_handoff, self.last_prompt, self.last_reply
```

#### Logic / Algorithm

1. `__init__` stores `self._handoff_spec = handoff`, `self.last_handoff = None`, `self.last_prompt = ""`, `self.last_reply = None`. (Stored under `_handoff_spec` so the public `handoff()` method name is not shadowed.)
2. In `generate_reply()`, after building the reply metadata and before returning: set `self.last_prompt = prompt`. If `self._handoff_spec is not None`, run the auto-handoff block:
   - `try`: `produced = await self.handoff(self._handoff_spec)`; `self.last_handoff = produced`; add `metadata["handoff"] = produced`.
   - `except Exception as exc`: add `metadata["handoff_error"] = repr(exc)`; leave `self.last_handoff = None`.
   - The auto-handoff runs against the freshly-appended reply in `self.history`, then the single `AgentMessage` carrying the augmented metadata is the one returned. `self.last_reply` is set to that message.
3. `handoff(spec, by)` resolves `spec` to the argument, else `self._handoff_spec`, else `MinimalHandoff()`. Builds `generator = by or HandoffAgent(spec, runner=self.runner, runners=self.runners, provider=self.runner_config.provider, model_name=self.runner_config.model_name, api_key=self.runner_config.api_key)`. Renders source text via `_render_run_for_handoff()`. Returns `await generator.generate_handoff(source_text)`.
4. `_render_run_for_handoff()` composes a comprehensive run digest: the agent name + original system prompt, the last user prompt (`self.last_prompt`), an ordered transcript from `self.history` (`AgentMessage.sender/content`), the tool-call log from `self._tool_call_contexts`, and the final output (last reply content). Uses small named helpers (`_render_history`, `_render_tool_calls`) to stay class-first.
5. `fork()` adds `handoff=self._handoff_spec` to the child constructor kwargs.

#### Edge Cases & Error Handling

- **Auto-handoff must not break the primary run** (Hidden Failure): wrapped in `try/except`; failure is recorded in metadata, primary reply still returned.
- **`handoff()` called before any run** (Hidden Assumption): `self.last_reply is None` → `_render_run_for_handoff()` renders "No completed run recorded." and still produces a (sparse) handoff rather than crashing.
- **No tool calls** (Edge Case): `_render_tool_calls` returns "No tools were used." rather than an empty section.
- **Empty history** (Edge Case): transcript renders "No conversation history."
- **Recursion guard** (Hidden Failure): `HandoffAgent.__init__` forces `handoff=None` so a handoff agent never auto-triggers its own handoff.

### 6.4 Handoff system prompt asset

**File(s):** `vidbyte/prompts/prompts/handoff/handoff.json`
**Type:** New file

#### What it does

Holds the comprehensive, static system prompt instructing a model how to write an excellent handoff document: role framing, what a handoff is for, how to mine a run transcript and tool log, how to write each section (concrete, decision-oriented, no fluff), how to flag open threads/risks/assumptions, the exact `## <Title>` output format, and rules (don't fabricate, prefer specifics, surface uncertainty).

#### Interface / API

```json
{
  "name": "Handoff",
  "description": "System prompt for the handoff agent that turns a completed agent run into a structured, reusable handoff document.",
  "key": "handoff",
  "prompts": { "system_prompt": "<comprehensive multi-section instructions>" }
}
```

#### Logic / Algorithm

1. Catalog `_json_assets` scans the `handoff/` subdirectory and loads the file.
2. `_load` derives prompt id `handoff.system_prompt` and requires `Prompt.HANDOFF_SYSTEM_PROMPT` to exist.
3. `_validate_enum_sync` confirms two-way enum/asset consistency.

#### Edge Cases & Error Handling

- Missing enum member → `ConfigurationError` at first `Prompts()` use (caught by tests). Mitigated by adding the enum member in the same change.

### 6.5 `Prompt` enum addition

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

Adds `HANDOFF_SYSTEM_PROMPT = "handoff.system_prompt"`.

### 6.6 Client factory & exports

**File(s):** `vidbyte/agents/client.py`, `vidbyte/agents/__init__.py`, `vidbyte/context/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

- `AgentClient.handoff(self, handoff=None, **kwargs) -> HandoffAgent` mirrors `.base()`.
- `vidbyte/agents/__init__.py` exports `HandoffAgent`.
- `vidbyte/context/__init__.py` exports `Handoff`, `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`.
- `vidbyte/__init__.py` re-exports `HandoffAgent` (from agents) and the `Handoff` family (from context) and adds them to `__all__`.

### 6.7 Handoff skill doc

**File(s):** `skills/vidbyte-sdk/handoff.md` (+ index update if `skills/vidbyte-sdk/SKILL.md` exists)
**Type:** New file (+ possible modify)

Markdown topic doc in the same style as `skills/vidbyte-sdk/pipelines.md`: what handoffs are, the `Handoff` object and prebuilt variants, the `HandoffAgent`, the `handoff=` auto-run param, customization, the module layout, and rules for adding new prebuilt handoffs.

---

## 7. Data Model Changes

N/A — no database/schema changes. All new types are in-memory Python objects. The only "model" additions are the `Handoff` class family (Section 6.1) and one new `Prompt` enum member (Section 6.5).

---

## 8. API Changes

N/A for HTTP endpoints. Public **Python API** additions are covered in Section 6 and summarized here:

- New: `vidbyte.HandoffAgent`, `vidbyte.Handoff`, `vidbyte.EngineeringHandoff`, `vidbyte.ResearchHandoff`, `vidbyte.MinimalHandoff`.
- New: `AgentClient.handoff(...)`, `BaseAgent.handoff(...)`, `BaseAgent(handoff=...)`, `BaseAgent.last_handoff`.
- Changed (additive, backward compatible): `BaseAgent.__init__` gains `handoff=None`; `generate_reply()` may populate `reply.metadata["handoff"]` / `["handoff_error"]`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/handoff-agent.md` | This design doc (first commit) |
| CREATE | `vidbyte/context/handoffs.py` | `Handoff` primitive + prebuilt subclasses |
| MODIFY | `vidbyte/context/__init__.py` | Export `Handoff` family |
| CREATE | `vidbyte/agents/handoff.py` | `HandoffAgent` thin `BaseAgent` subclass |
| MODIFY | `vidbyte/agents/base.py` | `handoff=` param, `handoff()` method, run rendering, `last_*` state, fork, auto-run hook |
| MODIFY | `vidbyte/agents/client.py` | `AgentClient.handoff()` factory |
| MODIFY | `vidbyte/agents/__init__.py` | Export `HandoffAgent` |
| CREATE | `vidbyte/prompts/prompts/handoff/handoff.json` | Comprehensive handoff system prompt asset |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `HANDOFF_SYSTEM_PROMPT` enum member |
| MODIFY | `vidbyte/__init__.py` | Root exports for `HandoffAgent` + `Handoff` family |
| CREATE | `skills/vidbyte-sdk/handoff.md` | Handoff skill/topic doc |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Register handoff doc in skill index (only if file exists) |
| CREATE | `tests/test_handoff_agent.py` | Unit tests (unittest, fake runners) |
| CREATE | `scripts/test_handoff_agent.py` | Phase 5 verification script |

---

## 10. Testing Plan

All tests use Python `unittest` with `IsolatedAsyncioTestCase` and fake runners (no network), matching `tests/` conventions. A fake runner returns a fixed markdown body with `## <Title>` sections.

### Unit Tests

**`Handoff` primitive**
- `it('renders title, instructions, and section blocks in to_context_text')` — [Edge Case]
- `it('returns empty section brief and title-only context text when sections is empty')` — [Edge Case]
- `it('fill() preserves the concrete subclass type (EngineeringHandoff stays EngineeringHandoff)')` — [Silent Failure] (a naive `Handoff(...)` rebuild would silently downcast)
- `it('fill() sets metadata["filled"]=True and is_filled reports True')` — [Hidden Assumption]
- `it('coerces non-string section values to str without raising')` — [Hidden Failure]
- `it('satisfies the ContextItem protocol (isinstance against runtime_checkable ContextItem)')` — [Hidden Assumption]
- `it('is accepted by ContextManager.add and rendered via to_context')` — [Hidden Assumption]
- `it('each prebuilt (Engineering/Research/Minimal) exposes a non-empty distinct section map')` — [Silent Failure] (guards against copy-paste duplication)

**`HandoffAgent`**
- `it('builds a system prompt containing the asset text and every spec section title')` — [Silent Failure] (a dropped section would silently shrink the prompt)
- `it('generate_handoff returns a filled Handoff of the spec subclass')` — [Hidden Assumption]
- `it('parse_sections maps each ## header to its content case-insensitively')` — [Edge Case]
- `it('parse_sections stores whole body under metadata["raw_output"] when no ## headers present')` — [Silent Failure]
- `it('parse_sections retains model-invented sections under metadata["extra_sections"]')` — [Hidden Failure]
- `it('defaults to MinimalHandoff when no spec is provided')` — [Edge Case]
- `it('never auto-triggers its own handoff (handoff spec forced to None)')` — [Hidden Failure] (recursion guard)

**`BaseAgent` integration**
- `it('handoff= param is stored without shadowing the handoff() method')` — [Hidden Failure] (name collision)
- `it('generate_reply attaches reply.metadata["handoff"] and sets last_handoff when handoff= is set')` — [Hidden Assumption]
- `it('generate_reply does NOT attach handoff when handoff= is None')` — [Edge Case]
- `it('auto-handoff failure records metadata["handoff_error"] and leaves last_handoff None without breaking the reply')` — [Hidden Failure] (the primary reply must survive)
- `it('handoff() called before any run renders a sparse digest and still returns a Handoff')` — [Hidden Assumption]
- `it('_render_run_for_handoff includes tool calls, history, and final output')` — [Silent Failure]
- `it('_render_run_for_handoff reports "No tools were used." when there are no tool calls')` — [Edge Case]
- `it('handoff(by=custom_agent) uses the provided generator instead of building one')` — [Hidden Assumption]
- `it('fork() propagates the handoff spec to the child')` — [Silent Failure]
- `it('handoff() reuses self.runner by default')` — [Hidden Assumption]

**Prompt catalog**
- `it('Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT) returns non-empty text')` — [Edge Case]
- `it('prompt enum/asset sync still validates (no ConfigurationError on Prompts())')` — [Hidden Failure]

**Exports**
- `it('HandoffAgent imports from vidbyte and vidbyte.agents')` — [Hidden Assumption]
- `it('Handoff family imports from vidbyte and vidbyte.context')` — [Hidden Assumption]
- `it('sdk.agents.handoff() returns a HandoffAgent')` — [Edge Case]

### Integration Tests

- End-to-end: build `Agent(handoff=EngineeringHandoff(), runner=fake)`, run it, assert `reply.metadata["handoff"]` is a filled `EngineeringHandoff` whose sections match the fake model output. Then feed `reply.metadata["handoff"]` into a second `Agent(context_items=[doc])` and assert it renders into the second agent's context (the loop closes). Silent-failure path to check: the handoff content must actually reach the second agent's context text, not just be stored.
- Hidden assumption the integration surfaces: the generator `HandoffAgent` inherits the parent's runner/provider; verify a parent built with only a `runner=` (no provider/model) still produces a handoff.
- Mock vs real: fake runners only; no real provider calls.

### Manual / QA Test Cases

1. Given a coding agent that used tools, when `agent.handoff(EngineeringHandoff())` is called, then the document includes a non-empty "Changes Made" and a "Risks & Gotchas" section and lists the tools used — [Edge Case: tool-heavy run].
2. Given `handoff=` set and the generator runner raises, when the agent runs, then `generate_reply` still returns the normal reply and `metadata["handoff_error"]` is populated — [Hidden Failure].
3. Given a custom `Handoff(sections={"Decision Log": "...", "Blockers": "..."})`, when used, then the produced document contains exactly those section titles — [Hidden Assumption: custom structure honored].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib (`re`, `typing`, `dataclasses`) | 3.11+ | Parsing, types | None |
| Existing `vidbyte` packages (agents, context, prompts, lib) | in-repo | Reuse primitives | Low — additive changes only |

No new third-party packages.

---

## 12. Rollout & Deployment

- No feature flags. Purely additive, backward-compatible Python API.
- Not a breaking change: `handoff=None` default preserves all existing behavior; `generate_reply()` return type is unchanged.
- No deployment ordering concerns (single package).
- Rollback: revert the PR; no migrations or persisted state.

---

## 13. Open Questions

Resolved with the requester (2026-06-03):

- [x] Auto-handoff failures are **non-fatal**: record in `reply.metadata["handoff_error"]`, leave `self.last_handoff = None`, still return the primary reply.
- [x] Document surfacing: `reply.metadata["handoff"]` + `self.last_handoff` (not a changed return type).
- [x] Prebuilt variants for v1: `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`. (`ConversationHandoff` dropped.)

Still defaulted, open to change later:

- [ ] Should the produced `Handoff` also be appended to `self.history`/`context_items` automatically? Current decision: no — leave placement to the developer to avoid polluting subsequent runs.
- [ ] Ship the deterministic no-LLM path (`Handoff.fill(agent-derived sections)`) now or defer? Current decision: defer; structure supports it later.

---

## 14. Alternatives Considered

### Alternative 1: A new `vidbyte/handoff/` subsystem (config + presets registry + document + agent)
- What: separate `HandoffConfig`, `HandoffPresets`, `HandoffDocument`, and agent modules.
- Why rejected: explicitly declined by the requester as over-built. The unified `Handoff` object plus a `BaseAgent` subclass reuses existing primitives and adds far less surface.

### Alternative 2: Prebuilt handoffs as factory functions (`engineering_handoff()`)
- What: module-level functions returning a configured object.
- Why rejected: the requester wants them as objects/classes (`EngineeringHandoff`), which also gives subclass-level customization and type identity preserved through `fill()`.

### Alternative 3: `HandoffAgent` as a composition wrapper holding a private `BaseAgent`
- What: `HandoffAgent` owns a `BaseAgent` field and delegates.
- Why rejected: a subclass inherits `fork`, tools, middleware, runner routing, and `arun/run` for free and matches "thin configuration over our base agent" more directly.

### Alternative 4: Change `generate_reply()` to return `(message, handoff)`
- What: return both objects.
- Why rejected: pipelines and existing callers rely on the `AgentMessage` return contract and `.content` being a string; metadata attachment is non-breaking.

### Alternative 5: Enforce output with a JSON schema (`response_format`)
- What: build a schema from section keys and require structured JSON.
- Why rejected for v1: heavier and provider-dependent; markdown `## <Title>` parsing is simpler, tolerant, and provider-agnostic. Documented as a future hardening option.

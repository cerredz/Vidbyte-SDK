# Design Doc: Create Handoff Tool

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

This feature adds an agent-invokable builtin tool, `create_handoff`, that lets an agent
deliberately author one or more structured handoff documents *during* a run (not only at
the end of it). The tool accepts rich intent (target schema, audience, objective, scope,
non-goals, authoring instructions, and optional custom sections), generates a filled
`Handoff` by routing through the existing `HandoffAgent` generative path, stores every
produced handoff on the calling agent (`agent.handoffs`), and syncs each one into the
agent's `ContextManager` registry as a first-class context primitive.

---

## 2. Goals & Non-Goals

### Goals
- Provide a `CreateHandoffTool` (`BaseTool`) under `vidbyte/tools/builtins/handoff/` that an agent can call mid-run.
- Always generate the handoff content through a `HandoffAgent` (reusing `BaseAgent.handoff`), never make the calling agent hand-author prose.
- Support all three prebuilt schemas (`engineering`, `research`, `minimal`) plus a `custom` schema where the caller supplies its own section titles + guidance.
- Carry substantial intent/context into generation: audience, objective, scope, non-goals, and free-form authoring instructions, composed into the generator's author-instructions block.
- Allow many handoffs per run: collect them in a new `BaseAgent.handoffs` list.
- Sync each produced handoff into `agent.context_manager` as a managed primitive (handoffs already implement the `ContextItem` shape).
- Wire the tool to its agent through the existing `_bind_agent_tool_context` / `bind_agent` mechanism.

### Non-Goals
- No new generation engine. Generation reuses `HandoffAgent` / `BaseAgent.handoff`.
- No new `ContextItem` subtype. `Handoff` already satisfies the registry contract.
- Not replacing the end-of-run auto-handoff (`_run_auto_handoff`); this is its on-demand sibling. (We do route auto-handoff through the new `record_handoff` so both land in one place.)
- No changes to provider clients, runtimes, or the permission model.
- No persistence beyond in-memory `agent.handoffs` + the context registry (no disk/db).

---

## 3. Background & Context

The repo already contains two halves of a handoff system:

- **Schemas** (`vidbyte/context/handoff/`): `Handoff` base plus `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`. Each section ships dense authoring guidance. `Handoff` deliberately doubles as a `ContextItem` (`kind="handoff"`, `primitive_id`, `primitive_frozen`, `to_context_text()`, `title`).
- **Generator** (`vidbyte/agents/handoff.py`): `HandoffAgent` produces a filled handoff from a source agent's transcript. It is currently driven only by `BaseAgent._run_auto_handoff` (passive, end-of-run) and the public `BaseAgent.handoff()` method.

What is missing is the **active** path: an agent intentionally producing a handoff as a deliverable, with explicit intent, at a chosen moment, possibly several times. This tool fills that gap and reuses the existing generator rather than duplicating it.

Constraints / dependencies discovered during the repo audit:
- `BaseTool.execute(call)` receives only a `ToolCall`; it has no agent handle. Agent-state-mutating builtins solve this with **late binding**: `BaseAgent._bind_agent_tool_context` calls `tool.bind_agent(self)` (used today by `AttachMcpServerTool`) or `tool.bind_context_getter(...)` (used by `AgentTool`).
- The default `PermissionPolicy` allows only `{SAFE, READ}`. `ContextUpsertTool` mutates agent state yet declares `ToolPermission.SAFE` so it runs out of the box. We follow this convention.
- `ToolSpec.input_schema` (a JSON Schema mapping) **is** honored by every provider formatter: `ToolsFormatter._schema_for_spec` prefers `input_schema` over flat `parameters`. This lets us declare a nested `custom_sections` object the model can populate.
- `ContextManager.upsert(item)` requires a non-empty `item.primitive_id` and refuses frozen primitives; it stores `item` directly in `_registry` and later reads `item.title` / `item.to_context_text()` — all present on `Handoff`.

---

## 4. Requirements

### Functional Requirements
1. The agent can call a tool named `create_handoff` with: `handoff_type` (enum: `engineering | research | minimal | custom`) and `objective` (string) as required inputs.
2. Optional inputs: `title`, `audience`, `scope`, `non_goals`, `instructions`, and `custom_sections` (object mapping section title → section guidance).
3. For `engineering`/`research`/`minimal`, the tool builds the corresponding `Handoff` subclass, preserving that subclass's default section guidance.
4. For `custom`, the tool builds a base `Handoff` whose sections come from `custom_sections`; if `custom_sections` is missing/empty it returns a tool error.
5. The intent fields (`audience`, `objective`, `scope`, `non_goals`, `instructions`) are composed into the spec's `instructions`, which `HandoffAgent.build_system_prompt` injects into the generator prompt as the author-instructions block.
6. Generation always runs through `BaseAgent.handoff(spec)` (i.e., a `HandoffAgent` over the current run transcript). The tool never fabricates section prose itself.
7. Each produced handoff is assigned a stable `primitive_id` (`handoff:<n>`, monotonic within the run) and appended to `agent.handoffs`.
8. Each produced handoff sets `agent.last_handoff` and, when `agent.context_manager` is present, is upserted into the registry.
9. The tool can be called multiple times in one run; each call adds a distinct entry to `agent.handoffs` with a distinct `primitive_id`.
10. `BaseAgent._run_auto_handoff` records its produced handoff through the same `record_handoff` path so auto + manual handoffs share one collection.
11. The tool returns a `ToolResult.success` whose `output` is the rendered handoff markdown and whose `metadata` includes `primitive_id`, `handoff_type`, the section map, and any `extra_sections` / `raw_output` surfaced by the generator.
12. Unknown `handoff_type`, missing `objective`, missing-bound agent, or `custom` without `custom_sections` produce `ToolResult.error` (not an exception) with an actionable message.

### Non-Functional Requirements
- **Performance:** Each tool call triggers exactly one LLM generation call (via `HandoffAgent`). This is acceptable and expected per product intent; no batching.
- **Scalability:** `agent.handoffs` is O(n) in number of calls; trivial for realistic n.
- **Security:** Declares `ToolPermission.SAFE` (consistent with `ContextUpsertTool`) so it runs under the default policy; performs no filesystem/network IO of its own beyond the model call already mediated by the agent's runner.
- **Observability:** Generation failures and partial outputs are surfaced in `ToolResult` (status + metadata), never silently swallowed. Sync failures (frozen id) are skipped without failing the run.
- **Reliability:** A missing `context_manager` must not fail handoff creation; the handoff is still stored on the agent.

---

## 5. High-Level Design

A new `CreateHandoffTool(BaseTool)` is added under `vidbyte/tools/builtins/handoff/`. It holds
no agent at construction; `BaseAgent._bind_agent_tool_context` is extended to call
`tool.bind_agent(self)` for `CreateHandoffTool` instances (mirroring `AttachMcpServerTool`).
The tool declares a rich `ToolSpec.input_schema` so providers expose the full nested intent
shape (including `custom_sections`).

On `execute`, the tool: (1) validates inputs and resolves the concrete `Handoff` spec from
`handoff_type`, attaching a composed intent string as `spec.instructions`, an optional `title`,
and a freshly minted `primitive_id`; (2) calls `await agent.handoff(spec)` to generate a filled
handoff via the existing `HandoffAgent` path; (3) calls `agent.record_handoff(produced)` to
append to `agent.handoffs`, update `last_handoff`, and upsert into the context registry; (4)
returns the rendered markdown plus structured metadata.

`BaseAgent` gains a `handoffs: list[Handoff]` field and a `record_handoff` method (with a private
`_sync_handoff_primitive` helper). `_run_auto_handoff` is updated to call `record_handoff` so the
existing auto-handoff and the new on-demand handoffs share one collection and one sync path.

```
agent (mid-run)
  └─ tool call: create_handoff(handoff_type, objective, audience, scope, non_goals,
                               instructions, title, custom_sections)
        │
   CreateHandoffTool.execute(call)            # bound to the live agent via bind_agent()
        ├─ _resolve_spec(args)                 # subclass | custom Handoff; set instructions+id+title
        ├─ _generate(spec) -> agent.handoff(spec)   # HandoffAgent over render_source_run(agent)
        ├─ agent.record_handoff(produced)
        │     ├─ agent.handoffs.append(produced)
        │     ├─ agent.last_handoff = produced
        │     └─ context_manager.upsert(produced)    # when present & id set
        └─ ToolResult.success(rendered_md, metadata={id, type, sections, extra_sections?})
```

Key design decisions:
- **Reuse `BaseAgent.handoff`** rather than constructing a `HandoffAgent` inside the tool — it already pulls provider/model config off the agent and renders the run transcript as source.
- **Late binding via `bind_agent`** — matches the existing precedent and avoids an agent↔tool construction cycle.
- **`input_schema` over flat `parameters`** — required to express `custom_sections` as a nested object; verified honored by the formatter.
- **`SAFE` permission** — required to run under the default policy; consistent with `ContextUpsertTool`.

---

## 6. Detailed Design

### 6.1 CreateHandoffTool

**File(s):** `vidbyte/tools/builtins/handoff/create.py`
**Type:** New file

#### What it does
Defines the agent-facing builtin that authors structured handoffs from caller intent, delegating generation to the bound agent's `HandoffAgent` path and recording results on the agent.

#### Interface / API
```python
class CreateHandoffTool(BaseTool):
    """Builtin tool that authors structured handoffs from caller intent during a run."""

    _SCHEMA_REGISTRY: dict[str, type[Handoff]]   # engineering/research/minimal -> subclass

    def __init__(self) -> None: ...
    def bind_agent(self, agent: object) -> None: ...          # late-bound by BaseAgent
    def spec(self) -> ToolSpec: ...                            # name="create_handoff", input_schema=...
    async def execute(self, call: ToolCall) -> ToolResult: ...

    # private helpers
    def _resolve_spec(self, args: Mapping[str, Any]) -> Handoff: ...
    def _compose_intent(self, args: Mapping[str, Any]) -> str: ...
    def _next_primitive_id(self) -> str: ...
    async def _generate(self, spec: Handoff) -> Handoff: ...
    def _render_result(self, produced: Handoff) -> ToolResult: ...
```

`spec()` returns a `ToolSpec` with `name="create_handoff"`, `permission=ToolPermission.SAFE`,
`binds_to_primitive="handoff"`, and this `input_schema`:

```json
{
  "type": "object",
  "required": ["handoff_type", "objective"],
  "additionalProperties": false,
  "properties": {
    "handoff_type":   { "type": "string", "enum": ["engineering", "research", "minimal", "custom"],
                        "description": "Which handoff schema to produce." },
    "objective":      { "type": "string",
                        "description": "Why this handoff exists and the target state the receiver must reach." },
    "audience":       { "type": "string",
                        "description": "Who receives this handoff (next agent/human) and what they must do next." },
    "title":          { "type": "string", "description": "Optional title override for the handoff." },
    "scope":          { "type": "string", "description": "What is in scope for the receiver." },
    "non_goals":      { "type": "string", "description": "Explicit exclusions / what not to do." },
    "instructions":   { "type": "string", "description": "Extra authoring guidance for the generator." },
    "custom_sections":{ "type": "object", "additionalProperties": { "type": "string" },
                        "description": "Required when handoff_type=custom: map of section title -> section guidance." }
  }
}
```

#### Logic / Algorithm
1. `execute`: if no agent is bound, return `ToolResult.error("create_handoff", "...")`.
2. Copy `call.arguments` into a plain dict.
3. `_resolve_spec(args)`:
   - Read `handoff_type` (lowercased, stripped). If not one of the four supported values, raise `ValueError`.
   - Read `objective`; if blank, raise `ValueError`.
   - Build `intent = _compose_intent(args)` — a single block joining the present intent fields under labeled headers (Objective / Audience / Scope / Non-Goals / Instructions).
   - If `handoff_type == "custom"`: require non-empty `custom_sections` (dict of str→str); raise `ValueError` otherwise. Build `Handoff(sections=custom_sections, title=title or None, instructions=intent, primitive_id=_next_primitive_id())`.
   - Else: look up the subclass in `_SCHEMA_REGISTRY` and build `cls(title=title or None, instructions=intent, primitive_id=_next_primitive_id())` (no `sections=` so the subclass keeps its rich `default_sections`).
4. Wrap `_resolve_spec` in `try/except ValueError` → return `ToolResult.error` with the message.
5. `produced = await _generate(spec)` where `_generate` calls `await self._agent.handoff(spec)`.
6. `self._agent.record_handoff(produced)`.
7. `return _render_result(produced)` — `ToolResult.success` with `output = produced.to_context_text()` and metadata: `{"primitive_id": produced.primitive_id, "handoff_type": handoff_type, "sections": dict(produced.sections)}`, plus `extra_sections` / `raw_output` from `produced.metadata` when present.

`_next_primitive_id` returns `f"handoff:{len(self._agent.handoffs) + 1}"`.

`_compose_intent` only includes fields that are non-empty, so a minimal call (just `objective`) yields a compact instruction block.

#### Edge Cases & Error Handling
- **No agent bound:** returns error (defensive; should not happen once attached to a `BaseAgent`).
- **Unknown `handoff_type`:** `ValueError` → tool error listing supported values.
- **Blank `objective`:** `ValueError` → tool error. (Note: `BaseTool.validate_call` cannot enforce this because we use `input_schema`, not `parameters`; we validate explicitly.)
- **`custom` without `custom_sections`:** `ValueError` → tool error.
- **`custom_sections` not a dict / values not strings:** coerce values via `str(...)`; if the container is not a mapping, treat as missing → error.
- **Generation raises:** the `ToolExecutor` already wraps `execute` exceptions into `ToolResult.error`; additionally, generator-level partial/unparseable output is non-fatal inside `HandoffAgent` (it stores `raw_output`/`extra_sections`), and we surface those in metadata.
- **No `context_manager`:** handled in `record_handoff`/`_sync_handoff_primitive` (skips sync).

### 6.2 handoff builtin package init

**File(s):** `vidbyte/tools/builtins/handoff/__init__.py`
**Type:** New file

#### What it does
Re-exports `CreateHandoffTool` for the builtins namespace.

#### Interface / API
```python
from vidbyte.tools.builtins.handoff.create import CreateHandoffTool
__all__ = ["CreateHandoffTool"]
```

### 6.3 builtins namespace export

**File(s):** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

#### What it does
Adds `CreateHandoffTool` to the builtins imports and `__all__`.

#### Logic / Algorithm
1. `from vidbyte.tools.builtins.handoff import CreateHandoffTool`.
2. Add `"CreateHandoffTool"` to `__all__`.

### 6.4 top-level package export

**File(s):** `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Exposes `CreateHandoffTool` at the package root, alongside `ContextUpsertTool` etc.

#### Logic / Algorithm
1. Import `CreateHandoffTool` from `vidbyte.tools.builtins.context_primitives`'s neighboring import block (i.e., from `vidbyte.tools.builtins.handoff`).
2. Add `"CreateHandoffTool"` to the root `__all__`.

### 6.5 BaseAgent handoff collection + recording

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Adds a per-run `handoffs` list, a `record_handoff` method that appends + updates `last_handoff` + syncs to the registry, and routes `_run_auto_handoff` through it. Extends `_bind_agent_tool_context` to bind `CreateHandoffTool`.

#### Interface / API
```python
self.handoffs: list[Handoff] = []                 # added in __init__, after self.last_handoff

def record_handoff(self, handoff: Handoff) -> None: ...
def _sync_handoff_primitive(self, handoff: Handoff) -> None: ...
```

#### Logic / Algorithm
1. In `__init__`, after `self.last_handoff = None`, add `self.handoffs = []`.
2. `record_handoff(handoff)`: append to `self.handoffs`, set `self.last_handoff = handoff`, call `self._sync_handoff_primitive(handoff)`.
3. `_sync_handoff_primitive(handoff)`: if `self.context_manager is None` or `not handoff.primitive_id`, return; else `try: self.context_manager.upsert(handoff) except ValueError: return` (frozen/invalid id is non-fatal).
4. In `_run_auto_handoff`, replace `self.last_handoff = produced` with `self.record_handoff(produced)` (keeps `metadata["handoff"] = produced`). The failure branch still sets `self.last_handoff = None`.
5. In `_bind_agent_tool_context`, add a local import of `CreateHandoffTool` and `if isinstance(tool, CreateHandoffTool): tool.bind_agent(self)`.

#### Edge Cases & Error Handling
- **`fork`/clone:** new agents construct via `__init__`, so `handoffs` starts empty (per-run semantics, matching how `history` is treated). No copy of `handoffs`.
- **Frozen primitive id collision:** `upsert` raises `ValueError`; `_sync_handoff_primitive` swallows it so handoff creation still succeeds.
- **Auto-handoff + manual handoff:** both flow through `record_handoff`, sharing the collection and sync path.

---

## 7. Data Model Changes

### 7.1 BaseAgent.handoffs

**Change type:** New (in-memory field)

```python
self.handoffs: list[Handoff] = []   # ordered, per-run, includes auto + on-demand handoffs
```

**Migration strategy:** N/A — new in-memory attribute, no persisted schema. Existing
`last_handoff` retained for backward compatibility and continues to reference the most
recent handoff.

### 7.2 Handoff as a context registry entry

**Change type:** None (reuse)

`Handoff` already implements the structural `ContextItem` shape consumed by
`ContextManager.upsert` / `render_primitives_zone` (`primitive_id`, `primitive_frozen`,
`kind`, `title`, `to_context_text()`). No changes required.

---

## 8. API Changes

N/A — no HTTP/RPC endpoints. The "API" surface is the new tool declaration, fully specified
by the `input_schema` in §6.1. For completeness, the tool contract:

### 8.1 TOOL create_handoff

**Change type:** New

**Request (tool arguments):**
```json
{
  "handoff_type": "string enum: engineering|research|minimal|custom (required)",
  "objective": "string - why the handoff exists / target state (required)",
  "audience": "string - receiver and their next action (optional)",
  "title": "string - title override (optional)",
  "scope": "string (optional)",
  "non_goals": "string (optional)",
  "instructions": "string - extra generator guidance (optional)",
  "custom_sections": "object<string,string> - required iff handoff_type=custom"
}
```

**Response (ToolResult):**
```json
{
  "tool_name": "create_handoff",
  "status": "success | error",
  "output": "string - rendered handoff markdown",
  "metadata": {
    "primitive_id": "handoff:<n>",
    "handoff_type": "engineering|research|minimal|custom",
    "sections": { "<title>": "<content>" },
    "extra_sections": { "<title>": "<content>" },
    "raw_output": "string (only when sections could not be parsed)"
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| error  | No agent bound to the tool |
| error  | `handoff_type` missing or not in the supported set |
| error  | `objective` missing/blank |
| error  | `handoff_type=custom` with missing/empty `custom_sections` |
| error  | Generation raised (normalized by `ToolExecutor`) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/create-handoff-tool.md` | This design doc |
| CREATE | `vidbyte/tools/builtins/handoff/__init__.py` | Export `CreateHandoffTool` |
| CREATE | `vidbyte/tools/builtins/handoff/create.py` | The `CreateHandoffTool` implementation |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Add `CreateHandoffTool` to imports + `__all__` |
| MODIFY | `vidbyte/__init__.py` | Top-level export of `CreateHandoffTool` |
| MODIFY | `vidbyte/agents/base.py` | Add `handoffs` list, `record_handoff`/`_sync_handoff_primitive`, route `_run_auto_handoff`, bind tool |
| CREATE | `tests/test_create_handoff_tool.py` | Unit tests (pytest convention) |
| CREATE | `scripts/test_create_handoff_tool.py` | Phase 5 standalone verification script |

---

## 10. Testing Plan

The generator (`HandoffAgent`/`BaseAgent.handoff`) makes a model call. Tests use a
**fake agent / stub** that records the spec it received and returns a deterministic filled
`Handoff` via `spec.fill(...)`, so we test the tool's resolution, recording, syncing, and
error handling without a live model. A separate test exercises the real `BaseAgent`
recording/sync path directly via `record_handoff`.

### Unit Tests
- `CreateHandoffTool` → `resolves engineering/research/minimal to the correct Handoff subclass with default sections preserved` — [Edge Case]
- `CreateHandoffTool` → `builds a custom Handoff from custom_sections` — [Edge Case]
- `CreateHandoffTool` → `returns error when handoff_type is unknown` — [Hidden Assumption] (input not pre-validated by `validate_call`)
- `CreateHandoffTool` → `returns error when objective is missing/blank` — [Hidden Assumption]
- `CreateHandoffTool` → `returns error when custom selected but custom_sections missing/empty` — [Edge Case]
- `CreateHandoffTool` → `returns error when no agent is bound` — [Hidden Assumption]
- `CreateHandoffTool` → `composes intent fields into spec.instructions and only includes present fields` — [Silent Failure] (would otherwise emit empty/garbled labels)
- `CreateHandoffTool` → `passes title override into the spec` — [Silent Failure]
- `CreateHandoffTool` → `assigns a non-empty primitive_id and increments it across multiple calls` — [Silent Failure] (off-by-one / duplicate ids overwrite registry entries)
- `CreateHandoffTool` → `appends each produced handoff to agent.handoffs in order` — [Edge Case] (0, 1, N calls)
- `CreateHandoffTool` → `does not mutate custom_sections caller dict / coerces non-string values` — [Hidden Failure]
- `CreateHandoffTool` → `surfaces extra_sections and raw_output from produced metadata into the result` — [Silent Failure] (produced-but-unparsed content must not be lost)
- `BaseAgent.record_handoff` → `appends, updates last_handoff, and upserts into context_manager` — [Edge Case]
- `BaseAgent.record_handoff` → `does not fail when context_manager is None` — [Hidden Assumption]
- `BaseAgent.record_handoff` → `skips sync (no raise) when the existing primitive is frozen` — [Hidden Failure]
- `BaseAgent._bind_agent_tool_context` → `binds the agent into a CreateHandoffTool added at construction and via add_tool` — [Hidden Assumption] (tool unusable if not bound)
- `BaseAgent` → `forked/cloned agent starts with empty handoffs` — [Silent Failure] (cross-run leakage)

### Integration Tests
- End-to-end with a stubbed `agent.handoff` that returns a filled handoff: call the tool twice with different `handoff_type`s; assert two entries in `agent.handoffs`, two distinct `primitive_id`s, and two entries visible via `ContextListTool` as `(handoff)`. Silent-failure path watched: a second handoff overwriting the first in the registry due to duplicate id.
- Real `ContextManager` (no model): construct a `Handoff` with an id, call `agent.record_handoff`, then render `context_manager.render_primitives_zone()` and confirm the handoff text appears. Hidden assumption surfaced: that `Handoff` satisfies the registry's `to_context_text()`/`title` contract.
- Mock vs real: the model/runner is the only mocked dependency; `ContextManager`, `Handoff`, and `BaseAgent` are real.

### Manual / QA Test Cases
1. Given an agent with a `ContextManager`, when an agent run calls `create_handoff(handoff_type="engineering", objective="...")` then later `create_handoff(handoff_type="custom", custom_sections={...}, objective="...")`, then `agent.handoffs` has 2 items and both appear in the context window primitives zone — [Edge Case: N calls].
2. Given an agent with **no** `ContextManager`, when `create_handoff` is called, then it still succeeds and `agent.handoffs` has 1 item — [Hidden Assumption].
3. Given `create_handoff(handoff_type="custom")` with no `custom_sections`, then the tool returns an error result and `agent.handoffs` is unchanged — [Edge Case].
4. Given `create_handoff(handoff_type="bogus", objective="x")`, then the tool returns an error naming the supported types — [Hidden Assumption].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.context.handoff.*` | in-repo | Handoff schemas | Low — stable, reused |
| `vidbyte.agents.handoff.HandoffAgent` (via `BaseAgent.handoff`) | in-repo | Generation | Low — reused, not modified |
| `vidbyte.context.manager.ContextManager` | in-repo | Primitive sync | Low — `upsert` already supports the shape |
| Model provider (through agent runner) | configured per agent | Generates handoff content | Medium — one extra model call per tool call (cost/latency) |

---

## 12. Rollout & Deployment

- **Feature flags:** None. The tool is opt-in — it only exists in an agent's run if the developer adds `CreateHandoffTool()` to the agent's `tools`.
- **Breaking change:** No. New additive field/method on `BaseAgent`; `last_handoff` semantics preserved. `_run_auto_handoff` now also appends to `handoffs` (additive).
- **Deployment order:** Single package; no cross-service ordering.
- **Rollback:** Revert the PR; no migrations or persisted state.

---

## 13. Open Questions

- [ ] `primitive_id` scheme: `handoff:<n>` (monotonic per run) — acceptable, or prefix with type/run id (e.g., `handoff:engineering:1`)? Default chosen: `handoff:<n>`.
- [ ] Should `extra_sections` produced by the generator be merged into `produced.sections` or kept only in metadata? Default chosen: keep in metadata (lossless, non-destructive).
- [ ] Should there be a soft cap on handoffs per run to bound model spend? Default chosen: no cap in v1 (documented as a follow-up).
- [ ] Should `record_handoff` be public API surface in `__all__`/docs, or internal? Default chosen: public method on `BaseAgent` (no separate export needed).

---

## 14. Alternatives Considered

### Alternative 1: Tool constructs its own HandoffAgent
- What: Instead of calling `BaseAgent.handoff(spec)`, the tool builds `HandoffAgent.from_source_agent(agent, spec)` and calls `generate_handoff` directly.
- Why rejected: `BaseAgent.handoff` already does exactly this and is the public seam; calling it keeps one generation path and less duplication.

### Alternative 2: Agent authors section prose in tool args (serializer model)
- What: The calling agent writes all section content; the tool only validates and fills.
- Why rejected: User explicitly wants every handoff routed through a `HandoffAgent` generator, and wants the tool to be a real generative component, not a serializer.

### Alternative 3: Flat `parameters` with a JSON-string `custom_sections`
- What: Avoid `input_schema`; pass `custom_sections` as a JSON string parsed in `execute`.
- Why rejected: `input_schema` is verified-honored by the formatter, giving the model a typed nested object — cleaner contract and fewer parse failures. (Flat params remain the fallback if `input_schema` is absent.)

### Alternative 4: New `HandoffContextItem` primitive type
- What: Add a dedicated context primitive wrapping a handoff before syncing.
- Why rejected: `Handoff` already satisfies the registry contract; a wrapper adds code with no benefit.

---

END OF DESIGN DOC

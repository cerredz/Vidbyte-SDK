# Design Doc: Context Edit and Recite Tools

**Status:** Draft  
**Author:** Claude  
**Created:** 2026-07-08  
**Last Updated:** 2026-07-08  

---

## 1. Overview

This feature adds two agent-facing context-window tools to the Vidbyte SDK: `context_edit` and `context_recite`. `context_edit` lets an agent surgically correct a managed primitive in the live `ContextManager` registry (for example after a user corrects wrong goal/plan/memory text). `context_recite` re-emits a named primitive at `END_OF_CONVERSATION` placement so it lands in the model's most recent attention span, generalizing Manus-style recitation onto the existing conversation-placement substrate. Both tools follow the established `context_upsert` / `context_list` / `context_remove` pattern: constructor-injected manager, opt-in mounting, no auto-attach, no runtime loop redesign.

---

## 2. Goals & Non-Goals

### Goals

- Ship `ContextEditTool` (`context_edit`) that exact-matches and replaces a unique string occurrence inside a managed primitive, then re-upserts the updated frozen dataclass while preserving placement.
- Ship `ContextReciteTool` (`context_recite`) that upserts a copy of a named source primitive at `ContextWindowPlacement.END_OF_CONVERSATION` so `AgentRuntime._build_conversation_messages` appends it after history.
- Enforce frozen-primitive protection on edit (refuse mutation of `primitive_frozen=True` sources).
- Allow recitation of frozen sources as a non-frozen copy (read-only projection into recent attention).
- Export both tools through the same public surfaces as the existing context-primitive tools.
- Update skill/docs that list model-callable context tools so agents discover the new tools.
- Keep existing `context_upsert` / `context_list` / `context_remove` behavior unchanged.

### Non-Goals

- `context_expire` and `context_reorder` (explicitly deferred; not part of this change).
- Per-primitive create family, `context_view`, `context_stats`, `context_move`, or the broader `context_window_tools()` factory from `docs/pre-design/context-window-editing-tools.md` (can land later; this PR only adds edit + recite).
- Editing conversation history messages, standing `BaseAgent.context_items`, or tool-call transcripts.
- Dual placement of a single `primitive_id` without a copy (one id still has one placement).
- Named-condition TTL, iteration expiry ticking, or any `AgentRuntime` lifecycle changes.
- Auto-attaching these tools to agents (still opt-in; only `IsDoneTool` is auto-attached).
- New primitive types or changes to `binds_to_primitive` output capture.
- Dedicated automated tests for this feature (per design-doc-no-tests workflow; existing patterns remain available for a follow-up).

---

## 3. Background & Context

### Why now

Agents already have coarse registry mutation (`context_upsert` replaces whole content; `context_remove` deletes). They lack:
1. A surgical correction path when a user says “that’s wrong — change X to Y” without rebuilding the whole primitive.
2. An attention mechanism to re-surface goal/plan/constraints into the end of the conversation, where recent-token bias helps long loops (Manus recitation pattern).

### Current state

| Piece | Location | Status |
|-------|----------|--------|
| `ContextUpsertTool` / `ContextListTool` / `ContextRemoveTool` | `vidbyte/tools/builtins/context_primitives/` | Shipped |
| `ContextManager` registry + `upsert(..., placement=)` + `_placements` | `vidbyte/context/manager.py` | Shipped |
| `ContextWindowPlacement` including `END_OF_CONVERSATION` | `vidbyte/context/runtime.py` | Shipped |
| `render_conversation_messages` | `ContextManager` | Shipped |
| Runtime assembly `(*top, *messages, *end)` | `AgentRuntime._build_conversation_messages` | Shipped |
| Broader edit/view/move/create design | `docs/pre-design/context-window-editing-tools.md` | Pre-design only |

### Constraints / dependencies

- Primitives are `@dataclass(frozen=True, slots=True)` — all mutation is `dataclasses.replace` + re-upsert.
- One `primitive_id` maps to exactly one placement; recitation must use a **copy id**.
- Tools receive `ContextManager` in `__init__`, never in `execute()` (house rule from `skills/vidbyte-sdk/context-algorithm-to-tool.md`).
- Same manager instance must be shared between `BaseAgent(context_manager=...)` and tool constructors for mutations to appear on the next iteration.
- Modules require Context Protocol Headers (Description / Purpose / Architecture / Relations).
- Function signatures must stay single-line with a 1–2 line intent comment under each method (design-doc-no-tests style requirements for implementation phase).

---

## 4. Requirements

### Functional Requirements

1. `ContextEditTool` must expose tool name `context_edit` with required parameters `primitive_id`, `old_string`, and `new_string`, permission `ToolPermission.SAFE`.
2. `context_edit` must look up the primitive via `ContextManager.get_by_id`. If missing, return `ToolResult.error` with an actionable message (do not raise).
3. `context_edit` must refuse when the target has `primitive_frozen=True`, returning `ToolResult.error` without mutation.
4. `context_edit` must refuse empty `old_string` (same spirit as `PatchTool` empty search).
5. `context_edit` must perform an exact unique-match replacement across editable string and string-tuple fields of the primitive (see §6.2). If total match count is 0 or greater than 1, return `ToolResult.error` without mutation.
6. On successful match, `context_edit` must rebuild the primitive with `dataclasses.replace`, re-upsert it with the **existing placement** when known (`placement_for`), otherwise `END_OF_CONTEXT`, and return `ToolResult.success` naming the id.
7. `ContextReciteTool` must expose tool name `context_recite` with required parameter `primitive_id` and optional `slot_id` (string), permission `ToolPermission.SAFE`.
8. `context_recite` must look up the source primitive; if missing, return `ToolResult.error`.
9. `context_recite` must upsert a **copy** of the source with:
   - `primitive_id` = `slot_id` if provided and non-empty after strip, else `recite:{source_primitive_id}`
   - `primitive_frozen=False` (even when source is frozen)
   - title updated to a recitation label when the type has a settable `title` field (prefix `Recite: ` only if not already prefixed)
   - placement = `ContextWindowPlacement.END_OF_CONVERSATION`
10. Re-reciting the same source into the same slot must overwrite the previous recitation copy (upsert semantics).
11. Recitation must leave the source primitive’s id and placement unchanged.
12. After recitation, `render_conversation_messages(END_OF_CONVERSATION)` must include the copy’s `to_context_text()` as an assistant message content (existing manager behavior; no runtime change required).
13. Both tools must never raise from `execute()` for expected failure modes; convert `ValueError` from `upsert` into `ToolResult.error`.
14. Both tools must be exported from `vidbyte/tools/builtins/context_primitives/__init__.py`, `vidbyte/tools/builtins/__init__.py`, and `vidbyte/__init__.py`.
15. Skill docs that document the context-primitive tool family must list `ContextEditTool` and `ContextReciteTool`.

### Non-Functional Requirements

- **Performance:** In-memory only; O(field text size) string counts; no model I/O.
- **Scalability:** Registry size remains developer/agent-managed; no new caps in this PR.
- **Security:** Both tools are `ToolPermission.SAFE`; no filesystem or network access. Frozen developer-owned primitives cannot be rewritten via edit. Recitation is a projection, not a privilege escalation into frozen mutation.
- **Observability:** No new logging; tool calls already appear in traces via existing tool-call recording.
- **Reliability:** Deterministic exact-match semantics; errors are steering strings for the model.
- **Compatibility:** Additive only; existing tool names and manager APIs keep current behavior. No breaking schema changes to primitives.

---

## 5. High-Level Design

The feature is additive inside the existing `context_primitives` tool package. Two new `BaseTool` subclasses mirror `ContextUpsertTool`: each stores a `ContextManager` reference and mutates the shared registry. No changes to `AgentRuntime` are required because:

- Edit updates a registry entry; the next iteration’s `render_primitives_zone()` / conversation placement rendering already re-reads the registry.
- Recite upserts with `END_OF_CONVERSATION`; `_build_conversation_messages` already appends those messages after history.

Optional small helpers on `ContextManager` (`edit_text` / `recite`) keep tools thin and centralize placement-preserving upsert and copy construction. Prefer **manager methods** for recite and placement-preserving re-upsert so algorithms could reuse them later without importing tools; keep field-level string matching logic inside the edit tool (or a private helper module next to the tool) because it is tool-oriented exact-match policy, not core registry semantics.

```
Developer:
  mgr = ContextManager()
  agent = BaseAgent(context_manager=mgr, tools=[ContextEditTool(mgr), ContextReciteTool(mgr), ...])

Model loop:
  context_edit(primitive_id, old_string, new_string)
       → get_by_id → unique field match → dataclasses.replace → upsert(same placement)
  context_recite(primitive_id, slot_id?)
       → get_by_id → copy with recite id → upsert(END_OF_CONVERSATION)

Next iteration:
  system   = fixed + primitives_zone(TOP/END_OF_CONTEXT) + body
  messages = TOP_OF_CONVERSATION + history + END_OF_CONVERSATION   ← recited copy appears here
```

**Key decisions:**
1. Edit targets **managed primitives only**, not history — matches product correction workflow when wrong beliefs live in named primitives.
2. Recite uses a **copy id** because one id can have only one placement.
3. Default recitation slot is `recite:{source_id}` so multiple sources can be recited without stomping each other; optional `slot_id` supports a Manus-like single sticky slot (`recite:active`).
4. Frozen sources may be recited (copy is unfrozen) but not edited.

---

## 6. Detailed Design

### 6.1 ContextManager placement-preserving helpers (optional but recommended)

**File(s):** `vidbyte/context/manager.py`  
**Type:** Modified

#### What it does

Adds two small public methods so tools do not re-implement placement preservation and recitation copy placement:

- `upsert_preserving_placement(item)` — upserts using current placement for that id when present, else `END_OF_CONTEXT`.
- `recite(primitive_id, *, slot_id=None) -> str` — builds/returns the recitation id used, upserts copy at `END_OF_CONVERSATION`.

#### Interface / API

```python
def upsert_preserving_placement(self, item: ContextItem) -> "ContextManager":
    # Re-upserts item using its prior placement when known; default END_OF_CONTEXT.

def recite(self, primitive_id: str, *, slot_id: str | None = None) -> str:
    # Copies source to END_OF_CONVERSATION under slot_id or recite:{id}; returns recitation id.
```

#### Logic / Algorithm

**`upsert_preserving_placement`:**
1. Read `primitive_id` from item; if falsy, raise `ValueError` (same as `upsert`).
2. `placement = self.placement_for(primitive_id) or ContextWindowPlacement.END_OF_CONTEXT`
3. `return self.upsert(item, placement=placement)`

**`recite`:**
1. `source = self.get_by_id(primitive_id)`; if None, raise `ValueError(f"Unknown primitive '{primitive_id}'")`.
2. Resolve `target_id = (slot_id or "").strip() or f"recite:{primitive_id}"`.
3. If source is not a dataclass, raise `ValueError`.
4. Build kwargs for `dataclasses.replace`: always set `primitive_id=target_id`, `primitive_frozen=False`; if field `title` exists, set to `source.title` if already starts with `"Recite: "` else `f"Recite: {source.title}"`.
5. `copy = dataclasses.replace(source, **kwargs)`.
6. `self.upsert(copy, placement=ContextWindowPlacement.END_OF_CONVERSATION)`.
7. Return `target_id`.

#### Edge Cases & Error Handling

- Missing source → `ValueError` caught by tool → `ToolResult.error`.
- Frozen source → still recite (copy unfrozen).
- Frozen recitation slot already present → `upsert` raises if that *slot* is frozen; tool converts to error. Recitation copies default unfrozen so this is rare.
- Non-dataclass ContextItem protocol objects → error.

---

### 6.2 ContextEditTool

**File(s):** `vidbyte/tools/builtins/context_primitives/edit.py`  
**Type:** New file

#### What it does

Exact unique string replacement inside a managed primitive’s editable fields, then placement-preserving re-upsert.

#### Interface / API

```python
class ContextEditTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...
    def spec(self) -> ToolSpec: ...  # name="context_edit"
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

**ToolSpec parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `primitive_id` | string | yes | Id of managed primitive to edit |
| `old_string` | string | yes | Exact text to find (must match exactly once) |
| `new_string` | string | yes | Replacement text |

Description should steer the model: use for correcting wrong content after user feedback; prefer `context_list` first; use `context_upsert` for full rewrites.

#### Logic / Algorithm

1. Parse and strip `primitive_id`; read `old_string` / `new_string` as strings (do not strip body strings — whitespace may be intentional).
2. If `primitive_id` empty → error.
3. If `old_string == ""` → error (`old_string cannot be empty`).
4. `item = manager.get_by_id(primitive_id)`; missing → error.
5. If `getattr(item, "primitive_frozen", False)` → error (frozen cannot be edited).
6. If not `dataclasses.is_dataclass(item)` → error.
7. Walk fields via `dataclasses.fields(item)` and classify editable values:
   - **Skip** fields named: `kind`, `primitive_id`, `primitive_frozen`, `metadata` (and non-str non-tuple types).
   - **String fields:** count `value.count(old_string)`; if > 0, record as candidate with match count.
   - **Tuple fields where every element is `str`:** for each element, count matches; sum counts for the field; track which index/indices match for replacement.
8. Sum total matches across all candidate fields:
   - 0 → error: not found; suggest exact spacing.
   - \>1 → error: ambiguous; ask for more unique `old_string`.
   - 1 → determine the single field (and tuple index if needed) and build replacement value.
9. `updated = dataclasses.replace(item, **{field_name: new_value})`.
10. `manager.upsert_preserving_placement(updated)` (or manual placement_for + upsert).
11. Success message: `Primitive '{id}' edited successfully.`

#### Edge Cases & Error Handling

| Condition | Result |
|-----------|--------|
| Missing id | error |
| Frozen | error, no mutation |
| Empty old_string | error |
| No match | error |
| Multiple matches (same field or across fields) | error |
| Match only in skipped fields (`kind`, etc.) | treated as no match |
| `new_string` empty | allowed (deletion of matched span) |
| Plan step unique match | replace that one step string in the tuple |
| Task `goal` unique match | replace `goal` |
| Text/document/memory `content` | replace `content` |
| File with `content=None` and no other match | no match error |

**Note:** This is strictly more general than the pre-design’s “content field only” sketch, but required for task/plan primitives that store primary text in `goal` / `steps` rather than `content`. Still exact unique match only — no fuzzy edit.

---

### 6.3 ContextReciteTool

**File(s):** `vidbyte/tools/builtins/context_primitives/recite.py`  
**Type:** New file

#### What it does

Re-emits a named primitive at end-of-conversation attention via a managed copy.

#### Interface / API

```python
class ContextReciteTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...
    def spec(self) -> ToolSpec: ...  # name="context_recite"
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

**ToolSpec parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `primitive_id` | string | yes | Source primitive to recite |
| `slot_id` | string | no | Optional fixed recitation id; default `recite:{primitive_id}` |

Description should explain: re-surfaces the primitive at the end of the conversation for recent attention; does not remove the original; call again after editing the source to refresh the recitation.

#### Logic / Algorithm

1. Parse `primitive_id` (strip); empty → error.
2. Optional `slot_id` from args (strip or None).
3. Call `manager.recite(primitive_id, slot_id=slot_id or None)` inside try/except `ValueError`.
4. Success: `Primitive '{source}' recited to END_OF_CONVERSATION as '{target_id}'.`

#### Edge Cases & Error Handling

| Condition | Result |
|-----------|--------|
| Missing source | error |
| Frozen source | success (copy unfrozen) |
| Existing unfrozen recitation slot | overwrite |
| Existing frozen recitation slot | error from upsert |
| Source itself already at END_OF_CONVERSATION | still create copy with recite id (may duplicate text in end zone — acceptable; agent can remove if needed) |

No change to `AgentRuntime` — existing path:

```python
top = render_conversation_messages(TOP_OF_CONVERSATION)
end = render_conversation_messages(END_OF_CONVERSATION)
return (*top, *messages, *end)
```

---

### 6.4 Package exports

**File(s):**
- `vidbyte/tools/builtins/context_primitives/__init__.py` (Modified)
- `vidbyte/tools/builtins/__init__.py` (Modified)
- `vidbyte/__init__.py` (Modified)

#### What it does

Export `ContextEditTool` and `ContextReciteTool` alongside existing three tools.

#### Logic

- Import new classes.
- Add to `__all__` in each package (alphabetically consistent with neighbors where already ordered).

---

### 6.5 Skill / usage docs

**File(s):**
- `skills/vidbyte-sdk/context-primitives.md` (Modified)
- `skills/usage/available_tools.md` (Modified)
- `skills/vidbyte-sdk-doc/SKILL.md` (Modified) — only the line listing context_primitives exports

#### What it does

Document the two new tools with mount examples matching existing upsert/list/remove snippets.

---

## 7. Data Model Changes

### 7.1 Context primitives

**Change type:** None  

No field changes on `TextContextItem`, `TaskContextItem`, etc.

### 7.2 ContextManager internal state

**Change type:** None required  

Uses existing `_registry` and `_placements`. Recitation stores a normal registry entry with `END_OF_CONVERSATION` placement.

### 7.3 Tool argument shapes

**Change type:** New (model-facing only)

```json
// context_edit
{
  "primitive_id": "string",
  "old_string": "string",
  "new_string": "string"
}

// context_recite
{
  "primitive_id": "string",
  "slot_id": "string (optional)"
}
```

**Migration strategy:** N/A — additive tools; no persisted schema.

---

## 8. API Changes

N/A as HTTP API — this feature is an in-process SDK tool API.

### 8.1 New Python types

| Symbol | Module | Kind |
|--------|--------|------|
| `ContextEditTool` | `vidbyte.tools.builtins.context_primitives.edit` | New class |
| `ContextReciteTool` | `vidbyte.tools.builtins.context_primitives.recite` | New class |
| `ContextManager.upsert_preserving_placement` | `vidbyte.context.manager` | New method |
| `ContextManager.recite` | `vidbyte.context.manager` | New method |

### 8.2 Mounting (developer usage)

```python
from vidbyte.context import ContextManager
from vidbyte.tools.builtins.context_primitives import (
    ContextEditTool,
    ContextListTool,
    ContextReciteTool,
    ContextRemoveTool,
    ContextUpsertTool,
)

mgr = ContextManager()
tools = [
    ContextUpsertTool(mgr),
    ContextListTool(mgr),
    ContextRemoveTool(mgr),
    ContextEditTool(mgr),
    ContextReciteTool(mgr),
]
agent = BaseAgent(..., context_manager=mgr, tools=tools)
```

### 8.3 Error cases (tool results)

| Tool | Condition | ToolResult |
|------|-----------|------------|
| edit | missing / frozen / empty old / 0 match / multi match | `error` string |
| recite | missing source / frozen slot conflict | `error` string |
| either | unexpected upsert ValueError | `error` with exception message |

No HTTP status codes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-edit-and-recite-tools.md` | This design doc |
| CREATE | `vidbyte/tools/builtins/context_primitives/edit.py` | `ContextEditTool` |
| CREATE | `vidbyte/tools/builtins/context_primitives/recite.py` | `ContextReciteTool` |
| MODIFY | `vidbyte/context/manager.py` | `upsert_preserving_placement`, `recite` |
| MODIFY | `vidbyte/tools/builtins/context_primitives/__init__.py` | Export new tools |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export new tools |
| MODIFY | `vidbyte/__init__.py` | Root public exports |
| MODIFY | `skills/vidbyte-sdk/context-primitives.md` | Document tools |
| MODIFY | `skills/usage/available_tools.md` | Document tools |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Export list |

No deletes.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `vidbyte.tools.base.BaseTool` | in-repo | Tool contract | Low |
| Existing `ContextManager` / `ContextWindowPlacement` | in-repo | Registry + placement | Low |
| Existing `AgentRuntime` conversation assembly | in-repo | Surfaces recitation | Low — no code change; relies on current behavior |
| Python `dataclasses` | stdlib | Frozen replace | Low |

No new third-party packages.

---

## 11. Rollout & Deployment

- **Feature flags:** None. Opt-in by mounting tools.
- **Breaking change:** No. Additive public exports only.
- **Migration path:** Developers who already mount the three context tools add `ContextEditTool` / `ContextReciteTool` with the same manager instance.
- **Deployment order:** Single SDK package release; no multi-service ordering.
- **Rollback:** Revert the PR; no data migration.

---

## 12. Open Questions

- [x] **Edit scope = managed primitives only (not history)?** Yes — decided; history rewrite out of scope.
- [x] **Recite = copy at END_OF_CONVERSATION?** Yes — decided; default id `recite:{source}`.
- [x] **Expire / reorder in this PR?** No — explicit non-goals.
- [ ] **Should re-edit of source auto-refresh existing `recite:{id}` copies?** Proposed: **no** in v1; tool description tells the agent to call `context_recite` again after edit. Auto-refresh can be a follow-up.
- [ ] **Should `title` itself be editable?** Proposed: **yes** (title is a string field not in the skip list). If that causes accidental multi-match ambiguity with body text, agent supplies a more unique `old_string`.
- [ ] **Conversation message role remains `"assistant"` for recitations?** Proposed: **yes** — keep existing `render_conversation_messages` behavior; changing role is a separate placement design discussion.

Unless the user objects at approval time, implementers should take the proposed defaults above.

---

## 13. Alternatives Considered

### Alternative 1: Edit conversation history messages

- **What:** Address prior user/assistant turns by index and rewrite them after correction.
- **Why rejected:** History is outside the managed registry; tool-call pairing, traces, and compaction all assume history integrity. Explicit non-goal; would need a separate `history_edit` design.

### Alternative 2: Recite by moving placement (no copy)

- **What:** `set_placement(id, END_OF_CONVERSATION)` only.
- **Why rejected:** Removes the primitive from the system primitives zone; not dual attention. User/spec asked for re-emit/copy semantics.

### Alternative 3: Dual-render same id in zone + conversation

- **What:** Manager renders one registry entry in two placements.
- **Why rejected:** Breaks the one-id/one-placement invariant and complicates remove/list semantics; copy is simpler and already fits upsert.

### Alternative 4: Edit only `content` field

- **What:** Pre-design sketch limited to `content`.
- **Why rejected for this PR:** Task/plan primitives store primary text in `goal` / `steps`. Unique-match across string/tuple fields keeps exact-match safety while supporting real correction workflows.

### Alternative 5: Full create-family + factory in same PR

- **What:** Implement entire `context-window-editing-tools` pre-design.
- **Why rejected:** User asked only for `context_edit` and `context_recite`. Scope control.

### Alternative 6: Fuzzy / regex edit

- **What:** Regex or whitespace-normalized match.
- **Why rejected:** Ambiguous and unsafe for agent tools; match `PatchTool` exact unique semantics.

---

## Implementation Notes (for Phase 4)

- Branch: `feat/context-edit-and-recite-tools` from clean `main` via git worktree (not the current local feature branch).
- First commit: this design doc only.
- Class-first tools; single-line method signatures; 1–2 line comments under every method; Context Protocol Headers on new modules.
- Prefer short private helpers on the edit tool for field walk / match / replace rather than one giant `execute`.
- Do not auto-register tools.
- No new tests required by this workflow; do not expand scope into expire/reorder.

# Design Doc: Tool Settings Contributor Skill

**Status:** Draft  
**Author:** Claude  
**Created:** 2026-07-08  
**Last Updated:** 2026-07-08  

---

## 1. Overview

Add a root-level contributor skill under `skills/tool-settings/` that documents the **process of creating and extending universal tool settings** in the Vidbyte SDK. The skill is distilled from the merged PR #259 (`feat: tool settings runtime enforcement`) and the live implementation on `main`: nested `ToolSettings` on `AgentLoopSettings`, pure decision methods on the settings object, and **runtime-inline enforcement** in `AgentRuntime` (not middleware). Contributors (and coding agents) should be able to add a new tool-settings field end-to-end without re-deriving the architecture from the design doc or source.

---

## 2. Goals & Non-Goals

### Goals

- Create `skills/tool-settings/SKILL.md` at the repo skills root (contributor-facing; not packaged in the wheel).
- Explain what `ToolSettings` is, how it differs from `AgentLoopSettings` flat budgets and from middleware, and when a new constraint belongs on `ToolSettings`.
- Provide a **step-by-step authoring checklist** for adding a new setting field: class + validation → loop wiring → runtime config → runtime enforcement → guards/stop reasons → exports → docs/skills.
- Capture the hard architectural rules proven in PR #259: stateless settings, counts from `call_contexts`, never block internal tools (`isDone`), denials vs abort, truncate model-visible only, no middleware for these policies.
- Cross-link related skills (`agentic-loop-settings`, `agent-runtimes`, `sdk/update-skill-files`) and the design doc `docs/design/tool-settings-runtime-enforcement.md`.
- Optionally extend `skills/sdk/update-skill-files.md` with a "Add or Change Tool Settings" matrix row so future agents update the right files.
- Optionally add a short pointer in `skills/agentic-loop-settings/SKILL.md` that nested `tool_settings` exists and the process skill owns deep guidance (avoids duplicating two full guides).

### Non-Goals

- No runtime/code behavior changes in `vidbyte/` (this work is documentation-only).
- No unit tests, verification scripts, or pytest additions (`design-doc-no-tests` workflow).
- No new nested settings class beyond documenting the existing `ToolSettings` pattern (e.g. do not invent `SandboxSettings` here).
- No rewrite of the full agentic-loop-settings parameter tables unless needed for a one-paragraph pointer.
- No packaging of this skill under `vidbyte/skills/` (contributor skills stay in top-level `skills/`).
- No reopening of PR #249 middleware approach; the skill must teach the **runtime-enforcement** model only.

---

## 3. Background & Context

### Why now?

PR #259 landed on `main` (commit `5de8ccb`, title *feat: tool settings runtime enforcement*). It introduced:

| Piece | Path |
|-------|------|
| Settings class | `vidbyte/agents/settings/tool.py` |
| Nesting on loop settings | `vidbyte/agents/settings/loop.py` (`tool_settings` field, validation, `to_runtime_config`) |
| Runtime config field | `vidbyte/lib/dataclasses/agents.py` (`AgentRuntimeConfig.tool_settings`, `AgentStopReason.TOOL_SETTINGS_DENIED`) |
| Enforcement | `vidbyte/agents/runtime.py` (`_enforce_tool_settings`, `_apply_tool_denial`, `_truncate_for_tool_settings`, `_executed_counts`) |
| Non-linear guard | `vidbyte/agents/base.py` |
| Exports | `vidbyte/agents/settings/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py` |
| User docs | `README.md` |
| Architecture design | `docs/design/tool-settings-runtime-enforcement.md` |

There is already a **usage/reference** skill for loop budgets (`skills/agentic-loop-settings/SKILL.md`), but it pre-dates `ToolSettings` and does not teach how to *extend* the system. Process-style skills exist for analogous work (`skills/mcp-server/add-tool.md`, `skills/vidbyte-sdk/adding-context-window-algorithms.md`). Contributors need the same for tool settings.

### Problem solved

Without a skill, agents re-invent wiring (or fall back to middleware from superseded PR #249). Silent failures include: mutable counters on the shared settings object, truncating raw `ToolResult` metadata, blocking `isDone`, enforcing only at iteration boundaries, forgetting public exports, or adding fields that never reach `AgentRuntime`.

### Current state

- Local `main` (worktree `worktrees/vidbyte-sdk-main-job-applier`) was updated to `origin/main` including PR #259 and later merges.
- `skills/README.md` clarifies top-level `skills/` = contributor instructions (not shipped in the wheel).
- Nested settings siblings today: `ToolSettings` (runtime-enforced) and `ToolErrorPolicy` (middleware-oriented error retry/render) under `vidbyte/agents/settings/`.

### Constraints

- Match existing skill tone: Context Protocol Header (or YAML frontmatter where used), numbered steps, explicit "What NOT to Do", file path tables.
- Prefer one `SKILL.md` under a folder (same pattern as `skills/agentic-loop-settings/`, `skills/agent-runtimes/`) rather than a bare root `.md`, unless the user prefers a single file like `skills/sessions.md`.

---

## 4. Requirements

### Functional Requirements

1. Create `skills/tool-settings/SKILL.md` that an agent can follow without reading PR #259.
2. Document the **mental model**: config object → `AgentLoopSettings.to_runtime_config()` → `AgentRuntimeConfig.tool_settings` → inline checks in `AgentRuntime._process_tool_call` / helpers.
3. Document the **existing settings surface** (`denied_tools`, `max_calls`, `max_calls_per_tool`, `result_max_chars`, `on_deny`) with types, defaults, and runtime effects.
4. Document **when** a new constraint belongs on `ToolSettings` vs flat `AgentLoopSettings` vs middleware vs `PermissionPolicy`.
5. Provide a **numbered process** for adding a new field or decision method, including every touch file.
6. Encode **invariants**:
   - `ToolSettings` is stateless; no per-run counters on the instance.
   - Per-tool executed counts derive from `call_contexts` where `state is not DENIED`.
   - Internal tools (`tool_is_internal` / `isDone`) bypass all tool-settings enforcement.
   - Deny-and-continue injects a denied tool result the model sees; abort stops with `AgentStopReason.TOOL_SETTINGS_DENIED`.
   - `max_calls` maps to / reconciles with `max_tool_calls`; mismatch raises `ConfigurationError`.
   - `result_max_chars` truncates **model-visible** output only; raw `ToolResult` in `ToolCallContext` stays intact; denials are not truncated (`truncate=False` path).
   - Non-linear runtimes reject `tool_settings` at construction.
7. Include a minimal **usage example** (developer-facing) so the skill is usable both as process guide and quick reference.
8. Include a **What NOT to Do** section (middleware reintroduction, allowlists if out of scope, mutating settings, etc.).
9. Link to `docs/design/tool-settings-runtime-enforcement.md` and related skills.
10. Update `skills/sdk/update-skill-files.md` with an "Add or Change Tool Settings" change-type row pointing at the new skill and the code files that must stay in sync.
11. Add a short cross-link from `skills/agentic-loop-settings/SKILL.md` to `skills/tool-settings/SKILL.md` (and mention nested `tool_settings` in the implemented params or a new subsection).

### Non-Functional Requirements

- **Clarity:** Process steps must be load-bearing and ordered; an agent should not skip exports or runtime wiring.
- **Accuracy:** Content must match `main` after PR #259 (not the superseded middleware design).
- **Maintainability:** Prefer tables of touch points over long prose; cite real method names so grep stays useful.
- **Scope control:** Keep the skill under ~250–400 lines; deep narrative stays in the design doc.
- **No runtime cost:** Documentation-only; no package dependency changes.

---

## 5. High-Level Design

One new contributor skill folder documents the **ToolSettings extension process** established by PR #259. The skill has two audiences in one document:

1. **Operators / SDK users** — short "how to configure" section so the skill is discoverable when someone asks "how do tool settings work?"
2. **Contributors / coding agents** — the bulk of the skill: how to add a new setting field and enforce it correctly.

Architecture taught (ASCII):

```
Developer config
  AgentLoopSettings(tool_settings=ToolSettings(...))
        |
        v
  AgentLoopSettings.to_runtime_config()
        |
        v
  AgentRuntimeConfig.tool_settings  (+ max_tool_calls mapped from max_calls)
        |
        v
  BaseAgent  --non-linear?--> ConfigurationError
        |
        v
  AgentRuntime._process_tool_call
        |
        +--> _enforce_tool_settings   (before middleware / execute)
        |       max_calls mid-iteration stop
        |       denial() -> continue (denied result) | abort (TOOL_SETTINGS_DENIED)
        |
        +--> execute_tool_call / middleware
        |
        +--> _append_tool_result_message
                _truncate_for_tool_settings  (model-visible only)
```

**Key design decisions for the skill content:**

| Decision | Why |
|----------|-----|
| Folder `skills/tool-settings/SKILL.md` | Matches `agentic-loop-settings/` and `agent-runtimes/`; groups future subdocs if needed. |
| Process-first, not pure API catalog | User asked for "the process of creating new tool settings"; API catalog is secondary. |
| Teach runtime enforcement only | PR #259 supersedes middleware approach (#249). |
| Light updates to adjacent skills | Keep agentic-loop-settings accurate; register the change type in update-skill-files. |

Data flow for **adding** a field (what the skill will prescribe):

```
1. tool.py          add field + validate + pure decision method (if needed)
2. loop.py          only if nesting/validation/reconcile/to_runtime_config changes
3. agents.py        AgentRuntimeConfig / AgentStopReason if new wire or stop
4. runtime.py       enforce at correct chokepoint (pre-exec vs post-exec)
5. base.py          non-linear / construction guards if policy is linear-only
6. exports          settings/__init__, agents/__init__, vidbyte/__init__
7. docs             README + this skill + design doc notes + update-skill-files
```

---

## 6. Detailed Design

### 6.1 New skill: Tool Settings process guide

**File(s):** `skills/tool-settings/SKILL.md`  
**Type:** New file

#### What it does

Contributor-facing skill that explains ToolSettings architecture and the end-to-end process for adding new universal tool settings.

#### Interface / API

N/A — Markdown skill document. Suggested front matter / header:

```markdown
<!-- Context Protocol Header
Description:
    Process guide for creating and extending ToolSettings in the Vidbyte SDK.
Purpose:
    Teaches contributors how ToolSettings is wired (settings → runtime config →
    AgentRuntime enforcement) and the checklist for adding a new constraint.
Architecture:
    SDK Skill Guide (contributor process).
Relations:
    Located in skills/tool-settings/SKILL.md.
    Implementation: vidbyte/agents/settings/tool.py, loop.py, runtime.py, base.py.
    Design: docs/design/tool-settings-runtime-enforcement.md.
Similar Files:
    - skills/agentic-loop-settings/SKILL.md
    - skills/mcp-server/add-tool.md
    - skills/vidbyte-sdk/adding-context-window-algorithms.md
-->
```

Optional YAML description block (if aligning with newer skills like `paradigm/`):

```yaml
---
name: tool-settings
description: >-
  Explains ToolSettings and the process for adding new universal tool-use
  constraints enforced in the direct agent runtime. Use when adding fields to
  ToolSettings, wiring tool policy into AgentRuntime, or reviewing tool-settings PRs.
---
```

#### Logic / Algorithm (document structure)

Proposed sections (skill body):

1. **When to use this skill** — adding/changing ToolSettings fields; reviewing tool-policy PRs; not for PermissionPolicy or ToolErrorPolicy middleware.
2. **Mental model** — nested settings, pure decisions, runtime ownership of counts/effects.
3. **Existing settings reference** — table of current fields and effects.
4. **Decision guide: where does my constraint live?**
   | Kind of constraint | Put it in |
   |--------------------|-----------|
   | Universal deny/cap/truncate of tool use | `ToolSettings` |
   | Loop budgets (iterations, tokens, legacy max_tool_calls) | `AgentLoopSettings` flat fields |
   | Retry/backoff/render of tool *errors* | `ToolErrorPolicy` (+ middleware) |
   | Permission / security capability gates | `PermissionPolicy` / security middleware |
   | Per-hook transforms | Middleware |
5. **Process: add a new ToolSettings field** — numbered steps (see 6.1 steps below).
6. **Process: add a new decision/effect** — denial vs stop vs transform; which helper to use.
7. **Invariants & edge cases** — isDone, concurrency, truncation, same-iteration max_calls.
8. **Usage example** — short Agent + ToolSettings snippet (from README / PR).
9. **Verification checklist** — compile/import, manual matrix of behaviors (no required pytest in this feature).
10. **What NOT to do**
11. **Related files & docs**

#### Step-by-step process the skill will mandate

**Step 1 — Add field on `ToolSettings`** (`vidbyte/agents/settings/tool.py`)

- Keyword-only ctor arg with a safe default (`None` / empty / `"continue"`-style enum).
- Normalize collections (strip names, reject `str` as iterable, frozenset/dict).
- Validate in `_validate()` / helpers; raise `ConfigurationError` (never bare `ValueError`).
- Prefer pure methods for decisions: e.g. `denial(...)`, `truncate(...)`. **No** instance mutation of run counters.
- Update `__repr__` to show active fields only.

**Step 2 — Nest / reconcile on `AgentLoopSettings`** (`vidbyte/agents/settings/loop.py`)

- Only if the new field needs loop-level reconciliation (like `max_calls` ↔ `max_tool_calls`).
- Keep `_validate_tool_settings()` type check: must be `ToolSettings` instance.
- If the field maps into an existing `AgentRuntimeConfig` budget, map it in `to_runtime_config()` and reject mismatches.
- Include `tool_settings` in `__repr__` when set (already done).

**Step 3 — Runtime config / stop reasons** (`vidbyte/lib/dataclasses/agents.py`)

- `AgentRuntimeConfig.tool_settings` already carries the whole object; usually **no new field** is needed if the setting lives only on `ToolSettings`.
- Add `AgentStopReason` members only when introducing a new **stop** outcome (do not overload `MIDDLEWARE_ABORT`).

**Step 4 — Enforce in `AgentRuntime`** (`vidbyte/agents/runtime.py`)

- Pre-execution policy (deny/stop/budget): extend `_enforce_tool_settings` / helpers; run **before** middleware `before_tool_call` so settings cannot be skipped.
- Post-execution transforms (truncate-like): apply on the model-visible path (`_model_visible_tool_result` / `_truncate_for_tool_settings`), never mutate the stored raw result.
- Skip when `settings is None` or `tool_is_internal`.
- For continue-denials: use `_denied_tool_result` + append to `call_contexts` + `_append_tool_result_message(..., truncate=False)` so denial text is not truncated.
- For abort-denials: `_stopped_result(..., stop_reason=AgentStopReason.TOOL_SETTINGS_DENIED)`.
- For total call budget mid-iteration: stop with `MAX_TOOL_CALLS` before executing the over-budget call.
- Derive counts via `_executed_counts(call_contexts)`.

**Step 5 — Construction guards** (`vidbyte/agents/base.py`)

- If the setting is only supported on the linear/direct runtime, keep/extend the non-linear `tool_settings is not None` `ConfigurationError` guard.

**Step 6 — Public exports**

- `vidbyte/agents/settings/__init__.py` — already exports `ToolSettings`; only add new public types if introduced.
- Re-exports: `vidbyte/agents/__init__.py`, `vidbyte/__init__.py` if new public symbols.
- Import paths agents must teach: `from vidbyte import ToolSettings` and `from vidbyte.agents import ToolSettings, AgentLoopSettings`.

**Step 7 — Documentation**

- `README.md` tool-settings paragraph if developer-visible behavior changes.
- This skill (`skills/tool-settings/SKILL.md`).
- Design doc under `docs/design/` for non-trivial behavior changes.
- `skills/sdk/update-skill-files.md` matrix row.
- Optionally `llms.txt` / `skills/usage/available_features.md` if the user-facing feature surface grows.

#### Edge Cases & Error Handling (skill must call out)

| Case | Expected behavior |
|------|-------------------|
| `tool_settings=None` | No behavior change vs pre-#259 |
| Blank tool name in denied/per-tool maps | `ConfigurationError` at construction |
| `max_tool_calls` ≠ `ToolSettings.max_calls` | `ConfigurationError` |
| Denied call with `on_deny="continue"` | `ToolCallState.DENIED`; excluded from executed counts |
| Multi-tool model turn near `max_calls` | Same-iteration stop before over-budget call |
| `result_max_chars=0` | Valid; body hidden except truncation marker |
| Internal `isDone` | Never denied/truncated by ToolSettings |
| Concurrent runs sharing one agent/settings | Safe only because settings are stateless |

---

### 6.2 Update skill file matrix

**File(s):** `skills/sdk/update-skill-files.md`  
**Type:** Modified

#### What it does

Adds a change-type section **"Add or Change Tool Settings"** so agents updating `ToolSettings` know which skill and code surfaces to touch.

#### Content sketch

```markdown
### Add or Change Tool Settings

**Example:** Adding a new field to `ToolSettings`, changing denial/abort/truncate
semantics, or wiring new enforcement in `AgentRuntime`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/tool-settings/SKILL.md` | Process steps, field table, invariants, NOT-to-do rules |
| `skills/agentic-loop-settings/SKILL.md` | Nested `tool_settings` pointer / stop reasons if budgets change |
| `README.md` | Developer-facing ToolSettings example if public behavior changes |
| `docs/design/tool-settings-runtime-enforcement.md` or a new design doc | Non-trivial architecture changes |
| Implementation paths | `vidbyte/agents/settings/tool.py`, `loop.py`, `runtime.py`, `base.py`, `vidbyte/lib/dataclasses/agents.py`, exports |
```

#### Edge Cases & Error Handling

- Keep the section distinct from "Add or Change Tool Error Policy" (middleware).

---

### 6.3 Cross-link from agentic-loop-settings skill

**File(s):** `skills/agentic-loop-settings/SKILL.md`  
**Type:** Modified

#### What it does

Adds a short subsection (or table row) for nested `tool_settings: ToolSettings | None` and links to `skills/tool-settings/SKILL.md` for process + deep semantics. Adds stop reason `tool_settings_denied` to the stop-reason table.

#### Logic / Algorithm

1. In parameter reference, add nested setting note under implemented settings or a new "Nested settings objects" section.
2. In stop reasons, add `"tool_settings_denied"`.
3. Link to tool-settings skill for authoring process (avoid duplicating full field docs).

#### Edge Cases & Error Handling

- Do not claim all `AgentLoopSettings` reserved fields are still accurate if they drifted; only touch tool-settings-related gaps unless an obvious one-line fix is free.

---

### 6.4 Optional: skills/README.md index line

**File(s):** `skills/README.md`  
**Type:** Modified (optional, recommended)

#### What it does

If the README grows into an index later, mention `tool-settings/`. Today it only explains contributor vs distributable skills; a single bullet is enough if we expand it. **Minimal change:** one sentence listing `skills/tool-settings/` as the process guide for ToolSettings. If the file stays a 10-line policy blurb, skip expansion and rely on folder discovery.

**Recommendation:** Add one short bullet under a "Contributor guides" list only if we introduce that list; otherwise leave `skills/README.md` unchanged to avoid scope creep.

---

## 7. Data Model Changes

N/A — no schema, dataclass, or runtime data model changes. Documentation only.

(Existing data model for reference in the skill, not changed by this work:)

```python
class ToolSettings:
    denied_tools: frozenset[str]
    max_calls: int | None
    max_calls_per_tool: dict[str, int]
    result_max_chars: int | None
    on_deny: str  # "continue" | "abort"
```

---

## 8. API Changes

N/A — no HTTP or Python public API changes. The skill documents the existing public surface:

```python
from vidbyte import Agent, ToolSettings
from vidbyte.agents import AgentLoopSettings, ToolSettings

AgentLoopSettings(
    tool_settings=ToolSettings(
        denied_tools={"delete_file"},
        max_calls=20,
        max_calls_per_tool={"search": 5},
        result_max_chars=8000,
        on_deny="continue",
    ),
)
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/tool-settings-skill.md` | This design doc |
| CREATE | `skills/tool-settings/SKILL.md` | Process + reference skill for creating/extending ToolSettings |
| MODIFY | `skills/sdk/update-skill-files.md` | Register "Add or Change Tool Settings" change-type matrix |
| MODIFY | `skills/agentic-loop-settings/SKILL.md` | Nested `tool_settings` pointer + stop reason + link to process skill |

Optional / deferred:

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `skills/README.md` | Only if we choose to expand the skills index |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None (docs only) | — | Markdown skills | Low |
| Source of truth | PR #259 / `main` | Accuracy of skill content | Medium if `main` drifts after writing — re-read files at implementation time |

No new packages, services, or feature flags.

---

## 11. Rollout & Deployment

- Documentation-only PR; no feature flag; not a breaking change.
- Target base: `main` (already contains PR #259).
- Rollout after design approval:
  1. Worktree `feat/tool-settings-skill` from `origin/main`.
  2. Commit design doc first.
  3. Write `skills/tool-settings/SKILL.md`.
  4. Patch `update-skill-files.md` and `agentic-loop-settings/SKILL.md`.
  5. Open draft PR.
- Rollback: revert the docs PR.

---

## 12. Open Questions

- [x] **Skill path:** Prefer `skills/tool-settings/SKILL.md` (folder + SKILL.md) over a bare `skills/creating-tool-settings.md`. **Recommendation: folder form** (matches `agentic-loop-settings/`). Confirm if you want a different name (`creating-tool-settings/`, `add-tool-settings/`).
- [ ] **Depth of usage vs process:** Skill will be process-first with a short usage section. Prefer a split (`SKILL.md` + `adding-a-field.md`) only if the single file exceeds readability; starting with one file.
- [ ] **Should `skills/usage/available_features.md` mention ToolSettings?** Useful for users; slightly outside "process skill" scope. **Recommendation: skip unless you want user-facing coverage in the same PR.**
- [ ] **Agentic-loop-settings accuracy pass:** That skill still lists some reserved params and omits nested objects entirely. This design only patches the ToolSettings gap; a full rewrite is out of scope unless you request it.

---

## 13. Alternatives Considered

### Alternative 1: Only extend `skills/agentic-loop-settings/SKILL.md`

- What: Fold all ToolSettings docs into the loop-settings skill.
- Why rejected: Loop settings skill is already a large parameter catalog. Process-of-extending needs steps, file manifests, and NOT-to-do rules that deserve a dedicated process skill (user asked for skill files explaining *creating* new tool settings).

### Alternative 2: Put skill under `skills/vidbyte-sdk/`

- What: e.g. `skills/vidbyte-sdk/adding-tool-settings.md` next to adding-prompts / algorithms.
- Why rejected (default): User asked for **skills root level**. Folder at root matches `agentic-loop-settings/`. Can move later if the team prefers vidbyte-sdk nesting.

### Alternative 3: Document middleware approach (PR #249)

- What: Teach auto-registered middleware enforcement.
- Why rejected: Superseded by PR #259; teaching it would recreate the dual-enforcement model intentionally removed.

### Alternative 4: Ship skill inside `vidbyte/skills/` package

- What: Distributable end-user skill via `vidbyte.skills` registry.
- Why rejected: This is contributor process documentation for the SDK repo (`skills/README.md` policy). Not a product skill for downstream agents.

---

## Appendix A — Source material used for this design

- PR: https://github.com/cerredz/Vidbyte-SDK/pull/259 (merged)
- Design: `docs/design/tool-settings-runtime-enforcement.md`
- Code: `vidbyte/agents/settings/tool.py`, `loop.py`, `runtime.py` (tool-settings helpers), `base.py` non-linear guard, `vidbyte/lib/dataclasses/agents.py`
- Existing process skill patterns: `skills/mcp-server/add-tool.md`, `skills/vidbyte-sdk/adding-context-window-algorithms.md`
- Adjacent reference skill: `skills/agentic-loop-settings/SKILL.md`

## Appendix B — Proposed skill outline (implementation will fill this)

```
# Tool Settings Skill Guide

1. When to use
2. Mental model + architecture diagram
3. Existing fields table
4. Where should my constraint live?
5. Process: add a new field (steps 1–7)
6. Process: pre-exec vs post-exec effects
7. Invariants
8. Usage example
9. Verification checklist
10. What NOT to do
11. Related files
```

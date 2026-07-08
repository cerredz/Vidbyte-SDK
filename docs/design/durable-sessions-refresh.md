# Design Doc: Durable Sessions Refresh (merge + consolidate + prebuilt session tools)

**Status:** Draft
**Author:** opencode
**Created:** 2026-07-04
**Last Updated:** 2026-07-04
**Updates:** PR #135 (`feat/durable-sessions`)

---

## 1. Overview

This PR refreshes the existing durable-sessions PR (#135, branch `feat/durable-sessions`) so it merges cleanly against current `main`, consolidates **all** session/checkpoint/fork/resume logic under `vidbyte/sessions/`, adds the durable-sessions feature to the central `llms.txt`, ships two root-level usage skills, and introduces three prebuilt developer-facing tools — `CheckpointTool`, `ForkTool`, `ResumeTool` — under `vidbyte/tools/builtins/sessions/` that let any agent checkpoint, fork, or resume its own thread or another agent's thread.

The durable-sessions feature itself (the `Session` facade, checkpoint DAG, `SessionStore` protocol, serializer, trace recorder, local + DB stores, agent `export_state()`/`restore()` seam) is unchanged in behavior. This refresh is structural and surface-expanding: resolve drift, relocate a small set of session-owned contracts, document the feature centrally, and expose it as first-class builtin tools.

---

## 2. Goals & Non-Goals

### Goals

1. **Merge freshness.** Resolve every conflict between `feat/durable-sessions` and `origin/main` (3 conflicting files + auto-merged files to verify) so the branch merges clean and reflects the current repo state.
2. **Consolidate session behavior while keeping dataclasses central.** Keep the session facade, errors, scope, store, serializer, trace recorder, and local stores in `vidbyte/sessions/`, but define the session-owned dataclasses (`RunState`, `Checkpoint`, `SessionMeta`, enums, `SESSION_SCHEMA_VERSION`) in `vidbyte/lib/dataclasses/sessions.py` per the SDK dataclass placement rule. `vidbyte/sessions/contracts.py` remains a compatibility re-export for the session namespace. Non-session provider adapters (Mongo/Supabase/Postgres/SQLite session stores) stay in `vidbyte/lib/providers/` per the existing lazy-driver convention.
3. **`llms.txt` coverage.** Add a "Durable Sessions" subsection to `llms.txt` under Core Features, add a bullet to the Feature Summary, and update the Package Map so LLM agents consuming the doc bundle discover the feature.
4. **Root-level skills.** Create `skills/sessions.md` (durable sessions usage) and `skills/forking.md` (fork/resume/time-travel patterns) in the root `skills/` folder; retire the now-duplicated `skills/vidbyte-sdk/sessions.md` by pointing it at the root skill.
5. **Prebuilt session tools.** Ship a central `SessionTool` plus granular `CheckpointTool`, `ForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, and `ResumeOutputTool` under `vidbyte/tools/builtins/sessions/`. They reuse `Session` + `SessionStore` + `SessionScope` and let an agent checkpoint/fork/rewind/resume its own current thread or another agent's thread (scope-gated). Relocate the existing combined `SessionTool` from `vidbyte/sessions/tool.py` into the builtins folder; move `SessionScope` (session logic, not a tool) to `vidbyte/sessions/scope.py`. The three resume tools differ by how another agent's thread is incorporated: **replace** (override the current context window), **append** (append the other agent's context window into the current one), **output** (append only the other agent's final output, erroring if that thread is not completed).
6. **Keep the agent pure and import-safe.** `BaseAgent` only gains the existing `export_state()`/`restore()` seam and a `_bind_agent_tool_context` branch for the new session builtins. Importing `vidbyte` still pulls no DB driver.
7. **Update repo conventions.** Rewrite the durable-sessions rule in `skills/sdk/SKILL.md` to reflect the new in-`vidbyte/sessions/` contract/error location and the builtin-tool surface.

### Non-Goals

- **No behavior change to the checkpoint DAG, serializer scrubbing, fail-open persistence, or trace capture.** Those semantics from the original design doc (`docs/design/durable-sessions.md`) are preserved.
- **No new tests or verification scripts.** Per the no-tests workflow. The existing `tests/test_durable_sessions.py` is updated only for import correctness and to drop removed-`SessionTool` cases; no new test cases are added.
- **No DB-provider relocation.** Mongo/Supabase/Postgres session stores stay in `vidbyte/lib/providers/` (lazy driver imports are a provider concern). Flagged as an open question in case the user wants full consolidation.
- **No deterministic replay, HITL interrupt, or delta checkpoints.** Still deferred per the original design doc.
- **No change to main's `SessionTracer`.** That feature groups trace spans; this PR's `TraceCapture` persists trace artifacts on checkpoints. They are complementary and do not interact.

---

## 3. Background & Context

The original durable-sessions PR (#135) was authored against `main` at commit `b8c15fa`. Since then, `main` advanced ~70 commits, adding: an artifact `sources` layer (with `llms.txt`), a `SessionTracer` under `vidbyte.trace`, paradigm harness scaffolding, LangSmith default tracing, and SDK review follow-ups. A probe merge of `origin/main` into the branch produces exactly three content conflicts, all additive-export unions:

- `vidbyte/lib/dataclasses/__init__.py` — branch added session dataclass re-exports; main added `sources` dataclass re-exports.
- `vidbyte/lib/errors/__init__.py` — branch added the `SessionError` family; main added `AggregateExecutionError` + the `SourceError` family.
- `vidbyte/lib/errors/base.py` — branch appended the `SessionError` classes; main appended the `SourceError` classes.

`README.md`, `skills/sdk/SKILL.md`, `vidbyte/__init__.py`, `vidbyte/agents/base.py`, and `vidbyte/lib/dataclasses/__init__.py` auto-merge but must be verified because both sides edited them.

The repo has two strong conventions that this refresh intentionally revises for session-owned code:

- **Dataclasses live in `vidbyte/lib/dataclasses/`.** The current `skills/sdk/SKILL.md` rule explicitly places session dataclasses at `vidbyte/lib/dataclasses/sessions.py`.
- **Errors live in `vidbyte/lib/errors/`.** The current rule places session errors there.

The user's directive ("all of the resume, checkpointing, forking logic inside `vidbyte/sessions/`") overrides these conventions **for session-owned contracts and errors only**. Non-session lib code is untouched. The `skills/sdk/SKILL.md` rule is rewritten to match.

The prebuilt-tool pattern is established by `vidbyte/tools/builtins/handoff/create.py` (`CreateHandoffTool`): a `BaseTool` subclass with a `bind_agent()`/`bind_session()` hook, a `ToolSpec` with `input_schema` JSON Schema, and async `execute()` returning `ToolResult.success`/`ToolResult.error`. `BaseAgent._bind_agent_tool_context` already binds `AgentTool`, `AttachMcpServerTool`, and `CreateHandoffTool` at agent construction; the new session builtins follow the same shape but bind to a `Session` (which wraps the agent) rather than the agent directly.

---

## 4. Requirements

### Functional Requirements

1. `git merge origin/main` into `feat/durable-sessions` completes with zero unresolved conflicts; the branch's existing tests still import and run.
2. `RunState`, `Checkpoint`, `SessionMeta`, `CheckpointPolicy`, `SessionStatus`, `TraceCapture`, and `SESSION_SCHEMA_VERSION` are importable from `vidbyte.lib.dataclasses.sessions`, `vidbyte.lib.dataclasses`, `vidbyte.sessions`, and the compatibility path `vidbyte.sessions.contracts`.
3. `SessionError`, `SessionNotFoundError`, `CheckpointNotFoundError`, `SessionSerializationError`, `SessionStoreError`, `SessionVersionError` are importable from `vidbyte.sessions` (and `vidbyte.sessions.errors`); they are **no longer** re-exported from `vidbyte.lib.errors`.
4. `SessionScope` is importable from `vidbyte.sessions` (and `vidbyte.sessions.scope`); `SessionTool` is removed from the public surface.
5. `CheckpointTool`, `ForkTool`, `ResumeTool` are importable from `vidbyte.tools.builtins` and `vidbyte.tools.builtins.sessions`; each takes a `SessionStore` (+ optional `SessionScope`) at construction and is usable as `tools=[CheckpointTool(store=store), ...]` on an agent wrapped by `Session(agent, store=store)`.
6. `Session.__init__` auto-binds any session-builtin tools found on the wrapped agent by calling `tool.bind_session(self)`, mirroring `BaseAgent._bind_agent_tool_context`. A session builtin does not function until bound (it returns an error `ToolResult`).
7. `CheckpointTool.execute` writes a checkpoint of the bound session (or a specified in-scope `session_id`) and returns the checkpoint id.
8. `ForkTool.execute` creates a new session branching from the bound session's head (or a specified in-scope `checkpoint_id`) and returns the new session id; the parent session's stored state is unchanged.
9. `ResumeTool.execute` continues an existing session: for the bound session with an earlier `checkpoint_id`, it rewinds the head (own-thread time-travel); for another in-scope `session_id`, it adopts that session's head state into the bound session as a new checkpoint (cross-thread resume). Returns the new head checkpoint id.
10. Cross-session operations on session ids outside `SessionScope` return a denied `ToolResult`, not an exception.
11. `llms.txt` contains a "Durable Sessions" subsection under Core Features, a Feature Summary bullet, and a Package Map entry for `vidbyte/sessions/` and `vidbyte/tools/builtins/sessions/`.
12. `skills/sessions.md` and `skills/forking.md` exist in the root `skills/` folder and cover attach/resume/fork/rewind/edit, and fork/time-travel patterns respectively.
13. `skills/sdk/SKILL.md` durable-sessions rule reflects the new in-`vidbyte/sessions/` contract/error location and the `vidbyte/tools/builtins/sessions/` tool surface.
14. `README.md` resolves cleanly and documents the three prebuilt tools and the new layout.
15. Importing `vidbyte` and `vidbyte.sessions` does not import `pymongo`, `psycopg`, or `supabase`.

### Non-Functional Requirements

- **Compatibility:** `vidbyte.lib.dataclasses.sessions` and the `SessionError` classes in `vidbyte.lib.errors` are removed; any external code importing them must update. This is an internal relocation on an unmerged feature branch, so no deprecation shim is required.
- **Import-safety:** the sessions package imports no DB driver; DB stores in `vidbyte/lib/providers/` import their drivers lazily and update their imports to `vidbyte.sessions.contracts`/`vidbyte.sessions.errors`.
- **Security:** `SessionScope` gating is the only cross-session access control; default is `own_runs()`. No new secret surfaces.
- **Observability:** unchanged from the original design doc.
- **Code style:** class-first; every function signature on one line; a 1–2 line comment under every signature; sparse inline comments elsewhere; Context Protocol Header on every new file.

---

## 5. High-Level Design

The refresh has four independent workstreams that compose into one PR:

```
(1) Merge freshness          (2) Consolidate logic          (3) Docs (llms.txt + skills)     (4) Prebuilt tools
─────────────────────        ─────────────────────────       ─────────────────────────        ─────────────────────────
merge origin/main            move session dataclasses        add llms.txt Durable Sessions    vidbyte/tools/builtins/sessions/
resolve 3 conflicts          -> vidbyte/sessions/contracts   add Feature Summary bullet       {checkpoint,fork,resume}.py
verify auto-merged files     move session errors             update Package Map               reuse Session + SessionStore + SessionScope
                             -> vidbyte/sessions/errors       create skills/sessions.md        Session.__init__ auto-binds
                             move SessionScope               create skills/forking.md         BaseAgent._bind_agent_tool_context
                             -> vidbyte/sessions/scope        retire skills/vidbyte-sdk/        branch for session builtins
                             delete vidbyte/sessions/tool.py  sessions.md (pointer)            remove SessionTool
                             update all imports               rewrite skills/sdk/SKILL.md      update builtins/__init__.py
                             update providers + agent         update README.md
```

### New package layout after the refresh

```
vidbyte/sessions/
    __init__.py          # re-exports (updated: drop SessionTool, add scope, re-route contracts/errors)
    contracts.py         # compatibility re-export of lib/dataclasses/sessions.py contracts
    errors.py            # NEW: SessionError family  (moved from lib/errors/base.py)
    scope.py             # NEW: SessionScope  (moved from tool.py)
    session.py           # Session facade (imports updated; + _bind_session_tools())
    store.py             # SessionStore + BaseSessionStore (imports updated)
    serialization.py     # SessionSerializer (imports updated)
    trace_capture.py     # TraceRecorder + CapturedTrace (imports updated)
    client.py            # SessionClient (unchanged)
    stores/
        __init__.py      # InMemory + File exports (imports updated)
        memory.py        # InMemorySessionStore (imports updated)
        file.py          # FileSessionStore (imports updated)

vidbyte/tools/builtins/sessions/
    __init__.py          # NEW: exports CheckpointTool, ForkTool, ResumeTool
    checkpoint.py        # NEW: CheckpointTool
    fork.py              # NEW: ForkTool
    resume.py            # NEW: ResumeTool

vidbyte/lib/providers/   # STAYS (lazy DB adapters; imports updated to vidbyte.sessions.contracts/errors)
    __init__.py
    base.py
    mongodb.py
    postgres.py
    supabase.py
```

### Prebuilt tool binding model

```
developer:
    store = FileSessionStore("./.vidbyte/sessions")
    agent = Agent(name="r", system_prompt="...", provider="openai", model_name="gpt-4.1",
                  tools=[CheckpointTool(store=store), ForkTool(store=store), ResumeTool(store=store)])
    session = Session(agent, store=store)

Session.__init__:
    wrap agent + store + id
    _bind_session_tools()  # scan agent.tools; for each SessionBuiltinTool, call tool.bind_session(self)

tool.bind_session(session):
    self._session = session
    self._scope.allow(session.id)

tool.execute(call):
    operation -> Session.checkpoint() / Session.fork() / Session.rewind() / Session.fork_from(...)
    cross-session -> scope.permits(target) ? store ops : denied ToolResult
```

---

## 6. Detailed Design

### 6.1 Merge conflict resolution

**Files:** `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/errors/__init__.py`, `vidbyte/lib/errors/base.py`
**Type:** Modified (conflict resolution + relocation)

For each conflict, take the union of both sides, **then** apply the relocation from §6.2:

- `lib/dataclasses/__init__.py`: export `RunState`, `Checkpoint`, `SessionMeta`, enums, and `SESSION_SCHEMA_VERSION` from `vidbyte.lib.dataclasses.sessions`.
- `lib/errors/__init__.py`: keep main's `AggregateExecutionError` + `SourceError` family; **remove** the `SessionError` family imports and `__all__` entries (errors moved to `vidbyte/sessions/errors.py`).
- `lib/errors/base.py`: keep main's `SourceError` classes; **remove** the `SessionError` family classes (moved to `vidbyte/sessions/errors.py`).

Auto-merged files to verify (no conflict, but both sides edited): `README.md`, `skills/sdk/SKILL.md`, `vidbyte/__init__.py`, `vidbyte/agents/base.py`. Each is reconciled in its own section below.

### 6.2 Session contracts relocation

**File:** `vidbyte/lib/dataclasses/sessions.py` (new), `vidbyte/sessions/contracts.py` (compatibility re-export)
**Type:** New + Delete

Define `RunState`, `Checkpoint`, `SessionMeta`, `CheckpointPolicy`, `SessionStatus`, `TraceCapture`, and `SESSION_SCHEMA_VERSION` in `vidbyte/lib/dataclasses/sessions.py` with an updated Context Protocol Header. Keep `vidbyte/sessions/contracts.py` as a re-export shim so existing session imports keep working. Field shapes, the frozen+slots dataclass declarations, and the persisted JSON shape from the original design doc §7.1 remain compatible.

### 6.3 Session errors relocation

**File:** `vidbyte/sessions/errors.py` (new)
**Type:** New

Move the six `SessionError` subclasses verbatim into `vidbyte/sessions/errors.py`, subclassing `VidbyteSdkError` (imported from `vidbyte.lib.errors.base` to preserve the single hierarchy root). The `details` convention is preserved.

### 6.4 SessionScope relocation + SessionTool relocation

**Files:** `vidbyte/sessions/scope.py` (new), `vidbyte/tools/builtins/sessions/session.py` (new — relocated), `vidbyte/sessions/tool.py` (deleted)
**Type:** New + New + Delete

Move `SessionScope` (with `own_runs()`, `sessions(ids)`, `all_runs()`, `allow()`, `permits()`, `allowed_ids()`) verbatim into `vidbyte/sessions/scope.py` — it is session logic (access control over session reads), not a tool. Relocate the existing `SessionTool` (the central combined tool with `create_checkpoint`/`fork_current`/`list_my_runs`/`read_run`) from `vidbyte/sessions/tool.py` into `vidbyte/tools/builtins/sessions/session.py`, updating its imports to `vidbyte.sessions.scope` and `vidbyte.sessions.store`. Delete `vidbyte/sessions/tool.py`. The granular tools in §6.6 sit alongside the relocated `SessionTool` in the same builtins subpackage.

### 6.5 Session facade + agent binding integration

**Files:** `vidbyte/sessions/session.py` (modified), `vidbyte/agents/base.py` (modified)
**Type:** Modified

`Session`:
- Update imports to `vidbyte.sessions.contracts`, `vidbyte.sessions.errors`, `vidbyte.sessions.scope`.
- Add `_bind_session_tools(self) -> None`: iterate the wrapped agent's tools; for any tool exposing a `bind_session` callable, call `tool.bind_session(self)`. Called at the end of `__init__` for new sessions and at the end of `resume`/`continue_`/`fork_from` after the agent is restored.
- Add `adopt(self, checkpoint_id: str, *, label: str = "resume") -> str`: load another session's checkpoint, restore the wrapped agent's history from it (replacing the current history), and write a new checkpoint on the current session — the **replace** semantic used by `ResumeReplaceTool`. Validates the source checkpoint exists (`CheckpointNotFoundError`); does **not** validate same-session (that is `rewind`'s job).
- Add `append_context(self, checkpoint_id: str, *, label: str = "resume") -> str`: load another session's checkpoint and **append** its history (framed as a nested `<resumed_thread>` block) to the wrapped agent's current history, then write a new checkpoint — the **append** semantic used by `ResumeAppendTool`.
- Add `append_output(self, session_id: str, *, label: str = "resume") -> str`: load the target session's meta; if `status != SessionStatus.COMPLETED`, raise `SessionError` (caught by the tool and returned as an error `ToolResult`); otherwise load the head checkpoint, extract the last assistant message, append it (framed) to the wrapped agent's history, and write a new checkpoint — the **output** semantic used by `ResumeOutputTool`.

`BaseAgent`:
- `export_state()`/`restore()` already present; update the `RunState` import to `vidbyte.lib.dataclasses.sessions`.
- `_bind_agent_tool_context`: add a branch that imports `CheckpointTool`/`ForkTool`/`RewindTool`/`ResumeReplaceTool`/`ResumeAppendTool`/`ResumeOutputTool`/`SessionTool` from `vidbyte.tools.builtins.sessions` and calls `tool.bind_session(...)` **if a session is already attached**. Because the agent is constructed before the `Session` in the common case, the authoritative binding happens in `Session._bind_session_tools()`; the agent-side branch exists only for the case where a session-bound tool is added to an already-session-backed agent.

### 6.6 Prebuilt session tools

**Files:** `vidbyte/tools/builtins/sessions/__init__.py`, `session.py`, `checkpoint.py`, `fork.py`, `rewind.py`, `resume_replace.py`, `resume_append.py`, `resume_output.py` (new); `vidbyte/tools/builtins/__init__.py` (modified)
**Type:** New + Modified

All tools subclass `BaseTool`, take `(store: SessionStore, *, scope: SessionScope | None = None)` at construction, default scope to `SessionScope.own_runs()`, expose `bind_session(session) -> None`, and return `ToolResult.success`/`ToolResult.error`. Each `ToolSpec` declares `permission=ToolPermission.SAFE`, a rich `description`, and a JSON-Schema `input_schema`. Each file's Context Protocol Header explains the tool's purpose and, for the three resume tools, how it differs from its siblings.

**`SessionTool` (`session.py`)** — central combined tool (relocated from `vidbyte/sessions/tool.py`); operations `create_checkpoint` / `fork_current` / `list_my_runs` / `read_run`; `read_run` returns a session's trace artifact (read-only observation), scoped.

**`CheckpointTool` (`checkpoint.py`)**
```
operation: checkpoint
args: session_id (optional, default = bound session), label (optional)
behavior:
  if session_id is None: bound_session.checkpoint(label=label)  -> ck id
  else if scope.permits(session_id): write a checkpoint on the target session's head via store  -> ck id
  else: denied ToolResult
returns: checkpoint id string
```

**`ForkTool` (`fork.py`)**
```
operation: fork
args: session_id (optional), checkpoint_id (optional, default = bound session head)
behavior:
  if checkpoint_id is None: bound_session.fork()  -> new session id
  else if scope.permits(source session): Session.fork_from(store, checkpoint_id)  -> new session id
  else: denied ToolResult
returns: new session id
```

**`RewindTool` (`rewind.py`)** — own-thread time-travel.
```
operation: rewind
args: checkpoint_id (required)
behavior: bound_session.rewind(to=checkpoint_id)  -> new head id
  (rewind validates same-session; a foreign checkpoint raises SessionError -> error ToolResult)
returns: new head checkpoint id
```

**`ResumeReplaceTool` (`resume_replace.py`)** — completely override the current context window with another agent's thread state.
```
operation: resume_replace
args: session_id (optional), checkpoint_id (optional, default = target head)
behavior:
  own thread (session_id is None or == bound session.id): bound_session.rewind(to=checkpoint_id)
  other thread (scope.permits): bound_session.adopt(checkpoint_id)  # replaces current history
  out of scope: denied ToolResult
returns: new head checkpoint id
```

**`ResumeAppendTool` (`resume_append.py`)** — append the other agent's context window into the current one (the other agent's history becomes a nested block inside the current context).
```
operation: resume_append
args: session_id (optional), checkpoint_id (optional, default = target head)
behavior:
  other thread (scope.permits): bound_session.append_context(checkpoint_id)  # appends framed history
  out of scope: denied ToolResult
returns: new head checkpoint id
```

**`ResumeOutputTool` (`resume_output.py`)** — append only the other agent's final output; errors if that thread is not completed.
```
operation: resume_output
args: session_id (required)
behavior:
  if not scope.permits(session_id): denied ToolResult
  else: bound_session.append_output(session_id)
    -> raises SessionError if target status != COMPLETED -> error ToolResult
returns: new head checkpoint id
```

`vidbyte/tools/builtins/__init__.py` adds `from vidbyte.tools.builtins.sessions import (CheckpointTool, ForkTool, RewindTool, ResumeAppendTool, ResumeOutputTool, ResumeReplaceTool, SessionTool)` and the names to `__all__`.

### 6.7 SQLite session store

**File:** `vidbyte/lib/providers/sqlite.py` (new), `vidbyte/lib/providers/__init__.py` (modified)
**Type:** New + Modified

Add `SqliteSessionStore(BaseSessionStore)` using the stdlib `sqlite3` module (no optional driver; eager import is safe, so unlike the Mongo/Supabase/Postgres stores it does not raise `ConfigurationError`). Same two-table schema as Postgres (`vidbyte_sessions`, `vidbyte_checkpoints`) created idempotently on first use with `CREATE TABLE IF NOT EXISTS` and indexes on `(session_id, seq)` and `parent_id`. Constructor: `SqliteSessionStore(*, path: str, table_prefix: str = "vidbyte_")`. Stores the serialized JSON payload (same shape as `FileSessionStore`) in `payload` columns. Re-export from `vidbyte.lib.providers`.

### 6.8 llms.txt

**File:** `llms.txt` (modified)
**Type:** Modified

- Add a bullet to "Feature Summary": `Durable sessions with continue/resume/fork over a checkpoint DAG and prebuilt Checkpoint/Fork/Resume agent tools.`
- Add a "### Durable Sessions" subsection under "## Core Features" covering: one-line `Session(agent)` attach, the verbs (continue/resume/fork/rewind/edit/checkpoint), the `SessionStore` backends (memory/file/Postgres/Mongo/Supabase), the rehydration contract, trace capture, and the three prebuilt tools in `vidbyte/tools/builtins/sessions/`.
- Update "## Package Map" with `vidbyte/sessions/` (facade, contracts, errors, scope, store, serializer, trace capture, local stores) and `vidbyte/tools/builtins/sessions/` (Checkpoint/Fork/Resume tools).

### 6.9 Skills

**Files:** `skills/sessions.md` (new), `skills/forking.md` (new), `skills/vidbyte-sdk/sessions.md` (modified to a pointer), `skills/sdk/SKILL.md` (modified)
**Type:** New + Modified

- `skills/sessions.md`: root-level usage skill — attach, run, checkpoint policy, trace capture, stores, resume/continue, the rehydration contract, the three prebuilt tools, and the `SessionScope` model. Follows the existing root-skill prose format (see `skills/creating-system-prompts.md`).
- `skills/forking.md`: root-level patterns skill — fork from head vs any checkpoint, parent lineage, rewind/time-travel, edit/history-transform, cross-agent fork via shared store + `SessionScope.sessions([...])`, and the `ResumeTool` adopt pattern for picking up another agent's thread.
- `skills/vidbyte-sdk/sessions.md`: replaced with a one-line pointer to `skills/sessions.md` + `skills/forking.md` to avoid duplication.
- `skills/sdk/SKILL.md`: rewrite the durable-sessions rule to:
  - "Keep durable-session behavior under `vidbyte/sessions/`, keep session dataclasses under `vidbyte/lib/dataclasses/sessions.py`, and preserve `vidbyte/sessions/contracts.py` as a compatibility re-export. Expose the namespace via `sdk.harnesses.sessions`."
  - "Keep database-backed session stores under `vidbyte/lib/providers/`; they subclass `ProviderSessionStore`, import their driver lazily, and raise `ConfigurationError` when the driver is absent."
  - "Ship prebuilt agent-facing session tools (`CheckpointTool`, `ForkTool`, `ResumeTool`) under `vidbyte/tools/builtins/sessions/`; they reuse `Session` + `SessionStore` + `SessionScope` and bind to a `Session` via `bind_session()`."
  - Keep the "persist raw history, re-supply non-serializable parts, never persist secrets, never use trace as a resume input" rule.

### 6.10 README + top-level exports

**Files:** `README.md` (modified), `vidbyte/__init__.py` (modified)
**Type:** Modified

- `README.md`: resolve the auto-merge; add a "Prebuilt session tools" subsection under the existing Durable Sessions section showing `tools=[CheckpointTool(store=store), ForkTool(store=store), ResumeTool(store=store)]` and the own/other-thread semantics.
- `vidbyte/__init__.py`: drop `SessionTool` from the `vidbyte.sessions` import block and `__all__`; keep `SessionScope`. Re-export `CheckpointTool`/`ForkTool`/`ResumeTool` from `vidbyte.tools.builtins` (verify against main's `SessionTracer` export so the auto-merge union is correct).

### 6.11 Existing test file maintenance

**File:** `tests/test_durable_sessions.py` (modified)
**Type:** Modified (no new tests)

Update imports to use `vidbyte.lib.dataclasses.sessions` for dataclass definitions, `vidbyte.sessions.contracts` for compatibility imports, and `vidbyte.sessions.errors` for session errors. Keep built-in session tool tests because the tools are part of this PR's public surface. `scripts/test-durable-sessions.py` is unchanged (it loads `tests.test_durable_sessions` by name).

---

## 7. Data Model Changes

N/A — no change to the `RunState`/`Checkpoint`/`SessionMeta` field shapes, the persisted JSON shape, or the DB table/collection schemas from the original design doc §7. The contracts are relocated, not redesigned. `SESSION_SCHEMA_VERSION` stays `1`.

---

## 8. API Changes

N/A — no HTTP endpoints. Public Python surface changes:

- **Added:** `vidbyte.tools.builtins.sessions.{CheckpointTool, ForkTool, ResumeTool}`; `vidbyte.sessions.scope.SessionScope` (re-exported from `vidbyte.sessions`).
- **Removed:** `vidbyte.sessions.tool.SessionTool`; the `SessionError` family from `vidbyte.lib.errors`; session dataclasses from `vidbyte.lib.dataclasses`.
- **Moved (same names, stable compatibility paths):** `RunState`, `Checkpoint`, `SessionMeta`, `CheckpointPolicy`, `SessionStatus`, `TraceCapture`, `SESSION_SCHEMA_VERSION` are defined at `vidbyte.lib.dataclasses.sessions` and re-exported from `vidbyte.lib.dataclasses`, `vidbyte.sessions.contracts`, and `vidbyte.sessions`; `SessionError` family remains at `vidbyte.sessions.errors` (re-exported from `vidbyte.sessions`).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/durable-sessions-refresh.md` | This design doc |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Resolve conflict; drop sessions re-exports (moved) |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Resolve conflict; drop SessionError re-exports (moved) |
| MODIFY | `vidbyte/lib/errors/base.py` | Resolve conflict; remove SessionError classes (moved) |
| CREATE | `vidbyte/lib/dataclasses/sessions.py` | RunState/Checkpoint/SessionMeta/enums |
| MODIFY | `vidbyte/sessions/contracts.py` | Compatibility re-export for session contracts |
| CREATE | `vidbyte/sessions/errors.py` | SessionError family (moved) |
| CREATE | `vidbyte/sessions/scope.py` | SessionScope (moved from tool.py) |
| DELETE | `vidbyte/sessions/tool.py` | SessionTool superseded by builtins |
| MODIFY | `vidbyte/sessions/__init__.py` | Re-exports: drop SessionTool, route contracts/errors/scope |
| MODIFY | `vidbyte/sessions/session.py` | Imports; add `_bind_session_tools()` + `adopt()` |
| MODIFY | `vidbyte/sessions/store.py` | Imports from contracts/errors |
| MODIFY | `vidbyte/sessions/serialization.py` | Imports from contracts/errors |
| MODIFY | `vidbyte/sessions/trace_capture.py` | Imports from contracts |
| MODIFY | `vidbyte/sessions/stores/__init__.py` | Imports from contracts/errors |
| MODIFY | `vidbyte/sessions/stores/memory.py` | Imports from contracts/errors |
| MODIFY | `vidbyte/sessions/stores/file.py` | Imports from contracts/errors |
| MODIFY | `vidbyte/lib/providers/base.py` | Imports from `vidbyte.sessions.contracts/errors` |
| MODIFY | `vidbyte/lib/providers/mongodb.py` | Imports from `vidbyte.sessions.contracts/errors` |
| MODIFY | `vidbyte/lib/providers/postgres.py` | Imports from `vidbyte.sessions.contracts/errors` |
| MODIFY | `vidbyte/lib/providers/supabase.py` | Imports from `vidbyte.sessions.contracts/errors` |
| MODIFY | `vidbyte/lib/providers/__init__.py` | Verify exports unchanged |
| MODIFY | `vidbyte/agents/base.py` | RunState import; `_bind_agent_tool_context` session-builtin branch |
| CREATE | `vidbyte/tools/builtins/sessions/__init__.py` | Export all session builtin tools |
| CREATE | `vidbyte/tools/builtins/sessions/session.py` | `SessionTool` (central combined, relocated from vidbyte/sessions/tool.py) |
| CREATE | `vidbyte/tools/builtins/sessions/checkpoint.py` | `CheckpointTool` |
| CREATE | `vidbyte/tools/builtins/sessions/fork.py` | `ForkTool` |
| CREATE | `vidbyte/tools/builtins/sessions/rewind.py` | `RewindTool` (own-thread time-travel) |
| CREATE | `vidbyte/tools/builtins/sessions/resume_replace.py` | `ResumeReplaceTool` (override current context) |
| CREATE | `vidbyte/tools/builtins/sessions/resume_append.py` | `ResumeAppendTool` (append other agent's context window) |
| CREATE | `vidbyte/tools/builtins/sessions/resume_output.py` | `ResumeOutputTool` (append other agent's final output; errors if not completed) |
| CREATE | `vidbyte/lib/providers/sqlite.py` | `SqliteSessionStore` (stdlib sqlite3, no lazy driver) |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Re-export the three session builtins |
| MODIFY | `vidbyte/__init__.py` | Drop SessionTool; keep SessionScope; verify union with main's SessionTracer |
| MODIFY | `README.md` | Resolve auto-merge; add prebuilt-tools subsection |
| MODIFY | `llms.txt` | Durable Sessions section + Feature Summary + Package Map |
| CREATE | `skills/sessions.md` | Root durable-sessions usage skill |
| CREATE | `skills/forking.md` | Root fork/resume/time-travel patterns skill |
| MODIFY | `skills/vidbyte-sdk/sessions.md` | Replace with pointer to root skills |
| MODIFY | `skills/sdk/SKILL.md` | Rewrite durable-sessions layout rule |
| MODIFY | `tests/test_durable_sessions.py` | Fix imports; drop removed-SessionTool cases |

**Totals:** 15 created, 24 modified, 2 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| stdlib `json`, `os`, `uuid` | — | session serialization/atomic writes | Low |
| `psycopg` (optional, lazy) | user DSN | PostgresSessionStore | Unchanged |
| `pymongo` (optional, lazy) | user URI | MongoDbSessionStore | Unchanged |
| `supabase` (optional, lazy) | user URL+key | SupabaseSessionStore | Unchanged |

No new dependencies. No network calls unless a developer constructs a DB store.

---

## 11. Rollout & Deployment

- **Feature flags:** none; additive on an unmerged feature branch.
- **Breaking changes:** internal relocation on an unmerged branch — `vidbyte.lib.dataclasses.sessions` and the `SessionError` classes in `vidbyte.lib.errors` are removed; `SessionTool` is removed. No shipped consumers to migrate.
- **Deployment order:** single PR; no service coordination.
- **Rollback:** revert the PR.
- **Migration:** none — `SESSION_SCHEMA_VERSION` stays `1`; existing persisted checkpoints (if any) load unchanged because the JSON shape is identical.

---

## 12. Open Questions

2. **DB-provider location.** RESOLVED: Mongo/Supabase/Postgres session stores stay in `vidbyte/lib/providers/` (provider adapters). Additionally add a **`SqliteSessionStore`** in `vidbyte/lib/providers/sqlite.py` using stdlib `sqlite3` (no lazy driver needed; eager import is safe). The provider-store pattern is extensible to more backends in follow-ups.
3. **`ResumeTool` cross-thread semantic.** RESOLVED: split into three granular tools — `ResumeReplaceTool` (override current context window with the other agent's state), `ResumeAppendTool` (append the other agent's context window into the current one), `ResumeOutputTool` (append only the other agent's final output; errors if the target session status is not `COMPLETED`). Plus `RewindTool` for own-thread time-travel. Each tool's header comment explains how it differs from the others.
4. **`SessionTool` fate.** RESOLVED: keep the central combined `SessionTool` AND ship the granular tools. Relocate `SessionTool` from `vidbyte/sessions/tool.py` to `vidbyte/tools/builtins/sessions/session.py`. `SessionScope` moves to `vidbyte/sessions/scope.py`.
5. **Builtin class naming.** RESOLVED: `*Tool` suffix per repo convention (`CheckpointTool`, `ForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool`, `SessionTool`).

---

## 13. Alternatives Considered

### Alternative 1: Keep session dataclasses and errors in `vidbyte/lib/` (don't move)
- What: leave `RunState`/`Checkpoint`/`SessionMeta` in `lib/dataclasses/sessions.py` while keeping `SessionError` in `vidbyte/sessions/errors.py`, confirming behavior remains in `vidbyte/sessions/`.
- Why rejected: the user's explicit directive is "all of the resume, checkpointing, forking logic inside `vidbyte/sessions/`"; the contracts and errors are the data and failure modes of that logic. Keeping them in lib leaves the package boundary split. The `skills/sdk/SKILL.md` rule is rewritten to authorize the new location.

### Alternative 2: Move DB providers into `vidbyte/sessions/providers/`
- What: full consolidation, including Mongo/Supabase/Postgres stores.
- Why rejected: those stores are provider adapters with lazy driver imports, matching the existing `vidbyte/lib/providers/` convention for provider-adjacent code; the user said non-session lib code can stay. Kept as Open Question #1 in case the user prefers full consolidation.

### Alternative 3: Remove `SessionTool` and ship only granular builtins
- What: delete the combined `SessionTool`, expose only `CheckpointTool`/`ForkTool`/`RewindTool`/`Resume*Tool`.
- Why rejected: the user explicitly wants both a central combined tool and the granular per-verb tools. `SessionTool` is relocated (not removed) to `vidbyte/tools/builtins/sessions/session.py` so all tool classes share one home.

### Alternative 4: Implement session builtins as functions, not `BaseTool` classes
- What: `@tool def checkpoint(...)` style.
- Why rejected: the builtins need a `SessionStore` + `SessionScope` bound at construction and a `bind_session(session)` hook; the class form matches `CreateHandoffTool` and the repo's class-first convention.

### Alternative 5: Add new tests for the builtins
- What: a `tests/test_session_builtins.py` or new cases in `test_durable_sessions.py`.
- Why rejected: this is the no-tests design-doc workflow. Builtin testing is a follow-up. The existing test file is only repaired for imports and removed-`SessionTool` cases.

---

## Summary

**File impact:** ~16 created, ~19 modified, ~2 deleted (per §9).

**Maps to the four user asks:**
1. Merge freshness + repo-state update → §6.1 + auto-merge verification across §6.
2. `llms.txt` + root skills → §6.7 + §6.8.
3. All session/forking logic inside `vidbyte/sessions/` → §6.2–6.5 (contracts, errors, scope moved in; providers stay in lib as provider adapters).
4. Prebuilt `Checkpoint`/`Fork`/`Rewind`/`ResumeReplace`/`ResumeAppend`/`ResumeOutput` + central `SessionTool` in `vidbyte/tools/` for own + other agent threads → §6.6. Plus a `SqliteSessionStore` provider → §6.7.

**Key risks / open questions:** all four original open questions are RESOLVED (§12). DB providers stay in `vidbyte/lib/providers/` with a new `SqliteSessionStore`; `SessionTool` is relocated (not removed) to the builtins folder; the single `ResumeTool` is split into `ResumeReplaceTool`/`ResumeAppendTool`/`ResumeOutputTool` plus `RewindTool`; class names use the `*Tool` convention.

**Request for approval:** Please resolve the four open questions in §12 (or accept the proposed defaults) and explicitly approve before I proceed to implementation. I will not write code until you approve.

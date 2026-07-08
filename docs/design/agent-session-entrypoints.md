# Design Doc: Agent-Native Session Entry Points (`persist()` + `session`)

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

Give `BaseAgent` a small, agent-native front door into durable sessions without moving any session machinery: an `agent.persist(store=..., ...)` method that attaches the agent to a `Session` in one call, a public `agent.session` property that formalizes the currently-private `_active_session` backdoor, a formal `agent.bind_session(session)` seam that replaces the `noqa: SLF001` private-attribute write in `Session._bind_session_tools()`, and a persistence hook in the agent's run path so that calling `agent.arun()` on a session-bound agent checkpoints exactly like calling `session.arun()` (closing the current silent-skip footgun). The `vidbyte/sessions/` package, its stores, serializer, and public exports are untouched; the agent gains ergonomics, not persistence machinery.

---

## 2. Original User Prompts

**Prompt 1 (via `/talk`):**

> question for the vidbyte-sdk/ repo (make sure that the local main is up to date first before answering). - recently had an idea for the vidbyte/session. I think that this is just the wrong abstraction layer for all of the functionality inside of this folder. I think that a much better place to put it, where it makes more sense, is the vidbyte/agents/session folder. And I think it is a lot more aligned to associate the checkpoint resume and forking capabilities inside of the agent class. We could even maybe initialize the session object in the agent constructor. Compared to what we have now and all the capabilities that we have in the session object, you think that this is the right approach to take? Like we are adding alot of functionality to our session object but I am wondering whether conceptually this should just be a native agent feature because like in practice you would want you agent to be able to fork/resume/checkpoints/store its own conversations throughout its runtime whether it is exploring different solution spaces, using multiple context windows for things, etc. But you would also want a dev to have control over this because lets say when there is an error they could use the session object to store the trace in their database in the code. What do you think about this decided, read the vidbyte/agent and vidbyte/sessions folder extensively to really get a good understand of what each location in the repo does

**Prompt 2 (via `/create-design`):**

> great, create a design doc for this change (adding the persist and session functions to agent). Also, after you create that first design doc I wanted to conceptually add two features to the session object, diffing and timeline. here is the description for both of them: - I was thinking about Adding this conceptually into the repo under our session object but I feel like we kind of already do this With the continual tracing functionality for Agent. Take a look. 1. Remembers & explains — "how did the agent get here?"
>
>   Session Timeline (yours)
>   Plain English: a chronological story of the run — every turn,
>   checkpoint, fork, edit, failure, and resume, in order.
>   Wrinkle: your current schema can't build this. A Checkpoint is a
>   state snapshot, not an event. "Forked here," "resumed here,"
>   "failed here" are events, and there's no event record in the PR —
>   failures currently get stuffed into
>   reply.metadata["__session_error__"], which isn't queryable.
>   Timeline forces you to add a first-class SessionEvent log
>   alongside the checkpoint DAG. That log is also what powers
>   Failure Recovery below, so build it once.
>
> What do you think a good way is to combine these two features And where should the entry point into this functionality live?
>
> - Checkpoint Diffing (both) — this is the keystone primitive
>   Plain English: compare two checkpoints — what changed in history,
>   tools, config, cost, trace.
>   Wrinkle: diffs are only stable if state has a canonical, ordered,
>   serializable form. Also, your secret-scrubbing means some fields
>   are already redacted — a diff over scrubbed data hides real
>   changes. And "diff" splits into structural (fields changed) vs
>   semantic (the answer got worse), which are different tools. Build
>   structural first; it's the dependency under Compare, Promote,
>   and delta-checkpoints. What returns from this function is simply what is different in each checkpoint.
> . can you talk through how we would implement this?

*(Note: this doc covers only the first part of Prompt 2 — the `persist`/`session` change. Timeline and Checkpoint Diffing were discussed conversationally and are explicitly out of scope here; they will get their own design if pursued.)*

---

## 3. Structured Conversation Notes

### Key Decisions

- **Do NOT move `vidbyte/sessions/` into `vidbyte/agents/`.** The user initially proposed relocating the whole sessions package to `vidbyte/agents/session` and possibly initializing a `Session` in the agent constructor. After a full audit of both packages, the recommendation (accepted by the user — "great, create a design doc for this change") was to keep the composition architecture and add agent-native *entry points* instead. Reasons: sessions sit architecturally *above* agents (they aggregate/persist agent runs); `BaseAgent` is constructed internally in many places (`_build_aggregate_agent()`, `agent.fork()`, `BaseAgent.restore()`, actor-runtime workers, `AgentTool`) and a constructor-initialized session would create junk sessions and eager `_write_initial_meta()` writes for every internal construction; the agent↔session cardinality is not 1:1 (`Session.resume()` builds a *new* agent from a checkpoint, one lineage spans many agent instances); and the durable-sessions design docs' load-bearing decision is "the agent stays pure; persistence lives entirely in the Session wrapper."
- **Add `BaseAgent.persist(...)`** — sugar that lazily imports `Session` and returns `Session(self, store=store, **kwargs)`. Reads as a native agent capability while machinery stays in `vidbyte/sessions/`.
- **Formalize `_active_session` into a public `session` property.** Today `Session._bind_session_tools()` writes `self._agent._active_session = self  # noqa: SLF001` and `BaseAgent._bind_session_tool` reads it back via `getattr(self, "_active_session", None)`. Initialize `self._active_session = None` in `BaseAgent.__init__` (before the tool-binding loop) and expose `agent.session -> Session | None`.
- **Add a formal `BaseAgent.bind_session(session)` seam.** `Session._bind_session_tools()` should call `agent.bind_session(self)` instead of poking the private attribute. `bind_session` sets `_active_session` and binds any session-builtin tools the agent carries (the `tool.bind_session(...)` loop can live on the agent side; `Session` keeps a thin call).
- **Close the `agent.arun()` footgun.** Today, once wrapped, only `session.arun()` persists; calling `agent.arun()` directly silently skips checkpointing. Move the per-turn persistence trigger so it fires from the agent's run path whenever a session is bound and policy is not `MANUAL`, keeping `Session.arun()` behavior identical (it must NOT double-persist — see Implementation Hints).
- **No import-time dependency from agents → sessions** beyond the already-allowed `vidbyte.lib.dataclasses.sessions`. All new session references in `base.py` use lazy imports inside methods (the pattern `export_state()` already uses for `SessionSerializer`) and `TYPE_CHECKING` for annotations.

### Rejected Alternatives

- **Relocating `vidbyte/sessions/` → `vidbyte/agents/session/`.** Rejected: public API churn (`vidbyte.sessions.*` is exported from the root `vidbyte/__init__.py`, wired into `sdk.harnesses.sessions`, referenced by `llms.txt`, `skills/sessions.md`, `skills/forking.md`, DB providers in `vidbyte/lib/providers/`, and `vidbyte/tools/builtins/sessions/`); it reverses the user's own 2026-07-04 consolidation directive recorded in `docs/design/durable-sessions-refresh.md`; it inverts layering (higher-level aggregate nested inside lower-level package); and `portable.py`/`usage.py` landed on main this week — the surface is under active development.
- **Auto-initializing a `Session` in the `BaseAgent` constructor.** Rejected: every internal `BaseAgent(...)` construction (aggregate inner agents, forks, restores, actor workers) would create junk sessions and write initial meta to a store. An opt-in `session=`/`store=` constructor kwarg defaulting to off is just `Session(agent)` spelled differently, adding a ~36th parameter to an already 1,332-line class.
- **Merging `agent.fork()` and `session.fork()`.** Rejected: they are deliberately different verbs — config cloning with fresh run identity vs. lineage branching over the checkpoint DAG. There is an in-flight `docs/design/agent-fork-isolation.md` about the former.
- **Durable-by-default (every agent run checkpointed automatically).** Named as a possible long-term vision; explicitly deferred. If pursued later, the right shape is a default store configured at SDK/client level plus this same sugar — still no package move.

### Constraints & Assumptions

- `BaseAgent` (`vidbyte/agents/base.py`, ~1,332 lines) must not gain import-time dependencies on `vidbyte.sessions` submodules (stores, serializer, portable, usage). `vidbyte.lib.dataclasses.sessions` (RunState etc.) is already imported at module top and is fine.
- `Session` semantics are unchanged: checkpoint DAG, `CheckpointPolicy` (`PER_TURN` default / `PER_STEP` / `MANUAL`), fail-open persistence (`_persist_fail_open` writes `reply.metadata["__session_error__"]` on store failure), `TraceRecorder` capture, rehydration contract.
- Existing tests live in `tests/` (e.g., `tests/test_durable_sessions.py`); repo conventions in `skills/sdk/SKILL.md` (dataclasses in `vidbyte/lib/dataclasses/`, session contracts re-exported via `vidbyte/sessions/contracts.py`, class-first code style, Context Protocol Header docstrings on every module).
- The repo documents features centrally in `llms.txt` and root `skills/*.md` (`skills/sessions.md`, `skills/forking.md`) — those must mention the new entry points.
- Assumption: `Session.__init__` remains the canonical constructor; `persist()` is pure delegation and adds no new construction path.

### Clarifications & Answers

- Q (user): should session functionality live inside the agent class / folder? A (agreed): no relocation; add `persist` + `session` on the agent as the native entry points; the builtin session tools (`CheckpointTool`, `ForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool` in `vidbyte/tools/builtins/sessions/`) already give agents runtime self-checkpoint/fork/resume, scope-gated via `SessionScope`.
- The user's two motivating capabilities are both preserved: (1) agent-native runtime lineage control → builtin session tools + the new hook; (2) dev-level control (e.g., on error, store the trace in their DB) → `agent.session.checkpoint(label="crash")` now first-class via the public property.

### Terminology / Glossary

- **Session** — durable aggregate wrapping a `BaseAgent`; owns continue/resume/fork/rewind/edit over an append-only checkpoint DAG (`vidbyte/sessions/session.py`).
- **Checkpoint / RunState** — one DAG node / the serializable agent snapshot inside it (`vidbyte/lib/dataclasses/sessions.py`).
- **Rehydration contract** — non-serializable parts (runner, tools, middleware, tracer, output_schema) are re-supplied by the caller at `resume`/`fork` time; `BaseAgent.export_state()`/`restore()` is the seam.
- **Session-builtin tools** — agent-facing tools in `vidbyte/tools/builtins/sessions/` that operate on the bound session; they require `bind_session(...)` before functioning.
- **Footgun** — calling `agent.arun()` on a session-wrapped agent today writes no checkpoint.

### Implementation Hints for the Downstream Model

- **Files to touch:** `vidbyte/agents/base.py` (main change), `vidbyte/sessions/session.py` (`_bind_session_tools` → call `agent.bind_session(self)`; `arun` double-persist guard), `skills/sessions.md`, `llms.txt` (Durable Sessions subsection), `vidbyte/agents/README.md` (mention the entry points), `tests/test_durable_sessions.py` (extend).
- **`persist()` shape:**
  ```python
  def persist(self, *, store: "SessionStore | None" = None, **kwargs: Any) -> "Session":
      """Attach this agent to a durable session (agent-native entry point)."""
      from vidbyte.sessions.session import Session
      return Session(self, store=store, **kwargs)
  ```
  Annotations via `TYPE_CHECKING` import of `Session`/`SessionStore`; follow the lazy-import pattern of `export_state()` (base.py:442).
- **Init ordering:** set `self._active_session: "Session | None" = None` in `__init__` *before* the `for _tool in self._agent_tool_items: self._bind_agent_tool_context(_tool)` loop (base.py:197), since `_bind_session_tool` reads it. Then simplify `_bind_session_tool` to use the real attribute instead of `getattr(self, "_active_session", None)`.
- **`bind_session` shape:** sets `_active_session` and loops `self._agent_tool_items` calling each tool's `bind_session(session)` when callable (this logic currently lives in `Session._bind_session_tools`, session.py:322 — move the loop to the agent, keep `Session._bind_session_tools` as a one-line call to `self._agent.bind_session(self)` wrapped in the existing try/except fail-open).
- **Persistence hook — the tricky part.** `BaseAgent.generate_reply()` has TWO successful return paths: the aggregate delegate early return (base.py:679–680, `return await self._aggregate_agent.generate_reply(...)`) and the normal path end (base.py:771). The hook must fire exactly once per top-level call on both paths. Simplest correct shape: a small private helper `_notify_session(reply)` that, when `self._active_session is not None` and its policy is not `MANUAL`, calls a session method (suggest adding `Session.record_turn(reply)` that delegates to the existing `_persist_fail_open(reply, label="")`). Then change `Session.arun()` to just `return await self._agent.arun(message, **options)` — the agent-side hook persists, so `Session.arun` must drop its own `_persist_fail_open` call or every turn double-checkpoints. Verify with a test: one turn via `session.arun()` → exactly one new checkpoint; one turn via `agent.arun()` on a bound agent → exactly one new checkpoint.
- **Policy access:** `Session` keeps `self._policy` private; either expose a read-only `policy` property on `Session` or have `record_turn` itself check the policy (preferred — keeps policy knowledge inside `Session`; the agent hook then unconditionally calls `record_turn` when a session is bound).
- **Fail-open invariant:** persistence must never break a run. `record_turn` inherits `_persist_fail_open` semantics; the agent-side hook should additionally be wrapped so a broken/stale session object cannot crash `generate_reply`.
- **Do NOT touch:** `vidbyte/sessions/` public exports, `SessionClient`, the stores, serializer, `vidbyte/tools/builtins/sessions/` tool specs, `sdk.harnesses.sessions` wiring, DB providers. No new dataclasses, no new errors.
- **Style:** class-first, Context Protocol Header docstrings, single-line inline comments above logic blocks (see existing `base.py`/`session.py` comment density), no bare relative imports.

### Open Questions

- Should `persist()` accept a plain string shorthand for the store (e.g., `persist(store="file:./sessions")`)? Suggest NO for v1 — keep it delegation-only; `SessionClient.file_store()` already exists.
- Should the `session` property be settable (`agent.session = s`) as an alias for `bind_session`? Suggest read-only property; binding stays explicit via `Session` attach or `bind_session`.
- Should `Session.run()` (sync) also become a thin delegate? It already routes through `arun` via `asyncio.run`; verify no behavior change needed.

---

## 4. Goals & Non-Goals

### Goals

- `agent.persist(store=..., policy=..., trace=..., tags=...) -> Session` one-line attach, lazily importing `Session`.
- Public read-only `agent.session -> Session | None` property; `_active_session` initialized to `None` in `__init__`.
- Formal `agent.bind_session(session)` replacing the `noqa: SLF001` private write in `Session._bind_session_tools()`.
- `agent.arun()` / `agent.run()` on a session-bound agent persists checkpoints identically to `session.arun()` (per policy, fail-open, exactly one checkpoint per turn).
- No import-time `vidbyte.agents` → `vidbyte.sessions` dependency beyond `lib/dataclasses/sessions`.
- Docs updated: `skills/sessions.md`, `llms.txt`, `vidbyte/agents/README.md`.
- Tests covering: persist delegation, property lifecycle (None → bound), no double-persist, MANUAL policy skips the hook, fail-open on store errors, internal agent constructions (fork/aggregate/restore) create no sessions.

### Non-Goals

- Moving or renaming anything under `vidbyte/sessions/`.
- Auto-creating sessions in the `BaseAgent` constructor, or any `session=`/`store=` constructor kwarg.
- Durable-by-default behavior or SDK-level default stores.
- Session Timeline / SessionEvent log (separate future design).
- Checkpoint Diffing (separate future design).
- Any change to checkpoint DAG semantics, serializer scrubbing, stores, builtin session tool specs, or the rehydration contract.

---

## 5. Background & Context

Durable sessions landed via `docs/design/durable-sessions.md` + `docs/design/durable-sessions-refresh.md`: `Session` wraps a pure `BaseAgent`, persisting `RunState` checkpoints through a `SessionStore` port, with agent-facing builtin tools for self-checkpoint/fork/resume. The user questioned whether the whole capability belongs inside the agent abstraction. The audit concluded the composition split is correct, but surfaced two real wounds this change heals: (1) the wrapper footgun — a session-bound agent silently skips persistence when run directly; (2) the informal `_active_session` backdoor with a lint suppression, which is the code signaling the boundary wants a formal seam. This change is deliberately small and severable: ergonomics + seam formalization + footgun fix, nothing else.

---

## 6. Requirements

1. `BaseAgent.persist(*, store=None, **kwargs)` returns a `Session` bound to the agent; kwargs pass through to `Session.__init__` unchanged.
2. `BaseAgent.session` returns the bound `Session` or `None`; it is the formalized `_active_session`.
3. `BaseAgent.bind_session(session)` sets the binding and binds all session-builtin tools carried by the agent; `Session` uses this seam (no private-attribute writes, `noqa: SLF001` removed).
4. After `Session(agent)` (or `agent.persist()`), `await agent.arun(msg)` writes exactly one checkpoint per turn under `PER_TURN`, zero under `MANUAL`; `await session.arun(msg)` likewise writes exactly one (no double-persist).
5. Persistence triggered from the agent path is fail-open: store failures mark `reply.metadata["__session_error__"]` and never raise, matching current `_persist_fail_open` semantics.
6. The aggregate-delegate path of `generate_reply` also triggers persistence exactly once per top-level call.
7. Importing `vidbyte.agents.base` does not import `vidbyte.sessions.session`, stores, or serializer at module import time.
8. Internal `BaseAgent` constructions (`fork()`, `restore()`, `_build_aggregate_agent()`, actor workers) never create sessions or store writes.
9. Existing public behavior of `Session`, `SessionClient`, stores, and builtin session tools is unchanged; `tests/test_durable_sessions.py` still passes with only additive edits.
10. `skills/sessions.md`, `llms.txt`, and `vidbyte/agents/README.md` document `agent.persist()` and `agent.session`.

---

## 7. Non-Functional Requirements

- **Performance:** `persist()` and the hook add no measurable overhead when no session is bound (a single `None` check per turn); no new imports on the hot path when unbound.
- **Scalability:** N/A — no new storage or concurrency behavior.
- **Security:** no new persisted fields; existing serializer secret-scrubbing paths unchanged.
- **Observability:** persistence failures remain visible via `reply.metadata["__session_error__"]`; no logging changes.
- **Reliability:** fail-open invariant — session persistence must never terminate or alter an agent run's result.

---

## 8. High-Level Design

Three small additions to `BaseAgent` and one refactor inside `Session`. `BaseAgent` gains: (a) `persist()`, pure lazy-import delegation to `Session(self, ...)`; (b) `_active_session = None` initialized in `__init__` with a public `session` property over it; (c) `bind_session(session)`, which sets the binding and runs the session-tool binding loop that currently lives in `Session._bind_session_tools`. `Session._bind_session_tools` becomes a thin, fail-open call to `agent.bind_session(self)`.

The footgun fix inverts who triggers per-turn persistence. Today `Session.arun()` runs the agent then persists. After this change, the agent's `generate_reply` completion path (both the normal return and the aggregate-delegate early return) calls a private `_notify_session(reply)` helper: if a session is bound, it calls `session.record_turn(reply)` — a new thin public method on `Session` that applies the checkpoint policy and delegates to the existing `_persist_fail_open`. `Session.arun()` becomes a pure delegate to `agent.arun()`, relying on the hook, so the two call sites are equivalent by construction and cannot double-persist.

```
 before:  dev ──> session.arun ──> agent.arun ──> reply
                       └── persist(reply)                (agent.arun alone: no persist)

 after:   dev ──> session.arun ─┐
          dev ──> agent.arun  ──┴─> generate_reply ──> reply
                                         └── _notify_session ──> session.record_turn
                                                                       └── policy check ──> _persist_fail_open
```

Key decisions: keep policy knowledge inside `Session` (`record_turn` checks `MANUAL`, the agent hook stays policy-ignorant); keep every new agent→session reference lazy or `TYPE_CHECKING`-only so the agent package's import graph is unchanged; make the whole change severable — if the hook proves risky, `persist()` + `session` + `bind_session` stand alone and `Session.arun()` can keep its current persist call.

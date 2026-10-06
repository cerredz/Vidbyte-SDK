# Design Doc: Session `batch_fork` (method + tool)

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

Add a `batch_fork` capability to the durable `Session` facade that branches N independent child sessions from a single checkpoint (defaulting to head), reusing the exact behavior of the existing `fork()`. Branches are fault-isolated: if some forks fail, the rest still succeed and are returned. The capability is exposed both as a Python method on `Session` and as an agent-facing builtin tool (`BatchForkTool`) so a running agent can fan itself out. This is the fan-out companion to `session.usage()` — together they form the seam for eval sweeps (fork a base state N ways, run variants, roll up usage).

---

## 2. Original User Prompts

The user's own words, verbatim and in order, across the conversation that produced all four session design docs.

**Prompt 1 (via `/talk`):**
```
- i want to add the following features to our session objectin the vidbyte-sdk/ repo:
  - want to add a batch_fork method to the session object, also make this a tool
  - want to add a session.usage object:   - Usage/cost rollups. You store traces per checkpoint but expose no aggregate. session.usage() -> {tokens, cost, latency,
  tool_calls} folded across the head chain. Near-free, and it's the
  seam for everything eval-related. Should be able to track the usage of all agents in the session. 
  - i want to be able to resume/fork by name and not just uuid, maybe like a session.tag() function to do this. 
  -  export() / import() — a portable session bundle (checkpoints +
  traces) to move between stores, attach to a bug report, or ship a
  repro. FileSessionStore already has the on-disk shape; this is
  mostly a zip.
. Can you kind of just scope out the session skill and see how we would implement this, and explain how we would do it?
```

**Prompt 2:**
```
1) the batch_fork should attempt to do the same thing the fork function does, just multiple of. If a few fail its fine, just keep running the others that dont. 2) I simply want the session.usage() function to use the already existing logic in the agent class's and calculate this for all agents in the session 3) go more into depth and explain to me how we would implement this 4) also explain this more. Using these answers, show me some implementation surfaces
```

**Prompt 3:**
```
great, can you create 4 design docs for this feature
```

---

## 3. Structured Conversation Notes

### Key Decisions
- **`batch_fork` == `fork()` × N.** It must reproduce `fork()`'s behavior exactly (branch a new `se_...` session from a checkpoint, record `parent_session_id` lineage, write a root `fork` checkpoint, never mutate the source). It just does it `count` times.
- **Fault isolation is a hard requirement** (user Prompt 2, item 1: "If a few fail its fine, just keep running the others that dont"). One branch raising must not abort the batch. Each branch is wrapped in its own try/except; failures are recorded and returned alongside successes.
- **Return a structured outcome list**, not a bare `list[Session]`, so callers can see which indices failed and why. Proposed `ForkOutcome(index, session | None, error | None)`.
- **The method creates branches; it does not run them.** Running N agents concurrently is a separate, expensive concern the caller opts into (e.g. `asyncio.gather` over the returned sessions' `arun`). This mirrors today's `ForkTool`, which only creates and returns an id.
- **The tool only creates and returns ids** (plus a failed-count), never runs branches — matching `ForkTool` semantics so a model can't trigger a surprise N-agent cost with one tool call.

### Rejected Alternatives
- **`batch_fork` runs the branches itself (concurrent `gather`).** Rejected as the default because implicit N-way execution from a tool call is a cost/latency surprise; left as a caller-side pattern over the returned sessions. A future `run=` convenience could be added but is out of scope.
- **Return `list[Session]` and drop failures silently.** Rejected — the user explicitly wants failures tolerated *and* the survivors returned; silently dropping loses the count/reason an eval harness needs.
- **Raise on first failure (fail-fast).** Directly contradicts Prompt 2.

### Constraints & Assumptions
- Distinct child `session_id`s per branch mean no store-key collisions. On `FileSessionStore`, each session is its own directory with atomic `os.replace` writes and per-session `_next_seq`, so sequential branch creation is safe. `InMemorySessionStore` is a plain dict backing — sequential creation is safe; if a caller later runs branches concurrently, that concurrency is on the caller, not `batch_fork`.
- `count` should be bounded in the tool schema (proposed max 64) to avoid a model requesting a runaway fan-out.
- No `SESSION_SCHEMA_VERSION` bump — this feature adds no persisted fields.

### Clarifications & Answers
- **Q: Should `batch_fork` be more sophisticated than `fork` (e.g. seed each branch with a different message)?** A (Prompt 2): No — "the same thing the fork function does, just multiple of."
- **Q: What happens on partial failure?** A (Prompt 2): Tolerate it, keep the successful branches running/returned.

### Terminology / Glossary
- **Fork:** branch a new session whose root checkpoint copies a source checkpoint's `RunState`; records `parent_session_id`. Implemented today by `Session.fork()` (bound thread) and `Session.fork_from()` (cross-thread classmethod).
- **Checkpoint DAG:** append-only tree of `Checkpoint` nodes; each node's `run_state.history` is the *cumulative* agent history at that point.
- **Bound session:** the `Session` a builtin tool is attached to via `bind_session()` (`tools/builtins/sessions/_base.py`).
- **Scope:** `SessionScope` (`sessions/scope.py`) gates which session ids a tool may touch; new branches are granted via `self._scope.allow(id)`.

### Implementation Hints for the Downstream Model
- **Method goes in** `vidbyte/sessions/session.py`, directly beside `fork()` (currently around line 99). Reuse `self.fork(at=..., tools=..., runner=..., middleware=...)` per branch — do NOT re-implement forking.
- **`ForkOutcome`** can be a `@dataclass(frozen=True, slots=True)` in `session.py` (or a tiny `sessions/contracts.py` addition if you prefer it re-exported). Keep it minimal.
- **Tool goes in** a new file `vidbyte/tools/builtins/sessions/batch_fork.py`, modeled almost line-for-line on `vidbyte/tools/builtins/sessions/fork.py`. Subclass `_SessionBuiltinTool`, use `self._require_bound(...)`, `self._caught(...)`, and `ToolResult.success/error`.
- **Register the tool** in `vidbyte/tools/builtins/sessions/__init__.py` (export `BatchForkTool`) and wherever the session builtins are assembled into the tool catalog (check `vidbyte/tools/catalog.py` and how `ForkTool` is wired — imitate exactly).
- **`__init__.py` of `vidbyte/sessions/`** re-exports the public surface; if `ForkOutcome` is public, add it to `__all__` there too.
- **Error string format:** match the codebase convention `f"{type(exc).__name__}: {exc}"` (see `_persist_fail_open` and `_caught`).
- **Do NOT touch** `fork_from`, `_persist`, or store internals — this is pure composition over existing verbs.

### Open Questions
- Should the tool return the failed *indices/reasons* or just a failed count? Proposed: `{"created": [ids], "failed": <int>}` to keep the model-facing payload small; revisit if agents need to react to specific failures.
- Should there be a `Session.batch_fork_and_run(messages=...)` convenience (concurrent execution) in this same PR, or strictly deferred? Proposed: deferred.

---

## 4. Goals & Non-Goals

### Goals
- Add `Session.batch_fork(count, *, at=None, tools=None, runner=None, middleware=None) -> list[ForkOutcome]`.
- Branch behavior identical to `fork()`, repeated `count` times.
- Tolerate per-branch failures; return all successes plus failure records.
- Add `BatchForkTool` builtin that creates N branches from the bound session's head (or a checkpoint) and returns the created ids + failed count.
- Register the tool in the session builtins package and tool catalog.

### Non-Goals
- Running the forked branches (concurrency, `gather`, seeding each with a message).
- Any change to the checkpoint schema or store contract.
- Cross-thread batch forking from the tool (the tool forks the *bound* thread only, matching the simplest `ForkTool` path; cross-thread can be a follow-up).

---

## 5. Background & Context

The durable-sessions feature (see `docs/design/durable-sessions.md`) already gives every agent a checkpoint DAG with `fork`, `rewind`, `resume`, and `edit` verbs. Evals and search-style workflows need to branch a single base state into many parallel variants — currently a caller must loop `fork()` by hand and handle failures themselves. `batch_fork` makes fan-out a first-class, fault-tolerant primitive and exposes it to agents as a tool so an agent can spawn its own exploration branches. It pairs with `session.usage()` (separate doc) to make "fork N ways, run, roll up cost" a two-call pattern.

---

## 6. Requirements

1. `Session.batch_fork(count, *, at=None, tools=None, runner=None, middleware=None)` returns a list of length `count`, one entry per attempted branch.
2. Each successful entry carries a live `Session` branched from `at or head`, identical to what `fork()` would return.
3. A branch that raises during creation is caught; its entry records the error string and a `None` session; remaining branches are still attempted.
4. Lineage (`parent_session_id`) and the root `fork` checkpoint are recorded per branch, exactly as `fork()` does.
5. `BatchForkTool.spec()` declares `count` (required, integer, bounded) and optional `checkpoint_id`.
6. `BatchForkTool.execute()` never raises; it returns a `ToolResult` with the created session ids and a failed count, and grants each new id in scope via `self._scope.allow(...)`.
7. The tool is exported from `tools/builtins/sessions/__init__.py` and registered in the catalog alongside the other session builtins.

---

## 7. Non-Functional Requirements

- **Performance:** O(count) sequential store writes; no added per-branch overhead beyond a single `fork()`.
- **Concurrency:** Branch creation is sequential and safe on both bundled stores (distinct session ids). The design must not introduce shared-mutable-state races; any concurrent *execution* of branches is explicitly the caller's responsibility.
- **Reliability:** Fault isolation is the central NFR — a failing branch must never abort the batch (Prompt 2).
- **Security:** Tool respects `SessionScope`; newly created branches are added to scope, consistent with `ForkTool`.
- **Observability:** N/A beyond existing checkpoint records; consider including failed count in the tool result for visibility.

---

## 8. High-Level Design

`Session.batch_fork` is a thin, fault-isolating loop over the existing `fork()` verb. For `i` in `range(count)` it calls `self.fork(at=at, tools=tools, runner=runner, middleware=middleware)` inside a try/except, appending a `ForkOutcome(i, session, None)` on success or `ForkOutcome(i, None, "ErrType: msg")` on failure. It returns the full list so callers see every attempt. No new persistence, no schema change — each `fork()` already mints a distinct `se_...` id, copies the source `RunState` into a fresh root checkpoint, and records `parent_session_id`.

`BatchForkTool` subclasses `_SessionBuiltinTool` and mirrors `ForkTool`. Its `execute()` resolves the bound session (error result if none), calls `session.batch_fork(count, at=checkpoint_id)`, grants each created branch id via `self._scope.allow(...)`, and returns `ToolResult.success` with `{"created": [ids...], "failed": <count>}`. Like `ForkTool`, it only *creates* branches; running them is out of band.

```
                      Session.batch_fork(count=3, at=head)
                                   |
        +----------------+----------------+----------------+
        v                v                v                v
   fork() #0         fork() #1        fork() #2   (each: fork_from source RunState)
        |                | (raises)        |
   ForkOutcome(ok)  ForkOutcome(err)  ForkOutcome(ok)   <- failures isolated, batch continues
        |                                 |
        +------------------ returned list ----------------+

   BatchForkTool.execute() -> ToolResult.success({"created": [se_a, se_c], "failed": 1})
```

Components:
- **Modified:** `vidbyte/sessions/session.py` (add `batch_fork` + `ForkOutcome`), `vidbyte/sessions/__init__.py` (`__all__` if `ForkOutcome` is public), `vidbyte/tools/builtins/sessions/__init__.py` (export), tool catalog wiring.
- **Created:** `vidbyte/tools/builtins/sessions/batch_fork.py` (`BatchForkTool`).
- **Deleted:** none.

---

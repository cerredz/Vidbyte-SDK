# Design Doc: Session tagging + resume/fork by name

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

Let users resume and fork sessions by a human-friendly **name** instead of only a `se_...` uuid. Add `session.tag(*names)` to attach labels to a session's metadata, and a single `store.resolve(identifier)` method that maps either a real session id or a tag/name to a concrete session id. The resume/continue/fork entry points call `resolve` first, so any identifier — id or name — works transparently. Built entirely on the `SessionMeta.tags` field that already exists; no schema change on the recommended path.

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

Note: Prompt 2 item **3** ("go more into depth and explain to me how we would implement this") refers to this feature — the user asked for a deeper implementation treatment of tagging / resume-by-name.

---

## 3. Structured Conversation Notes

### Key Decisions
- **`tag()` writes to the existing `SessionMeta.tags` tuple.** No new field needed — `SessionMeta` already has `tags: tuple[str, ...]` (`sessions/contracts.py:106`) and `store.list_sessions(tag=...)` already filters on it (`sessions/store.py:81`).
- **Introduce ONE resolver, `store.resolve(identifier) -> str`, in `BaseSessionStore`** — not scattered lookups in each verb. Resume/continue_/fork_from call it first.
- **Exact id wins over tags.** `resolve` checks `_read_meta(identifier)` first; a real `se_...` id is never shadowed by a tag that happens to equal it.
- **Ambiguous name resolves deterministically to the most-recently-updated match** (`max(matches, key=updated_at)`). Tags are inherently non-unique; rather than error, pick "latest wins" and document it.
- **Unknown name raises `SessionNotFoundError`** naming the identifier (consistent with existing store error style).
- **Recommended path is tag-latest (zero schema change).** A stricter unique-`alias` field is explicitly the rejected/deferred alternative because it bumps `SESSION_SCHEMA_VERSION` and needs a uniqueness invariant.

### Rejected Alternatives
- **Unique `alias` field on `SessionMeta`.** Gives guaranteed 1:1 name→session and deterministic resume with no "latest wins" ambiguity — but requires a schema-version bump, a collision check on write, and index maintenance. Deferred until a hard uniqueness requirement appears. Documented as the escape hatch.
- **Resolve by scanning in every verb (`resume`, `fork_from`, `continue_`) independently.** Rejected — duplicated logic, drift risk. One `resolve` on the store.
- **Error on ambiguous tag.** Rejected as too brittle for a labeling feature; "latest wins" is friendlier and predictable.
- **Separate `name` concept distinct from `tags`.** Rejected for v1 — `tags` already exists, already filters, already persists; reuse it.

### Constraints & Assumptions
- A session's meta row exists before its first run: `Session.__init__` calls `_write_initial_meta` (`session.py:203`), so there is always a `SessionMeta` to tag/resolve, even pre-first-run.
- Tags are non-unique by nature; callers who reuse a tag across sessions accept "latest-updated wins" on resolve.
- No `SESSION_SCHEMA_VERSION` bump on the recommended path.
- Adding `resolve` to the `SessionStore` Protocol means every backend must provide it; the default implementation in `BaseSessionStore` covers the bundled memory + file stores. DB providers (`vidbyte/lib/providers/*`) should override with an indexed query.

### Clarifications & Answers
- **Q (implied by Prompt 1): how to resume/fork by name?** A: `session.tag(name)` labels the session; `resolve(name)` maps it back to an id; verbs accept either. The user suggested `session.tag()` by name in Prompt 1 ("maybe like a session.tag() function to do this") and asked for depth in Prompt 2 item 3.

### Terminology / Glossary
- **Tag / name:** a human-friendly label in `SessionMeta.tags`. In this feature "name" and "tag" are the same mechanism; a name is just a tag used for lookup.
- **Alias (deferred):** a hypothetical *unique* name field — NOT built in v1.
- **Resolve:** map an identifier (id or tag) → a concrete `session_id`.
- **`updated_at`:** ISO-8601 timestamp on `SessionMeta`, bumped on head advance and meta writes; used to break tag ambiguity.

### Implementation Hints for the Downstream Model
- **`session.tag(*names)`** in `vidbyte/sessions/session.py`: read `self._store.get_meta(self._session_id)`, merge names into `meta.tags` with de-dupe preserving order (`tuple(dict.fromkeys((*meta.tags, *names)))`), `replace(meta, tags=..., updated_at=_now())`, `put_meta`, `return self`. Use the module's existing `_now()` and `dataclasses.replace` (both already imported in `session.py`).
- **`resolve` on `BaseSessionStore`** (`vidbyte/sessions/store.py`): 
  1. `if self._read_meta(identifier) is not None: return identifier`
  2. `matches = [m for m in self._read_all_meta() if identifier in m.tags]`
  3. empty → raise `SessionNotFoundError(f"No session id or tag: {identifier}.", details={"identifier": identifier})`
  4. else `return max(matches, key=lambda m: m.updated_at).session_id`
  `_read_meta` / `_read_all_meta` are the existing abstract raw primitives — reuse them.
- **Add `resolve(identifier: str) -> str`** to the `SessionStore` Protocol (`store.py:29`) so type-checkers and DB providers see it.
- **Wire into entry points** in `vidbyte/sessions/session.py`: at the top of `resume` (classmethod, ~line 152) do `session_id = store.resolve(session_id)`; `continue_` delegates to `resume` so it's covered; for `fork_from` (~line 167) the arg is a `checkpoint_id` not a session id — leave checkpoint resolution alone, but if you want fork-by-session-name, add resolution where a session id (not checkpoint id) is accepted. Double-check whether "fork by name" means fork the *named session's head* — if so, resolve name→session_id then fork from that session's head (mirror `ForkTool._fork_other` / `_target_head_id`).
- **`SessionNotFoundError`** already exists in `vidbyte/sessions/errors.py` — reuse, do not add a new error type.
- **DB providers:** if present under `vidbyte/lib/providers/`, override `resolve` with a `tags` array-contains query ordered by `updated_at desc limit 1`. Check whether such providers exist before assuming.
- **Do NOT** add an `alias` field or bump the schema version on this path.

### Open Questions
- **Does "fork by name" mean "fork the named session's head into a new session"?** Assumed yes. Confirm the exact surface: e.g. `Session.fork_from(store, store.resolve(name) → head)` vs a dedicated `Session.fork_named(store, name)`.
- Should `tag()` also support **removing** a tag (`untag`)? Not requested; add only if asked.
- Should tag **uniqueness** ever be enforced? If yes, that's the deferred `alias` path — flag to the user before building.

---

## 4. Goals & Non-Goals

### Goals
- `Session.tag(*names) -> Session` attaches one or more labels to the session's meta.
- `BaseSessionStore.resolve(identifier) -> str` maps an id or tag/name to a concrete session id, exact-id-first, latest-wins on tag ambiguity.
- `resume` / `continue_` (and, per the open question, name-based fork) accept a name anywhere they accept a session id.
- Add `resolve` to the `SessionStore` Protocol.

### Non-Goals
- A unique `alias` field or any uniqueness guarantee (deferred; would bump schema).
- Tag removal / rename.
- Changing how `list_sessions` filters by tag (already works).
- DB-provider implementations beyond noting they should override `resolve`.

---

## 5. Background & Context

Today sessions are addressable only by their generated `se_...` uuid, which is unfriendly for humans running or resuming named workflows ("resume the nightly-eval session"). `SessionMeta` already carries a `tags` tuple and `list_sessions` already filters on it, so the labeling substrate exists — what's missing is (1) a mutator to add tags to a live session and (2) a resolver so the resume/fork verbs accept a name. The user asked for depth here (Prompt 2, item 3). The central design tension is that tags are non-unique while resume-by-name wants determinism; this doc resolves it with exact-id-precedence plus latest-wins, and records the unique-`alias` upgrade path for if strict uniqueness is ever required.

---

## 6. Requirements

1. `Session.tag(*names)` merges `names` into `SessionMeta.tags` (de-duped, order-preserving), updates `updated_at`, persists via `put_meta`, and returns `self`.
2. `BaseSessionStore.resolve(identifier)` returns `identifier` unchanged when it is an existing session id.
3. When `identifier` is not an id but matches one or more sessions' tags, `resolve` returns the `session_id` of the most-recently-updated match.
4. When `identifier` matches neither an id nor any tag, `resolve` raises `SessionNotFoundError` naming the identifier.
5. `Session.resume` (and `continue_` via delegation) resolves its `session_id` argument through `resolve` before use, so names work transparently.
6. Name-based fork resolves a name to the named session's head before forking (pending confirmation of exact surface).
7. `resolve` is part of the `SessionStore` Protocol.

### Non-Functional Requirements — see section 7.

---

## 7. Non-Functional Requirements

- **Performance:** Default `resolve` scans all meta rows (`_read_all_meta`) on a tag lookup — O(sessions). Acceptable for memory/file stores; DB providers should override with an indexed query.
- **Determinism:** Resolution must be deterministic given store state (exact-id-first, then latest `updated_at`).
- **Compatibility:** No schema-version bump; existing sessions (with or without tags) resolve correctly.
- **Security:** No new data surface; tags are already persisted and scrubbed like other meta.
- **Reliability:** Unknown names fail loudly with a clear error rather than silently resolving wrong.

---

## 8. High-Level Design

`tag()` is a small meta mutator: read the session's `SessionMeta`, merge new labels into `tags` (de-duped), bump `updated_at`, and `put_meta`. Because `_write_initial_meta` guarantees a meta row exists from construction, tagging works even before the first run.

Resolution is centralized in one new `BaseSessionStore.resolve(identifier)` method, added to the `SessionStore` Protocol. It tries an exact session-id match first (so real ids always win), then falls back to scanning tags and returning the most-recently-updated match, raising `SessionNotFoundError` when nothing matches. The resume/continue/fork entry points call `resolve` on their incoming identifier, making "name or id" transparent everywhere without duplicating lookup logic. The deliberate design choice is to lean on the existing non-unique `tags` mechanism with a documented "latest wins" rule, keeping the change schema-free; a stricter unique `alias` field is the recorded upgrade path if 1:1 naming ever becomes a requirement.

```
Session.tag("nightly-eval")  ->  SessionMeta.tags += ("nightly-eval",)  (put_meta)

Session.resume(store, "nightly-eval")
        |
        v
store.resolve("nightly-eval")
   exact id? --no--> scan tags --> matches --> max(updated_at) --> "se_abc123"
        |                                                              |
   (yes)-> return as-is                                      resume from head
```

Components:
- **Modified:** `vidbyte/sessions/session.py` (add `tag()`, call `resolve` in `resume`/fork surface), `vidbyte/sessions/store.py` (add `resolve` to Protocol + `BaseSessionStore` default). Possibly DB providers under `vidbyte/lib/providers/` (override `resolve`) if they exist.
- **Reused unchanged:** `SessionMeta.tags`, `list_sessions`, `SessionNotFoundError`, `_read_meta`, `_read_all_meta`.
- **Deleted:** none.

---

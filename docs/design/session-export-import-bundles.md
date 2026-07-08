# Design Doc: Portable session export / import bundles

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

Add store-agnostic `export_session(store, session_id) -> bytes` and `import_session(store, bundle, *, new_id=None) -> str` to move a single session's full checkpoint DAG (meta + all checkpoints + their persisted traces) between stores as a portable zip bundle — to attach to a bug report, ship a repro, or migrate backends. Export reads through the public `SessionStore` Protocol (so any backend can export). Import writes **verbatim** through a new low-level `store.ingest()` primitive that preserves ids, seq, parent links, and head exactly — because the existing `store.put()` deliberately reassigns seq and advances head, which would corrupt an imported DAG.

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

Note: Prompt 2 item **4** ("also explain this more") refers to this feature — the user asked for a deeper implementation treatment of export/import.

---

## 3. Structured Conversation Notes

### Key Decisions
- **Store-agnostic, not filesystem-coupled.** Export reads via the public Protocol (`get_meta`, `history`) + `SessionSerializer`, so `InMemorySessionStore` and DB backends export too — not just `FileSessionStore`. The user noted "FileSessionStore already has the on-disk shape; this is mostly a zip," which is true for the *layout*, but the implementation must go through the serializer so all stores are covered.
- **The central trap: import CANNOT use `store.put()`.** `BaseSessionStore.put()` (`sessions/store.py:45-50`) reassigns `seq` via `_next_seq` and calls `_advance_head`. A repro must land byte-identical (same ids, seq, parent_id, head_id). Therefore a new **verbatim ingest primitive** is required.
- **Add `BaseSessionStore.ingest(meta, checkpoints)`** that writes each checkpoint via the existing raw `_write_checkpoint` (preserving id/seq/parent_id) and the meta via `_write_meta` (preserving head_id) — no reseq, no head advance.
- **Re-id on import is the default for repros.** With `new_id` set, rewrite only the `session_id` field on the meta and on every checkpoint. Checkpoint ids and `parent_id` are UUIDs that stay unchanged, so `head_id`/`parent_id` links remain valid. This lets someone import a bug bundle into a store that already holds sessions without clobbering anything, then `resume()` it as a fresh session.
- **Bundle format = zip mirroring the FileStore on-disk layout:** `manifest.json` + `meta.json` + `checkpoints/NNNNNNNN-<id>.json`. Human-inspectable; a File export is recognizably the same shape as a session directory.
- **`manifest.json` records `SESSION_SCHEMA_VERSION`**; the serializer's `_require_version` already rejects incompatible-version records on parse, so cross-version imports fail loudly.

### Rejected Alternatives
- **"Just zip the FileStore directory."** Rejected as the *implementation* (though it's the mental model): couples export to one backend and can't export in-memory or DB sessions. Go through the serializer + Protocol instead.
- **Reuse `store.put()` for import.** Rejected — it reseqs and advances head, corrupting the imported DAG. This is the key reason `ingest` exists.
- **Preserve the original session id on import by default.** Rejected as the default — risks clobbering an existing session in the target store. Default to re-id (`new_id`); allow same-id import only when the id is absent in the target (else raise, instructing the caller to pass `new_id`).
- **Rewrite checkpoint ids on re-id.** Unnecessary — checkpoint ids are globally unique UUIDs; only the `session_id` field needs rewriting, which keeps `head_id`/`parent_id` valid.

### Constraints & Assumptions
- Export covers a **single session's** checkpoints (its own DAG subtree), obtained via `store.history(session_id)` (ordered by seq) + `store.get_meta(session_id)`.
- Traces are already embedded in each `Checkpoint` (`trace_artifact`, `trace_summary`, `trace_events`) and serialized by `checkpoint_to_dict`, so "checkpoints + traces" travel together for free.
- The serializer already round-trips every record type (`checkpoint_to_dict`/`from_dict`, `meta_to_dict`/`from_dict`) with credential scrubbing — reuse it, add nothing.
- `ingest` is the only genuinely new persistence code across all four session features.
- No `SESSION_SCHEMA_VERSION` bump — the bundle carries the current version and imports of that version write existing record shapes.

### Clarifications & Answers
- **Q (implied): what shape is the bundle?** A: a zip mirroring FileStore's layout (`manifest.json`, `meta.json`, `checkpoints/*.json`), built through the serializer.
- **Q (implied): how do you import without breaking the DAG or clobbering existing sessions?** A: verbatim `ingest` + default re-id.

### Terminology / Glossary
- **Bundle:** a zip archive containing one session's `manifest.json`, `meta.json`, and per-checkpoint JSON files.
- **Verbatim / ingest:** writing records exactly as given, preserving id/seq/parent/head — as opposed to `put()`, which mints new seq and advances head.
- **Re-id:** rewriting the `session_id` field on the meta and every checkpoint to a fresh id so an import lands as a new, non-clobbering session.
- **On-disk shape:** `FileSessionStore`'s layout — `<root>/<session_id>/meta.json` + `<root>/<session_id>/checkpoints/NNNNNNNN-<id>.json` (`sessions/stores/file.py`).

### Implementation Hints for the Downstream Model
- **New file:** `vidbyte/sessions/portable.py` with `export_session(store, session_id, *, serializer=None) -> bytes` and `import_session(store, bundle, *, new_id=None, serializer=None) -> str`. Use stdlib `io.BytesIO`, `zipfile`, `json`.
- **Export:** `meta = store.get_meta(session_id)`, `checkpoints = store.history(session_id)`; write `manifest.json` (`{"schema_version": SESSION_SCHEMA_VERSION, "session_id", "checkpoint_count", "exported_at": _now()}`), `meta.json` = `serializer.meta_to_dict(meta)`, and each checkpoint at `checkpoints/{cp.seq:08d}-{cp.id}.json` = `serializer.checkpoint_to_dict(cp)`. Mirror the exact filename pattern in `file.py:_write_checkpoint`.
- **`ingest` on `BaseSessionStore`** (`sessions/store.py`): iterate checkpoints sorted by seq → `self._write_checkpoint(cp)`; then `self._write_meta(meta)`. Add `ingest(meta, checkpoints)` to the `SessionStore` Protocol too.
- **Import:** open zip from `io.BytesIO(bundle)`; parse `meta.json` via `serializer.meta_from_dict`, checkpoints via `serializer.checkpoint_from_dict` for every `checkpoints/*` name (sorted). If `new_id`: `meta = replace(meta, session_id=new_id)` and `cps = [replace(c, session_id=new_id) for c in cps]` (use `dataclasses.replace`; `Checkpoint`/`SessionMeta` are frozen slots dataclasses). Else if `store._read_meta(meta.session_id) is not None`: raise `SessionStoreError("Session already exists; pass new_id= to import as a copy.", details=...)`. Then `store.ingest(meta, cps)`; return `meta.session_id`.
- **Reuse errors:** `SessionStoreError` from `vidbyte/sessions/errors.py`. Reuse `_now()` pattern (ISO-8601 UTC) — the serializer/session modules already have it; keep a local helper if needed.
- **Serializer construction:** default `serializer or SessionSerializer()` exactly like `FileSessionStore.__init__`.
- **Optional surfacing:** consider exposing `export`/`import` on `SessionClient` (`sessions/client.py`) and re-exporting the two functions from `vidbyte/sessions/__init__.py __all__`. Not required, but check how `SessionClient` wraps other operations and match it.
- **Do NOT** call `store.put()` in import. Do NOT couple to `FileSessionStore` internals — go through Protocol + serializer.

### Open Questions
- **Multi-session bundles?** Current scope is one session per bundle. If a fork tree (parent + children) should travel together, that's a `export_tree`/`import_tree` extension — deferred; confirm if needed.
- **Should `parent_session_id` be preserved or cleared on re-id?** Preserving it keeps lineage pointing at an id that may not exist in the target store. Proposed: preserve as-is (informational); resolution already tolerates missing parents. Confirm.
- **Surface as `Session.export()` instance method too** (vs. only module functions)? The user wrote `export()`/`import()` as if on the session. Proposed: add thin `Session.export(self) -> bytes` delegating to `export_session(self._store, self._session_id)`, and keep `import_session` as a module/classmethod (import has no existing session to hang off). Confirm the exact ergonomic surface.

---

## 4. Goals & Non-Goals

### Goals
- `export_session(store, session_id) -> bytes` producing a portable zip (manifest + meta + checkpoints, traces included), reading via the public Protocol.
- `import_session(store, bundle, *, new_id=None) -> str` writing the bundle verbatim into any store and returning the resulting session id.
- New `BaseSessionStore.ingest(meta, checkpoints)` verbatim-write primitive (added to the Protocol).
- Default re-id on import to avoid clobbering; explicit same-id import guarded by an existing-session check.
- Round-trip fidelity: `export → import → resume` reproduces the session's DAG and traces.

### Non-Goals
- Multi-session / fork-tree bundles.
- Any change to how checkpoints or traces are captured or serialized (reuse `SessionSerializer` as-is).
- A `SESSION_SCHEMA_VERSION` bump.
- Encryption/compression tuning beyond stdlib `ZIP_DEFLATED`.

---

## 5. Background & Context

Sessions are durable but currently trapped in whatever store created them — there's no way to hand a session to a teammate, attach a failing run to a bug report, or migrate from an in-memory/file store to a database backend. The persisted shape is already portable-friendly (`FileSessionStore` writes exactly the meta+checkpoints layout, and traces are embedded in each checkpoint), so the missing pieces are a serializer-driven packager and a verbatim writer. The one non-obvious constraint — that `store.put()` reseqs and advances head and therefore cannot be used for import — is what makes the new `ingest` primitive necessary and shapes the whole feature. The user asked for a deeper treatment here (Prompt 2, item 4).

---

## 6. Requirements

1. `export_session(store, session_id)` returns a zip byte string containing `manifest.json`, `meta.json`, and one JSON file per checkpoint under `checkpoints/`.
2. Export reads only through the public `SessionStore` Protocol (`get_meta`, `history`) so all backends can export.
3. Embedded traces (`trace_artifact`, `trace_summary`, `trace_events`) are included via `checkpoint_to_dict`.
4. `manifest.json` records `schema_version`, `session_id`, `checkpoint_count`, and `exported_at`.
5. `BaseSessionStore.ingest(meta, checkpoints)` writes all records verbatim — preserving id, seq, parent_id, head_id — with no reseq and no head advance.
6. `import_session(store, bundle, *, new_id=None)` parses the bundle, optionally re-ids (default when `new_id` given), and calls `ingest`; returns the final session id.
7. Importing a bundle whose session id already exists in the target store (with no `new_id`) raises `SessionStoreError` instructing the caller to pass `new_id`.
8. Re-id rewrites only `session_id` fields (meta + each checkpoint); checkpoint ids and links are preserved so the DAG stays intact.
9. A round-trip (`export` then `import_session(..., new_id=X)`) yields a session resumable via `Session.resume`.
10. `ingest` is part of the `SessionStore` Protocol.

---

## 7. Non-Functional Requirements

- **Performance:** O(checkpoints) serialize on export and write on import; single zip in memory. Fine for repro-sized sessions.
- **Portability:** Bundle must import into a *different* store type than it was exported from (memory ↔ file ↔ DB).
- **Fidelity:** Byte-identical DAG structure after import (ids/seq/links/head), modulo the deliberately rewritten `session_id` on re-id.
- **Safety:** Import must never clobber an existing session silently; guard with the existing-id check + `new_id`.
- **Compatibility:** `manifest` version + serializer `_require_version` reject incompatible bundles loudly.
- **Security:** Serializer already scrubs credential-like keys on the way in; no secrets travel in a bundle. Verify scrub coverage holds for trace payloads.

---

## 8. High-Level Design

A new `vidbyte/sessions/portable.py` module provides two functions. `export_session` pulls the session's `SessionMeta` and ordered `Checkpoint` list through the public store Protocol, serializes each with the existing `SessionSerializer`, and packs them into an in-memory zip mirroring `FileSessionStore`'s on-disk layout (`manifest.json`, `meta.json`, `checkpoints/NNNNNNNN-<id>.json`). Because traces are embedded in each checkpoint and the serializer already handles them, the bundle is "checkpoints + traces" with no extra work.

`import_session` reverses this: parse the zip, deserialize meta + checkpoints, optionally re-id (rewrite only `session_id` fields, keeping UUID checkpoint ids and their links valid), and write everything through a new `BaseSessionStore.ingest(meta, checkpoints)` primitive. `ingest` exists precisely because the normal `put()` path reassigns seq and advances head — behavior that would corrupt an imported DAG. `ingest` uses the same raw `_write_checkpoint`/`_write_meta` primitives the stores already implement, so both bundled stores (and any DB provider) get verbatim import for free. Re-id-by-default plus an existing-id guard means importing a bug bundle is safe against clobbering, and the result is immediately `resume`-able.

```
EXPORT (any store)                          IMPORT (any store, verbatim)
------------------                          ----------------------------
store.get_meta(id) ─┐                       unzip ─> meta.json  ─> meta
store.history(id)  ─┤                              └> checkpoints/* ─> [Checkpoint]
                    v                                        │
   SessionSerializer.*_to_dict                     optional re-id (session_id only)
                    v                                        v
   zip{ manifest.json, meta.json,            store.ingest(meta, checkpoints)
        checkpoints/NNNN-<id>.json }           └ _write_checkpoint (keep seq/id/parent)
                    │                            └ _write_meta      (keep head_id)
                    v                                        v
                bytes  ── ship / attach ──>  resumable session in target store
```

Components:
- **Created:** `vidbyte/sessions/portable.py` (`export_session`, `import_session`).
- **Modified:** `vidbyte/sessions/store.py` (add `ingest` to `BaseSessionStore` + Protocol), `vidbyte/sessions/__init__.py` (`__all__`), optionally `vidbyte/sessions/client.py` (surface on `SessionClient`) and `vidbyte/sessions/session.py` (thin `Session.export`).
- **Reused unchanged:** `SessionSerializer`, `_write_checkpoint`/`_write_meta` in both stores, `SessionStoreError`, `Checkpoint`/`SessionMeta` (frozen dataclasses via `replace`).
- **Deleted:** none.

---

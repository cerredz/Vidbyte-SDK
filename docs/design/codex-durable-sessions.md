# Design Doc: Codex Durable Sessions

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`CodexHarnessAgent` sets `session_persistence_supported = False`, and `Session.__init__` refuses such an agent before touching the store, so no Codex run can be checkpointed, resumed after a process restart, or replayed. The blocker is that `RunState` — the serializable snapshot `Session` checkpoints — has no field for a provider-owned thread id, which for Codex is the only handle to the conversation. This change adds an optional `provider_state` field to `RunState`, implements `export_state()` and `restore()` on the Codex agent, routes `Session`'s restore path through a small registry so the dispatch stays inside the SDK's layer graph, and flips the flag. It restores *conversation* state only: a resumed thread does not undo the files the previous turns edited.

---

## 2. Goals & Non-Goals

### Goals

- Add `RunState.provider_state`, an optional JSON-safe mapping, without bumping `SESSION_SCHEMA_VERSION` — see §7 for why that matters.
- Implement `CodexHarnessAgent.export_state()` carrying the native thread id, the translated provider settings, fork lineage, and history.
- Implement `CodexHarnessAgent.restore()` following `BaseAgent.restore`'s rehydration contract: rebuild from `RunState`, re-supply non-serializable parts as arguments.
- Route `Session._restore_agent` through `SessionRestoreRegistry` so a Codex checkpoint rebuilds a Codex agent, without adding a lower-layer import of `vidbyte.agents.codex`.
- Reject an unresumable checkpoint loudly at restore: an ephemeral thread, or a checkpoint with no thread id.
- Flip `session_persistence_supported` to `True`.

### Non-Goals

- File and workspace restoration. Restoring a thread restores what was said, not what was written to disk. Roadmap task D05 keeps file recovery explicitly separate, and this design states the limit rather than implying it.
- Cross-host portability. A Codex rollout lives on the host that created it; this change detects a missing thread id but cannot verify a remote rollout still exists without a provider call, which `export_state`/`restore` deliberately do not make.
- `Session.fork()` producing a native Codex thread fork. Session forking branches Vidbyte checkpoint state; composing it with `CodexFork` is roadmap task F05 and needs the two lineages reconciled first.
- Serializing the `ContextManager`, `output_schema` type, or middleware. Those are live objects; the rehydration contract re-supplies them, exactly as `BaseAgent.restore` already does.
- Verifying at restore that the provider still holds the thread. That requires a live `thread_resume`, which belongs to the first turn after restore, not to rehydration.

---

## 3. Background & Context

`Session.__init__` gates on the flag before any store mutation (`vidbyte/sessions/session.py:102`):

```python
if not getattr(agent, "session_persistence_supported", True):
    raise SessionError("This agent type does not support durable session persistence.", ...)
```

`Session.checkpoint` and `record_turn` both persist through `_persist`, which calls `self._agent.export_state()` (`vidbyte/sessions/session.py:312`). `BaseAgent.export_state` (line 403) builds a `RunState` whose fields are all shaped around a direct-runtime agent: `provider`, `model_name`, `temperature`, `runtime_type`, `runtime_config`, `algorithm`. None can hold a provider thread id.

The restore side is the harder half. `Session._restore_agent` (line 427) is a single static method called from `fork_from` and `resume` (lines 278 and 290), and it hardcodes one implementation:

```python
from vidbyte.agents.base import BaseAgent
return BaseAgent.restore(source.run_state, tools=tools, middleware=middleware, tracer=tracer, output_schema=output_schema)
```

That is why simply flipping the flag would ship a hole rather than a feature: `Session(codex_agent)` would construct, checkpoint, and then hand back a `BaseAgent` on resume — a different agent type, silently.

The layering constraint is what shapes the fix. `lint/rules/a006_directed_dependency_graph.py` lists `vidbyte.sessions` in `LOWER_LAYER_PREFIXES` and `vidbyte.agents` in `ORCHESTRATION_PREFIXES`, so a concrete module under `vidbyte/sessions/` importing `vidbyte/agents/` is a blocking finding — and the rule's AST visitor descends into function bodies, so the existing local import inside `_restore_agent` is counted. It appears in `lint/baseline.json`'s A006 allowance of 34 as pre-existing debt. Adding a second such import for `vidbyte.agents.codex.agent` would push the count past the allowance and fail the gate.

`vidbyte/lib/registries/` is the SDK's established answer to "look up an implementation by key," holding `AgentRegistry`, `RuntimeRegistry`, `ComponentRegistry`, `ToolRegistry`, and others. Self-registration at import time is likewise an existing pattern: `vidbyte/agents/runtimes/actor/actor.py:243` calls `actor_registry.register(...)`, and `vidbyte/tools/mcp/presets.py:421` calls `McpPresetRegistry.register(_preset)`. A registry in `vidbyte/lib/` is importable from `vidbyte/sessions/` (lower to lower), which is what makes the dispatch legal rather than merely tidy.

The roadmap tracks this as **D01** ("Implement export and restore"), **D02** ("Align checkpoints with turns"), and **D03** ("Define portability"), and its completion criterion is that export and restore work across process restarts "without treating transcript text as provider state."

---

## 4. Requirements

### Functional Requirements

1. `RunState` gains `provider_state: Mapping[str, Any]`, defaulting to an empty mapping.
2. `SESSION_SCHEMA_VERSION` is **not** bumped. The field is optional with a default, so a payload written before this change rehydrates unchanged.
3. `SessionSerializer` writes and reads `provider_state` through its existing `_safe` JSON-safe path.
4. `CodexHarnessAgent.export_state()` returns a `RunState` whose `provider_state` carries the state kind, the native `thread_id`, the serialized `CodexAgentSettings`, `additional_context`, `context_placements`, and the `forked_from_thread_id`/`fork_depth` lineage from the agent's metadata.
5. `export_state()` records `provider="codex"` and `runtime_type="codex_harness"`, so a reader can tell what produced the checkpoint without inspecting `provider_state`.
6. `export_state()` serializes `self.history` through `SessionSerializer.message_to_dict`, matching `BaseAgent.export_state`.
7. `export_state()` contains no live objects and no secrets: the `ContextManager`, `output_schema` type, and middleware are all omitted rather than partially serialized.
8. `CodexHarnessAgent.restore(state, *, output_schema=None, context_manager=None, middleware=())` rebuilds an agent whose `thread_id` equals the exported one, and whose history is rehydrated.
9. `restore()` raises `SessionError` when `provider_state` has no thread id, because a checkpoint without one cannot resume a conversation and would silently start a fresh thread.
10. `restore()` raises `SessionError` when the exported thread was `ephemeral`, because an in-memory thread dies with the process that created it and can never be resumed.
11. `SessionRestoreRegistry` maps a `provider_state` kind to a restore callable; `Session._restore_agent` consults it and falls back to `BaseAgent.restore` when no kind is present or registered.
12. `CodexHarnessAgent` registers itself for the `codex` kind at module import.
13. `session_persistence_supported` becomes `True`, so `Session(codex_agent)` constructs.
14. A restored agent's provider settings are equal to the exported agent's, so the next turn resumes with the same model, sandbox, and approval mode.

### Non-Functional Requirements

- **Performance:** one dict construction per checkpoint. No provider call, no I/O beyond what the `SessionStore` already does.
- **Scalability:** `provider_state` is bounded by the settings record's own size, which is a fixed set of scalar fields plus the caller's `thread.config` mapping. It does not grow with turn count; history already dominates a checkpoint's size.
- **Security:** `provider_state` passes through `SessionSerializer._safe`, and the settings serializer omits `client.env` entirely — environment variables are the one Codex settings field that routinely holds credentials.
- **Observability:** `provider` and `runtime_type` on the `RunState` make a Codex checkpoint identifiable in a store without parsing `provider_state`.
- **Reliability:** restore fails loudly on an unresumable checkpoint rather than producing an agent that looks restored and is actually fresh.

---

## 5. High-Level Design

Three pieces, in dependency order.

**`RunState.provider_state`** is the enabling change. It is a single optional mapping, and it is deliberately generic rather than Codex-specific: `MultiAgent` also sets `session_persistence_supported = False`, and any future provider-owned-state agent needs the same slot. Because it defaults to empty and is read with `.get`, no schema version bump is needed, which matters more than it sounds — `SessionSerializer._require_version` demands exact equality, so a bump would make every already-persisted session unreadable.

**`CodexSessionTranslator`** in `vidbyte/agents/codex/session.py` owns the two conversions: `CodexAgentSettings` to a JSON-safe mapping and back. This is the same shape as every other file in the package — one collaborator, one concern — and it keeps the agent facade thin. It is also where the two portability rejections live, because they are properties of the persisted state rather than of the agent that will be built from it.

**`SessionRestoreRegistry`** in `vidbyte/lib/registries/session_restore.py` is what makes the dispatch legal. `Session._restore_agent` cannot import `vidbyte.agents.codex` without a blocking A006 regression, but it can import `vidbyte.lib.registries`. The registry holds `kind -> callable`, the Codex module registers itself at import, and `_restore_agent` looks up the kind on the checkpoint's `provider_state`, falling back to `BaseAgent.restore` when there is none. One entry today; `MultiAgent` is the obvious second.

The rejected alternative worth naming here is putting the dispatch in `BaseAgent.restore` — see §14.

```
checkpoint
   |
   v
Session._persist -> agent.export_state()
                        |
                        |-- CodexSessionTranslator.to_provider_state()
                        |      {kind: codex, thread_id, codex: {...}, lineage}
                        v
                   RunState(provider="codex", runtime_type="codex_harness",
                            provider_state={...}, history=[...])
                        |
                        v
                   SessionStore  (survives process restart)

resume / fork_from
   |
   v
Session._restore_agent(checkpoint)
   |
   |-- SessionRestoreRegistry.resolve(provider_state["kind"])
   |        found  -> CodexHarnessAgent.restore(...)   <- rejects ephemeral / no thread id
   |        absent -> BaseAgent.restore(...)           <- unchanged for every other agent
   v
live agent whose next turn calls thread_resume(thread_id)
```

---

## 6. Detailed Design

### 6.1 RunState provider state

**File(s):** `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/sessions/serialization.py`
**Type:** Modified

#### What it does

Gives a checkpoint a slot for state owned by a provider rather than by Vidbyte.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class RunState:
    ...
    provider_state: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. `_run_state_to_dict` adds `"provider_state": self._safe(state.provider_state)`, reusing the existing JSON-safe path rather than adding a second one.
2. `_run_state_from_dict` reads `dict(data.get("provider_state", {}) or {})`, so an older payload yields an empty mapping.

#### Edge Cases & Error Handling

- **Older payload with no key.** Reads as empty, and `_restore_agent` then takes the `BaseAgent` path — which is exactly correct, because an old payload was written by a `BaseAgent`.
- **Non-JSON-safe value.** `_safe` already handles this for four other fields; no new policy.

### 6.2 CodexSessionTranslator

**File(s):** `vidbyte/agents/codex/session.py`
**Type:** New file

#### What it does

Converts Codex provider settings to and from a JSON-safe mapping, and refuses a checkpoint that cannot resume.

#### Interface / API

```python
class CodexSessionTranslator:
    """Converts Codex provider state to and from a checkpoint mapping."""

    @classmethod
    def to_provider_state(cls, request: CodexSessionExportRequest) -> dict[str, Any]: ...

    @classmethod
    def to_settings(cls, provider_state: Mapping[str, Any]) -> CodexAgentSettings: ...

    @classmethod
    def require_resumable(cls, provider_state: Mapping[str, Any]) -> str: ...
```

`CodexSessionExportRequest` is a frozen slots dataclass holding `settings: CodexHarnessAgentSettings` and `thread_id: str`.

#### Logic / Algorithm

`to_provider_state`:
1. Emit `kind`, `thread_id`, the lineage keys from `settings.metadata`, and `additional_context`.
2. Emit the client, thread, turn, and subagent settings field by field, converting each enum to its `.value` and each tuple to a list. Field-by-field rather than reflective, so a new provider setting is a deliberate decision here rather than a silent inclusion.
3. Omit `client.env` entirely.

`to_settings` rebuilds the four settings records, coercing each enum from its stored value and each list back to a tuple.

`require_resumable` returns the thread id, raising `SessionError` when it is empty or when `thread.ephemeral` was true.

#### Edge Cases & Error Handling

- **`client.env` was set.** Omitted from the checkpoint, and a restored agent has an empty `env`. The file header states this, because a caller relying on `env` must re-supply it — the alternative is writing credentials into a session store.
- **An unknown enum value in a stored payload.** The enum constructor raises, which surfaces as a `SessionError` from the restore boundary rather than a bare `ValueError`.
- **`thread.config` mapping.** Passed through `_safe`; it is already constrained to JSON values by `CodexThreadSettings.__post_init__`.

### 6.3 Agent export and restore

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### Interface / API

```python
class CodexHarnessAgent:
    session_persistence_supported = True

    def export_state(self) -> RunState: ...

    @classmethod
    def restore(
        cls,
        state: RunState,
        *,
        output_schema: object | None = None,
        context_manager: object | None = None,
        middleware: Sequence[object] = (),
        **_ignored: object,
    ) -> CodexHarnessAgent: ...
```

`restore` accepts and discards the extra keyword arguments `Session._restore_agent` passes to `BaseAgent.restore` (`tools`, `tracer`), because a Codex agent has neither. Swallowing them in a named `**_ignored` is deliberate and documented: the registry's callable signature must accept the shared call shape.

#### Logic / Algorithm

`export_state`:
1. Build `provider_state` through `CodexSessionTranslator.to_provider_state`.
2. Return a `RunState` with `provider="codex"`, `runtime_type="codex_harness"`, `algorithm="default"`, `temperature=None`, empty `runtime_config`/`loop_settings`/`aggregate_plan`/`context_summary`/`trace_option`, the agent's `metadata`, and serialized history.

`restore`:
1. Call `require_resumable`, which raises before anything is built.
2. Rebuild `CodexHarnessAgentSettings` from the `RunState` scalars plus the re-supplied live objects.
3. Construct the agent, which re-runs the full construction-time translation — so a checkpoint carrying settings this SDK version rejects fails at restore rather than at the first turn.
4. Rehydrate `history` through `SessionSerializer.message_from_dict`.

#### Edge Cases & Error Handling

- **Restore then run.** The first `arun` after restore takes the `thread_resume` path because `thread_id` is non-empty. A thread the provider no longer holds fails there with `CODEX_THREAD_RESUME_FAILED`, which is the right boundary: only a live call can know.
- **Files.** Not restored, and not claimed to be. The file header and the design's overview both say so.
- **`output_schema` not re-supplied.** The restored agent has none, and a turn that previously validated structured output will not. This matches `BaseAgent.restore`'s contract exactly, where `output_schema` is likewise a re-supplied argument.

### 6.4 Session restore dispatch

**File(s):** `vidbyte/lib/registries/session_restore.py`, `vidbyte/lib/registries/__init__.py`, `vidbyte/sessions/session.py`
**Type:** New file, then modified

#### Interface / API

```python
class SessionRestoreRegistry:
    """Maps a persisted provider-state kind to the callable that rebuilds its agent."""

    @classmethod
    def register(cls, kind: str, factory: Callable[..., Any]) -> None: ...

    @classmethod
    def resolve(cls, kind: str) -> Callable[..., Any] | None: ...
```

#### Logic / Algorithm

1. `Session._restore_agent` reads `source.run_state.provider_state.get("kind", "")`.
2. An empty or unregistered kind takes the existing `BaseAgent.restore` path, byte-for-byte unchanged.
3. A registered kind calls its factory with the same keyword arguments.

#### Edge Cases & Error Handling

- **Registered kind, but the module was never imported.** Cannot occur through the public surface: `vidbyte/agents/__init__.py` imports `CodexHarnessAgent` eagerly, and `vidbyte/__init__.py` re-exports it. A caller who imports `vidbyte.sessions` alone and hand-builds a Codex checkpoint gets the `BaseAgent` fallback; §13 records this as the one gap.
- **Double registration.** Last registration wins, and the registry does not raise. Import is idempotent in practice, and raising on re-import would break module reloading in test runners.

---

## 7. Data Model Changes

### 7.1 RunState

**Change type:** Modified

```python
provider_state: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:**

- Forward migration: none required. The field is optional with a default, and `_run_state_from_dict` reads it with `.get(..., {})`, so every payload written before this change rehydrates unchanged.
- `SESSION_SCHEMA_VERSION` stays at `1`. This is a deliberate decision, not an oversight: `SessionSerializer._require_version` raises `SessionVersionError` unless the stored version equals the constant exactly, so bumping it would make every already-persisted session in every store unreadable. An additive optional field does not warrant that.
- Rollback: reverting this branch leaves stored `provider_state` keys in the payloads, which an older reader ignores because it never asks for them.

---

## 8. API Changes

N/A - no HTTP endpoints. The public Python surface gains `RunState.provider_state`, `SessionRestoreRegistry`, `CodexHarnessAgent.export_state`/`restore`, and the flipped `session_persistence_supported`. All additive.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-durable-sessions.md` | This design document |
| CREATE | `vidbyte/agents/codex/session.py` | `CodexSessionTranslator` |
| CREATE | `vidbyte/lib/registries/session_restore.py` | `SessionRestoreRegistry` |
| MODIFY | `vidbyte/lib/dataclasses/sessions.py` | `RunState.provider_state` |
| MODIFY | `vidbyte/sessions/serialization.py` | Read and write `provider_state` |
| MODIFY | `vidbyte/sessions/session.py` | Dispatch `_restore_agent` through the registry |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Export `SessionRestoreRegistry` |
| MODIFY | `vidbyte/lib/constants/codex.py` | Provider-state kind, runtime-type, and key names (A007) |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | `CodexSessionExportRequest` |
| MODIFY | `vidbyte/agents/codex/agent.py` | `export_state`, `restore`, flag, self-registration |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export the new dataclass |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export for public-export integrity (S015) |
| CREATE | `tests/test_codex_durable_sessions.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-durable-sessions.py` | Phase 5 verification script |

Totals: 5 create, 10 modify, 0 delete.

---

## 10. Testing Plan

All tests run offline against an `InMemorySessionStore` and a fake transport.

### Unit Tests

- `CodexSessionTranslator` -> `round-trips every provider settings field` — [Silent Failure] — the headline defect: a settings field dropped from the mapping silently restores as a default, so a sandbox-restricted agent could resume unrestricted. Asserts the rebuilt `CodexAgentSettings` equals the original.
- `CodexSessionTranslator` -> `round-trips every enum through its value` — [Silent Failure] — an enum stored as `repr` restores as a default rather than raising.
- `CodexSessionTranslator` -> `omits client env from the provider state` — [Hidden Assumption] — the environment mapping is the one settings field that routinely holds credentials, and a session store is not a secret store.
- `CodexSessionTranslator` -> `carries fork lineage from the agent metadata` — [Silent Failure] — losing `fork_depth` makes a restored child look like a root.
- `CodexSessionTranslator.require_resumable` -> `raises for an empty thread id` — [Hidden Failure] — without it, restore silently starts a fresh thread that looks resumed.
- `CodexSessionTranslator.require_resumable` -> `raises for an ephemeral thread` — [Hidden Failure] — an in-memory thread dies with its process; resuming it is impossible, not merely unlikely.
- `CodexSessionTranslator.to_settings` -> `raises a SessionError, not a ValueError, for an unknown enum value` — [Hidden Failure] — the restore boundary must classify its own failures.
- `CodexHarnessAgent.export_state` -> `records provider codex and runtime_type codex_harness` — [Edge Case]
- `CodexHarnessAgent.export_state` -> `contains no live objects` — [Hidden Assumption] — asserts the exported state is JSON-serializable end to end, which a leaked `ContextManager` would break.
- `CodexHarnessAgent.export_state` -> `serializes history` — [Silent Failure]
- `CodexHarnessAgent.restore` -> `rebuilds the same thread id and settings` — [Silent Failure]
- `CodexHarnessAgent.restore` -> `tolerates the tools and tracer keyword arguments Session passes` — [Hidden Assumption] — the registry's callable must accept the shared call shape or resume raises `TypeError`.
- `SessionRestoreRegistry` -> `resolves a registered kind` — [Edge Case]
- `SessionRestoreRegistry` -> `returns None for an unknown kind` — [Edge Case]
- `RunState` -> `defaults provider_state to an empty mapping` — [Edge Case]

### Integration Tests

The flow to prove is a full checkpoint-and-resume cycle through a real `Session` and a real `SessionStore`, because the defects here — the wrong agent type on resume, a version error on old data, a checkpoint that cannot be read back — only appear end to end.

- `Session(codex_agent)` constructs rather than raising. [Edge Case] — the flag flip, proven at its actual gate.
- One turn, then `session.checkpoint()`, then `Session.resume(store, id)` yields a `CodexHarnessAgent` — **not** a `BaseAgent` — whose `thread_id` matches. [Hidden Failure] — this is the hole that flipping the flag alone would have shipped, and only an `isinstance` assertion after a real resume catches it.
- A `RunState` payload written **without** `provider_state` still deserializes, and resuming it yields a `BaseAgent`. [Hidden Assumption] — proves backward compatibility and that the fallback path is intact for every existing agent.
- A serialized checkpoint round-trips through `SessionSerializer.checkpoint_to_dict`/`checkpoint_from_dict` with `provider_state` preserved. [Silent Failure] — a field written but not read back would leave restore silently taking the `BaseAgent` path.
- Resuming a checkpoint whose thread was ephemeral raises `SessionError`, and no agent is constructed. [Hidden Failure]
- Two sequential turns then a checkpoint carries both history entries into the restored agent. [Silent Failure]
- The restored agent's next turn calls `thread_resume` rather than `thread_start` — asserted by inspecting the fake transport's request `thread_id`. [Silent Failure] — the whole point of persisting the thread id; a restored agent that starts a fresh thread loses the conversation while appearing to work.

### Manual / QA Test Cases

1. Given a Codex agent that ran one turn and was checkpointed, when the process restarts and the session resumes from the store, then the agent is a `CodexHarnessAgent` with the original thread id, and its next turn resumes the native thread. — [Hidden Failure]
2. Given a Codex agent whose thread was created with `ephemeral=True`, when a resume is attempted, then it fails with a `SessionError` naming the ephemeral thread rather than starting a fresh one. — [Hidden Failure]
3. Given a session store holding checkpoints written before this change, when they are read, then they deserialize without a `SessionVersionError`. — [Hidden Assumption]
4. Given a restored Codex agent, when its working tree is inspected, then the files from the previous turns are in whatever state the filesystem left them — the session restored the conversation, not the workspace. — [Hidden Assumption]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Reached only on the first turn after restore, via `thread_resume` | A thread the provider no longer holds fails there, which is the correct boundary |

No dependency additions.

---

## 12. Rollout & Deployment

No feature flag. The change is additive and backward compatible: `provider_state` defaults to empty, the schema version is unchanged, and the `BaseAgent.restore` path is untouched for every agent that does not register a kind.

The one behavior change is intended: `Session(codex_agent)` now constructs instead of raising, which no existing caller can be relying on.

This is PR 5 of five independent Codex-translation PRs, each branched from `origin/main`. It should be merged last. It is the only one of the five that touches files outside `vidbyte/agents/codex/` and `vidbyte/lib/`, so it warrants the closest review of the shared `Session` path.

---

## 13. Open Questions

- [ ] `SessionRestoreRegistry` relies on `vidbyte.agents.codex.agent` having been imported for its kind to resolve. Through the public surface that always holds, because `vidbyte/agents/__init__.py` imports the class eagerly. A caller importing only `vidbyte.sessions` would get the `BaseAgent` fallback. Should the registry raise on an unregistered-but-known kind instead of falling back silently?
- [ ] Should `Session.fork()` on a Codex checkpoint also create a native thread fork, so the two lineages stay aligned? Today it branches Vidbyte state only, and both children resume the same native thread. Roadmap F05.
- [ ] Should `export_state` optionally include a workspace marker (a git commit, a worktree path) so a caller can reconcile files themselves? It would not restore anything, but it would let a caller detect drift. Deliberately out of scope here.

---

## 14. Alternatives Considered

### Alternative 1: Import `CodexHarnessAgent` directly in `Session._restore_agent`

- What: Add a second local import alongside the existing `from vidbyte.agents.base import BaseAgent`.
- Why rejected: `lint/rules/a006_directed_dependency_graph.py` counts imports inside function bodies, and `vidbyte.sessions` importing `vidbyte.agents` is a lower-layer-imports-orchestration finding. The existing one is baselined debt at an allowance of 34; a second would regress the gate. Raising the baseline to accommodate new code is explicitly forbidden.

### Alternative 2: Dispatch inside `BaseAgent.restore`

- What: Let `BaseAgent.restore` detect Codex provider state and return a `CodexHarnessAgent`.
- Why rejected: A classmethod on `BaseAgent` returning something that is not a `BaseAgent` breaks its declared return type and its name. Every caller reading `BaseAgent.restore(...)` would be wrong about what it produces.

### Alternative 3: Bump `SESSION_SCHEMA_VERSION` to 2

- What: Treat the new field as a schema change.
- Why rejected: `SessionSerializer._require_version` demands exact equality, so a bump makes every already-persisted session raise `SessionVersionError`. The field is optional with a default and reads back as empty from older payloads, so there is nothing a version bump would protect against and a large amount it would break.

### Alternative 4: Store the full native transcript instead of the thread id

- What: Serialize the conversation text so a session is portable across hosts.
- Why rejected: A transcript is not provider state. Codex owns the thread, and replaying text into a new thread produces a different conversation with a different id, different cached prefixes, and no relationship to the original — while looking, to the caller, like a resume. The roadmap states this directly: exporting a text transcript cannot make a native thread portable.

### Alternative 5: Verify the thread still exists during `restore()`

- What: Call `thread_resume` at restore time to confirm the rollout.
- Why rejected: It makes rehydration a network operation, which no other `restore` in the SDK is, and it would spawn a Codex process during what a caller expects to be a local object construction. The first turn after restore already surfaces a missing thread as `CODEX_THREAD_RESUME_FAILED`, at a boundary the caller is already awaiting.

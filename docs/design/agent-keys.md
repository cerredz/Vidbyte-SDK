# Design Doc: Agent Keys

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-20
**Last Updated:** 2026-08-20

---

## 1. Overview

`AgentKeys` is a new class, owned by every `BaseAgent` instance, that tracks five specific pieces of agent-runtime state as content-addressed, decodable keys: the agent's full settings, its latest response, its entire toolset, its latest tool input/output, and any named step a caller records. Each is exposed as a short SHA-256 digest suitable for use as a database key or idempotency token, and each digest can be resolved back to the original JSON-safe data it was derived from via `AgentKeys.decode(digest)`. `AgentKeys` is constructed eagerly inside `BaseAgent.__init__`, owns its own state (an in-memory content store), and is updated by `BaseAgent` (and, for tool calls, the runtime loop) pushing data into it as the agent runs — not by `AgentKeys` reaching back into the agent to pull state on demand.

---

## 2. Goals & Non-Goals

### Goals
- Track exactly five keys throughout the agent runtime: (1) all agent settings as one hash, (2) the latest response as a hash, (3) the entire toolset as a hash, (4) the latest tool input and output as one hash, (5) any caller-named step as a hash.
- Every one of the five must be decodable: given the digest, recover the original data.
- `AgentKeys` is constructed in `BaseAgent.__init__`, holds its own state, and is written to by `BaseAgent`/the runtime loop as things happen — not pulled from the agent lazily.
- Eliminate the four existing independent reimplementations of "canonicalize to JSON, sha256, sometimes truncate" scattered across `agents/settings/tool.py`, `middleware/builtins/loop_detection.py`, `agents/multi/ledger_controller.py`, and `agents/algorithms/prosecutor_defender_judge.py`, by extracting one shared pure hashing module they all call into.
- Keep the in-memory content store bounded so a long-running agent cannot grow it without limit.

### Non-Goals
- `BaseAgent` does not gain a first-class "step" concept, step registry, or loop hooks. `record_step` is a pure key-derivation-and-storage helper that callers (e.g. a harness state machine) invoke explicitly with a name and version; `BaseAgent` never calls it automatically. This was already decided and confirmed in the prior design conversation and is unchanged here.
- No persistence beyond the current process. `AgentKeys`' store is an in-memory cache scoped to one `BaseAgent` instance's lifetime; it is not a database and does not survive process exit or agent garbage collection. A caller who needs a digest to remain decodable after this process ends must persist `(digest, decoded_payload)` themselves — e.g. a harness writing a wallet-charge record to its own store.
- No change to `ToolSettings.fingerprint`'s external behavior or callers beyond swapping its internal hashing to the shared primitive — its return shape (`f"{tool_name}:{digest[:16]}"`) is unchanged.
- No new tests (per this workflow's "no tests" scope) — existing CI must still pass in full.

---

## 3. Background & Context

This follows a multi-turn design conversation about adding deterministic key/hash derivation to `vidbyte-sdk`'s `BaseAgent`, originally motivated by a production principle about step names being database keys (rename a step, or fail to version it, and a resumed run can silently redo — or double-charge — work). Repo research across that conversation established:

- `BaseAgent` (`vidbyte/agents/base.py`) has no "step" concept; steps belong one layer up, in harness state machines (e.g. `vidbyte-harnesses`' `job_applier`).
- The composition pattern for attaching a facade to `BaseAgent` already exists twice: `AgentLoopSettings`/`ToolSettings` (constructed once, held as attributes) and `Behavior` (lazily built, cached). This feature uses eager construction in `__init__`, matching the settings objects' pattern, because `AgentKeys` needs to start accumulating store entries (the initial settings snapshot, the initial toolset) from construction time.
- Four independent hand-rolled implementations of the same "JSON-canonicalize, sha256, truncate" idiom already exist: `ToolSettings.fingerprint` (`agents/settings/tool.py:82-89`), `LoopDetectionMiddleware._make_key`/`_make_output_key` (`middleware/builtins/loop_detection.py:181-193`), `MultiAgentOrchestratorLedger._fingerprint` (`agents/multi/ledger_controller.py:183-189`), and two inline `hashlib.sha256(...)` calls in `ProsecutorDefenderJudgeAlgorithm` (`agents/algorithms/prosecutor_defender_judge.py:399,491`). One of these (`ledger_controller._fingerprint`) differs in a way that matters: it refuses to serialize non-JSON-native values and falls back to an identity marker, while the other three silently stringify via `default=str`, which is memory-address-dependent for objects without a `__str__` override and can produce non-deterministic digests for structurally-identical inputs. This PR centralizes the shared mechanics without erasing that one deliberate behavioral difference.
- The user has now specified the exact five keys to track, and required all five to be decodable. A raw SHA-256 digest is not invertible; decodability is achieved via content-addressed storage (see Section 13).

---

## 4. Requirements

### Functional Requirements
1. `AgentKeys` is constructed inside `BaseAgent.__init__` and assigned to `self.keys`, with all data it needs (agent name, provider, model name, runtime type, run id, system prompt) passed in at construction.
2. `AgentKeys.record_settings(settings_snapshot)` accepts a JSON-safe dict describing the agent's full configuration, stores it, and returns a digest. `BaseAgent` calls this at the end of `__init__` and at the start of every `generate_reply()` call, so the settings key always reflects what was in effect for the most recent run.
3. `AgentKeys.record_response(message)` accepts a JSON-safe dict of the latest `AgentMessage` (via `SessionSerializer.message_to_dict`), stores it, and returns a digest. `BaseAgent` calls this immediately after `self.last_reply = reply` inside `generate_reply()`.
4. `AgentKeys.record_toolset(tool_names, mcp_tool_names=())` accepts the current set of bound tool names (local + MCP-attached), stores it, and returns a digest. `BaseAgent` calls this at the end of `__init__` and again inside `add_tool()` after the mutation.
5. `AgentKeys.record_tool_call(tool_name, arguments, output)` accepts one tool call's input and output together, stores it, and returns a digest. `BaseAgent` calls this from `_record_tool_contexts` for the most recently recorded `ToolCallContext`.
6. `AgentKeys.record_step(name, *, version, run_id=None)` accepts a caller-supplied step name and required version (never auto-triggered by `BaseAgent`), stores `{name, version, run_id, identity_key}`, and returns a digest. Raises `ConfigurationError` if `version < 1` or no `run_id` can be resolved (explicit arg or `self.run_id`).
7. `AgentKeys.decode(digest)` returns the exact JSON-safe mapping that was stored for that digest, or raises `AgentKeyNotFoundError` if the digest is unknown (never recorded, or evicted — see Non-Functional Requirements).
8. `AgentKeys.identity_key()` returns a digest of `{agent_name, provider, model_name, runtime_type, system_prompt_hash}`, computed once at construction and cached (owned data, not recomputed per call).
9. `AgentKeys` exposes `latest_settings_key`, `latest_response_key`, `latest_toolset_key`, `latest_tool_call_key` as `str | None` properties (O(1) reads of the last digest recorded for each kind; `None` before the first record).
10. `vidbyte/agents/hashing.py` provides `canonical_json`, `hex_digest`, and `stable_key` as the single shared implementation of the canonicalize-then-hash idiom; the four existing duplicate implementations are migrated onto it without changing their observable digest shape (`tool_name:16-hex-chars`) except where digest *values* necessarily change as a byproduct of centralizing (none of the four persist digests across process restarts, so this is safe).

### Non-Functional Requirements
- **Bounded memory:** `AgentKeys`' internal store is capped at `max_store_entries` (default 2000), evicting the oldest entry (FIFO, via `collections.OrderedDict`) when exceeded. Content-addressing means unchanged content (e.g. settings that never change post-construction) reuses the same digest and does not grow the store — the cap primarily bounds `record_response`/`record_tool_call`, which produce new content on essentially every call. This is a deliberate, named tradeoff: bounded memory in exchange for old digests eventually returning `AgentKeyNotFoundError` on decode once evicted. See Open Questions for the default cap value.
- **Determinism:** every hash is computed via `json.dumps(value, sort_keys=True, default=str)` before `sha256`, matching the existing idiom already proven in `ToolSettings.fingerprint`.
- **No new I/O:** everything is in-memory, synchronous, pure-Python (`hashlib`, `json`, `collections.OrderedDict`). No network or filesystem access.
- **Typed returns:** every `record_*`/`identity_key`/`latest_*_key` method returns `str` (or `str | None` for the latest-key properties); `decode` returns `Mapping[str, Any]`. No `Any`-typed dispatch.
- **CI gate (recorded per workflow requirement):** this repo's canonical CI command is `python scripts/run_ci.py` (after `python -m pip install -e ".[dev]"`), confirmed present at `vidbyte-sdk/scripts/run_ci.py`. Diagnostic-only stages: `python scripts/run_ci.py --stage source` and `--stage package`. This must pass in full before the PR is opened, per Phase 5d.

---

## 5. High-Level Design

`AgentKeys` is a content-addressed store scoped to one `BaseAgent` instance. Every `record_*` method takes a JSON-safe payload, wraps it in a small envelope (`{schema, kind, ...payload}`), canonicalizes and hashes that envelope with the shared `vidbyte/agents/hashing.py` primitives, stores `digest -> envelope` in an internal `OrderedDict`, updates a "latest digest for this kind" pointer, evicts the oldest entry if the store exceeds its cap, and returns the digest. `decode(digest)` is a single lookup against that same store — one method serves all five kinds, since every envelope carries its own `kind` field and SHA-256 collision across kinds is not a practical concern.

```
BaseAgent.__init__ ---------> AgentKeys(agent_name, provider, model_name,
                                          runtime_type, run_id, system_prompt)
                                          |
                                          | (owns) identity_key (cached)
                                          | (owns) _store: OrderedDict[digest, envelope]
                                          | (owns) _latest_settings_digest, _latest_response_digest,
                                          |        _latest_toolset_digest, _latest_tool_call_digest
                                          v
BaseAgent.__init__      ---> record_settings(...) ---\
BaseAgent.generate_reply ---> record_settings(...)     \
BaseAgent.generate_reply ---> record_response(...)       >--> AgentKeys._remember(kind, payload)
BaseAgent.__init__      ---> record_toolset(...)         /         |
BaseAgent.add_tool       ---> record_toolset(...)      /           v
BaseAgent._record_tool_contexts -> record_tool_call(...)    canonical_json -> hex_digest -> store -> evict-if-over-cap
(harness/caller, on demand) -> record_step(...)     /
                                          \
                                           `---------> decode(digest) -> Mapping[str, Any]
```

Separately, `vidbyte/agents/hashing.py` is a small pure module with no dependency on `BaseAgent` or `AgentKeys`, providing the shared `canonical_json`/`hex_digest`/`stable_key` primitives. `AgentKeys` is one consumer of it; `ToolSettings.fingerprint`, `LoopDetectionMiddleware`, `MultiAgentOrchestratorLedger`, and `ProsecutorDefenderJudgeAlgorithm` are migrated to be the other four, each keeping its own preimage-building logic (what goes into the payload, and any kind-specific fallback behavior) local to itself.

---

## 6. Detailed Design

### 6.1 `vidbyte/agents/hashing.py` (new file)

**File(s):** `vidbyte/agents/hashing.py`
**Type:** New file

#### What it does
Pure, stateless canonicalization and hashing primitives shared by every hashing call site under `agents/` and `middleware/`. No imports beyond `hashlib` and `json`.

#### Interface / API
```python
def canonical_json(value: Any) -> str: ...
def hex_digest(text: str, *, length: int | None = None) -> str: ...
def stable_key(prefix: str, payload: Any, *, length: int = 16) -> str: ...
```

#### Logic / Algorithm
1. `canonical_json(value)`: `json.dumps(value, sort_keys=True, default=str)`.
2. `hex_digest(text, *, length=None)`: `hashlib.sha256(text.encode()).hexdigest()`, truncated to `length` hex characters if given.
3. `stable_key(prefix, payload, *, length=16)`: try `canonical_json(payload)`; on any exception, fall back to `str(payload)` (matches every existing call site's current safety net); then `f"{prefix}:{hex_digest(serialized, length=length)}"`.

#### Edge Cases & Error Handling
- Non-JSON-native values inside `payload` stringify via `default=str` inside `canonical_json`, exactly matching current behavior at three of the four migrated call sites. This is a pre-existing latent property (not introduced by this change): an object without a `__str__`/`__repr__` override serializes to its default memory-address-bearing repr, which is not deterministic across two instances of logically-identical data. Flagged here per the design conversation's finding; not fixed in this PR since tool-call arguments (the primary caller) are already JSON-native by construction (they come from parsed LLM tool calls). `ledger_controller._fingerprint` deliberately does not use `stable_key`/`canonical_json`'s fallback for this exact reason — see 6.5.

---

### 6.2 `vidbyte/agents/settings/keys.py` (new file)

**File(s):** `vidbyte/agents/settings/keys.py`
**Type:** New file

#### What it does
`AgentKeys` — the content-addressed store for the five tracked keys, owned by one `BaseAgent` instance.

#### Interface / API
```python
_AGENT_KEYS_SCHEMA_VERSION = 1
_DEFAULT_MAX_STORE_ENTRIES = 2000

class AgentKeys:
    def __init__(self, *, agent_name: str, provider: str | None, model_name: str | None, runtime_type: str, run_id: str | None, system_prompt: str, max_store_entries: int = _DEFAULT_MAX_STORE_ENTRIES) -> None: ...
    def identity_key(self) -> str: ...
    def record_settings(self, settings_snapshot: Mapping[str, Any]) -> str: ...
    def record_response(self, message: Mapping[str, Any]) -> str: ...
    def record_toolset(self, tool_names: Iterable[str], mcp_tool_names: Iterable[str] = ()) -> str: ...
    def record_tool_call(self, tool_name: str, arguments: Mapping[str, Any] | None, output: str) -> str: ...
    def record_step(self, name: str, *, version: int, run_id: str | None = None) -> str: ...
    def decode(self, digest: str) -> Mapping[str, Any]: ...

    @property
    def latest_settings_key(self) -> str | None: ...
    @property
    def latest_response_key(self) -> str | None: ...
    @property
    def latest_toolset_key(self) -> str | None: ...
    @property
    def latest_tool_call_key(self) -> str | None: ...
```

#### Logic / Algorithm
1. `__init__` stores the five identity fields directly (write-once in `BaseAgent`, verified against `base.py` — see the prior design conversation's audit), precomputes `system_prompt`'s hash and `identity_key()`'s digest, and initializes an empty `OrderedDict` store plus four `None` "latest" pointers.
2. Each `record_*` method builds its specific payload dict from its parameters, then delegates to one private helper, `_remember(kind, payload)`, which:
   a. Wraps the payload as `{"schema": _AGENT_KEYS_SCHEMA_VERSION, "kind": kind, **payload}`.
   b. Computes `digest = hex_digest(canonical_json(envelope))` (full 64-char digest, no truncation — these keys are meant to leave the process, unlike the 16-char in-memory dedup keys `hashing.stable_key` produces for loop detection).
   c. Stores `self._store[digest] = envelope`; if `digest` already present, moves it to the end (`OrderedDict.move_to_end`) rather than duplicating, so re-recording identical content refreshes its eviction priority instead of no-op'ing into staleness.
   d. Evicts the oldest entry (`self._store.popitem(last=False)`) while `len(self._store) > self.max_store_entries`.
   e. Returns `digest`.
3. Each `record_*` method sets its corresponding `self._latest_<kind>_digest = digest` after calling `_remember`.
4. `record_step` additionally validates `version >= 1` and resolves `run_id` (explicit arg, else `self.run_id`) before building its payload, raising `ConfigurationError` on either failure — this validation happens before `_remember` is called, so an invalid step is never stored.
5. `decode(digest)` does `self._store.get(digest)`; raises `AgentKeyNotFoundError` (new, `vidbyte/lib/errors/base.py`) if absent.

#### Edge Cases & Error Handling
- Recording identical content twice (e.g. `record_toolset` called again after `add_tool()` adds a tool whose name was already present, or `record_settings` called on unchanged settings) reuses the existing digest — no store growth, and `decode` still works for it.
- `decode()` on a digest that was evicted under memory pressure raises `AgentKeyNotFoundError`, not a silent `None` — a caller relying on long-term decodability must persist the payload themselves (stated in Non-Goals).
- `record_step` with `version=0` or a non-resolvable `run_id`: raises `ConfigurationError` before touching the store, mirroring `AgentLoopSettings`/`ToolSettings`'s existing validate-before-store style.

---

### 6.3 `vidbyte/lib/errors/base.py` (modified)

**File(s):** `vidbyte/lib/errors/base.py`
**Type:** Modified

#### What it does
Adds `AgentKeyNotFoundError`, following the exact flat-subclass pattern already used for every other SDK error (e.g. `AgentForkError(VidbyteSdkError)` at line 117).

#### Interface / API
```python
class AgentKeyNotFoundError(VidbyteSdkError):
    """Raised when AgentKeys.decode() is given a digest that was never recorded or has been evicted."""
```

#### Edge Cases & Error Handling
N/A — this is a leaf exception class with no logic.

---

### 6.4 `vidbyte/agents/base.py` (modified)

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Wires `AgentKeys` into `BaseAgent`'s lifecycle at five points.

#### Interface / API
No signature changes to any existing public method. `BaseAgent` gains one new attribute, `self.keys: AgentKeys`, and one new private helper:
```python
def _settings_snapshot(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. **Construction** — immediately after `self.runner_config = AgentRunnerConfig(...)` (existing code, `base.py:146-153`), construct `self.keys = AgentKeys(agent_name=name, provider=provider_str, model_name=model_name, runtime_type=self.runtime_type.value, run_id=self.runner_config.run_id, system_prompt=system_prompt)`.
2. **End of `__init__`** (after the existing `for _tool in self._agent_tool_items: self._bind_agent_tool_context(_tool)` loop, `base.py:226-227`) — call `self.keys.record_toolset([self._tool_name(t) for t in self._agent_tool_items], self.mcp_tool_names())` and `self.keys.record_settings(self._settings_snapshot())`.
3. **`_settings_snapshot()`** (new private method, placed near `_export_runtime_config`/`_export_loop_settings`, `base.py:447-485`) — assembles `{agent_name, provider, model_name, temperature, runtime_type, runtime_config: self._export_runtime_config(), algorithm: self.algorithm.name, capabilities: list(self.capabilities), description, metadata: dict(self.metadata), loop_settings: self._export_loop_settings(), output_schema: self._export_output_schema()}`, reusing the three existing export helpers verbatim — no new serialization logic, only assembly.
4. **`generate_reply()`** — call `self.keys.record_settings(self._settings_snapshot())` at the top (captures settings as of this specific run, in case `output_schema` or other fields were reassigned between runs — see the prior design conversation's finding that `output_schema` reassignment after construction is an explicitly supported path per the comment at `base.py:995-1003`). Call `self.keys.record_response(SessionSerializer().message_to_dict(reply))` immediately after the existing `self.history.append(reply)` / `self.last_reply = reply` lines (`base.py:657-659`), using the same lazy `from vidbyte.sessions.serialization import SessionSerializer` import pattern already used inside `export_state()` (`base.py:391`).
5. **`add_tool()`** (`base.py:281-288`) — after the existing mutation, call `self.keys.record_toolset([self._tool_name(t) for t in self._agent_tool_items], self.mcp_tool_names())`.
6. **`_record_tool_contexts()`** (`base.py:929-935`) — after the existing `self._tool_call_contexts.extend(...)`, if any new contexts were added, call `self.keys.record_tool_call(contexts[-1].tool_name, contexts[-1].arguments, contexts[-1].result.output if contexts[-1].result else "")` for the last newly-added context.

#### Edge Cases & Error Handling
- `_record_tool_contexts` may be called with zero new contexts (e.g. a turn with no tool calls) — guarded by an `if` before calling `record_tool_call`, no-op otherwise.
- `add_tool()` triggers a full `record_toolset` recompute on every call; for an agent that adds many tools in a loop, this recomputes (not re-stores, per 6.2's dedup-by-content behavior) but does allocate a new envelope only when the resulting name set actually changed — acceptable, this is not a hot path.

---

### 6.5 `vidbyte/agents/settings/tool.py` (modified)

**File(s):** `vidbyte/agents/settings/tool.py`
**Type:** Modified

#### What it does
`ToolSettings.fingerprint` delegates to the shared primitive instead of its private `hashlib`/`json` calls.

#### Logic / Algorithm
Replace lines 82-89 with:
```python
def fingerprint(self, tool_name: str, arguments: Mapping[str, object] | None) -> str:
    # Builds a stable tool-name + args fingerprint used by identical-call budgets.
    from vidbyte.agents.hashing import stable_key
    return stable_key(tool_name, dict(arguments or {}))
```
Remove the now-unused `import hashlib` / `import json` at the top of the file if nothing else in it uses them (confirm at implementation time — `tool.py` is small and these were likely only used by `fingerprint`).

#### Edge Cases & Error Handling
Return shape is unchanged (`f"{tool_name}:{16-hex-digest}"`); `ToolSettings` remains constructible with no `BaseAgent`/`AgentKeys` reference, since `hashing.py` has no such dependency — this was the specific layering constraint identified in the prior design conversation (`ToolSettings` is built standalone, before any agent may exist).

---

### 6.6 `vidbyte/middleware/builtins/loop_detection.py` (modified)

**File(s):** `vidbyte/middleware/builtins/loop_detection.py`
**Type:** Modified

#### Logic / Algorithm
Replace `_make_key` (lines 181-188) and `_make_output_key` (lines 190-193) bodies with calls to `vidbyte.agents.hashing.stable_key(tool_name, arguments)` and `stable_key(tool_name, output)` respectively. Remove the now-unused `import hashlib` if nothing else in the file needs it.

#### Edge Cases & Error Handling
Same shape, same fallback-on-serialization-failure behavior — no observable change beyond the shared import.

---

### 6.7 `vidbyte/agents/multi/ledger_controller.py` (modified)

**File(s):** `vidbyte/agents/multi/ledger_controller.py`
**Type:** Modified

#### Logic / Algorithm
Replace the `json.dumps(...)` line inside `_fingerprint` (line 187) with `vidbyte.agents.hashing.canonical_json(value)`. **Keep the surrounding `try`/`except (TypeError, ValueError): return f"opaque:..."` structure exactly as-is** — this is the one deliberate behavioral difference from the other three call sites (no silent `default=str` stringification of opaque values) and must not be collapsed into the shared primitive's fallback behavior.

#### Edge Cases & Error Handling
Unchanged — this file's opaque-value handling is strictly better than what `canonical_json` alone provides, and stays local to it by design.

---

### 6.8 `vidbyte/agents/algorithms/prosecutor_defender_judge.py` (modified)

**File(s):** `vidbyte/agents/algorithms/prosecutor_defender_judge.py`
**Type:** Modified

#### Logic / Algorithm
Replace both inline `hashlib.sha256(candidate.encode("utf-8")).hexdigest()`-shaped calls (lines 399 and 491) with `vidbyte.agents.hashing.hex_digest(candidate)` (no `canonical_json` step needed — the input is already plain text, not a structure). Remove the now-unused `import hashlib` if nothing else in the file needs it (it also imports `json` — check whether that's used elsewhere before removing).

#### Edge Cases & Error Handling
Unchanged — full, untruncated digest, matching current behavior exactly (`hex_digest` with no `length` defaults to the full 64-char digest).

---

## 7. Data Model Changes

N/A — no database schema changes. The closest analog is `AgentKeys`' internal store envelope shape, documented here since nothing external depends on it today but a future persistence layer might:

```python
# One entry in AgentKeys._store, keyed by its own digest:
{
    "schema": 1,
    "kind": "settings" | "response" | "toolset" | "tool_call" | "step",
    # + kind-specific fields, e.g. for "tool_call": {"tool_name": str, "arguments": dict, "output": str}
}
```

**Migration strategy:** N/A — new in-memory structure, no existing data to migrate.

---

## 8. API Changes

N/A — `vidbyte-sdk` is a Python library; there is no HTTP API surface touched by this change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/hashing.py` | Shared canonicalize+hash primitives (`canonical_json`, `hex_digest`, `stable_key`) |
| CREATE | `vidbyte/agents/settings/keys.py` | `AgentKeys` class — the five tracked keys, content-addressed store, decode |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `AgentKeyNotFoundError(VidbyteSdkError)` |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export `AgentKeyNotFoundError` in `__all__`, matching existing export pattern |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Export `AgentKeys` from the flat `__all__`, matching `ToolSettings`/`AgentLoopSettings` |
| MODIFY | `vidbyte/agents/base.py` | Construct `self.keys` in `__init__`; add `_settings_snapshot()`; call `record_settings`/`record_toolset`/`record_response`/`record_tool_call` at the five hook points in Section 6.4 |
| MODIFY | `vidbyte/agents/settings/tool.py` | `ToolSettings.fingerprint` delegates to `hashing.stable_key` |
| MODIFY | `vidbyte/middleware/builtins/loop_detection.py` | `_make_key`/`_make_output_key` delegate to `hashing.stable_key` |
| MODIFY | `vidbyte/agents/multi/ledger_controller.py` | `_fingerprint`'s serialization step delegates to `hashing.canonical_json`, opaque-value fallback preserved locally |
| MODIFY | `vidbyte/agents/algorithms/prosecutor_defender_judge.py` | Both inline `hashlib.sha256` calls delegate to `hashing.hex_digest` |

10 files: 2 created, 8 modified, 0 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `hashlib` (stdlib) | N/A | SHA-256 digest | None — already used across the codebase |
| `json` (stdlib) | N/A | Canonical serialization | None — already used across the codebase |
| `collections.OrderedDict` (stdlib) | N/A | FIFO-evictable store for `AgentKeys._store` | None |

No new third-party dependencies, no external services.

---

## 11. Rollout & Deployment

- No feature flag — this is purely additive (`self.keys` is a new attribute; nothing existing is removed or renamed) and the four hashing migrations preserve observable digest *shape* (their exact digest *values* change as a byproduct of centralizing, but none of the four persist digest values across process restarts today, so this is safe).
- Not a breaking change to any public `BaseAgent` API.
- Single-package deployment (`vidbyte-sdk` is a library, not a service) — rollout is "the next `pip install` of the SDK picks it up."
- Rollback: revert the PR; `self.keys` and its five call sites are additive, so reverting is a clean subtraction.
- **Required CI gate before PR:** `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`, run to completion from the implementation worktree, per Phase 5d of this workflow.

---

## 12. Open Questions

- [ ] Is `_DEFAULT_MAX_STORE_ENTRIES = 2000` the right default cap, or should it be lower/higher/unbounded? Chosen as a round number that comfortably covers realistic per-run tool-call and turn counts while bounding worst-case memory (~2-4 MB at ~1-2 KB/entry) for a long-running or actor-model agent; not derived from a measured workload.
- [ ] Should `_settings_snapshot()`'s scope include `description`, `capabilities`, and `metadata`, or should "ALL OF THE AGENT SETTINGS" be narrower — just `AgentLoopSettings`/`ToolSettings`/runtime config, excluding descriptive/free-form fields? Current design takes the broad reading given the emphasis in the request; narrowing is a one-line change to the dict literal in `_settings_snapshot()`.
- [ ] Should `record_settings` also fire on `add_tool()` (since toolset is arguably part of "all settings")? Current design keeps `record_settings` and `record_toolset` as separate digests/kinds per the request's explicit five-way split, and does not cross-trigger one from the other.
- [ ] FIFO eviction means an old digest can stop decoding once the store fills — acceptable given Non-Goals states this store is not meant as durable persistence, but confirm this matches expectations before relying on `decode()` for anything long-lived.

---

## 13. Alternatives Considered

### Alternative 1: Plain SHA-256 digests, no store (the design from the prior conversation turns)
- What: each key method computes and returns a bare hash of its subject; nothing is stored, nothing is decodable.
- Why rejected: directly fails the explicit requirement that all five keys "should be able to be decoded." A cryptographic hash is one-way by construction — there is no algorithm that recovers input from a SHA-256 digest. This alternative was what was actually built across the earlier turns of this conversation and is being superseded here specifically because it cannot satisfy decodability.

### Alternative 2: Reversible encoding (base64 of canonical JSON) instead of hashing
- What: `base64.b64encode(canonical_json(payload).encode())` — trivially invertible, no store needed.
- Why rejected: technically decodable, but not a hash at all — no fixed size, no collision-resistant identity, and for "ALL OF THE AGENT SETTINGS" or "entire toolset" the resulting string could be kilobytes long, which is a poor database/idempotency key (the original motivating use case explicitly wanted short, stable, DB-safe keys). Content-addressed storage gets both properties: a short fixed-size key for storage/comparison, and full decodability via lookup.

### Alternative 3: Persistent (disk/DB-backed) store instead of in-memory
- What: back `AgentKeys._store` with SQLite or a file, so decodability survives process restarts.
- Why rejected for this PR: no persistence layer was requested, and `vidbyte-sdk` deliberately keeps `BaseAgent` free of a hard dependency on any specific storage backend (the existing `SessionStore` abstraction is how durable persistence is done elsewhere in this SDK, via pluggable backends). Adding disk I/O to every `record_*` call would also make what is currently a synchronous, allocation-only hot-path operation (recording every tool call, every turn) into a blocking I/O operation. If durable decodability is needed later, the right extension point is a caller-supplied `SessionStore`-like backend passed into `AgentKeys`, not a hardcoded file/DB — flagged as a natural follow-up, not built here.

### Alternative 4: Unbounded store (no eviction cap)
- What: let `_store` grow for the life of the agent instance with no cap.
- Why rejected: fails the unbounded-growth check this workflow's audit explicitly runs for every new piece of state — an actor-model or long-running agent recording a tool-call entry every iteration would grow memory without bound. A bounded FIFO cache with a documented, adjustable cap is the smaller, safer default; the tradeoff (old digests eventually stop decoding) is stated plainly rather than hidden.

---

## 14. Implementation Notes (post-review, PR #348 comments)

Five review comments on PR #348 asked for stricter house-style boundaries than the original design used. All five were implemented in a follow-up PR built on top of this branch:

1. **`AgentKeys.__init__`'s six loose keyword arguments became one `AgentIdentity` dataclass** (`vidbyte/lib/dataclasses/agent_keys.py`), and `_settings_snapshot()`'s raw dict became one `AgentSettingsSnapshot` dataclass wrapping it. Both are `frozen=True, slots=True` with `__post_init__` validation (enum-typed `provider`, length-bounded strings, a `0.0–2.0` temperature range, etc.), following the same "settings class is a thin adapter over one strictly validated dataclass" pattern already used elsewhere in this SDK. `provider`, `model_name`, and `run_id` stay the one deliberate `| None` exception on `AgentIdentity`, documented in its own docstring: `BaseAgent` legitimately constructs agents before a provider/model is pinned or a run_id exists, and forcing a non-null sentinel for `run_id` specifically would have silently defeated `record_step`'s existing "no run_id, no step" safety check. `BaseAgent.__init__`'s own public signature is unchanged — it builds the dataclass internally, so this is not a breaking API change.
2. **`vidbyte/agents/hashing.py` was deleted and rebuilt as `vidbyte/lib/hashing.py`**, a `Hashing` static-method class where every method takes a dedicated `*Input` dataclass and returns a dedicated `*Output` dataclass (`CanonicalJsonInput/Output`, `HexDigestInput/Output`, `StableKeyInput/Output`). All four original call sites (`AgentKeys`, `ToolSettings.fingerprint`, `LoopDetectionMiddleware`, `ProsecutorDefenderJudgeAlgorithm`) were migrated to call through it.
3. **`_AGENT_KEYS_SCHEMA_VERSION`/`_DEFAULT_MAX_STORE_ENTRIES`** moved to `vidbyte/lib/constants/agent_keys.py` (`AGENT_KEYS_SCHEMA_VERSION`, `DEFAULT_MAX_STORE_ENTRIES`).
4. **The five `_KIND_*` string constants** became `AgentKeyKind(str, Enum)` at `vidbyte/lib/enums/agent_keys.py`.

**Judgment call not taken further:** an early draft also validated `AgentIdentity.model_name` against `ProviderModelRegistry`'s known-model catalog when a provider was present. Removed after `python scripts/run_ci.py --stage source` showed three failing tests that legitimately construct agents with synthetic model names (`"model-a"`, `"m"`) to test plumbing unrelated to any real provider — `BaseAgent` never validated `model_name` against the catalog before, and that stricter check belongs to the YAML-config-loading path (`AgentDescriptor`, which already does this), not to `BaseAgent`'s raw constructor. `model_name` stays a length-bounded non-empty string on `AgentIdentity`; only `provider` is enum-strict.

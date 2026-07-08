# Design Doc: Durable Sessions (continue / resume / fork)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-06
**Last Updated:** 2026-06-06

---

## 1. Overview

Durable Sessions add a new harness-level primitive, `vidbyte/sessions/`, that lets a developer attach any agent to a persistent **Session** in one line and gain `continue`, `resume`, and `fork` over a checkpoint DAG. The Session captures the agent's run state (history + config-by-value, secrets scrubbed) after each turn, persists it through a pluggable `SessionStore` (in-memory, filesystem, or a database provider under `vidbyte/lib/providers/`), and optionally captures the agent's trace artifact alongside each checkpoint. The agent itself stays pure: persistence lives entirely in the Session wrapper, so this works for every runtime and never changes how agents are written.

---

## 2. Goals & Non-Goals

### Goals

- One-line attach: `session = Session(agent)` (defaults to in-memory) or `sdk.harnesses.sessions.attach(agent, store=...)`.
- `continue`, `resume`, and `fork`, plus `rewind` and `edit`, over an append-only **checkpoint DAG** (parent-pointer tree) that also yields time-travel and listing.
- Pluggable `SessionStore` Protocol with three first-class local stores (`InMemorySessionStore`, `FileSessionStore`) and database provider stores under `vidbyte/lib/providers/` (MongoDB, Supabase, Postgres) using lazy optional imports.
- Trace capture: a Session reads the attached agent's trace settings and persists the trace artifact (and optionally raw span events) onto each checkpoint, controllable via a `TraceCapture` policy.
- A pure agent state seam: `BaseAgent.export_state()` / `BaseAgent.restore(...)` moving a plain `RunState` dataclass — no I/O, no store references on the agent.
- Lineage at the data layer (`parent_session_id`) so forks and future subagent/child sessions are first-class.
- An opt-in, permission-gated `SessionTool` so an agent can checkpoint / fork / read its own runs (foundation for the subagent "checkpoint before launching, return after" pattern).
- Secret scrubbing and schema versioning on everything persisted.

### Non-Goals

- **Deterministic replay.** Fork/rewind restore *state* only; the next action runs fresh. We do not cache tool results or guarantee side-effect-free re-execution. (Documented loudly; future work.)
- **Remote/network checkpointers as a core dependency.** Database providers are optional extras imported lazily; the SDK core imports cleanly without them.
- **Delta/diff checkpoints.** v1 writes full `RunState` payloads. The DAG schema does not preclude deltas later.
- **Human-in-the-loop interrupt/resume mid-iteration** (LangGraph `interrupt`-style pausing). The data model reserves a `SessionStatus.INTERRUPTED`, but mid-run pause/resume is future work.
- **Serializing live objects** (runners, `@tool` callables, middleware, MCP handles, `output_schema` types). These are re-supplied by the caller at `resume`/`fork` time (the rehydration contract).
- Persisting `context_items` / `context_manager` (re-supplied at restore; noted as a limitation).

---

## 3. Background & Context

The SDK is deliberately stateless: `BaseAgent` owns `self.history: list[AgentMessage]` in memory, and `agent.fork()` clones live configuration (optionally copying history) but persists nothing. There is no `SessionStore`, no serialized `RunState`, no checkpoint IDs, and no resume boundary. Comparable frameworks all provide this: Claude persists sessions with continue/resume/fork; LangGraph checkpoints support replay/fork/time-travel; AutoGen documents save/load state.

This work introduces the first persistent-state primitive in the SDK. Per `skills/sdk/SKILL.md`, dataclasses live in `vidbyte/lib/dataclasses/`, errors in `vidbyte/lib/errors/`, and namespace clients hang off `vidbyte/harnesses/`. The existing `HarnessClient` (`vidbyte/harnesses/client.py`) and `ProvidersClient` are empty scaffolding, and `sdk.harnesses` is already a public entry point — the natural home for sessions. The rule "no remote protocol transports without a separate approved design" is honored by making DB providers optional lazy-imported adapters behind a Protocol, exactly like the existing `Trace.langfuse/langsmith/phoenix` provider tracers.

Continual tracing already exists: `ContinualTraceMiddleware` publishes a structured artifact to `AgentResult.metadata["trace"]`, which `generate_reply` folds into `AgentMessage.metadata`; the agent also exposes `last_trace` and `_tracer`. Sessions consume this rather than re-implement it.

---

## 4. Requirements

### Functional Requirements

1. `Session(agent)` attaches an agent to an in-memory store in one line; `Session(agent, store=...)` selects a store.
2. `session.arun(message)` / `session.run(message)` execute the agent and write a checkpoint per the configured `CheckpointPolicy` (default `PER_TURN`).
3. `session.checkpoint(label=...)` writes a manual checkpoint and returns its id.
4. `sdk.harnesses.sessions.resume(store, session_id, *, tools=(), runner=None, middleware=())` reconstructs a live `Session` from the head checkpoint, with caller-supplied non-serializable parts.
5. `sdk.harnesses.sessions.continue_(...)` is sugar for resuming the head checkpoint.
6. `sdk.harnesses.sessions.fork(store, checkpoint_id, *, tools=(), ...)` creates a new session id whose root parent is the given checkpoint, recording `parent_session_id`; mutating the fork never alters the parent's stored state.
7. `session.rewind(to=checkpoint_id)` moves the session head to an earlier checkpoint (time-travel).
8. `session.edit(transform)` produces a new checkpoint with transformed history (state editing / redaction / what-if).
9. `store.history(session_id)` returns checkpoints ordered by `seq`; `store.list_sessions(...)` returns `SessionMeta` filtered by agent/tag/status.
10. `RunState` round-trips losslessly through serialization for history and config-by-value.
11. `api_key` and credential-like metadata never appear in any persisted artifact.
12. A `RunState`/`Checkpoint` with an unknown `schema_version` raises a typed `SessionVersionError` on load.
13. Three local stores (`InMemorySessionStore`, `FileSessionStore`) plus DB provider stores (`MongoDbSessionStore`, `SupabaseSessionStore`, `PostgresSessionStore`) implement one `SessionStore` Protocol and are interchangeable.
14. `FileSessionStore` writes atomically (temp file + `os.replace`); a corrupt artifact raises a typed `SessionStoreError`, not a raw `JSONDecodeError`.
15. Trace capture: when the attached agent has tracing enabled (or `TraceCapture` requests it), each checkpoint stores `trace_artifact` (from `reply.metadata["trace"]` / `agent.last_trace`) and, under `TraceCapture.FULL`, raw span `events` from a `DebugTracer`-style tracer. Non-traced runs leave these `None`.
16. `SessionTool` exposes permission-gated `create_checkpoint`, `fork_current`, `list_my_runs`, and `read_run` to an agent, scoped to its own runs by default.
17. Unknown `session_id` / `checkpoint_id` raise `SessionNotFoundError` / `CheckpointNotFoundError`.

### Non-Functional Requirements

- **Performance:** local store writes are O(size of one checkpoint); SQLite/DB lookups are indexed on `(session_id, seq)` and `parent_id`. Persistence runs after the agent reply and must not block the model loop beyond a single serialize+write.
- **Concurrency:** `FileSessionStore` tolerates concurrent writers via atomic replace + monotonic `seq`; DB stores rely on the backend. v1 policy is last-write-wins with a monotonic `seq` guard.
- **Security:** deterministic secret scrubbing reusing the existing redaction approach in `vidbyte/agents/base.py` (`_safe_trace_mapping`); cross-session reads gated by `SessionScope`.
- **Observability:** `session_id` and `checkpoint_id` are added to trace metadata so traces and checkpoints cross-reference.
- **Reliability:** persistence failures surface as typed `SessionError`s; trace capture is fail-open (never breaks a run).
- **Import-safety:** importing `vidbyte` and `vidbyte.sessions` must not require `pymongo`, `supabase`, or `psycopg`.

---

## 5. High-Level Design

A new `vidbyte/sessions/` package provides the `Session` aggregate (the facade owning the verbs), a `SessionStore` Protocol (the storage port), the serialization/scrub layer, the `CheckpointPolicy`/`TraceCapture` policies, and an agent-facing `SessionTool`. Local stores (`InMemorySessionStore`, `FileSessionStore`) live in `vidbyte/sessions/stores/`. Database-backed stores live under `vidbyte/lib/providers/` (as requested) and implement the same `SessionStore` Protocol via lazy optional imports. Contracts (`RunState`, `Checkpoint`, `SessionMeta`, enums) live in `vidbyte/lib/dataclasses/sessions.py`; errors extend `VidbyteSdkError`. A `SessionClient` is wired into `HarnessClient`, exposed as `sdk.harnesses.sessions`.

The unifying model is a **checkpoint DAG**: each `Checkpoint` carries `(id, session_id, parent_id, seq, run_state, trace_*)`. Snapshot-per-turn and event-log granularity are the same primitive at different write frequencies (`CheckpointPolicy.PER_TURN` vs `PER_STEP`). The verbs are queries on the DAG: `continue` = head; `resume` = any checkpoint; `fork` = new session id rooted at a checkpoint; `rewind` = move head to an ancestor; `edit` = new checkpoint with transformed state.

The agent stays pure. `BaseAgent` gains only `export_state() -> RunState` and `restore(state, *, tools, runner, middleware) -> BaseAgent`, which move a plain dataclass with no I/O. The Session calls `export_state()` after each run, attaches trace data lifted from the reply, and writes a checkpoint.

```
                         attach (1 line)
   [ BaseAgent ] <-----------------------------  [ Session ]
        | run/arun                                   | after reply:
        v                                            |  export_state() -> RunState
   AgentMessage  -- metadata["trace"] ----------->   |  + lift trace_artifact
                                                     v
                                          [ Checkpoint(id, parent_id, seq, run_state, trace) ]
                                                     |
                                                     v  put()
                                       [ SessionStore Protocol ]
                       _______________________|________________________
                      |              |               |                 |
            InMemorySessionStore  FileSessionStore  Mongo/Supabase/Postgres
            (sessions/stores)     (sessions/stores) (lib/providers, lazy import)

   resume/fork(store, id, tools=, runner=, middleware=)
        -> load Checkpoint -> RunState -> BaseAgent.restore(...) -> Session
```

Key decisions: (1) harness-level primitive, agent pure — matches LangGraph/Claude/AutoGen; (2) one DAG serves all verbs and both granularities; (3) rehydration contract — only data persists, live objects are re-supplied; (4) trace is a *derived observation* riding on checkpoints, never a `resume` input; (5) DB providers are optional lazy adapters behind the Protocol.

---

## 6. Detailed Design

### 6.1 Session contracts

**File(s):** `vidbyte/lib/dataclasses/sessions.py`
**Type:** New file

#### What it does
Defines the serializable session data model and enums, centrally per repo rules.

#### Interface / API
```python
class CheckpointPolicy(str, Enum):
    PER_TURN = "per_turn"      # snapshot after each run (default)
    PER_STEP = "per_step"      # reserved for event-log granularity
    MANUAL = "manual"          # only explicit checkpoint() calls persist

class SessionStatus(str, Enum):
    ACTIVE = "active"; COMPLETED = "completed"; INTERRUPTED = "interrupted"; FAILED = "failed"

class TraceCapture(str, Enum):
    OFF = "off"                # never persist trace
    AUTO = "auto"             # capture iff the agent has tracing enabled (default)
    ARTIFACT = "artifact"     # always capture the artifact
    FULL = "full"             # artifact + raw span events

SESSION_SCHEMA_VERSION: int = 1

@dataclass(frozen=True, slots=True)
class RunState:
    schema_version: int
    agent_name: str
    system_prompt: str
    description: str
    capabilities: tuple[str, ...]
    provider: str | None
    model_name: str | None
    modality: str
    temperature: float | None
    runner_options: Mapping[str, Any]
    runtime_type: str
    runtime_config: Mapping[str, Any]          # max_iterations/max_tokens/compaction/actor cfg
    algorithm: str                              # context-window algorithm name
    metadata: Mapping[str, Any]
    agent_metadata: Mapping[str, Any]           # name/description/use_cases
    tool_names: tuple[str, ...]
    history: tuple[Mapping[str, Any], ...]      # scrubbed AgentMessage dicts

@dataclass(frozen=True, slots=True)
class Checkpoint:
    id: str
    session_id: str
    parent_id: str | None
    seq: int
    created_at: str
    run_state: RunState
    label: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    trace_artifact: Mapping[str, Any] | None = None
    trace_summary: Mapping[str, Any] | None = None
    trace_events: tuple[Mapping[str, Any], ...] | None = None

@dataclass(frozen=True, slots=True)
class SessionMeta:
    session_id: str
    head_id: str | None
    parent_session_id: str | None
    agent_name: str
    status: SessionStatus
    created_at: str
    updated_at: str
    tags: tuple[str, ...] = ()
```

#### Edge Cases & Error Handling
- All fields default-friendly; `history` empty tuple is valid (fresh session).
- `schema_version` always written; loaders compare against `SESSION_SCHEMA_VERSION`.

---

### 6.2 Session errors

**File(s):** `vidbyte/lib/errors/base.py` (modified), `vidbyte/lib/errors/__init__.py` (modified)
**Type:** Modified

#### Interface / API
```python
class SessionError(VidbyteSdkError): ...
class SessionNotFoundError(SessionError): ...
class CheckpointNotFoundError(SessionError): ...
class SessionSerializationError(SessionError): ...
class SessionStoreError(SessionError): ...
class SessionVersionError(SessionError): ...
```

#### Logic / Algorithm
1. Add classes under `VidbyteSdkError` with the existing `details` convention.
2. Re-export from `vidbyte/lib/errors/__init__.py`.

---

### 6.3 Serialization & secret scrubbing

**File(s):** `vidbyte/sessions/serialization.py`
**Type:** New file

#### What it does
Converts `RunState`/`Checkpoint`/`SessionMeta` to and from JSON-safe dicts, scrubs secrets, and projects `AgentMessage`s safely. Hosts a small codec registry for non-JSON metadata values.

#### Interface / API
```python
class SessionSerializer:
    def checkpoint_to_dict(self, checkpoint: Checkpoint) -> dict[str, Any]: ...
    def checkpoint_from_dict(self, data: Mapping[str, Any]) -> Checkpoint: ...   # SessionVersionError on mismatch
    def meta_to_dict(self, meta: SessionMeta) -> dict[str, Any]: ...
    def meta_from_dict(self, data: Mapping[str, Any]) -> SessionMeta: ...
    def message_to_dict(self, message: AgentMessage) -> dict[str, Any]: ...      # scrubs metadata
    def message_from_dict(self, data: Mapping[str, Any]) -> AgentMessage: ...
```

#### Logic / Algorithm
1. `message_to_dict` keeps `sender/recipient/content/message_type` and a scrubbed `metadata` (drop credential-like keys; whitelist JSON-safe `trace`/`trace_metadata`; replace non-JSON values with a `{"__dropped__": type_name}` marker).
2. Reuse the redaction key-set from `BaseAgent._safe_trace_mapping` (lifted into a shared helper) for secret stripping; `api_key` is always stripped from `runner_options`.
3. `checkpoint_from_dict` raises `SessionVersionError` when `schema_version != SESSION_SCHEMA_VERSION`.
4. Any malformed structure raises `SessionSerializationError`.

#### Edge Cases & Error Handling
- Non-serializable nested values → marker, never an exception.
- Missing required keys → `SessionSerializationError` with the offending field in `details`.

---

### 6.4 Agent state seam

**File(s):** `vidbyte/agents/base.py` (modified)
**Type:** Modified

#### What it does
Adds the pure, I/O-free bridge between a live agent and a `RunState`.

#### Interface / API
```python
def export_state(self) -> RunState: ...
@classmethod
def restore(cls, state: RunState, *, tools: Sequence[object] = (), runner: object | None = None, middleware: Sequence[AgentMiddleware] = (), tracer: object | None = None, trace: object | None = None, output_schema: object | None = None) -> BaseAgent: ...
```

#### Logic / Algorithm
1. `export_state` reads `name`, `system_prompt`, `runner_config` (minus `api_key`), `runtime_type`, runtime/actor config, `algorithm.name`, `metadata`, `agent_metadata`, `tool_names`, and `[message_to_dict(m) for m in self.history]`.
2. `restore` constructs a `BaseAgent` from `RunState` config-by-value, injecting caller-supplied `tools`/`runner`/`middleware`/`tracer`/`output_schema`, then assigns `child.history` from the deserialized history.
3. Both methods are synchronous and perform no I/O.

#### Edge Cases & Error Handling
- `restore` with no `runner` and no provider/model → constructs a config-only agent (runs later raise the existing `AgentExecutionError` until a runner is supplied), preserving current behavior.
- `tool_names` mismatch vs supplied tools is recorded in `metadata["__resume_tool_mismatch__"]` (non-fatal) for later validation by `SessionTool`/middleware.

---

### 6.5 SessionStore Protocol

**File(s):** `vidbyte/sessions/store.py`
**Type:** New file

#### Interface / API
```python
@runtime_checkable
class SessionStore(Protocol):
    def put(self, checkpoint: Checkpoint) -> None: ...
    def get(self, checkpoint_id: str) -> Checkpoint: ...                 # CheckpointNotFoundError
    def head(self, session_id: str) -> Checkpoint | None: ...
    def history(self, session_id: str) -> list[Checkpoint]: ...          # ordered by seq
    def put_meta(self, meta: SessionMeta) -> None: ...
    def get_meta(self, session_id: str) -> SessionMeta: ...              # SessionNotFoundError
    def list_sessions(self, *, agent_name: str | None = None, tag: str | None = None, status: SessionStatus | None = None) -> list[SessionMeta]: ...
    def prune(self, session_id: str, *, keep: int | None = None) -> None: ...
```

#### Logic / Algorithm
A small abstract `BaseSessionStore` provides shared helpers (next `seq`, meta upsert from a checkpoint, retention by `keep`). Concrete stores implement raw read/write.

---

### 6.6 Local stores

**File(s):** `vidbyte/sessions/stores/memory.py`, `vidbyte/sessions/stores/file.py`, `vidbyte/sessions/stores/__init__.py`
**Type:** New files

#### What they do
- `InMemorySessionStore`: dict-backed, for tests/ephemeral use.
- `FileSessionStore`: one directory per session under a root; `meta.json` + `checkpoints/<seq>-<id>.json`; atomic writes.

#### Logic / Algorithm (FileSessionStore)
1. `put` serializes the checkpoint, writes to a temp file in the session dir, then `os.replace` onto the final name; updates `meta.json` the same way; advances `head_id`/`updated_at`.
2. `history` lists and sorts checkpoint files by `seq`.
3. `prune(keep=N)` deletes oldest checkpoint files beyond `N`, preserving the head chain.

#### Edge Cases & Error Handling
- Missing session dir on read → `SessionNotFoundError`.
- Corrupt/partial JSON → `SessionStoreError` (wraps decode error).
- Concurrent writers: atomic replace + monotonic `seq`; last-write-wins on `meta.json`.

---

### 6.7 Database provider stores

**File(s):** `vidbyte/lib/providers/__init__.py`, `vidbyte/lib/providers/base.py`, `vidbyte/lib/providers/mongodb.py`, `vidbyte/lib/providers/supabase.py`, `vidbyte/lib/providers/postgres.py`
**Type:** New files

#### What they do
Implement `SessionStore` against external databases, with the same serialized JSON shape as `FileSessionStore`. Each lazily imports its driver inside `__init__` and raises `ConfigurationError` with install guidance if absent (mirroring `Trace.langfuse/langsmith/phoenix`).

#### Interface / API
```python
class PostgresSessionStore(BaseSessionStore):
    def __init__(self, *, dsn: str, table_prefix: str = "vidbyte_") -> None: ...
class MongoDbSessionStore(BaseSessionStore):
    def __init__(self, *, uri: str, database: str = "vidbyte", collection_prefix: str = "vidbyte_") -> None: ...
class SupabaseSessionStore(BaseSessionStore):
    def __init__(self, *, url: str, key: str, table_prefix: str = "vidbyte_") -> None: ...
```

#### Logic / Algorithm
1. Two logical tables/collections: `sessions` (one `SessionMeta` per row, keyed by `session_id`) and `checkpoints` (one per row, indexed on `session_id, seq` and `parent_id`), storing the serialized JSON payload.
2. `put` upserts the checkpoint and the derived meta; `get`/`head`/`history`/`list_sessions` are indexed queries.
3. Schema/DDL is created on first use (idempotent `CREATE TABLE IF NOT EXISTS` for Postgres; index ensure for Mongo; Supabase assumes provisioned tables and validates their presence).

#### Edge Cases & Error Handling
- Missing driver → `ConfigurationError` ("install `psycopg`/`pymongo`/`supabase`...").
- Connection/query failure → `SessionStoreError` carrying provider name in `details`.
- Unknown id → `SessionNotFoundError` / `CheckpointNotFoundError`.

---

### 6.8 TraceCapture helper

**File(s):** `vidbyte/sessions/trace_capture.py`
**Type:** New file

#### What it does
Extracts trace data from a completed reply and the attached agent, honoring the `TraceCapture` policy.

#### Interface / API
```python
class TraceRecorder:
    def __init__(self, policy: TraceCapture) -> None: ...
    def capture(self, agent: BaseAgent, reply: AgentMessage) -> _CapturedTrace: ...
```

#### Logic / Algorithm
1. Resolve effective capture: `OFF` → nothing; `AUTO` → capture iff `agent._trace_option` is enabled or `agent.last_trace` is set; `ARTIFACT`/`FULL` → always.
2. `artifact` = `reply.metadata.get("trace")` or `agent.last_trace`; `summary` = `reply.metadata.get("trace_metadata")`.
3. Under `FULL`, also read `agent._tracer.events` when the tracer exposes a JSON-able `events` list (`DebugTracer`/`ContinualTracer`), scrubbed and bounded.
4. Fail-open: any extraction error returns empty capture and never raises.

#### Edge Cases & Error Handling
- Non-linear runtime (no continual-trace middleware) → artifact `None`, no error.
- Tracer without `events` → `trace_events` `None`.

---

### 6.9 Session facade

**File(s):** `vidbyte/sessions/session.py`
**Type:** New file

#### What it does
The aggregate that binds an agent + store + session id and owns the verbs. Provides the one-line attach.

#### Interface / API
```python
class Session:
    def __init__(self, agent: BaseAgent, *, store: SessionStore | None = None, session_id: str | None = None, policy: CheckpointPolicy = CheckpointPolicy.PER_TURN, trace: TraceCapture = TraceCapture.AUTO, tags: Sequence[str] = (), parent_session_id: str | None = None) -> None: ...

    @property
    def id(self) -> str: ...
    @property
    def head(self) -> str | None: ...

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage: ...
    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage: ...
    def checkpoint(self, *, label: str = "") -> str: ...
    def fork(self, *, at: str | None = None, tools: Sequence[object] | None = None, runner: object | None = None, middleware: Sequence[AgentMiddleware] | None = None) -> "Session": ...
    def rewind(self, *, to: str) -> "Session": ...
    def edit(self, transform: Callable[[list[AgentMessage]], Sequence[AgentMessage]], *, label: str = "") -> "Session": ...
    def complete(self) -> None: ...     # mark COMPLETED

    @classmethod
    def resume(cls, store: SessionStore, session_id: str, *, checkpoint_id: str | None = None, tools: Sequence[object] = (), runner: object | None = None, middleware: Sequence[AgentMiddleware] = (), tracer: object | None = None, output_schema: object | None = None) -> "Session": ...
    @classmethod
    def continue_(cls, store: SessionStore, session_id: str, **kwargs: Any) -> "Session": ...
    @classmethod
    def fork_from(cls, store: SessionStore, checkpoint_id: str, **kwargs: Any) -> "Session": ...
```

#### Logic / Algorithm
1. `__init__` defaults `store` to `InMemorySessionStore()`, mints `session_id` (uuid4) when absent, writes initial `SessionMeta`. This is the one-line attach (`Session(agent)`).
2. `arun` runs the agent, builds a `Checkpoint` from `agent.export_state()` + `TraceRecorder.capture(...)` with `parent_id = self.head`, `seq = head.seq + 1`, then `store.put(...)` unless policy is `MANUAL`. Returns the reply.
3. `checkpoint` performs the same write on demand and returns the id.
4. `fork`/`fork_from` load the chosen checkpoint, `BaseAgent.restore(...)`, mint a new `session_id` with `parent_session_id` set, write a root checkpoint copy, and return a new `Session`.
5. `rewind` sets head to an ancestor checkpoint (validates ancestry); subsequent writes branch from there.
6. `edit` applies `transform` to the restored history and writes a new checkpoint.
7. `resume`/`continue_` load head (or `checkpoint_id`), `restore` with caller parts, and return a live `Session` bound to the same `session_id`.

#### Edge Cases & Error Handling
- `fork`/`resume` with unknown ids → `CheckpointNotFoundError` / `SessionNotFoundError`.
- `rewind(to=...)` to a checkpoint of a different session → `SessionError`.
- `run` inside a running event loop → raises (mirrors `BaseAgent.run`).
- **Persistence failure is fail-open:** if `store.put(...)` fails during `arun`, the run does **not** end — the reply is still returned, the failure is recorded in `reply.metadata["__session_error__"]` and on `SessionMeta.status` bookkeeping, and the next successful write resumes the chain. Durability is best-effort by explicit decision; a failed turn is surfaced but never aborts the agent. Trace capture is likewise fail-open.

---

### 6.10 Agent-facing SessionTool

**File(s):** `vidbyte/sessions/tool.py`
**Type:** New file

#### What it does
A permission-gated `BaseTool` letting an agent operate on sessions (foundation for subagent checkpoint/return).

#### Interface / API
```python
class SessionScope:
    @staticmethod
    def own_runs() -> "SessionScope": ...
    @staticmethod
    def sessions(ids: Sequence[str]) -> "SessionScope": ...

class SessionTool(BaseTool):
    def __init__(self, store: SessionStore, *, scope: SessionScope | None = None) -> None: ...
    def spec(self) -> ToolSpec: ...                 # READ/SAFE permission
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm
1. Operations: `create_checkpoint(label)`, `fork_current()`, `list_my_runs()`, `read_run(id)`; `read_run` returns the `trace_artifact` (not raw history) for human/agent-readable observation.
2. `scope` defaults to own runs; cross-session reads outside scope return a denied `ToolResult` (aligns with existing `PermissionPolicy`/confused-deputy guard).

#### Edge Cases & Error Handling
- Out-of-scope id → denied result, not an exception.
- Unknown id → error `ToolResult`.

---

### 6.11 SessionClient + harness wiring

**File(s):** `vidbyte/sessions/client.py` (new), `vidbyte/harnesses/client.py` (modified)
**Type:** New + Modified

#### Interface / API
```python
class SessionClient:
    def attach(self, agent: BaseAgent, *, store: SessionStore | None = None, **kwargs: Any) -> Session: ...
    def resume(self, store: SessionStore, session_id: str, **kwargs: Any) -> Session: ...
    def continue_(self, store: SessionStore, session_id: str, **kwargs: Any) -> Session: ...
    def fork(self, store: SessionStore, checkpoint_id: str, **kwargs: Any) -> Session: ...
    def file_store(self, root: str) -> FileSessionStore: ...
    def memory_store(self) -> InMemorySessionStore: ...

# HarnessClient gains:
self.sessions = SessionClient()
```

---

### 6.12 Package exports

**File(s):** `vidbyte/sessions/__init__.py` (new), `vidbyte/__init__.py` (modified)
**Type:** New + Modified

Re-export `Session`, `SessionClient`, `SessionStore`, `InMemorySessionStore`, `FileSessionStore`, `SessionTool`, `SessionScope`, `CheckpointPolicy`, `TraceCapture`, `SessionStatus`, `RunState`, `Checkpoint`, `SessionMeta`, and the `SessionError` family. Add the same names to top-level `vidbyte/__init__.py` `__all__`. DB provider stores are imported from `vidbyte.lib.providers` explicitly (not auto-imported at top level, to keep import-safety).

---

## 7. Data Model Changes

### 7.1 `RunState`, `Checkpoint`, `SessionMeta` (+ enums)

**Change type:** New (`vidbyte/lib/dataclasses/sessions.py`) — see 6.1.

**Persisted JSON shape (FileSessionStore / DB):**
```json
{
  "schema_version": 1,
  "checkpoint": {
    "id": "ck_...", "session_id": "se_...", "parent_id": "ck_... | null",
    "seq": 3, "created_at": "ISO-8601", "label": "", "status": "active",
    "run_state": { "agent_name": "...", "system_prompt": "...", "provider": "openai",
      "model_name": "gpt-4.1", "modality": "text", "runner_options": {},
      "runtime_type": "linear", "runtime_config": {}, "algorithm": "default",
      "metadata": {}, "agent_metadata": {}, "tool_names": ["grep"],
      "history": [ {"sender":"...","recipient":"...","content":"...","message_type":"response","metadata":{}} ] },
    "trace_artifact": { } , "trace_summary": { }, "trace_events": null
  }
}
```

**Migration strategy:** additive only. `schema_version` gates loads; future versions add a migration switch in `SessionSerializer.checkpoint_from_dict`. No existing data exists to migrate.

### 7.2 Database tables (Postgres / Supabase) and collections (Mongo)

**Change type:** New (created idempotently on first use)
```sql
CREATE TABLE IF NOT EXISTS vidbyte_sessions (
  session_id TEXT PRIMARY KEY, head_id TEXT, parent_session_id TEXT,
  agent_name TEXT, status TEXT, created_at TEXT, updated_at TEXT, tags JSONB, payload JSONB);
CREATE TABLE IF NOT EXISTS vidbyte_checkpoints (
  id TEXT PRIMARY KEY, session_id TEXT, parent_id TEXT, seq INTEGER,
  created_at TEXT, payload JSONB);
CREATE INDEX IF NOT EXISTS ix_ck_session_seq ON vidbyte_checkpoints (session_id, seq);
CREATE INDEX IF NOT EXISTS ix_ck_parent ON vidbyte_checkpoints (parent_id);
```

---

## 8. API Changes

N/A — no HTTP endpoints. This is a Python SDK; the public surface changes are the new classes/methods in Sections 6.9–6.12.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/dataclasses/sessions.py` | RunState, Checkpoint, SessionMeta, enums |
| MODIFY | `vidbyte/lib/errors/base.py` | Add SessionError family |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Re-export SessionError family |
| CREATE | `vidbyte/sessions/__init__.py` | Public package exports |
| CREATE | `vidbyte/sessions/serialization.py` | Serializer + secret scrub + codec registry |
| CREATE | `vidbyte/sessions/store.py` | SessionStore Protocol + BaseSessionStore |
| CREATE | `vidbyte/sessions/stores/__init__.py` | Local store exports |
| CREATE | `vidbyte/sessions/stores/memory.py` | InMemorySessionStore |
| CREATE | `vidbyte/sessions/stores/file.py` | FileSessionStore (atomic JSON) |
| CREATE | `vidbyte/sessions/trace_capture.py` | TraceRecorder + TraceCapture handling |
| CREATE | `vidbyte/sessions/session.py` | Session facade + verbs |
| CREATE | `vidbyte/sessions/tool.py` | SessionTool + SessionScope |
| CREATE | `vidbyte/sessions/client.py` | SessionClient |
| MODIFY | `vidbyte/harnesses/client.py` | Wire `self.sessions = SessionClient()` |
| CREATE | `vidbyte/lib/providers/__init__.py` | Provider store exports (lazy) |
| CREATE | `vidbyte/lib/providers/base.py` | Shared DB store helpers |
| CREATE | `vidbyte/lib/providers/mongodb.py` | MongoDbSessionStore |
| CREATE | `vidbyte/lib/providers/supabase.py` | SupabaseSessionStore |
| CREATE | `vidbyte/lib/providers/postgres.py` | PostgresSessionStore |
| MODIFY | `vidbyte/agents/base.py` | Add export_state()/restore(); lift scrub helper |
| MODIFY | `vidbyte/__init__.py` | Top-level exports for session public surface |
| CREATE | `tests/test_durable_sessions.py` | Unit + integration tests |
| CREATE | `scripts/test-durable-sessions.py` | Verification script (Phase 5) |
| MODIFY | `README.md` | Document durable sessions |
| MODIFY | `skills/sdk/SKILL.md` | Add sessions package layout + rules |
| CREATE | `skills/vidbyte-sdk/sessions.md` | Sessions usage skill |

---

## 10. Testing Plan

### Unit Tests

- `SessionSerializer` → `round-trips a RunState with empty history` — [Edge Case]
- `SessionSerializer` → `round-trips history of 1 and N messages identically` — [Edge Case]
- `SessionSerializer` → `strips api_key from runner_options` — [Hidden Assumption]
- `SessionSerializer` → `drops credential-like metadata keys (token/secret/password)` — [Silent Failure]
- `SessionSerializer` → `replaces non-JSON metadata value with __dropped__ marker, does not raise` — [Hidden Failure]
- `SessionSerializer` → `whitelists trace/trace_metadata keys through scrub` — [Silent Failure]
- `SessionSerializer` → `raises SessionVersionError on unknown schema_version` — [Hidden Assumption]
- `SessionSerializer` → `raises SessionSerializationError on missing required field` — [Hidden Failure]
- `BaseAgent.export_state` → `captures provider/model/runtime/history and omits api_key` — [Hidden Assumption]
- `BaseAgent.restore` → `reproduces system_prompt, runtime_type, history from RunState` — [Silent Failure]
- `BaseAgent.restore` → `records tool mismatch marker when supplied tools differ from tool_names` — [Hidden Assumption]
- `BaseAgent.restore` → `restored agent with no runner raises AgentExecutionError only on run` — [Edge Case]
- `InMemorySessionStore` → `get unknown checkpoint raises CheckpointNotFoundError` — [Edge Case]
- `InMemorySessionStore` → `head returns latest by seq` — [Silent Failure]
- `InMemorySessionStore` → `list_sessions filters by status/tag/agent` — [Silent Failure]
- `FileSessionStore` → `put then get round-trips a checkpoint` — [Edge Case]
- `FileSessionStore` → `corrupt JSON file raises SessionStoreError not JSONDecodeError` — [Hidden Failure]
- `FileSessionStore` → `write is atomic: no partial file remains after simulated mid-write failure` — [Hidden Failure]
- `FileSessionStore` → `get_meta on missing session raises SessionNotFoundError` — [Edge Case]
- `FileSessionStore` → `prune(keep=N) deletes oldest beyond N and preserves head chain` — [Silent Failure]
- `BaseSessionStore` → `seq is monotonic across concurrent puts to one session` — [Hidden Failure]
- `TraceRecorder` → `AUTO captures artifact when agent tracing enabled` — [Edge Case]
- `TraceRecorder` → `AUTO captures nothing when tracing disabled` — [Edge Case]
- `TraceRecorder` → `OFF never captures even when artifact present` — [Hidden Assumption]
- `TraceRecorder` → `FULL captures tracer.events; ARTIFACT leaves events None` — [Silent Failure]
- `TraceRecorder` → `extraction error returns empty capture, never raises` — [Hidden Failure]
- `Session` → `Session(agent) attaches with in-memory store in one line and mints id+meta` — [Edge Case]
- `Session.arun` → `writes a checkpoint with parent_id=prev head and seq+1` — [Silent Failure]
- `Session.arun` → `MANUAL policy writes no checkpoint until checkpoint() called` — [Hidden Assumption]
- `Session.fork` → `new session_id, parent_session_id set, parent stored state unchanged after child writes` — [Silent Failure]
- `Session.rewind` → `to ancestor moves head; new run branches from it` — [Edge Case]
- `Session.rewind` → `to foreign checkpoint raises SessionError` — [Hidden Assumption]
- `Session.edit` → `transform applied; original checkpoint retained` — [Silent Failure]
- `Session.resume` → `unknown session_id raises SessionNotFoundError` — [Edge Case]
- `Session.continue_` → `resumes head and preserves full history into next run` — [Silent Failure]
- `SessionTool` → `read_run out of scope returns denied ToolResult, not exception` — [Hidden Assumption]
- `SessionTool` → `read_run returns trace_artifact not raw history` — [Silent Failure]
- `SessionTool` → `unknown id returns error ToolResult` — [Edge Case]
- `lib.providers` → `importing vidbyte and vidbyte.sessions does not import pymongo/psycopg/supabase` — [Hidden Assumption]
- `lib.providers` → `constructing a provider store without its driver raises ConfigurationError with install hint` — [Hidden Failure]

### Integration Tests

- End-to-end with a scripted runner (pattern from `tests/test_continual_trace.py`): `start → arun → new Session.resume(memory store) → arun continues with prior history present in context` — verifies the resume boundary and rehydration. Mock: runner; real: store + serializer + agent.
- `fork after two turns; child diverges; parent head/history unchanged` over `FileSessionStore` (real temp dir) — silent-failure path: ensure fork copies, not aliases, state.
- `trace-enabled agent → checkpoint.trace_artifact equals reply.metadata["trace"]` — surfaces the continual-trace ↔ session coupling that unit tests can't.
- `FileSessionStore` parity: same serialized payload as `InMemorySessionStore` for an identical run (catches store-specific drift).
- Hidden assumption surfaced by integration: a non-linear runtime (`mcts_search`) session persists via the facade with `trace_artifact=None` and resumes (no middleware required).

### Manual / QA Test Cases

1. Given a fresh agent, when `Session(agent)` then two `arun` calls, then in a new Python process `Session.resume(FileSessionStore(root), id, tools=[...])` and `arun`, then the reply reflects the earlier turns — [Hidden Failure: cold-process rehydration].
2. Given a completed session, when `fork` from the first checkpoint and run a different prompt, then `store.history(parent)` is unchanged and the fork has its own lineage — [Silent Failure].
3. Given an agent configured with `api_key`, when any checkpoint is written, then grepping the store files shows no key material — [Hidden Assumption: secret leakage].
4. Given a `PostgresSessionStore` without `psycopg` installed, when constructed, then a `ConfigurationError` names the missing package — [Edge Case].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| stdlib `json`, `os`, `uuid`, `sqlite3` | — | local serialization/atomic writes | Low |
| `psycopg` (optional) | user-provided DSN | PostgresSessionStore | Lazy import; not a core dep |
| `pymongo` (optional) | user-provided URI | MongoDbSessionStore | Lazy import; not a core dep |
| `supabase` (optional) | user URL+key | SupabaseSessionStore | Lazy import; not a core dep |

No network calls occur unless a developer explicitly constructs a DB provider store.

---

## 12. Rollout & Deployment

- **Feature flags:** none; the package is additive and opt-in.
- **Breaking changes:** none. `BaseAgent` gains two methods; no signatures change.
- **Deployment order:** single package; no service coordination.
- **Rollback:** revert the PR; no persisted production data depends on it.
- **Optional extras:** document `pip install psycopg|pymongo|supabase` for DB stores.

---

## 13. Open Questions (RESOLVED)

- [x] Package name: **`vidbyte/sessions/`** (plural, matches repo convention). — confirmed.
- [x] `SessionStore` sync vs async: **sync v1**; async adapters later. — confirmed default.
- [x] `arun` persistence failure: **fail-open** — a failed checkpoint write never ends the run; the reply is returned and the error recorded in `reply.metadata["__session_error__"]`. — confirmed by user ("if checkpointing fails, I don't want the run to end").
- [x] `SessionTool` + `SessionScope`: **included in this PR** (foundation; subagent auto-wiring deferred). — confirmed (ship everything).
- [x] DB provider stores: **ship all three** (Mongo/Supabase/Postgres) behind lazy imports + absence tests. — confirmed (ship everything).

---

## 14. Alternatives Considered

### Alternative 1: Persistence methods on `BaseAgent` (`agent.save()/resume()`)
- What: put session verbs directly on the agent.
- Why rejected: pollutes the pure agent, can't span pipelines/subagents, and middleware-style auto-persist can't run on non-linear runtimes. Harness-level facade matches LangGraph/Claude/AutoGen and the existing empty `harnesses/` namespace.

### Alternative 2: Persistence as middleware (`SessionPersistenceMiddleware`)
- What: snapshot on the `after_run` hook.
- Why rejected: `BaseAgent` forbids middleware on MCTS/actor runtimes, so it silently can't persist non-linear runs. The facade wraps `arun` and works everywhere. (Middleware-based *intra-run* PER_STEP checkpointing remains a clean future addition.)

### Alternative 3: Two separate subsystems for snapshot vs event-log
- What: distinct snapshot store and event-log store.
- Why rejected: they are one primitive — a checkpoint DAG at different write granularities. One Protocol + a `CheckpointPolicy` flag avoids duplicate code and a divergent test matrix.

### Alternative 4: Persist the compacted/context-window view as source of truth
- What: store what the model saw.
- Why rejected: compaction and trajectory checkpoints mutate the *context window*, not `history`. Raw `history` is the lossless source of truth; the window is rebuilt per run. Trace artifacts are stored as *derived observation*, never as a resume input.

### Alternative 5: Make DB stores hard dependencies
- What: import drivers at module load.
- Why rejected: violates import-safety and the repo's "no remote transport as core" posture. Lazy optional imports keep the core clean while satisfying the multi-store requirement.

---

## Summary

**File impact:** ~21 created, ~6 modified, 0 deleted (per Section 9).

**Maps to your five requirements:**
1. One-line attach → `Session(agent)` / `sdk.harnesses.sessions.attach(agent)` (6.9, 6.11).
2. continue/resume/fork + DAG (+ rewind/edit/time-travel) (6.9, 6.1).
3. Multiple stores: memory + file (6.6) and DB providers at `vidbyte/lib/providers/` (6.7).
4. Trace option that reads the agent's trace settings and saves the trace (6.8, 6.1 `trace_*` fields).
5. Also pulled forward from the conversation: rehydration contract, secret scrubbing, schema versioning, `SessionTool` + child/subagent lineage foundation, observability cross-linking — with deterministic replay and HITL interrupt explicitly deferred (Section 2).

**Key risks / open questions:** package name (plural proposed); sync vs async store; fail-open vs fail-closed persistence; SessionTool scope inclusion; shipping all three DB providers now. See Section 13.

**Request for approval:** Please review, resolve the Section 13 questions (or accept the proposed defaults), and explicitly approve before I proceed to Phase 3 (worktree) and implementation. I will not write code until you approve.
